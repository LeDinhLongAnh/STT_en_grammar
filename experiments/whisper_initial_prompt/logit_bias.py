#!/usr/bin/env python3
"""
Whisper Logit Bias engine cho router domain STT.

Cơ chế: Implement whisper.decoding.LogitFilter subclass, inject vào
DecodingTask.logit_filters tại runtime. Bias được áp dụng IN-PLACE trên
raw logits tại mỗi bước decode — trước khi token được chọn. Đây là
logit bias thực sự, không phải post-processing string replacement.

Pipeline:
    audio → whisper encoder → decoder → raw logits
        → RouterDomainBias.apply(logits, tokens)   ← đây
            → token selection → transcript

Sử dụng:
    bias_cfg = load_logit_bias_config()
    tokenizer = whisper.tokenizer.get_tokenizer(...)
    bias_filter = build_bias_filter(bias_cfg, tokenizer, scenario_id="guest_wifi")
    text, elapsed = transcribe_with_bias(model, audio, prompt, bias_filter)
"""

from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_DEFAULT_CONFIG = Path(__file__).resolve().parent / "logit_bias.json"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_logit_bias_config(path: Path = _DEFAULT_CONFIG) -> dict[str, Any]:
    """Load logit_bias.json. Returns empty-enabled dict if file missing."""
    if not path.is_file():
        return {"enabled": False, "global": {}, "scenario": {}, "phrase_aware": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def is_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("enabled", True))


# ---------------------------------------------------------------------------
# Tokenization helpers
# ---------------------------------------------------------------------------

def tokenize_term(tokenizer: Any, term: str) -> list[int]:
    """Return token IDs for a domain term using the model's actual tokenizer.

    Whisper tokenizer prepends a leading space to start-of-word tokens.
    We try both " term" and "term" and return whichever is shorter/sensible.
    Token IDs in logit_bias.json were computed with this same logic and are
    provided as a fast-path cache — but this function validates/overrides them
    at runtime so they always match the loaded model.
    """
    ids_with_space = tokenizer.encode(" " + term)
    ids_no_space = tokenizer.encode(term)
    # Prefer leading-space encoding (typical mid-sentence word)
    return ids_with_space if ids_with_space else ids_no_space


def build_bias_map(
    config: dict[str, Any],
    tokenizer: Any,
    scenario_id: Optional[str] = None,
    bias_mode: str = "first_token_only",
) -> Tuple[dict[int, float], dict[int, dict[int, float]], dict[str, Any]]:
    """Build (bias_map, phrase_map, debug_info) from config + tokenizer.

    bias_map:   {token_id: bias_value}  — global + scenario terms
    phrase_map: {prev_token_id: {next_token_id: extra_bias}}  — phrase-aware
    debug_info: human-readable dict for UI display
    """
    bias_map: dict[int, float] = {}
    debug_terms: dict[str, dict[str, Any]] = {}

    def _add_term(term: str, bias_value: float, stored_tokens: list[int]) -> None:
        # Re-tokenize at runtime with the actual model tokenizer for safety.
        runtime_tokens = tokenize_term(tokenizer, term)
        if runtime_tokens != stored_tokens and stored_tokens:
            # Use runtime tokens (stored tokens may be from a different model).
            actual_tokens = runtime_tokens
        else:
            actual_tokens = stored_tokens or runtime_tokens

        if bias_mode == "first_token_only":
            tokens_to_bias = actual_tokens[:1]
        else:  # all_tokens
            tokens_to_bias = actual_tokens

        for tok in tokens_to_bias:
            bias_map[tok] = max(bias_map.get(tok, 0.0), bias_value)

        debug_terms[term] = {
            "bias": bias_value,
            "tokens_all": actual_tokens,
            "tokens_biased": tokens_to_bias,
        }

    # Global terms
    for term, entry in config.get("global", {}).items():
        if term.startswith("_"):
            continue
        _add_term(term, float(entry["bias"]), entry.get("tokens", []))

    # Scenario-specific terms (additional, may override global)
    if scenario_id:
        scenario_block = config.get("scenario", {}).get(scenario_id, {})
        for term, entry in scenario_block.items():
            if term.startswith("_"):
                continue
            _add_term(term, float(entry["bias"]), entry.get("tokens", []))

    # Phrase-aware map: {int(prev): {int(next): float(extra)}}
    phrase_map: dict[int, dict[int, float]] = {}
    for prev_str, nexts in config.get("phrase_aware", {}).items():
        if prev_str.startswith("_"):
            continue
        try:
            prev_tok = int(prev_str)
        except ValueError:
            continue
        phrase_map[prev_tok] = {}
        for next_str, extra in nexts.items():
            try:
                phrase_map[prev_tok][int(next_str)] = float(extra)
            except ValueError:
                continue

    debug_info = {
        "global_count": len(config.get("global", {})),
        "scenario_id": scenario_id,
        "scenario_count": len(config.get("scenario", {}).get(scenario_id or "", {})),
        "bias_mode": bias_mode,
        "terms": debug_terms,
        "total_token_slots": len(bias_map),
    }
    return bias_map, phrase_map, debug_info


