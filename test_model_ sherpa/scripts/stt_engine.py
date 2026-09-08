#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stt_engine.py
-------------
Load va chay 2 recognizer sherpa-onnx:
  - Pipeline A (baseline)     : modified_beam_search, khong hotwords
  - Pipeline B (context-aware): modified_beam_search, co hotwords tu config/hotwords.txt

Cac ham chinh:
  - load_models()          : Load ca 2 recognizer (goi trong thread rieng)
  - transcribe_both(samples) -> (str, str)  : Chay ca A va B, tra ve (text_A, text_B)
  - reload_pipeline_b()    : Tai tao recognizer B sau khi hotwords thay doi
  - is_loaded() -> bool    : Kiem tra xem ca 2 model da san sang chua
"""

from __future__ import annotations

import os
import re
import threading
import numpy as np
from pathlib import Path

# ---------------------------------------------------------------------------
# Duong dan model va config — chinh sua o day neu can thiet
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent          # thu muc goc: test_model_whisper + sherpa
MODELS_DIR  = BASE_DIR / "models" / "sherpa-onnx-zipformer-vi"
CONFIG_DIR  = BASE_DIR / "config"

# Duong dan cac file model STT
ENCODER_PATH  = str(MODELS_DIR / "encoder.int8.onnx")
DECODER_PATH  = str(MODELS_DIR / "decoder.onnx")
JOINER_PATH   = str(MODELS_DIR / "joiner.int8.onnx")
TOKENS_PATH   = str(MODELS_DIR / "tokens.txt")
BPE_MODEL_PATH = str(MODELS_DIR / "bpe.model")
BPE_VOCAB_PATH = str(MODELS_DIR / "bpe.vocab")

# File hotwords ma Pipeline B doc de chay context-aware STT
HOTWORDS_FILE  = str(CONFIG_DIR / "hotwords.txt")

# So luong CPU thread cho moi recognizer
NUM_THREADS = 4


# ---------------------------------------------------------------------------
# Trang thai noi bo
# ---------------------------------------------------------------------------
_lock = threading.Lock()

# Cac recognizer duoc giu trong bien module-level
_recognizer_a = None   # baseline
_recognizer_b = None   # context-aware
_load_status  = "chua_load"   # "chua_load" | "dang_load" | "da_load" | "loi"
_load_error   = ""


# ---------------------------------------------------------------------------
# Ham noi bo: tao recognizer
# ---------------------------------------------------------------------------
def _make_recognizer_a():
    """Tao recognizer A: khong co hotwords, dung modified_beam_search thuan tuy."""
    import sherpa_onnx
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder  = ENCODER_PATH,
        decoder  = DECODER_PATH,
        joiner   = JOINER_PATH,
        tokens   = TOKENS_PATH,
        decoding_method = "modified_beam_search",
        max_active_paths = 4,
        num_threads = NUM_THREADS,
    )


def _prepare_clean_hotwords_file() -> str:
    """Doc HOTWORDS_FILE, loai bo comment (#), tu dong UPPERCASE cac tu,
    va ghi ra file tam config/hotwords_prepared.txt cho sherpa-onnx dung.

    Model zipformer-vi chi co token chu HOA trong tokens.txt va bpe.vocab.
    Neu hotwords la chu thuong, BPE se khong map duoc va bo qua.
    Dong thoi sherpa-onnx bao loi neu doc comment chua dau ':'.
    """
    if not os.path.exists(HOTWORDS_FILE) or os.path.getsize(HOTWORDS_FILE) == 0:
        return ""

    try:
        with open(HOTWORDS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        clean_lines = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                word, score = line.rsplit(":", 1)
                clean_lines.append(f"{word.strip().upper()} :{score.strip()}")
            else:
                clean_lines.append(line.upper())

        if not clean_lines:
            return ""

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        prep_path = str(CONFIG_DIR / "hotwords_prepared.txt")
        with open(prep_path, "w", encoding="utf-8") as f:
            f.write("\n".join(clean_lines) + "\n")
        return prep_path
    except Exception as e:
        print(f"[CANH BAO] Loi khi chuan hoa hotwords: {e}")
        return HOTWORDS_FILE


def _make_recognizer_b():
    """Tao recognizer B: co hotwords tu file HOTWORDS_FILE.

    Neu file hotwords chua ton tai hoac rong, tao recognizer giong A
    nhung voi cau hinh BPE san sang de nhan hotwords.
    """
    import sherpa_onnx

    # Chuan bi file hotwords da chuan hoa (uppercase, loc comment)
    hotwords_file_param = _prepare_clean_hotwords_file()

    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder  = ENCODER_PATH,
        decoder  = DECODER_PATH,
        joiner   = JOINER_PATH,
        tokens   = TOKENS_PATH,
        decoding_method = "modified_beam_search",
        max_active_paths = 4,
        num_threads = NUM_THREADS,
        # Cau hinh hotwords — chi co hieu luc khi hotwords_file_param != ""
        hotwords_file   = hotwords_file_param,
        modeling_unit   = "bpe",
        bpe_vocab       = BPE_VOCAB_PATH,
    )


# ---------------------------------------------------------------------------
# Ham public: load model (goi tu thread ngoai de khong block UI)
# ---------------------------------------------------------------------------
def load_models() -> None:
    """Load ca 2 recognizer A va B.

    Ham nay nen duoc goi trong 1 thread rieng (ThreadPoolExecutor hoac threading.Thread)
    de UI khong bi treo. Ket qua truy cap qua get_status() va is_loaded().
    """
    global _recognizer_a, _recognizer_b, _load_status, _load_error
    with _lock:
        if _load_status in ("dang_load", "da_load"):
            return   # Tranh goi nhieu lan
        _load_status = "dang_load"
        _load_error  = ""

    try:
        # Kiem tra file ton tai truoc khi load
        for label, path in [
            ("encoder", ENCODER_PATH),
            ("decoder", DECODER_PATH),
            ("joiner",  JOINER_PATH),
            ("tokens",  TOKENS_PATH),
        ]:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Khong tim thay file model ({label}): {path}")

        # Load recognizer A
        ra = _make_recognizer_a()

        # Load recognizer B
        rb = _make_recognizer_b()

        with _lock:
            _recognizer_a = ra
            _recognizer_b = rb
            _load_status  = "da_load"

    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        with _lock:
            _load_status = "loi"
            _load_error  = str(e)
        raise RuntimeError(f"Load model that bai: {e}") from e


# ---------------------------------------------------------------------------
# Ham public: reload Pipeline B sau khi doi hotwords
# ---------------------------------------------------------------------------
def reload_pipeline_b() -> str:
    """Tai tao recognizer B de nap hotwords moi tu file HOTWORDS_FILE.

    Tra ve thong bao ket qua.
    Ham nay khoa _lock nen chi goi sau khi load_models() da xong.
    """
    global _recognizer_b
    if not is_loaded():
        return "Model chua duoc load. Vui long load model truoc."

    try:
        new_rb = _make_recognizer_b()
        with _lock:
            _recognizer_b = new_rb
        return "Pipeline B da reload voi hotwords moi thanh cong."
    except Exception as e:
        return f"Loi khi reload Pipeline B: {e}"


# ---------------------------------------------------------------------------
# Ham public: kiem tra trang thai
# ---------------------------------------------------------------------------
def is_loaded() -> bool:
    with _lock:
        return _load_status == "da_load"


def get_status() -> str:
    """Tra ve chuoi mo ta trang thai load: dung hien thi tren UI."""
    with _lock:
        if _load_status == "chua_load":
            return "Chua load model"
        elif _load_status == "dang_load":
            return "Dang load model, vui long cho..."
        elif _load_status == "da_load":
            return "Model da san sang"
        elif _load_status == "loi":
            return f"Loi load model: {_load_error}"
        return "Trang thai khong xac dinh"


# ---------------------------------------------------------------------------
# Ham public: chay STT tren ca 2 pipeline
# ---------------------------------------------------------------------------
def transcribe_both(samples: np.ndarray) -> tuple[str, str]:
    """Chay samples (float32 16kHz mono) qua ca 2 recognizer.

    Tra ve (text_pipeline_a, text_pipeline_b).
    Raises RuntimeError neu model chua load.
    """
    if not is_loaded():
        raise RuntimeError("Model chua duoc load. Vui long bam 'Load Model' truoc.")

    import sherpa_onnx

    # --- Pipeline A ---
    with _lock:
        ra = _recognizer_a
    stream_a = ra.create_stream()
    stream_a.accept_waveform(16000, samples)
    ra.decode_stream(stream_a)
    result_a = stream_a.result.text.strip()

    # --- Pipeline B ---
    with _lock:
        rb = _recognizer_b
    stream_b = rb.create_stream()
    stream_b.accept_waveform(16000, samples)
    rb.decode_stream(stream_b)
    result_b = stream_b.result.text.strip()

    # Hau xu ly: quy doi tu dong am / phien am ve tu chuan cho Pipeline B
    try:
        import homophone_mapper as hm
        result_b = hm.normalize_homophones(result_b)
    except Exception as e:
        print(f"[CANH BAO] Loi khi ap dung homophone normalization: {e}")

    return result_a, result_b


# ---------------------------------------------------------------------------
# Ham tien ich: tinh WER/CER chuan hoa (khong phan biet hoa/thuong, bo dau cau)
# ---------------------------------------------------------------------------
def _normalize_for_metric(text: str) -> str:
    """Chuyen ve chu thuong, xoa toan bo dau cau va chuan hoa khoang trang."""
    if not text:
        return ""
    text = text.lower()
    # Loai bo toan bo dau cau Unicode/ASCII, chi giu lai chu va so
    text = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
    # Gom nhieu khoang trang lien tiep thanh 1 khoang trang
    return re.sub(r'\s+', ' ', text).strip()


def compute_wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate (WER) don gian khong dung thu vien ngoai.

    WER = (S + D + I) / N   (Substitution + Deletion + Insertion) / total words reference
    Dung Levenshtein edit-distance o cap do tu.
    """
    ref_words = _normalize_for_metric(reference).split()
    hyp_words = _normalize_for_metric(hypothesis).split()
    N = len(ref_words)
    if N == 0:
        return 0.0 if len(hyp_words) == 0 else 1.0

    # Ma tran Levenshtein
    m, n = len(ref_words), len(hyp_words)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[j] = prev[j - 1]
            else:
                dp[j] = 1 + min(prev[j], dp[j - 1], prev[j - 1])
    return dp[n] / N


def compute_cer(reference: str, hypothesis: str) -> float:
    """Character Error Rate (CER) don gian.

    CER = Levenshtein(ref, hyp) / len(ref)
    """
    ref_chars = list(_normalize_for_metric(reference).replace(" ", ""))
    hyp_chars = list(_normalize_for_metric(hypothesis).replace(" ", ""))
    N = len(ref_chars)
    if N == 0:
        return 0.0 if len(hyp_chars) == 0 else 1.0

    m, n = len(ref_chars), len(hyp_chars)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            if ref_chars[i - 1] == hyp_chars[j - 1]:
                dp[j] = prev[j - 1]
            else:
                dp[j] = 1 + min(prev[j], dp[j - 1], prev[j - 1])
    return dp[n] / N
