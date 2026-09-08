#!/usr/bin/env python3
"""Helper module cho Sherpa VI dashboard: load config, routing, metrics.

Vai trò tương đương whisper_initial_prompt/run.py nhưng dành cho
Sherpa-ONNX Zipformer VI với contextual biasing (hotwords).
"""

from __future__ import annotations

import io
import json
import re
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "scenarios_vi.json"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ScenarioResolution:
    """Kết quả routing sau khi nhận dạng giọng nói."""
    scenario_id: str | None
    scenario_name: str | None
    canonical_action: str | None
    confidence: float
    status: str          # "matched" | "ambiguous" | "no_match"
    slots: dict[str, Any]
    evidence: list[str]
    alternatives: list[tuple[str, float]]


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_map(config: dict[str, Any]) -> dict[str, Any]:
    return {s["id"]: s for s in config.get("scenarios", [])}


def save_config(config: dict[str, Any], path: Path = DEFAULT_CONFIG) -> None:
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Vietnamese keyword routing
# ---------------------------------------------------------------------------

_VI_PHRASES: dict[str, tuple[str, ...]] = {
    "network_status": (
        "trạng thái mạng", "chất lượng kết nối", "mạng hôm nay",
        "ổn định không", "kiểm tra mạng", "tình trạng mạng",
        "kết nối có ổn", "mạng có vấn đề",
    ),
    "router_status": (
        "trạng thái router", "thông tin router", "bộ định tuyến",
        "router đang", "kiểm tra router", "tình trạng router",
    ),
    "wifi_device_info": (
        "địa chỉ ip", "chi tiết kết nối", "thông tin thiết bị",
        "thiết bị đang dùng", "ip của",
    ),
    "online_devices": (
        "thiết bị đang kết nối", "ai đang online", "liệt kê thiết bị",
        "có những thiết bị", "đang dùng wifi", "đang kết nối vào",
        "thiết bị nào đang",
    ),
    "active_sessions": (
        "đang chơi game", "xem video", "phiên hoạt động",
        "đang stream", "ai đang chơi", "đang dùng mạng nhiều",
    ),
    "guest_wifi": (
        "wifi khách", "mạng khách", "wifi phụ", "mạng dành cho khách",
        "oai phai khách", "wai phai khách", "khoai phai khách",
        "oai phai phụ", "wai phai phụ", "khoai phai phụ"
    ),
    "bandwidth_limit": (
        "giới hạn băng thông", "bóp băng thông", "đặt tốc độ",
        "giới hạn tốc độ", "cắt giảm tốc độ",
        "tốc độ tối đa", "mbps", "megabit",
    ),
    "block_internet": (
        "chặn internet", "cắt mạng", "ngắt kết nối",
        "khoá mạng", "cấm truy cập internet", "không cho vào internet",
        "tắt internet",
    ),
    "unblock_internet": (
        "bỏ chặn internet", "gỡ chặn mạng", "cho phép truy cập lại",
        "mở mạng trở lại", "kết nối lại internet", "khôi phục mạng",
        "cho dùng internet lại",
    ),
    "block_application": (
        "chặn youtube", "cấm tiktok", "chặn netflix",
        "khoá facebook", "cấm game", "không cho dùng",
        "chặn liên quân", "cấm free fire",
    ),
    "unblock_application": (
        "bỏ chặn youtube", "gỡ chặn tiktok", "cho phép netflix lại",
        "mở lại youtube", "bỏ khoá facebook", "cho dùng lại",
        "gỡ lệnh chặn",
    ),
    "optimize_app": (
        "ưu tiên", "tối ưu", "tăng tốc",
        "ưu tiên băng thông", "tối ưu cho",
    ),
}

_VI_APPS = {"youtube", "tiktok", "netflix", "facebook", "game",
            "liên quân", "free fire", "fifa"}

_VI_DEVICES = {"điện thoại", "máy tính bảng", "laptop",
               "tivi", "tivi thông minh", "máy tính"}

