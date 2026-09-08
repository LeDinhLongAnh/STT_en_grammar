import jiwer

def calculate_wer(reference: str, hypothesis: str) -> float:
    if not reference.strip() and not hypothesis.strip():
        return 0.0
    if not reference.strip():
        return 1.0
    try:
        transform = jiwer.Compose([
            jiwer.ToLowerCase(),
            jiwer.RemovePunctuation(),
            jiwer.RemoveMultipleSpaces(),
            jiwer.Strip(),
        ])
        return jiwer.wer(transform(reference), transform(hypothesis))
    except Exception:
        return 1.0

def calculate_cer(reference: str, hypothesis: str) -> float:
    if not reference.strip() and not hypothesis.strip():
        return 0.0
    if not reference.strip():
        return 1.0
    try:
        transform = jiwer.Compose([
            jiwer.ToLowerCase(),
            jiwer.RemovePunctuation(),
            jiwer.RemoveMultipleSpaces(),
            jiwer.Strip(),
        ])
        return jiwer.cer(transform(reference), transform(hypothesis))
    except Exception:
        return 1.0

def evaluate_context_harm(wer_baseline: float, wer_context: float) -> str:
    """
    Đánh giá xem context làm tốt lên hay xấu đi.
    """
    diff = wer_baseline - wer_context
    if diff > 0.05:
        return "IMPROVED"
    elif diff > 0.01:
        return "SLIGHTLY IMPROVED"
    elif abs(diff) <= 0.01:
        return "NO CHANGE"
    elif diff < -0.05:
        return "CONTEXT HARM"
    else:
        return "DEGRADED"
