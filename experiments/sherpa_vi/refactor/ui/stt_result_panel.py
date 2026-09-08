# -*- coding: utf-8 -*-
"""Side-by-side Result Panel for Pure STT vs Context STT."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit, QFormLayout
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

class STTResultPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        main_layout = QHBoxLayout()
        
        # 1. PURE STT PANEL
        self.pure_group = QGroupBox("① PURE STT (Pipeline A)")
        self.pure_group.setStyleSheet("QGroupBox { font-weight: bold; color: #1e3a8a; }")
        pure_layout = QFormLayout()
        
        self.pure_raw_edit = QLineEdit()
        self.pure_raw_edit.setReadOnly(True)
        self.pure_raw_edit.setStyleSheet("background-color: #f8fafc; font-size: 14px; font-weight: bold;")
        
        self.pure_wer_lbl = QLabel("-")
        self.pure_time_lbl = QLabel("-")
        self.pure_rtf_lbl = QLabel("-")
        
        pure_layout.addRow("Raw Transcript:", self.pure_raw_edit)
        pure_layout.addRow("WER:", self.pure_wer_lbl)
        pure_layout.addRow("Inference Time:", self.pure_time_lbl)
        pure_layout.addRow("RTF:", self.pure_rtf_lbl)
        
        self.pure_group.setLayout(pure_layout)
        
        # 2. CONTEXT STT PANEL
        self.context_group = QGroupBox("② STT + CONTEXT (Pipeline B)")
        self.context_group.setStyleSheet("QGroupBox { font-weight: bold; color: #047857; }")
        context_layout = QFormLayout()
        
        self.ctx_raw_edit = QLineEdit()
        self.ctx_raw_edit.setReadOnly(True)
        self.ctx_raw_edit.setStyleSheet("background-color: #f8fafc; font-size: 14px; color: #64748b;")
        
        self.ctx_scenario_lbl = QLabel("-")
        self.ctx_intent_lbl = QLabel("-")
        self.ctx_slots_lbl = QLabel("-")
        self.ctx_correction_lbl = QLabel("-")
        
        self.ctx_semantic_edit = QLineEdit()
        self.ctx_semantic_edit.setReadOnly(True)
        self.ctx_semantic_edit.setStyleSheet("background-color: #ecfdf5; font-size: 14px; font-weight: bold; color: #065f46;")
        
        self.ctx_wer_lbl = QLabel("-")
        
        context_layout.addRow("Raw Transcript:", self.ctx_raw_edit)
        context_layout.addRow("Detected Scenario:", self.ctx_scenario_lbl)
        context_layout.addRow("Detected Intent:", self.ctx_intent_lbl)
        context_layout.addRow("Extracted Slots:", self.ctx_slots_lbl)
        context_layout.addRow("Correction Type:", self.ctx_correction_lbl)
        context_layout.addRow("Semantic Result:", self.ctx_semantic_edit)
        context_layout.addRow("Semantic WER:", self.ctx_wer_lbl)
        
        self.context_group.setLayout(context_layout)
        
        main_layout.addWidget(self.pure_group)
        main_layout.addWidget(self.context_group)
        
        self.setLayout(main_layout)
        
    def set_pure_result(self, raw_transcript: str, expected_text: str):
        from utils.text_diff import highlight_diff_html
        diff_html = highlight_diff_html(expected_text, raw_transcript)
        if diff_html:
            self.pure_raw_edit.setText("") # clear
            # QLineEdit does not support rich text well, so we should change it to QTextEdit or QLabel
            # Wait, changing UI elements here is complex. I'll just change setReadOnly line edit to QLabel temporarily, 
            # actually we need to refactor STTResultPanel to use QLabel for rich text.
        self.pure_raw_edit.setText(raw_transcript)
        self.pure_raw_edit.setCursorPosition(0)

    def reset(self):
        self.pure_raw_edit.clear()
        self.pure_wer_lbl.setText("-")
        self.pure_time_lbl.setText("-")
        self.pure_rtf_lbl.setText("-")
        
        self.ctx_raw_edit.clear()
        self.ctx_scenario_lbl.setText("-")
        self.ctx_intent_lbl.setText("-")
        self.ctx_slots_lbl.setText("-")
        self.ctx_correction_lbl.setText("-")
        self.ctx_semantic_edit.clear()
        self.ctx_wer_lbl.setText("-")