_VI_BLOCK_WORDS = {"chặn", "cấm", "khoá", "khoá", "cắt mạng", "ngắt"}
_VI_UNBLOCK_WORDS = {"bỏ chặn", "gỡ chặn", "cho phép lại", "mở lại",
                     "khôi phục", "kết nối lại"}


def _norm(text: str) -> str:
    return text.lower().strip()


def _contains_any(text: str, phrases: tuple[str, ...] | list[str]) -> list[str]:
    return [p for p in phrases if p in text]


def _extract_slots_vi(text: str, config: dict[str, Any]) -> dict[str, Any]:
    norm = _norm(text)
    slots: dict[str, Any] = {}
    for key in ("people", "devices", "applications", "networks"):
        slot_def = config.get("slots", {}).get(key)
        if isinstance(slot_def, list):
            found = [v for v in slot_def if v.lower() in norm]
            if found:
                slots[key] = found
        elif isinstance(slot_def, dict):
            found = []
            for canonical, aliases in slot_def.items():
                if any(alias.lower() in norm for alias in aliases):
                    found.append(canonical)
            if found:
                slots[key] = found

    for val in ("100", "50", "20", "10"):
        if val in norm:
            slots["bandwidth_value"] = int(val)
            break
    if any(w in norm for w in ("bật", "mở", "kích hoạt")):
        slots.setdefault("action", "on")
    if any(w in norm for w in ("tắt", "vô hiệu", "tắt đi")):
        slots.setdefault("action", "off")
    return slots


def resolve_scenario_vi(text: str, config: dict[str, Any]) -> ScenarioResolution:
    """Rule-based routing bằng regex tiếng Việt."""
    norm = _norm(text)
    scenarios = scenario_map(config)
    scores: dict[str, float] = {sid: 0.0 for sid in scenarios}
    evidence: dict[str, list[str]] = {sid: [] for sid in scenarios}

    for scenario_id, phrases in _VI_PHRASES.items():
        if scenario_id not in scores:
            continue
        for phrase in _contains_any(norm, list(phrases)):
            boost = 7.0 if len(phrase.split()) > 1 else 5.0
            scores[scenario_id] += boost
            evidence[scenario_id].append(phrase)

    # Example coverage scoring
    query_words = set(re.findall(r"[a-zÀ-ỹ0-9]+", norm))
    if query_words:
        for sid, scenario in scenarios.items():
            best = 0.0
            for ex in scenario.get("examples", []):
                ex_words = set(re.findall(r"[a-zÀ-ỹ0-9]+", _norm(str(ex))))
                if ex_words:
                    best = max(best, len(query_words & ex_words) / len(query_words))
            scores[sid] += best * 3.0

    # App / block / unblock signals
    has_app = any(app in norm for app in _VI_APPS)
    is_unblock = any(w in norm for w in _VI_UNBLOCK_WORDS)
    is_block = (not is_unblock) and any(w in norm for w in _VI_BLOCK_WORDS)
    if is_unblock:
        target = "unblock_application" if has_app else "unblock_internet"
        scores[target] += 12.0
        evidence[target].append("unblock action")
    elif is_block:
        target = "block_application" if has_app else "block_internet"
        scores[target] += 12.0
        evidence[target].append("block action")

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_id, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = best_score - second_score

    action_signal = (is_block or is_unblock
                     or any(scores[sid] > 0 for sid in scores))
    if not norm or not action_signal or best_score < 4.5:
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
    slots = _extract_slots_vi(text, config)
    scenario = scenarios.get(chosen_id) if chosen_id else None
    canonical = str(scenario.get("canonical_action", chosen_id)) if scenario else None
    alternatives = [(sid, round(sc, 2)) for sid, sc in ranked[:3]]
    return ScenarioResolution(
        scenario_id=chosen_id,
        scenario_name=str(scenario["name"]) if scenario else None,
        canonical_action=canonical,
        confidence=confidence,
        status=status,
        slots=slots,
        evidence=evidence[best_id][:4] if best_id in evidence else [],
        alternatives=alternatives,
    )


