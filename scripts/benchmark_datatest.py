#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch Benchmark script for datatest/dataset.json across 3 modes:
1. Baseline (No Prompt)
2. Global Prompt
3. Global Prompt + Logit Bias
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import sys
import time
from pathlib import Path

# Paths
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
EXP_DIR = WORKSPACE_ROOT / "experiments" / "whisper_initial_prompt"
if str(EXP_DIR) not in sys.path:
    sys.path.insert(0, str(EXP_DIR))
EXP_ROOT = WORKSPACE_ROOT / "experiments"
if str(EXP_ROOT) not in sys.path:
    sys.path.insert(0, str(EXP_ROOT))

# Ensure stdout supports UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import whisper
import run as experiment
import logit_bias
from result_logger import log_test_result, generate_markdown_report


def main():
    parser = argparse.ArgumentParser(description="Chay batch benchmark tren toan bo tap datatest")
    parser.add_argument("--model", default="tiny.en", help="Ten whisper model (tiny.en, base.en, small.en...)")
    parser.add_argument("--dataset", default=str(WORKSPACE_ROOT / "datatest" / "dataset.json"), help="File dataset.json")
    parser.add_argument("--limit", type=int, default=0, help="Gioi han so mau chay (0 = tat ca)")
    args = parser.parse_args()

    dataset_file = Path(args.dataset)
    if not dataset_file.is_file():
        print(f"[LOI] Khong tim thay dataset tai: {dataset_file}")
        sys.exit(1)

    with open(dataset_file, "r", encoding="utf-8") as f:
        samples = json.load(f)

    if args.limit > 0:
        samples = samples[:args.limit]

    total = len(samples)
    print("=" * 65)
    print(f"  WHISPER BATCH BENCHMARK — DATASET ({total} samples)")
    print(f"  Model  : {args.model}")
    print(f"  Dataset: {dataset_file}")
    print("=" * 65)

    # 1. Load Whisper model
    print(f"\n[1/3] Dang nap model {args.model} vao RAM...")
    t0 = time.time()
    model = whisper.load_model(args.model, device="cpu", download_root=str(EXP_DIR / ".models"))
    print(f"      Nap xong trong {time.time() - t0:.2f}s")

    # 2. Setup prompts and logit bias
    print("[2/3] Dang chuan bi Global Prompt va Logit Bias filter...")
    config = experiment.load_config(experiment.DEFAULT_CONFIG)
    global_prompt = str(config.get("global_prompt", ""))
    
    tokenizer = whisper.tokenizer.get_tokenizer(multilingual=False, language="en", task="transcribe")
    bias_cfg = logit_bias.load_logit_bias_config()
    bias_filter = logit_bias.build_bias_filter(bias_cfg, tokenizer)
    print(f"      Global Prompt: \"{global_prompt[:45]}...\"")
    print(f"      Logit bias tokens: {len(bias_filter.bias_map)} tokens")

    # 3. Chay benchmark
    print(f"\n[3/3] Bat dau benchmark {total} mau am thanh...\n")
    print(f"{'STT':<4} | {'ID':<11} | {'Ground Truth':<35} | {'Base WER':<9} | {'Prompt WER':<10} | {'Bias WER':<9} | {'Danh gia'}")
    print("-" * 105)

    results_summary = []
    csv_path = EXP_DIR / "test_history.csv"

    for idx, item in enumerate(samples, 1):
        sample_id = item.get("id", f"sample_{idx:03d}")
        rel_audio = item.get("audio_file", f"audio/{sample_id}.wav")
        audio_path = WORKSPACE_ROOT / "datatest" / rel_audio
        gt = str(item.get("ground_truth", "")).strip()

        if not audio_path.is_file():
            print(f"[{idx:02d}/{total}] BO QUA - File khong ton tai: {audio_path}")
            continue

        audio, duration = experiment.read_pcm16_mono_16k(audio_path)

        # Mode 1: Baseline (Khong prompt)
        text_none, sec_none = experiment.transcribe(model, audio, None)
        err_none, words_none = experiment.edit_counts(gt, text_none) if gt else (0, 0)
        wer_none = err_none / words_none if words_none else 0.0

        # Mode 2: Global Prompt
        text_glob, sec_glob = experiment.transcribe(model, audio, global_prompt)
        err_glob, words_glob = experiment.edit_counts(gt, text_glob) if gt else (0, 0)
        wer_glob = err_glob / words_glob if words_glob else 0.0

        # Mode 3: Global Prompt + Logit Bias
        text_bias, sec_bias = logit_bias.transcribe_with_bias(model, audio, global_prompt, bias_filter)
        err_bias, words_bias = experiment.edit_counts(gt, text_bias) if gt else (0, 0)
        wer_bias = err_bias / words_bias if words_bias else 0.0

        # Danh gia (So sanh Mode 3 vs Mode 1)
        verdict = "TỐT HƠN" if err_bias < err_none else "XẤU HƠN" if err_bias > err_none else "KHÔNG ĐỔI"
        icon = "🟢" if verdict == "TỐT HƠN" else "🔴" if verdict == "XẤU HƠN" else "⚪"

        # Log to CSV
        row = {
            "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Model": f"whisper-{args.model}",
            "Source_Type": "DATASET_BATCH",
            "Scenario": item.get("accent", "vietnamese"),
            "Reference": gt,
            "Baseline_Text": text_none,
            "Baseline_WER": f"{wer_none * 100:.1f}%",
            "Global_Text": text_glob,
            "Global_WER": f"{wer_glob * 100:.1f}%",
            "Global_RAM_MB": "0.0",
            "GlobalBias_Text": text_bias,
            "GlobalBias_WER": f"{wer_bias * 100:.1f}%",
            "GlobalBias_RAM_MB": "0.0",
            "Scenario_Text": text_bias,
            "Scenario_WER": f"{wer_bias * 100:.1f}%",
            "Prompt_Verdict": verdict,
            "Audio_Duration_s": f"{duration:.2f}",
            "Saved_Audio_Path": str(audio_path),
        }
        log_test_result(csv_path, row)

        gt_short = (gt[:32] + "..") if len(gt) > 34 else gt
        print(f"{idx:<4} | {sample_id:<11} | {gt_short:<35} | {wer_none*100:>6.1f}%   | {wer_glob*100:>7.1f}%   | {wer_bias*100:>6.1f}%  | {icon} {verdict}")

        results_summary.append({
            "id": sample_id,
            "gt": gt,
            "wer_none": wer_none,
            "wer_glob": wer_glob,
            "wer_bias": wer_bias,
            "verdict": verdict
        })

    # Tong ket
    count = len(results_summary)
    if count > 0:
        mean_base = sum(r["wer_none"] for r in results_summary) / count * 100
        mean_glob = sum(r["wer_glob"] for r in results_summary) / count * 100
        mean_bias = sum(r["wer_bias"] for r in results_summary) / count * 100
        better = sum(1 for r in results_summary if r["verdict"] == "TỐT HƠN")
        worse = sum(1 for r in results_summary if r["verdict"] == "XẤU HƠN")
        same = sum(1 for r in results_summary if r["verdict"] == "KHÔNG ĐỔI")

        print("=" * 105)
        print(f"📊 KẾT QUẢ TỔNG KẾT BENCHMARK ({count} câu):")
        print(f"  - WER trung bình Mode 1 (Không Prompt):            {mean_base:.1f}%")
        print(f"  - WER trung bình Mode 2 (Global Prompt):           {mean_glob:.1f}%  ({mean_base - mean_glob:+.1f}%)")
        print(f"  - WER trung bình Mode 3 (Global + Logit Bias):     {mean_bias:.1f}%  ({mean_base - mean_bias:+.1f}%)")
        print(f"  - Tỷ lệ: 🟢 Tốt hơn: {better}/{count} ({better/count*100:.1f}%) | 🔴 Xấu hơn: {worse}/{count} ({worse/count*100:.1f}%) | ⚪ Bằng: {same}/{count} ({same/count*100:.1f}%)")
        print("=" * 105)

        # Update Markdown report
        md_text = generate_markdown_report(csv_path, f"Báo cáo Benchmark Tập Dữ Liệu ({args.model})")
        report_file = EXP_DIR / "TEST_REPORT.md"
        report_file.write_text(md_text, encoding="utf-8")
        print(f"\n✅ Đã cập nhật báo cáo chi tiết tại: {report_file}")


if __name__ == "__main__":
    main()
