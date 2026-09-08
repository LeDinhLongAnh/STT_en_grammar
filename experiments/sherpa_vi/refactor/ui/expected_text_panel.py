# -*- coding: utf-8 -*-
"""Expected Text Panel for Ground Truth."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit)
from PyQt5.QtCore import Qt

class ExpectedTextPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        group = QGroupBox("STEP 3: EXPECTED TEXT (GROUND TRUTH)")
        group.setStyleSheet("QGroupBox { font-weight: bold; }")
        
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Câu mong muốn / Câu gốc:"))
        
        self.expected_edit = QLineEdit()
        self.expected_edit.setPlaceholderText("Nhập câu mong muốn để so sánh WER, CER...")
        self.expected_edit.setStyleSheet("font-size: 14px; padding: 5px;")
        
        hbox.addWidget(self.expected_edit)
        
        group.setLayout(hbox)
        layout.addWidget(group)
        self.setLayout(layout)
        
    def get_text(self) -> str:
        return self.expected_edit.text().strip()
    
    def set_text(self, text: str):
        self.expected_edit.setText(text)