# ---------------------------------------------------------------------------
# Text Normalization & Phonetic Biasing
# ---------------------------------------------------------------------------

def normalize_text(text: str, config: dict[str, Any]) -> str:
    """Post-processing: Replace phonetic aliases with their canonical English/standard words."""
    import re
    if not text:
        return text
    
    # We want case-insensitive replacement but preserve original casing for the rest.
    # E.g. "BẬT OAI PHAI KHÁCH" -> "BẬT WIFI KHÁCH"
    normalized = text
    slots = config.get("slots", {})
    
    for category in ("networks", "applications", "devices"):
        slot_def = slots.get(category)
        if isinstance(slot_def, dict):
            for canonical, aliases in slot_def.items():
                for alias in aliases:
                    # Ignore short or meaningless aliases
                    if len(alias) < 3:
                        continue
                    # Case insensitive replace using regex
                    pattern = re.compile(re.escape(alias), re.IGNORECASE)
                    # Replace with canonical, maintaining UPPERCASE if original text was mostly upper
                    replacement = canonical.upper() if text.isupper() else canonical
                    normalized = pattern.sub(replacement, normalized)
                    
    return normalized


def get_phonetic_hotwords(scenario_id: str, config: dict[str, Any]) -> str:
    """Extract Vietnamese phonetic aliases to use as hotwords for Sherpa."""
    scenarios = scenario_map(config)
    scenario = scenarios.get(scenario_id, {})
    
    # Combine original prompt + phonetic aliases
    base_prompt = scenario.get("prompt", "")
    hotwords = [base_prompt] if base_prompt else []
    
    slots = config.get("slots", {})
    # For simplicity, extract all aliases from applications and networks
    for category in ("applications", "networks"):
        slot_def = slots.get(category, {})
        if isinstance(slot_def, dict):
            for canonical, aliases in slot_def.items():
                # If the base_prompt implies this canonical (e.g., 'youtube', 'wifi')
                if canonical.lower() in base_prompt.lower():
                    hotwords.extend(aliases)
                    
    # Also add standard phrases from _VI_PHRASES for this scenario
    phrases = _VI_PHRASES.get(scenario_id, [])
    hotwords.extend(phrases)
    
    return "\n".join(list(set(hotwords)))

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def read_wav_to_float32_16k(path: Path) -> tuple[np.ndarray, float]:
    """Read a WAV file, resample to 16 kHz mono float32 if needed."""
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    if framerate != 16000:
        try:
            import librosa
            samples = librosa.resample(samples, orig_sr=framerate, target_sr=16000)
        except ImportError:
            # Simple nearest-neighbour downsample
            factor = framerate / 16000
            indices = (np.arange(int(len(samples) / factor)) * factor).astype(int)
            samples = samples[indices]

    duration = len(samples) / 16000.0
    return samples, duration


def audio_bytes_to_float32_16k(audio_bytes: bytes) -> tuple[np.ndarray, float]:
    """Convert in-memory WAV bytes to float32 16kHz numpy array."""
    buf = io.BytesIO(audio_bytes)
    with wave.open(buf, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    if framerate != 16000:
        factor = framerate / 16000
        indices = (np.arange(int(len(samples) / factor)) * factor).astype(int)
        samples = samples[indices]

    duration = len(samples) / 16000.0
    return samples, duration


def float32_to_wav_bytes(samples: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Convert float32 numpy array to WAV bytes."""
    audio_int16 = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def edit_counts(reference: str, hypothesis: str) -> tuple[int, int]:
    """Return (edit_distance, ref_word_count) for WER computation."""
    ref = reference.lower().split()
    hyp = hypothesis.lower().split()
    if not ref:
        return 0, 0
    # Wagner-Fischer DP
    dp = list(range(len(hyp) + 1))
    for r in ref:
        new_dp = [dp[0] + 1]
        for j, h in enumerate(hyp):
            new_dp.append(min(
                dp[j] + (0 if r == h else 1),
                dp[j + 1] + 1,
                new_dp[j] + 1,
            ))
        dp = new_dp
    return dp[-1], len(ref)

