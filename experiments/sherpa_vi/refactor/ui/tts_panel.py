# -*- coding: utf-8 -*-
"""TTS Generation Panel for UI."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
                             QGridLayout)
from PyQt5.QtCore import Qt, pyqtSignal
from core.tts_engine import TTSEngine

class TTSPanel(QWidget):
    # Signal emitted when user requests to generate audio
    # text, selected_voices, speed
    generate_requested = pyqtSignal(str, list, float)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tts_engine = TTSEngine.get_instance()
        # Initialize engine to get voices list (can take a moment)
        self.tts_engine.ensure_loaded()
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        group = QGroupBox("🎙 TTS Generator")
        vbox = QVBoxLayout()
        
        # 1. Text Input
        hbox_text = QHBoxLayout()
        hbox_text.addWidget(QLabel("Text:"))
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Nhập câu cần đọc...")
        hbox_text.addWidget(self.text_input)
        vbox.addLayout(hbox_text)
        
        # 2. Voices Checkboxes
        vbox.addWidget(QLabel("Available Voices:"))
        self.voices_layout = QGridLayout()
        self.voice_checkboxes = []
        row, col = 0, 0
        for i, voice in enumerate(self.tts_engine.voices):
            cb = QCheckBox(voice)
            if i == 0:
                cb.setChecked(True)
            self.voice_checkboxes.append(cb)
            self.voices_layout.addWidget(cb, row, col)
            col += 1
            if col > 3:
                col = 0
                row += 1
        vbox.addLayout(self.voices_layout)
        
        # 3. Speed & Pitch
        hbox_settings = QHBoxLayout()
        hbox_settings.addWidget(QLabel("Speed:"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.8x", "1.0x", "1.2x", "1.5x"])
        self.speed_combo.setCurrentText("1.0x")
        hbox_settings.addWidget(self.speed_combo)
        
        hbox_settings.addWidget(QLabel("Pitch:"))
        self.pitch_combo = QComboBox()
        self.pitch_combo.addItems(["Low", "Normal", "High"])
        self.pitch_combo.setCurrentText("Normal")
        self.pitch_combo.setEnabled(False) # Placeholder if Vieneu doesn't support Pitch
        hbox_settings.addWidget(self.pitch_combo)
        
        hbox_settings.addStretch()
        vbox.addLayout(hbox_settings)
        
        # 4. Buttons
        hbox_btns = QHBoxLayout()
        self.gen_btn = QPushButton("Generate Audio")
        self.gen_btn.clicked.connect(self._on_generate)
        
        hbox_btns.addWidget(self.gen_btn)
        hbox_btns.addStretch()
        vbox.addLayout(hbox_btns)
        
        group.setLayout(vbox)
        layout.addWidget(group)
        self.setLayout(layout)
        
    def _on_generate(self):
        text = self.text_input.text().strip()
        if not text:
            return
            
        selected_voices = [cb.text() for cb in self.voice_checkboxes if cb.isChecked()]
        if not selected_voices:
            return
            
        speed_str = self.speed_combo.currentText().replace("x", "")
        speed = float(speed_str)
        
        self.generate_requested.emit(text, selected_voices, speed)
        
    def set_busy(self, is_busy: bool):
        self.gen_btn.setDisabled(is_busy)
        self.gen_btn.setText("⏳ Generating..." if is_busy else "Generate Audio")