# ---------------------------------------------------------------------------
# LogitFilter subclass — the actual bias applied during decoding
# ---------------------------------------------------------------------------

class RouterDomainBias:
    """Whisper LogitFilter-compatible bias for router domain vocabulary.

    Subclasses whisper.decoding.LogitFilter by duck-typing (implements apply()).
    Can be injected into DecodingTask.logit_filters without importing whisper
    at module import time.

    apply() is called by DecodingTask._main_loop() with:
        logits: torch.Tensor shape (n_batch, vocab_size) — modified IN-PLACE
        tokens: torch.Tensor shape (n_batch, seq_len)   — read-only context

    MAX_TOTAL_BIAS: Trần tổng bias (global + phrase_aware) cho mỗi token.
    Ngăn cộng dồn không kiểm soát khi cả global và phrase_aware cùng boost
    một token. Mức 4.0 chọn vì bias cao nhất kiểm chứng thủ công là 'which'=3.0;
    một số combo hợp lệ (guest+Wi-Fi = 2.5+1.5) đúng bằng trần này.
    """

    MAX_TOTAL_BIAS: float = 4.0

    def __init__(
        self,
        bias_map: dict[int, float],
        phrase_map: dict[int, dict[int, float]],
        debug_info: dict[str, Any],
    ) -> None:
        self.bias_map = bias_map
        self.phrase_map = phrase_map
        self.debug_info = debug_info
        # Pre-compute lists for fast batch apply
        self._token_ids: list[int] = list(bias_map.keys())
        self._biases: list[float] = [bias_map[t] for t in self._token_ids]

    def apply(self, logits: Any, tokens: Any) -> None:  # noqa: ANN001
        """Apply logit bias in-place. Called once per decode step."""
        # --- Global flat bias ---
        for tok, bias in zip(self._token_ids, self._biases):
            logits[:, tok] += bias

        # --- Phrase-aware bias (clamped to MAX_TOTAL_BIAS per token) ---
        # Check last token of each beam (tokens[:, -1]) and boost followers.
        # global bias đã được áp ở trên; tính headroom để không vượt trần.
        if self.phrase_map and tokens.shape[1] > 0:
            last_tokens = tokens[:, -1].tolist()
            for last_tok in set(last_tokens):
                followers = self.phrase_map.get(int(last_tok))
                if followers:
                    for next_tok, extra in followers.items():
                        global_applied = self.bias_map.get(next_tok, 0.0)
                        headroom = max(0.0, self.MAX_TOTAL_BIAS - global_applied)
                        logits[:, next_tok] += min(extra, headroom)


# ---------------------------------------------------------------------------
# Build filter
# ---------------------------------------------------------------------------

def build_bias_filter(
    config: dict[str, Any],
    tokenizer: Any,
    scenario_id: Optional[str] = None,
) -> Optional[RouterDomainBias]:
    """Return a RouterDomainBias or None if disabled."""
    if not is_enabled(config):
        return None
    bias_mode = config.get("bias_mode", "first_token_only")
    bias_map, phrase_map, debug_info = build_bias_map(
        config, tokenizer, scenario_id, bias_mode)
    if not bias_map:
        return None
    return RouterDomainBias(bias_map, phrase_map, debug_info)


# ---------------------------------------------------------------------------
# Context manager: inject LogitFilter into DecodingTask
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _inject_logit_filter(filter_obj: RouterDomainBias):
    """Temporarily patch whisper.decoding.DecodingTask.__init__ to inject filter.

    This context manager wraps the original __init__ so that any DecodingTask
    created within the context automatically gets the custom filter appended to
    its logit_filters list — without modifying the Whisper library source.
    """
    import whisper.decoding as _wd

    original_init = _wd.DecodingTask.__init__

    def patched_init(self_task, model, options):  # noqa: ANN001
        original_init(self_task, model, options)
        self_task.logit_filters.append(filter_obj)

    _wd.DecodingTask.__init__ = patched_init
    try:
        yield
    finally:
        _wd.DecodingTask.__init__ = original_init


