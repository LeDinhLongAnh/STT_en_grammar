#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
results_logger.py
-----------------
Ghi va quan ly lich su ket qua so sanh STT.

Chuc nang:
  - Tao session file moi moi lan mo app (session_<timestamp>.json + .csv)
  - append_result(...)  : Them 1 dong ket qua vao session hien tai + ghi ngay ra file
  - get_history()       : Lay toan bo lich su trong session hien tai (dang list of dict)
  - export_markdown()   : Xuat lich su ra file .md, tra ve duong dan
"""

from __future__ import annotations

import csv
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Duong dan luu tru ket qua
# ---------------------------------------------------------------------------
BASE_DIR     = Path(__file__).parent.parent
RESULTS_DIR  = BASE_DIR / "experiments" / "results"


# ---------------------------------------------------------------------------
# Session hien tai (khoi tao khi module duoc import lan dau)
# ---------------------------------------------------------------------------
_lock        = threading.Lock()
_session_ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
_session_json = str(RESULTS_DIR / f"session_{_session_ts}.json")
_session_csv  = str(RESULTS_DIR / f"session_{_session_ts}.csv")
_history: list[dict] = []

# CSV headers
_CSV_HEADERS = [
    "stt", "thoi_gian", "nguon_audio",
    "reference", "pipeline_a", "pipeline_b",
    "wer_a", "wer_b", "cer_a", "cer_b"
]


# ---------------------------------------------------------------------------
# Khoi tao thu muc va file CSV header
# ---------------------------------------------------------------------------
def _init_session() -> None:
    """Tao thu muc va ghi header CSV cho session hien tai."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if not os.path.exists(_session_csv):
        with open(_session_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
            writer.writeheader()


_init_session()


# ---------------------------------------------------------------------------
# Ham public: them ket qua
# ---------------------------------------------------------------------------
def append_result(
    source: str,          # "TTS" | "File" | "Mic"
    pipeline_a: str,      # Ket qua Pipeline A
    pipeline_b: str,      # Ket qua Pipeline B
    reference: str = "",  # Cau tham chieu (co the rong)
    wer_a: float = -1.0,
    wer_b: float = -1.0,
    cer_a: float = -1.0,
    cer_b: float = -1.0,
) -> dict:
    """Them 1 dong ket qua vao lich su session va ghi ngay ra JSON + CSV.

    Tra ve dict da them.
    """
    with _lock:
        idx = len(_history) + 1
        entry = {
            "stt"        : idx,
            "thoi_gian"  : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "nguon_audio": source,
            "reference"  : reference,
            "pipeline_a" : pipeline_a,
            "pipeline_b" : pipeline_b,
            "wer_a"      : round(wer_a, 4) if wer_a >= 0 else None,
            "wer_b"      : round(wer_b, 4) if wer_b >= 0 else None,
            "cer_a"      : round(cer_a, 4) if cer_a >= 0 else None,
            "cer_b"      : round(cer_b, 4) if cer_b >= 0 else None,
        }
        _history.append(entry)

        # Ghi JSON (overwrite toan bo lich su de dam bao nhat quan)
        with open(_session_json, "w", encoding="utf-8") as jf:
            json.dump(_history, jf, ensure_ascii=False, indent=2)

        # Append vao CSV
        with open(_session_csv, "a", newline="", encoding="utf-8") as cf:
            writer = csv.DictWriter(cf, fieldnames=_CSV_HEADERS)
            writer.writerow(entry)

    return entry


# ---------------------------------------------------------------------------
# Ham public: lay lich su
# ---------------------------------------------------------------------------
def get_history() -> list[dict]:
    """Tra ve danh sach tat ca ket qua trong session hien tai."""
    with _lock:
        return list(_history)


def get_history_as_table() -> list[list]:
    """Tra ve lich su dang list of list, phu hop hien thi voi gr.Dataframe."""
    with _lock:
        rows = []
        for e in _history:
            wer_a_str = f"{e['wer_a']:.2%}" if e['wer_a'] is not None else "-"
            wer_b_str = f"{e['wer_b']:.2%}" if e['wer_b'] is not None else "-"
            rows.append([
                e["stt"],
                e["thoi_gian"],
                e["nguon_audio"],
                e["reference"] or "(khong co)",
                e["pipeline_a"],
                e["pipeline_b"],
                wer_a_str,
                wer_b_str,
            ])
        return rows


# ---------------------------------------------------------------------------
# Ham public: xuat Markdown
# ---------------------------------------------------------------------------
def export_markdown() -> str:
    """Xuat lich su session hien tai ra file Markdown.

    Tra ve duong dan file da xuat.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = str(RESULTS_DIR / f"export_{ts}.md")

    with _lock:
        history_copy = list(_history)

    lines = [
        f"# Ket qua kiem tra STT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| STT | Thoi gian | Nguon | Reference | Pipeline A (Baseline) | Pipeline B (Context) | WER A | WER B |",
        "|-----|-----------|-------|-----------|----------------------|---------------------|-------|-------|",
    ]
    for e in history_copy:
        ref  = e.get("reference") or "(khong co)"
        wer_a = f"{e['wer_a']:.2%}" if e.get("wer_a") is not None else "-"
        wer_b = f"{e['wer_b']:.2%}" if e.get("wer_b") is not None else "-"
        # Thay the ky tu pipe trong noi dung STT (tranh loi format Markdown table)
        def esc(s):
            return str(s).replace("|", "&#124;")
        lines.append(
            f"| {e['stt']} | {e['thoi_gian']} | {e['nguon_audio']} "
            f"| {esc(ref)} | {esc(e['pipeline_a'])} | {esc(e['pipeline_b'])} "
            f"| {wer_a} | {wer_b} |"
        )

    lines += [
        "",
        f"---",
        f"*Session JSON: `{_session_json}`*",
        f"*Session CSV: `{_session_csv}`*",
    ]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return md_path


def get_session_files() -> dict:
    """Tra ve duong dan cac file session hien tai."""
    return {
        "json": _session_json,
        "csv" : _session_csv,
    }
