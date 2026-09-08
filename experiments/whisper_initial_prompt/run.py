#!/usr/bin/env python3
"""Compare Whisper base.en with no prompt, a global prompt, and a scenario prompt."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "scenarios.json"
DEFAULT_MANIFEST = ROOT / "manifest.tsv"
MODES = ("none", "global", "scenario")


@dataclass
class ManifestRow:
    wav: Path
    scenario_id: str
    reference: str


@dataclass
class ScenarioResolution:
    """Safe, explainable routing result produced after speech recognition."""

    scenario_id: str | None
    scenario_name: str | None
    canonical_action: str | None
    confidence: float
    status: str
    slots: dict[str, Any]
    evidence: list[str]
    alternatives: list[tuple[str, float]]


_STOP_WORDS = {
    "a", "all", "an", "and", "any", "are", "be", "can", "current", "do",
    "does", "for", "from", "give", "how", "i", "in", "is", "it", "me",
    "my", "of", "on", "please", "right", "show", "tell", "the", "this",
    "to", "what", "which", "who", "you",
}

_SCENARIO_PHRASES: dict[str, tuple[str, ...]] = {
    "network_status": ("network status", "network condition", "network doing",
                       "network working", "check my network", "wrong with my network",
                       "connection quality", "speed test", "network today", "wifi stable",
                       "wi-fi stable"),
    "router_status": ("router status", "router doing", "router working",
                      "check the router", "problem with the router", "router information",
                      "router info", "gateway information", "gateway info", "router uptime"),
    "wifi_device_info": ("device info", "device information", "wifi details",
                         "device details", "what device", "about john", "about alice",
                         "connection details", "connection detail", "details for",
                         "info for", "ip and status"),
    "online_devices": ("online devices", "connected devices", "who is online",
                       "currently online", "connected to my wifi", "active device",
                       "devices online", "device online", "number of device online"),
    "gaming_sessions": ("gaming sessions", "playing games", "playing a game",
                        "who is gaming", "currently gaming", "game sessions"),
    "guest_wifi": ("guest wifi", "guest network"),
    "open_qos": ("open qos", "show qos", "qos page", "each device is doing",
                 "activity type", "gaming or streaming", "using the network",
                 "optimize gaming", "boost youtube", "prioritize netflix"),
    "bandwidth_limit": ("bandwidth limit", "speed limit", "limit the speed",
                        "limit to", "set the limit", "limit of", "cap the"),
}

_INFORMATION_SIGNALS: dict[str, set[str]] = {
    "network_status": {"network"},
    "router_status": {"router"},
    "wifi_device_info": {"info", "information", "details", "device", "connection"},
    "online_devices": {"online", "connected"},
    "gaming_sessions": {"gaming", "game", "games"},
    "open_qos": {"qos", "activity", "streaming"},
}


def _content_words(text: str) -> set[str]:
    return {word for word in normalize_words(text) if word not in _STOP_WORDS}


def _contains_any(text: str, phrases: tuple[str, ...] | list[str]) -> list[str]:
    return [phrase for phrase in phrases
            if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text)]


def _extract_slots(text: str, config: dict[str, Any]) -> dict[str, Any]:
    normalized = " ".join(normalize_words(text))
    slots: dict[str, Any] = {}
    for key in ("people", "devices", "applications"):
        found = []
        for value in config.get("slots", {}).get(key, []):
            candidate = " ".join(normalize_words(str(value)))
            # "my son's" normalizes to "my son's"; allow the configured "my son" too.
            if candidate in normalized or candidate.replace("my ", "") in normalized:
                found.append(value)
        if found:
            slots[key] = found

    number_words = {"ten": 10, "twenty": 20, "fifty": 50, "one hundred": 100}
    for spoken, value in number_words.items():
        if spoken in text.lower() or str(value) in normalize_words(text):
            slots["bandwidth_value"] = value
            break

    on_hits = _contains_any(normalized, ("turn on", "enable", "activate", "open"))
    off_hits = _contains_any(
        normalized, ("turn off", "disable", "deactivate", "switch off"))
    configured_apps = {
        " ".join(normalize_words(str(app)))
        for app in config.get("slots", {}).get("applications", [])
    }
    app_in_text = any(app in normalized for app in configured_apps)
    closed_domain_guest = (on_hits or off_hits) and "internet" not in normalized and not app_in_text
    if "guest" in normalized or ("wifi" in normalized and (on_hits or off_hits)) \
            or closed_domain_guest:
        if on_hits and off_hits:
            slots["guest_wifi_state"] = "ambiguous"
        elif on_hits:
            slots["guest_wifi_state"] = "on"
        elif off_hits:
            slots["guest_wifi_state"] = "off"
    return slots


def resolve_scenario(text: str, config: dict[str, Any]) -> ScenarioResolution:
    """Map even a short transcript to a scenario, but reject unsafe guesses.

    Initial Prompt improves spelling. This resolver owns intent routing and slot
    extraction. Its confidence is a routing score, not an ASR probability.
    """
    normalized = " ".join(normalize_words(text))
    query_words = _content_words(text)
    scenarios = scenario_map(config)
    scores = {scenario_id: 0.0 for scenario_id in scenarios}
    evidence: dict[str, list[str]] = {scenario_id: [] for scenario_id in scenarios}

    for scenario_id, phrases in _SCENARIO_PHRASES.items():
        for phrase in _contains_any(normalized, list(phrases)):
            scores[scenario_id] += 7.0 if len(phrase.split()) > 1 else 5.0
            evidence[scenario_id].append(phrase)

    # Example matching broadens natural phrasing and specifically rewards a
    # short utterance that is a meaningful fragment of a configured example.
    if query_words:
        for scenario_id, scenario in scenarios.items():
            best_coverage = 0.0
            for example in scenario.get("examples", []):
                example_words = _content_words(str(example))
                if example_words:
                    best_coverage = max(
                        best_coverage, len(query_words & example_words) / len(query_words))
            scores[scenario_id] += best_coverage * 3.0

    tokens = set(normalize_words(text))
    apps = {
        word.lower() for app in config.get("slots", {}).get("applications", [])
        for word in normalize_words(str(app))
    }
    has_app = bool(tokens & apps)
    explicit_block = bool(_contains_any(
        normalized, ("do not allow", "do not let", "disable", "stop", "prevent",
                     "cut off", "turn off internet")))
    explicit_unblock = "remove" in tokens and "block" in tokens
    unblock_phrases = ("unblock", "restore", "allow", "reconnect", "back on",
                       "use the internet again", "use youtube again")
    is_unblock = explicit_unblock or (
        bool(_contains_any(normalized, unblock_phrases)) and not explicit_block)
    is_block = explicit_block or (
        bool(_contains_any(normalized, ("block",))) and not is_unblock)

    if "guest" in tokens:
        scores["guest_wifi"] += 5.0
        evidence["guest_wifi"].append("guest")
    elif is_unblock:
        target = "unblock_application" if has_app else "unblock_internet"
        scores[target] += 12.0
        evidence[target].append("unblock action" + (" + application" if has_app else ""))
    elif is_block:
        target = "block_application" if has_app else "block_internet"
        scores[target] += 12.0
        evidence[target].append("block action" + (" + application" if has_app else ""))

    # Closed-domain structure observed in real Vietnamese-accent mic recordings:
    # Whisper may render "guest Wi-Fi" as rest weapon/button or S2 file. In this
    # command set, a plain power action (without internet/app) can only mean the
    # Guest Wi-Fi scenario, so intent routing need not depend on exact spelling.
    guest_action = bool(tokens & {"on", "off", "enable", "disable", "activate", "deactivate"})
    guest_structure = guest_action and "internet" not in tokens and not has_app
    if guest_structure:
        scores["guest_wifi"] += 9.0
        evidence["guest_wifi"].append("closed-domain power command")

    if "limit" in tokens and (tokens & {"bandwidth", "speed", "10", "20", "50", "100",
                                        "ten", "twenty", "fifty", "hundred"}):
        scores["bandwidth_limit"] += 6.0
        evidence["bandwidth_limit"].append("limit + value/domain")
    if "about" in tokens and tokens & {"phone", "tablet", "laptop", "tv", "device"}:
        scores["wifi_device_info"] += 5.0
        evidence["wifi_device_info"].append("about + device")
    if "connected" in tokens and (tokens & {"device", "devices"}):
        scores["online_devices"] += 5.0
        evidence["online_devices"].append("connected devices")
    if "doing" in tokens and "device" in tokens:
        scores["open_qos"] += 8.0
        evidence["open_qos"].append("device activity")

    # Small noun signals help fragments such as "router status" or "who's online".
    for scenario_id, signals in _INFORMATION_SIGNALS.items():
        hits = tokens & signals
        if hits:
            scores[scenario_id] += 2.0 * len(hits)
            evidence[scenario_id].extend(sorted(hits))

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_id, best_score = ranked[0]
    second_score = ranked[1][1]

    # An action/domain signal is mandatory. A bare person/device is not enough
    # to trigger a potentially destructive router operation.
    action_or_domain = is_block or is_unblock or "guest" in tokens or any(
        tokens & signals for signals in _INFORMATION_SIGNALS.values())
    action_or_domain = action_or_domain or bool(
        tokens & {"bandwidth", "limit", "speed"})
    action_or_domain = action_or_domain or (
        "about" in tokens and bool(tokens & {"phone", "tablet", "laptop", "tv", "device"}))
    action_or_domain = action_or_domain or any(evidence.values())
    margin = best_score - second_score
    if not normalized or not action_or_domain or best_score < 4.5:
        status = "no_match"
        chosen_id = None
    elif margin < 1.25:
        status = "ambiguous"
        chosen_id = None
    else:
        status = "matched"
        chosen_id = best_id

    confidence = 0.0 if chosen_id is None else min(
        0.99, 0.50 + best_score / 30.0 + margin / 40.0)
    slots = _extract_slots(text, config)
    scenario = scenarios.get(chosen_id) if chosen_id else None
    canonical = None
    if scenario:
        canonical = str(scenario.get("canonical_action", chosen_id))
    alternatives = [(scenario_id, round(score, 2)) for scenario_id, score in ranked[:3]]
    return ScenarioResolution(
        scenario_id=chosen_id,
        scenario_name=str(scenario["name"]) if scenario else None,
        canonical_action=canonical,
        confidence=confidence,
        status=status,
        slots=slots,
        evidence=evidence[best_id][:4],
        alternatives=alternatives,
    )


def normalize_words(text: str) -> list[str]:
    # Whisper prefers the spelling "Wi-Fi" while router references commonly
    # use "wifi". A formatting hyphen must not count as an ASR word error.
    # Support both regular ASCII hyphen (-) and unicode non-breaking hyphens (\u2010-\u2014)
    text = re.sub(r"(?<=\w)[-\u2010-\u2014](?=\w)", "", text.lower())
    words = re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text)
    # Bandwidth is a numeric slot without a spoken unit. Whisper may format the
    # same value as "50" or "fifty"; that is not an ASR error for this system.
    normalized: list[str] = []
    index = 0
    single_numbers = {"ten": "10", "twenty": "20", "fifty": "50"}
    while index < len(words):
        if words[index:index + 2] == ["one", "hundred"]:
            normalized.append("100")
            index += 2
        else:
            normalized.append(single_numbers.get(words[index], words[index]))
            index += 1
    return normalized


def edit_counts(reference: str, hypothesis: str) -> tuple[int, int]:
    ref = normalize_words(reference)
    hyp = normalize_words(hypothesis)
    previous = list(range(len(hyp) + 1))
    for i, left in enumerate(ref, 1):
        current = [i]
        for j, right in enumerate(hyp, 1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (left != right),
            ))
        previous = current
    return previous[-1], len(ref)


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    scenarios = data.get("scenarios", [])
    ids = [item.get("id") for item in scenarios]
    if not scenarios or len(ids) != len(set(ids)) or any(not item for item in ids):
        raise ValueError("scenarios.json needs non-empty, unique scenario ids")
    for item in scenarios:
        examples = item.get("examples") or []
        if examples:
            item["prompt"] = " ".join(
                sentence.strip() for sentence in examples if sentence.strip())
        if not item.get("prompt"):
            raise ValueError(f"scenario '{item['id']}' needs a prompt or examples")
    return data


def scenario_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in config["scenarios"]}


def read_manifest(path: Path, known_scenarios: set[str]) -> list[ManifestRow]:
    rows: list[ManifestRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_number, fields in enumerate(csv.reader(handle, delimiter="\t"), 1):
            if not fields or fields[0].lstrip().startswith("#"):
                continue
            if len(fields) != 3:
                raise ValueError(f"{path}:{line_number}: expected 3 tab-separated fields")
            wav_name, scenario_id, reference = (field.strip() for field in fields)
            if scenario_id not in known_scenarios:
                raise ValueError(f"{path}:{line_number}: unknown scenario '{scenario_id}'")
            rows.append(ManifestRow((path.parent / wav_name).resolve(), scenario_id, reference))
    return rows


def read_pcm16_mono_16k(path: Path) -> tuple[np.ndarray, float]:
    """Read corpus WAVs without FFmpeg; reject formats that hide resampling differences."""
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.getnframes()
        compression = wav.getcomptype()
        raw = wav.readframes(frames)
    if compression != "NONE" or sample_width != 2 or sample_rate != 16000:
        raise ValueError(
            f"{path}: need uncompressed 16-bit 16 kHz WAV; got "
            f"compression={compression}, width={sample_width * 8}, rate={sample_rate}"
        )
    if channels not in (1, 2):
        raise ValueError(f"{path}: only mono or stereo WAV is supported")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if channels == 2:
        samples = samples.reshape(-1, 2).mean(axis=1)
    samples /= 32768.0
    return samples, len(samples) / 16000.0


def prepare_float32_16k(samples: np.ndarray, source_rate: float) -> np.ndarray:
    """Sanitize/resample native microphone samples for direct Whisper input."""
    if source_rate <= 0:
        raise ValueError("microphone sample rate must be positive")
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    audio = np.nan_to_num(audio, nan=0.0, posinf=1.0, neginf=-1.0)
    if int(round(source_rate)) != 16000 and len(audio):
        output_size = max(1, int(round(len(audio) * 16000.0 / source_rate)))
        source_x = np.linspace(0.0, 1.0, len(audio), endpoint=False)
        target_x = np.linspace(0.0, 1.0, output_size, endpoint=False)
        audio = np.interp(target_x, source_x, audio).astype(np.float32)
    return np.clip(audio, -1.0, 1.0).astype(np.float32)


def prepare_pcm16_16k(samples: np.ndarray, source_rate: float) -> np.ndarray:
    """Convert microphone floats to corpus-compatible PCM16 at 16 kHz."""
    audio = prepare_float32_16k(samples, source_rate)
    return (audio * 32767.0).astype("<i2")


def prompt_for(mode: str, config: dict[str, Any], scenario: dict[str, Any]) -> str | None:
    if mode == "none":
        return None
    if mode == "global":
        return str(config["global_prompt"])
    if mode == "scenario":
        return str(scenario["prompt"])
    raise ValueError(f"unknown mode: {mode}")


def strengthen_prompt(prompt: str | None, strength: int) -> str | None:
    """Increase Whisper conditioning without pretending it is a score/weight."""
    if strength not in (1, 2, 3):
        raise ValueError("prompt strength must be 1, 2, or 3")
    clean = (prompt or "").strip()
    return " ".join([clean] * strength) if clean else None


def adaptive_scenario_strength(requested: int, scenario_id: str, routing_text: str) -> int:
    """Escalate only a measured hard case instead of over-biasing every command."""
    if requested not in (1, 2, 3):
        raise ValueError("prompt strength must be 1, 2, or 3")
    tokens = set(normalize_words(routing_text))
    if scenario_id == "guest_wifi" and "wifi" in tokens and "guest" not in tokens:
        return 3
    return requested


def transcribe(model: Any, audio: np.ndarray, prompt: str | None) -> tuple[str, float]:
    options: dict[str, Any] = {
        "language": "en",
        "task": "transcribe",
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "carry_initial_prompt": True,
        "beam_size": 5,
        "patience": 1.0,
        "fp16": False,
        # None suppresses both segment text and tqdm; False still prints a bar.
        "verbose": None,
    }
    if prompt:
        options["initial_prompt"] = prompt
    started = time.perf_counter()
    result = model.transcribe(audio, **options)
    elapsed = time.perf_counter() - started
    return str(result.get("text", "")).strip(), elapsed


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--manifest", type=Path, default=None)
    source.add_argument("--wav", type=Path)
    parser.add_argument("--scenario", help="scenario id, required with --wav")
    parser.add_argument("--reference", default="", help="ground truth for --wav")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--model", default="base.en")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--output", type=Path, help="write detailed JSON results")
    parser.add_argument("--check-model", action="store_true", help="download/load model and exit")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    config = load_config(args.config.resolve())
    scenarios = scenario_map(config)

    try:
        import whisper
    except ImportError:
        print("error: openai-whisper is not installed; run setup.ps1", file=sys.stderr)
        return 2

    print(f"loading Whisper {args.model} on CPU...")
    model = whisper.load_model(args.model, device="cpu", download_root=str(ROOT / ".models"))
    if args.check_model:
        print(f"model ready: {args.model}")
        return 0

    if args.wav:
        if not args.scenario:
            print("error: --scenario is required with --wav", file=sys.stderr)
            return 2
        if args.scenario not in scenarios:
            print(f"error: unknown scenario '{args.scenario}'", file=sys.stderr)
            return 2
        rows = [ManifestRow(args.wav.resolve(), args.scenario, args.reference)]
    else:
        manifest = (args.manifest or DEFAULT_MANIFEST).resolve()
        rows = read_manifest(manifest, set(scenarios))

    missing = [row for row in rows if not row.wav.is_file()]
    for row in missing:
        print(f"missing: {row.wav}")
    rows = [row for row in rows if row.wav.is_file()]
    if not rows:
        print("no audio evaluated; record the manifest WAV files first", file=sys.stderr)
        return 3

    results: list[dict[str, Any]] = []
    totals = {mode: {"errors": 0, "words": 0, "seconds": 0.0, "audio": 0.0}
              for mode in args.modes}
    for index, row in enumerate(rows, 1):
        audio, duration = read_pcm16_mono_16k(row.wav)
        scenario = scenarios[row.scenario_id]
        print(f"\n[{index}/{len(rows)}] {row.wav.name}  scenario={row.scenario_id}")
        item: dict[str, Any] = {
            "wav": str(row.wav), "scenario": row.scenario_id,
            "reference": row.reference, "duration_s": duration, "decodes": {},
        }
        for mode in args.modes:
            prompt = prompt_for(mode, config, scenario)
            text, elapsed = transcribe(model, audio, prompt)
            errors, words = edit_counts(row.reference, text) if row.reference else (0, 0)
            wer = errors / words if words else math.nan
            item["decodes"][mode] = {
                "text": text, "prompt": prompt, "seconds": elapsed,
                "rtf": elapsed / duration if duration else math.nan,
                "errors": errors, "reference_words": words, "wer": wer,
            }
            totals[mode]["errors"] += errors
            totals[mode]["words"] += words
            totals[mode]["seconds"] += elapsed
            totals[mode]["audio"] += duration
            wer_text = f" WER={wer * 100:.1f}%" if words else ""
            print(f"  {mode:8} {elapsed:6.2f}s RTF={elapsed / duration:.2f}{wer_text}  {text}")
        results.append(item)

    print("\nsummary")
    for mode in args.modes:
        total = totals[mode]
        wer = total["errors"] / total["words"] if total["words"] else math.nan
        rtf = total["seconds"] / total["audio"]
        print(f"  {mode:8} WER={wer * 100:6.2f}%  RTF={rtf:.3f}")

    if "none" in args.modes:
        for mode in (candidate for candidate in args.modes if candidate != "none"):
            improved = worsened = unchanged = 0
            for item in results:
                base = item["decodes"]["none"]["errors"]
                prompted = item["decodes"][mode]["errors"]
                improved += prompted < base
                worsened += prompted > base
                unchanged += prompted == base
            print(f"  {mode:8} vs none: improved={improved}, worsened={worsened}, "
                  f"unchanged={unchanged}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
