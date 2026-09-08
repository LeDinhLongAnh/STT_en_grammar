# -*- coding: utf-8 -*-
"""Unified Audio Manager for STT GUI."""

import time
import numpy as np
from typing import List, Optional, Callable
from dataclasses import dataclass, field

@dataclass
class AudioSample:
    id: str
    source: str  # "wav", "tts", "mic"
    path: str
    text: str  # Original reference text if applicable
    voice: str  # TTS voice if applicable
    duration: float
    sample_rate: int
    created_at: float = field(default_factory=time.time)
    samples: Optional[np.ndarray] = None


class AudioManager:
    """Manages audio lifecycle, playback, and batch queue."""
    _instance: Optional["AudioManager"] = None

    def __init__(self):
        self.samples: List[AudioSample] = []
        self.current_index: int = -1
        # In a full implementation, we'd use sounddevice here for playback
        # Since this is core logic, we will define interfaces.
        self._playback_callback: Optional[Callable] = None
        
    @classmethod
    def get_instance(cls) -> "AudioManager":
        if cls._instance is None:
            cls._instance = AudioManager()
        return cls._instance

    def add_sample(self, sample: AudioSample):
        self.samples.append(sample)
        self.current_index = len(self.samples) - 1

    def get_current_sample(self) -> Optional[AudioSample]:
        if 0 <= self.current_index < len(self.samples):
            return self.samples[self.current_index]
        return None

    def set_current_index(self, index: int):
        if 0 <= index < len(self.samples):
            self.current_index = index

    def clear(self):
        self.samples.clear()
        self.current_index = -1

    def register_playback_callback(self, cb: Callable):
        """Register a callback for the UI to handle actual sounddevice playback."""
        self._playback_callback = cb

    def play_current(self):
        sample = self.get_current_sample()
        if sample and sample.samples is not None and self._playback_callback:
            self._playback_callback("play", sample)

    def stop_playback(self):
        if self._playback_callback:
            self._playback_callback("stop", None)

    def next(self):
        if self.current_index < len(self.samples) - 1:
            self.current_index += 1
            return True
        return False

    def previous(self):
        if self.current_index > 0:
            self.current_index -= 1
            return True
        return False
