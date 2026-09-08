# -*- coding: utf-8 -*-
"""Microphone Recording Panel."""

import time
import uuid
from pathlib import Path
import numpy as np
import sounddevice as sd
import soundfile as sf

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from core.audio_manager import AudioSample

class MicrophonePanel(QWidget):
    recording_finished = pyqtSignal(object)  # Emits AudioSample
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_recording = False
        self.sample_rate = 16000
        self.channels = 1
        self.recorded_data = []
        self.stream = None
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        hbox = QHBoxLayout()
        
        hbox.addWidget(QLabel("Input Device:"))
        self.device_cb = QComboBox()
        self.populate_devices()
        hbox.addWidget(self.device_cb)
        
        self.record_btn = QPushButton("🔴 START RECORDING")
        self.record_btn.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold;")
        self.record_btn.clicked.connect(self.toggle_recording)
        hbox.addWidget(self.record_btn)
        
        self.time_lbl = QLabel("00:00")
        self.time_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #dc2626;")
        hbox.addWidget(self.time_lbl)
        
        hbox.addStretch()
        layout.addLayout(hbox)
        self.setLayout(layout)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.start_time = 0
        
    def populate_devices(self):
        try:
            devices = sd.query_devices()
            for i, dev in enumerate(devices):
                if dev['max_input_channels'] > 0:
                    self.device_cb.addItem(f"{dev['name']}", i)
        except Exception:
            self.device_cb.addItem("Default", None)
            
    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()
            
    def _audio_callback(self, indata, frames, time, status):
        if status:
            print(status)
        self.recorded_data.append(indata.copy())

    def start_recording(self):
        self.recorded_data = []
        dev_idx = self.device_cb.currentData()
        
        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                device=dev_idx,
                channels=self.channels,
                callback=self._audio_callback
            )
            self.stream.start()
            self.is_recording = True
            self.record_btn.setText("⏹ STOP RECORDING")
            self.record_btn.setStyleSheet("background-color: #374151; color: white; font-weight: bold;")
            
            self.start_time = time.time()
            self.timer.start(100)
        except Exception as e:
            import traceback
            traceback.print_exc()
            
    def stop_recording(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            
        self.is_recording = False
        self.timer.stop()
        self.record_btn.setText("🔴 START RECORDING")
        self.record_btn.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold;")
        
        if not self.recorded_data:
            return
            
        audio_data = np.concatenate(self.recorded_data, axis=0)
        audio_data = audio_data.flatten().astype(np.float32)
        
        # Save to wav
        root = Path(__file__).resolve().parents[2]
        rec_dir = root / "recordings" / "mic"
        rec_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"record_{time.strftime('%Y%m%d_%H%M%S')}.wav"
        file_path = rec_dir / filename
        
        sf.write(str(file_path), audio_data, self.sample_rate, subtype='PCM_16')
        
        duration = len(audio_data) / self.sample_rate
        
        sample = AudioSample(
            id=str(uuid.uuid4()),
            source="mic",
            path=str(file_path),
            text="",
            voice="",
            duration=duration,
            sample_rate=self.sample_rate,
            samples=audio_data
        )
        
        self.recording_finished.emit(sample)
        self.time_lbl.setText("00:00")

    def update_time(self):
        elapsed = int(time.time() - self.start_time)
        mins = elapsed // 60
        secs = elapsed % 60
        self.time_lbl.setText(f"{mins:02d}:{secs:02d}")
