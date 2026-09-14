#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Result logging and reporting helper for Whisper and Sherpa VI experiments."""

from __future__ import annotations

import csv
import datetime
import os
from pathlib import Path
from typing import Any, Dict, List


CSV_COLUMNS = [
    "Timestamp",
    "Model",
    "Source_Type",
    "Scenario",
    "Reference",
    "Baseline_Text",
    "Baseline_WER",
    "Global_Text",
    "Global_WER",
    "GlobalBias_Text",
    "GlobalBias_WER",
    "GlobalBias_RAM_MB",
    "Scenario_Text",
    "Scenario_WER",
    "Prompt_Verdict",
    "Audio_Duration_s",
    "Saved_Audio_Path",
]


def log_test_result(csv_path: Path, result_row: Dict[str, Any]) -> None:
    """Append a single test case result to CSV. Ensures UTF-8-SIG for Excel compatibility."""
    # Ensure backward compatibility for Scenario_Text/WER
    if not result_row.get("Scenario_Text"):
        result_row["Scenario_Text"] = result_row.get("GlobalBias_Text") or result_row.get("Global_Text") or ""
    if not result_row.get("Scenario_WER"):
        result_row["Scenario_WER"] = result_row.get("GlobalBias_WER") or result_row.get("Global_WER") or ""

    file_exists = csv_path.exists() and csv_path.stat().st_size > 0
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        
        row = {col: result_row.get(col, "") for col in CSV_COLUMNS}
        writer.writerow(row)


def generate_markdown_report(csv_path: Path, title: str = "Báo cáo thử nghiệm STT: Prompt vs Không Prompt") -> str:
    """Generate a clean Markdown report summarizing Prompt Effect from the CSV log."""
    if not csv_path.exists():
        return f"# {title}\n\nChưa có dữ liệu kiểm thử nào được ghi nhận."

    rows: List[Dict[str, str]] = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    if not rows:
        return f"# {title}\n\nChưa có dữ liệu kiểm thử nào."

    total = len(rows)
    improved = sum(1 for r in rows if "TỐT HƠN" in r.get("Prompt_Verdict", "").upper())
    worsened = sum(1 for r in rows if "XẤU HƠN" in r.get("Prompt_Verdict", "").upper())
    unchanged = total - improved - worsened

    # Group by Source_Type
    sources: Dict[str, int] = {}
    for r in rows:
        src = r.get("Source_Type", "UNKNOWN")
        sources[src] = sources.get(src, 0) + 1

    source_breakdown = ", ".join(f"{k}: {v} câu" for k, v in sorted(sources.items()))

    has_bias = any(r.get("GlobalBias_Text") for r in rows)
    has_global = any(r.get("Global_Text") for r in rows)

    lines = [
        f"# {title}",
        f"",
        f"**Thời gian xuất báo cáo:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**Tổng số lượt test:** {total} lượt ({source_breakdown})  ",
        f"",
        f"## 1. Tóm tắt hiệu quả của Prompt (So sánh: Không Prompt vs Có Prompt)",
        f"",
        f"| Chỉ số | Số lượng | Tỷ lệ (%) |",
        f"|---|---:|---:|",
        f"| 🟢 **Tốt hơn (Prompt giúp sửa đúng)** | **{improved}** | **{improved / total * 100:.1f}%** |",
        f"| 🔴 **Xấu hơn (Prompt gây ảo giác/sai)** | **{worsened}** | **{worsened / total * 100:.1f}%** |",
        f"| ⚪ **Không đổi (Cả hai cùng đúng/sai)** | **{unchanged}** | **{unchanged / total * 100:.1f}%** |",
        f"",
        f"## 2. Bảng kết quả chi tiết từng lượt test",
        f"",
    ]

    if has_bias and has_global:
        lines.append("| Thời gian | Nguồn | Câu chuẩn (Reference) | 1. Không Prompt | 2. Global Prompt | 3. Global + Logit Bias | Đánh giá |")
        lines.append("|---|:---:|---|---|---|---|:---:|")
        for r in rows[-30:]:
            t = r.get("Timestamp", "")[11:]
            src = r.get("Source_Type", "")
            ref = r.get("Reference", "")
            base = r.get("Baseline_Text", "")
            base_wer = r.get("Baseline_WER", "")
            base_disp = f"{base} *({base_wer})*" if base else "—"

            glob = r.get("Global_Text", "")
            glob_wer = r.get("Global_WER", "")
            glob_disp = f"{glob} *({glob_wer})*" if glob else "—"

            bias = r.get("GlobalBias_Text") or r.get("Scenario_Text") or glob
            bias_wer = r.get("GlobalBias_WER") or r.get("Scenario_WER") or glob_wer
            bias_disp = f"{bias} *({bias_wer})*" if bias else "—"

            verd = r.get("Prompt_Verdict", "")
            icon = "🟢" if "TỐT HƠN" in verd else "🔴" if "XẤU HƠN" in verd else "⚪"
            lines.append(f"| {t} | `{src}` | {ref} | {base_disp} | {glob_disp} | {bias_disp} | {icon} {verd} |")
    else:
        lines.append("| Thời gian | Nguồn | Kịch bản | Câu chuẩn (Reference) | 1. Không Prompt | 2. Có Prompt | Đánh giá |")
        lines.append("|---|:---:|---|---|---|---|:---:|")
        for r in rows[-30:]:
            t = r.get("Timestamp", "")[11:]
            src = r.get("Source_Type", "")
            scen = r.get("Scenario", "")
            ref = r.get("Reference", "")
            base = r.get("Baseline_Text", "")
            base_wer = r.get("Baseline_WER", "")
            base_disp = f"{base} *({base_wer})*" if base else "—"

            prompt_text = r.get("GlobalBias_Text") or r.get("Scenario_Text") or r.get("Global_Text") or ""
            prompt_wer = r.get("GlobalBias_WER") or r.get("Scenario_WER") or r.get("Global_WER") or ""
            prompt_disp = f"{prompt_text} *({prompt_wer})*" if prompt_text else "—"

            verd = r.get("Prompt_Verdict", "")
            icon = "🟢" if "TỐT HƠN" in verd else "🔴" if "XẤU HƠN" in verd else "⚪"
            lines.append(f"| {t} | `{src}` | {scen} | {ref} | {base_disp} | {prompt_disp} | {icon} {verd} |")

    return "\n".join(lines)
