# -*- coding: utf-8 -*-
"""Pure STT Engine Wrapper for Sherpa-ONNX."""

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple
import numpy as np

# Ensure sherpa_onnx is importable
try:
    import sherpa_onnx
except ImportError:
    pass

class STTEngine:
    """Wrapper for Sherpa-ONNX to perform Pure STT without Context interference."""
    
    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = Path(model_dir) if model_dir else None
        self.recognizer = None
        self.is_loaded = False
        if self.model_dir:
            self.load_model(str(self.model_dir))

    def load_model(self, model_dir: str):
        """Load the Sherpa-ONNX transducer model from a specific directory."""
        self.model_dir = Path(model_dir)
        if not self.model_dir.exists():
            raise FileNotFoundError(f"Model directory not found: {self.model_dir}")
            
        encoder = self.model_dir / "encoder.int8.onnx"
        decoder = self.model_dir / "decoder.onnx"
        joiner = self.model_dir / "joiner.int8.onnx"
        tokens = self.model_dir / "tokens.txt"
        bpe = self.model_dir / "bpe.vocab"
        
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(encoder),
            decoder=str(decoder),
            joiner=str(joiner),
            tokens=str(tokens),
            num_threads=2, 
            sample_rate=16000, 
            feature_dim=80,
            modeling_unit="bpe",
            bpe_vocab=str(bpe) if bpe.exists() else "",
            decoding_method="modified_beam_search",
            hotwords_file="", 
            hotwords_score=0.0,
        )
        self.is_loaded = True

    def transcribe(self, samples: np.ndarray, hotwords: str = "", hotwords_score: float = 0.0) -> Tuple[str, float]:
        """
        Transcribe audio samples.
        If hotwords are provided, it initializes a temporary recognizer with those hotwords.
        Returns: (transcript, inference_time_in_seconds)
        """
        if self.recognizer is None:
            raise RuntimeError("Model is not loaded.")

        start_time = time.time()
        
        if hotwords.strip():
            # If context is injected, we must create a temporary recognizer instance
            # because Sherpa-ONNX Python API requires hotwords at initialization.
            hw_file = ""
            tmp = None
            lines = [ln.strip().upper() for ln in hotwords.splitlines() if ln.strip()]
            if lines:
                fd, tmp = tempfile.mkstemp(suffix=".txt", prefix="sherpa_hw_")
                os.close(fd)
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                hw_file = tmp
                
            try:
                rec = sherpa_onnx.OfflineRecognizer.from_transducer(
                    encoder=str(self.model_dir / "encoder.int8.onnx"),
                    decoder=str(self.model_dir / "decoder.onnx"),
                    joiner=str(self.model_dir / "joiner.int8.onnx"),
                    tokens=str(self.model_dir / "tokens.txt"),
                    num_threads=2, sample_rate=16000, feature_dim=80,
                    modeling_unit="bpe",
                    bpe_vocab=str(self.model_dir / "bpe.vocab") if (self.model_dir / "bpe.vocab").exists() else "",
                    decoding_method="modified_beam_search",
                    hotwords_file=hw_file, 
                    hotwords_score=hotwords_score,
                )
                stream = rec.create_stream()
                stream.accept_waveform(16000, samples)
                rec.decode_stream(stream)
                text = stream.result.text.strip()
            finally:
                if tmp and os.path.exists(tmp):
                    os.remove(tmp)
        else:
            # Pure STT path (Pipeline A)
            stream = self.recognizer.create_stream()
            stream.accept_waveform(16000, samples)
            self.recognizer.decode_stream(stream)
            text = stream.result.text.strip()
            
        inference_time = time.time() - start_time
        return text, inference_time
