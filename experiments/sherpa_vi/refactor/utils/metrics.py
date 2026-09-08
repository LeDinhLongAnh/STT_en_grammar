# -*- coding: utf-8 -*-
"""Evaluation Metrics for STT Assessment."""

from typing import Tuple, List

def compute_edit_distance(ref: List[str], hyp: List[str]) -> int:
    """Compute Levenshtein distance between two lists of strings."""
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = min(
                    dp[i - 1][j] + 1,      # deletion
                    dp[i][j - 1] + 1,      # insertion
                    dp[i - 1][j - 1] + 1   # substitution
                )
    return dp[n][m]

def calculate_wer(reference: str, hypothesis: str) -> Tuple[float, int, int]:
    """Calculate Word Error Rate. Returns (WER, errors, num_words)."""
    if not reference:
        return 0.0, 0, 0
        
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()
    
    if not ref_words:
        return (1.0, len(hyp_words), 0) if hyp_words else (0.0, 0, 0)
        
    errors = compute_edit_distance(ref_words, hyp_words)
    wer = float(errors) / len(ref_words)
    return wer, errors, len(ref_words)

def calculate_cer(reference: str, hypothesis: str) -> Tuple[float, int, int]:
    """Calculate Character Error Rate. Returns (CER, errors, num_chars)."""
    if not reference:
        return 0.0, 0, 0
        
    ref_chars = list(reference.lower())
    hyp_chars = list(hypothesis.lower())
    
    if not ref_chars:
        return (1.0, len(hyp_chars), 0) if hyp_chars else (0.0, 0, 0)
        
    errors = compute_edit_distance(ref_chars, hyp_chars)
    cer = float(errors) / len(ref_chars)
    return cer, errors, len(ref_chars)

def is_exact_match(reference: str, hypothesis: str) -> bool:
    """Check if the text is exactly the same (case-insensitive, stripped)."""
    if not reference and not hypothesis:
        return True
    if not reference or not hypothesis:
        return False
    return reference.lower().strip() == hypothesis.lower().strip()

def calculate_normalized_match(reference: str, hypothesis: str) -> bool:
    """Check if text matches after basic punctuation and extra space removal."""
    import re
    def norm(t):
        if not t: return ""
        t = t.lower().strip()
        t = re.sub(r'[.?!,;:]+', '', t)
        t = re.sub(r'\s+', ' ', t)
        return t
    return norm(reference) == norm(hypothesis)

def calculate_rtf(audio_duration: float, inference_time: float) -> float:
    """Calculate Real Time Factor (RTF)."""
    if audio_duration <= 0:
        return 0.0
    return inference_time / audio_duration
