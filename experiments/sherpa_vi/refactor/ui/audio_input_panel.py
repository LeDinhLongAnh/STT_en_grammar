# -*- coding: utf-8 -*-
"""Unified Audio Input Area."""

import uuid
from pathlib import Path
import soundfile as sf
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QPushButton, QFileDialog, QMessageBox)
from PyQt5.QtCore import pyqtSignal

from core.audio_manager import AudioManager, AudioSample
from ui.tts_panel import TTSPanel
from ui.microphone_panel import MicrophonePanel

class AudioInputPanel(QWidget):
    # Emitted when new audio is added
    audio_added = pyqtSignal(object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_manager = AudioManager.get_instance()
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        
        # 1. Load WAV Tab
        wav_tab = QWidget()
        wav_layout = QVBoxLayout()
        self.btn_load_wav = QPushButton("Load WAV File")
        self.btn_load_wav.setStyleSheet("padding: 10px; font-weight: bold;")
        self.btn_load_wav.clicked.connect(self.load_wav)
        wav_layout.addWidget(self.btn_load_wav)
        wav_layout.addStretch()
        wav_tab.setLayout(wav_layout)
        
        # 2. Microphone Tab
        self.mic_panel = MicrophonePanel()
        self.mic_panel.recording_finished.connect(self._on_audio_added)
        
        # 3. TTS Tab
        self.tts_panel = TTSPanel()
        self.tts_panel.generate_requested.connect(self.handle_tts_generate)
        self.tts_worker = None
        
        self.tabs.addTab(wav_tab, "1. Load WAV")
        self.tabs.addTab(self.mic_panel, "2. Microphone")
        self.tabs.addTab(self.tts_panel, "3. Generate TTS")
        
        layout.addWidget(self.tabs)
        self.setLayout(layout)
        
    def load_wav(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open WAV File", "", "WAV Files (*.wav)")
        if file_path:
            try:
                data, samplerate = sf.read(file_path)
                # Convert to mono 16k if needed (simple assumption here)
                if len(data.shape) > 1:
                    data = data[:, 0]
                
                # We should resample if it's not 16k, but for brevity we assume 16k or handle elsewhere
                duration = len(data) / float(samplerate)
                
                sample = AudioSample(
                    id=str(uuid.uuid4()),
                    source="wav",
                    path=file_path,
                    text="",
                    voice="",
                    duration=duration,
                    sample_rate=samplerate,
                    samples=data.astype('float32')
                )
                self._on_audio_added(sample)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load WAV:\n{e}")

    def handle_tts_generate(self, text, voices, speed):
        from core.tts_engine import TTSWorker
        self.tts_panel.set_busy(True)
        voice = voices[0] if voices else "Default"
        
        self.tts_worker = TTSWorker(text, voice, speed)
        self.tts_worker.completed.connect(lambda s, d, v: self.on_tts_completed(s, d, v, text))
        self.tts_worker.failed.connect(self.on_tts_failed)
        self.tts_worker.start()
        
    def on_tts_completed(self, samples, duration, voice, text):
        self.tts_panel.set_busy(False)
        
        # Save to wav
        import time
        root = Path(__file__).resolve().parents[2]
        rec_dir = root / "recordings" / "tts"
        rec_dir.mkdir(parents=True, exist_ok=True)
        
        # Clean text for filename
        import re
        clean_text = re.sub(r'[^\w\s-]', '', text)[:30].strip().replace(' ', '_')
        if not clean_text:
            clean_text = "audio"
            
        filename = f"tts_{time.strftime('%Y%m%d_%H%M%S')}_{clean_text}.wav"
        file_path = rec_dir / filename
        
        sf.write(str(file_path), samples, 16000, subtype='PCM_16')
        
        sample = AudioSample(
            id=str(uuid.uuid4()),
            source="tts",
            path=str(file_path),
            text=text,
            voice=voice,
            duration=duration,
            sample_rate=16000,
            samples=samples
        )
        self._on_audio_added(sample)
        QMessageBox.information(self, "TTS Success", f"Generated & saved to: {filename} ({duration:.1f}s)")
        
    def on_tts_failed(self, err):
        self.tts_panel.set_busy(False)
        QMessageBox.critical(self, "TTS Error", f"Failed to generate TTS:\n{err}")

    def _on_audio_added(self, sample):
        self.audio_manager.add_sample(sample)
        self.audio_added.emit(sample)