# ---------------------------------------------------------------------------
# transcribe_with_bias: drop-in for run.transcribe()
# ---------------------------------------------------------------------------

def transcribe_with_bias(
    model: Any,
    audio: Any,
    prompt: Optional[str],
    bias_filter: Optional[RouterDomainBias],
) -> tuple[str, float]:
    """Transcribe audio with optional logit bias injected during decode.

    Identical interface to run.transcribe(). If bias_filter is None,
    behaves exactly like run.transcribe().
    """
    import whisper

    options: dict[str, Any] = {
        "language": "en",
        "task": "transcribe",
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "carry_initial_prompt": True,
        "beam_size": 5,
        "patience": 1.0,
        "fp16": False,
        "verbose": None,
    }
    if prompt:
        options["initial_prompt"] = prompt

    started = time.perf_counter()

    if bias_filter is None:
        result = model.transcribe(audio, **options)
    else:
        with _inject_logit_filter(bias_filter):
            result = model.transcribe(audio, **options)

    elapsed = time.perf_counter() - started
    return str(result.get("text", "")).strip(), elapsed


# ---------------------------------------------------------------------------
# Debug / introspection helpers
# ---------------------------------------------------------------------------

def format_debug_panel(
    config: dict[str, Any],
    bias_filter: Optional[RouterDomainBias],
    scenario_id: Optional[str] = None,
) -> str:
    """Return a human-readable string for the debug panel / console."""
    if not is_enabled(config):
        return "Logit Bias: OFF (disabled in logit_bias.json)"
    if bias_filter is None:
        return "Logit Bias: OFF (filter not built)"

    info = bias_filter.debug_info
    lines = [
        f"Logit Bias: ON",
        f"Global terms: {info['global_count']}",
        f"Scenario: {info['scenario_id'] or '(none)'}",
        f"Scenario terms: {info['scenario_count']}",
        f"Bias mode: {info['bias_mode']}",
        f"Total token slots in bias_map: {info['total_token_slots']}",
        "",
        "Tokenization (biased tokens shown):",
    ]
    for term, detail in sorted(info["terms"].items())[:20]:  # cap at 20 for readability
        tokens_str = str(detail["tokens_biased"])
        lines.append(f"  {term:14} bias={detail['bias']:.1f}  tokens={tokens_str}")
    return "\n".join(lines)


def validate_config(
    config: dict[str, Any],
    tokenizer: Any,
) -> list[str]:
    """Return list of warnings if stored token IDs differ from runtime tokenizer."""
    warnings: list[str] = []
    for term, entry in config.get("global", {}).items():
        if term.startswith("_"):
            continue
        stored = entry.get("tokens", [])
        runtime = tokenize_term(tokenizer, term)
        if stored and runtime != stored:
            warnings.append(
                f"Token mismatch for '{term}': stored={stored}, runtime={runtime}"
            )
    return warnings


# ---------------------------------------------------------------------------
# CLI: python logit_bias.py --check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Logit bias tool")
    parser.add_argument("--check", action="store_true",
                        help="Validate config + show token IDs")
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG)
    parser.add_argument("--scenario", default=None)
    args = parser.parse_args()

    try:
        import whisper
    except ImportError:
        print("error: openai-whisper not installed", file=sys.stderr)
        sys.exit(2)

    cfg = load_logit_bias_config(args.config)
    tok = whisper.tokenizer.get_tokenizer(
        multilingual=False, language="en", task="transcribe")

    warnings = validate_config(cfg, tok)
    if warnings:
        print("=== TOKEN ID WARNINGS ===")
        for w in warnings:
            print(" ", w)
        print()

    flt = build_bias_filter(cfg, tok, args.scenario)
    print(format_debug_panel(cfg, flt, args.scenario))

    if args.check:
        # Full token dump
        print("\n=== FULL TOKEN DUMP (runtime tokenizer) ===")
        for term in sorted(cfg.get("global", {})):
            if term.startswith("_"):
                continue
            ids = tokenize_term(tok, term)
            print(f"  {term:16} -> {ids}")
