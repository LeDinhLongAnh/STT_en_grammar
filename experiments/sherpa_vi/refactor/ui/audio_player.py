# -*- coding: utf-8 -*-
"""Unified Audio Player Widget for GUI."""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import Qt
import sounddevice as sd
from core.audio_manager import AudioManager

class AudioPlayerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_manager = AudioManager.get_instance()
        self.audio_manager.register_playback_callback(self._handle_playback)
        self.is_playing = False
        
        self.init_ui()
        
    def init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.prev_btn = QPushButton("⏮")
        self.prev_btn.clicked.connect(self.play_previous)
        self.prev_btn.setFixedWidth(40)
        
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self.toggle_play)
        
        self.next_btn = QPushButton("⏭")
        self.next_btn.clicked.connect(self.play_next)
        self.next_btn.setFixedWidth(40)
        
        self.info_label = QLabel("No Audio")
        self.info_label.setStyleSheet("color: #666; font-style: italic;")
        
        layout.addWidget(self.prev_btn)
        layout.addWidget(self.play_btn)
        layout.addWidget(self.next_btn)
        layout.addWidget(self.info_label)
        layout.addStretch()
        
        self.setLayout(layout)
        self.update_ui()
        
    def _handle_playback(self, action, sample=None):
        if action == "play" and sample:
            self._play_audio(sample)
        elif action == "stop":
            self._stop_audio()
            
    def _play_audio(self, sample):
        if sample.samples is None:
            return
        sd.stop()
        sd.play(sample.samples, samplerate=sample.sample_rate)
        self.is_playing = True
        self.play_btn.setText("⏹ Stop")
        self.info_label.setText(f"Playing: {sample.source} ({sample.duration:.1f}s)")
        
    def _stop_audio(self):
        sd.stop()
        self.is_playing = False
        self.play_btn.setText("▶ Play")
        self.update_ui()
        
    def toggle_play(self):
        if self.is_playing:
            self.audio_manager.stop_playback()
        else:
            self.audio_manager.play_current()
            
    def play_next(self):
        self.audio_manager.stop_playback()
        if self.audio_manager.next():
            self.update_ui()
            self.audio_manager.play_current()
            
    def play_previous(self):
        self.audio_manager.stop_playback()
        if self.audio_manager.previous():
            self.update_ui()
            self.audio_manager.play_current()
            
    def update_ui(self):
        sample = self.audio_manager.get_current_sample()
        if sample:
            self.info_label.setText(f"[{self.audio_manager.current_index + 1}/{len(self.audio_manager.samples)}] {sample.source}: {sample.duration:.1f}s")
        else:
            self.info_label.setText("No Audio")
            
        self.prev_btn.setEnabled(self.audio_manager.current_index > 0)
        self.next_btn.setEnabled(self.audio_manager.current_index < len(self.audio_manager.samples) - 1)
        self.play_btn.setEnabled(sample is not None)
