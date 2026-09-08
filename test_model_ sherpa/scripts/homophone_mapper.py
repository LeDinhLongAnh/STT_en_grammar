#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
homophone_mapper.py
-------------------
Module quy doi tu dong am / phien am ve tu chuan (Post-processing normalization).
Vi du:
  - "oai phai", "quai phai", "hoai phai"  -> "Wi-Fi"
  - "diu tup", "du tup"                  -> "YouTube"
  - "lap top", "lap top"                 -> "Laptop"
  - "in-to-net", "in to net"             -> "Internet"

Doc cau hinh tu config/homophones.txt hoac tu chuoi van ban tren giao dien.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
HOMOPHONES_FILE = str(CONFIG_DIR / "homophones.txt")

_lock = threading.Lock()
# Danh sach tuple: (length, compiled_regex, canonical_word)
_compiled_rules: list[tuple[int, re.Pattern, str]] = []
_raw_content: str = ""


def _compile_rules_from_text(content: str) -> list[tuple[int, re.Pattern, str]]:
    """Phan tich text va bien dich thanh danh sach regex da sap xep theo do dai giam dan."""
    rules: list[tuple[int, re.Pattern, str]] = []
    lines = content.splitlines()

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue

        canonical_part, variants_part = line.split(":", 1)
        canonical = canonical_part.strip()
        if not canonical:
            continue

        variants = [v.strip() for v in variants_part.split(",") if v.strip()]
        for var in variants:
            # Tach tu theo khoang trang hoac dau gach noi
            parts = re.split(r"[-\s]+", var)
            parts = [p for p in parts if p]
            if not parts:
                continue

            # Cho phep linh hoat giua dau gach noi '-' va khoang trang ' '
            pat_str = r"[-\s]+".join(re.escape(p) for p in parts)
            # Ranh gioi tu tieng Viet (khong phai ky tu chu/so o hai dau)
            regex = re.compile(rf"(?<!\w){pat_str}(?!\w)", re.IGNORECASE)
            rules.append((len(var), regex, canonical))

    # Sap xep cum dai len truoc de uu tien match cum tu truoc khi match tu don
    rules.sort(key=lambda x: x[0], reverse=True)
    return rules


def load_homophones(path: str = HOMOPHONES_FILE) -> None:
    """Doc file homophones.txt va bien dich quy tac."""
    global _compiled_rules, _raw_content
    content = ""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"[CANH BAO] Khong the doc file {path}: {e}")

    rules = _compile_rules_from_text(content)
    with _lock:
        _compiled_rules = rules
        _raw_content = content


def reload_from_text(content: str) -> int:
    """Nap lai quy tac tu chuoi van ban (khi nguoi dung sua tren UI).

    Tra ve so luong bien the da duoc nap.
    """
    global _compiled_rules, _raw_content
    rules = _compile_rules_from_text(content)
    with _lock:
        _compiled_rules = rules
        _raw_content = content
    return len(rules)


def get_raw_text() -> str:
    """Lay noi dung tho cua file homophones."""
    with _lock:
        if _raw_content:
            return _raw_content
    if os.path.exists(HOMOPHONES_FILE):
        with open(HOMOPHONES_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def save_and_reload(content: str) -> str:
    """Luu noi dung moi vao file config/homophones.txt va reload quy tac."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(HOMOPHONES_FILE, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n" if content.strip() else "")
        count = reload_from_text(content)
        return f"Da luu thanh cong {count} quy tac tu dong am vao '{HOMOPHONES_FILE}'."
    except Exception as e:
        return f"Loi khi luu tu dong am: {e}"


def normalize_homophones(text: str) -> str:
    """Ap dung quy tac thay the tu dong am / phien am len van ban text."""
    if not text:
        return text

    with _lock:
        rules = list(_compiled_rules)

    if not rules:
        # Neu chua load, thu load 1 lan
        load_homophones()
        with _lock:
            rules = list(_compiled_rules)

    result = text
    for _, regex, canonical in rules:
        result = regex.sub(canonical, result)

    return result


# Tu dong load quy tac khi import module
load_homophones()
