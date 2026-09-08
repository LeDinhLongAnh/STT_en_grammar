# -*- coding: utf-8 -*-
"""Text Normalization Utilities for STT Context Engine."""

import re
from typing import Any

# Vietnamese units mapping for normalization
VI_UNITS_MAP = {
    "mega bit": "megabit",
    "mê ga bít": "megabit",
    "mê ga bit": "megabit",
    "mê ga bi tơ": "megabit",
    "megabít": "megabit",
    "mbps": "megabit",
    "mb": "megabit",
    "mê": "megabit",
    "gigabit": "gigabit",
    "gbps": "gigabit",
    "giga bit": "gigabit",
    "ghi ga bít": "gigabit",
    "ghi": "gigabit",
}

# Number words mapping (basic 1-100)
VI_NUMBERS_MAP = {
    "một": "1", "hai": "2", "ba": "3", "bốn": "4", "năm": "5",
    "sáu": "6", "bảy": "7", "tám": "8", "chín": "9", "mười": "10",
    "mười một": "11", "mười hai": "12", "mười lăm": "15",
    "hai mươi": "20", "ba mươi": "30", "bốn mươi": "40", "năm mươi": "50",
    "sáu mươi": "60", "bảy mươi": "70", "tám mươi": "80", "chín mươi": "90",
    "một trăm": "100"
}
ALIASES = {
    "tui iu": "tối ưu",
    "chai game": "chơi game",
    "quai phai": "wifi",
    "wi-fi": "wifi"
    "bận": "bật"
    "hoa phai": "wifi"
    
}


def normalize_basic(text: str) -> str:
    """Basic normalization: lowercase, strip, remove extra spaces."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    # Remove basic punctuation
    text = re.sub(r'[.?!,;:]+', '', text)
    return text


def normalize_units_and_numbers(text: str) -> str:
    """Normalize Vietnamese spoken numbers and units into canonical forms."""
    norm = normalize_basic(text)
    
    # Replace units
    for spoken, canonical in VI_UNITS_MAP.items():
        # Word boundary matching
        pattern = re.compile(rf'\b{spoken}\b')
        norm = pattern.sub(canonical, norm)
        
    # Replace exact tens/hundreds
    for spoken, digit in sorted(VI_NUMBERS_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        pattern = re.compile(rf'\b{spoken}\b')
        norm = pattern.sub(digit, norm)
        
    return norm


def replace_aliases_with_canonical(text: str, config: dict[str, Any]) -> str:
    """Replace phonetic aliases with their canonical values based on config."""
    if not text:
        return ""
        
    normalized = text
    # Support both v1 config format and v2 config format
    
    # V1 Format logic (config["slots"]["category"])
    if "slots" in config:
        slots = config.get("slots", {})
        for category in slots.keys():
            slot_def = slots.get(category)
            if isinstance(slot_def, dict):
                for canonical, aliases in slot_def.items():
                    for alias in aliases:
                        if len(alias) < 3:
                            continue
                        pattern = re.compile(re.escape(alias), re.IGNORECASE)
                        replacement = canonical.upper() if text.isupper() else canonical
                        normalized = pattern.sub(replacement, normalized)
                        
    # V2 Format logic (config["intents"][]["hotwords"])
    # In V2, we might have global mappings or intent-specific mappings.
    # For now, V1 logic covers the main replacements. We can expand this.
    
    return normalized


def get_phonetic_hotwords(scenario_id: str, config: dict[str, Any]) -> str:
    """Extract phonetic hotwords to feed into Sherpa-ONNX."""
    hotwords = []
    
    # Try V2 format first
    for intent in config.get("intents", []):
        if intent.get("scenario_id") == scenario_id or intent.get("intent") == scenario_id:
            hotwords.extend(intent.get("hotwords", []))
            
    # Fallback to V1 format if V2 not fully matched
    if not hotwords and "scenarios" in config:
        scenarios = config.get("scenarios", {})
        scenario = scenarios.get(scenario_id, {})
        base_prompt = scenario.get("prompt", "")
        if base_prompt:
            hotwords.append(base_prompt)
            
        slots = config.get("slots", {})
        for category in ("applications", "networks", "devices"):
            slot_def = slots.get(category, {})
            if isinstance(slot_def, dict):
                for canonical, aliases in slot_def.items():
                    if base_prompt and canonical.lower() in base_prompt.lower():
                        hotwords.extend(aliases)
                        
    return "\n".join(list(set(hotwords)))
