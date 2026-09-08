# -*- coding: utf-8 -*-
"""Comparison Summary Table."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import Qt

class ComparisonSummaryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.table = QTableWidget(7, 4)
        self.table.setHorizontalHeaderLabels(["Metric", "① Pure STT", "② Contextual Biasing", "③ Post-processing"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        
        metrics = [
            "Raw Transcript",
            "WER",
            "CER",
            "Exact Match",
            "Normalized Match",
            "STT Inference Time",
            "Context Logic Time"
        ]
        
        for i, m in enumerate(metrics):
            item = QTableWidgetItem(m)
            item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(i, 0, item)
            
        layout.addWidget(self.table)
        self.setLayout(layout)
        
    def _fill_col(self, col: int, data: dict):
        if not data:
            for i in range(7):
                self.table.setItem(i, col, QTableWidgetItem("-"))
            return
            
        self.table.setItem(0, col, QTableWidgetItem(data.get('final_output', data.get('raw_transcript', ''))))
        self.table.setItem(1, col, QTableWidgetItem(f"{data.get('wer', 0)*100:.1f}%"))
        self.table.setItem(2, col, QTableWidgetItem(f"{data.get('cer', 0)*100:.1f}%"))
        self.table.setItem(3, col, QTableWidgetItem("Yes" if data.get('exact') else "No"))
        self.table.setItem(4, col, QTableWidgetItem("Yes" if data.get('norm') else "No"))
        self.table.setItem(5, col, QTableWidgetItem(f"{data.get('stt_time', 0):.3f} s" if 'stt_time' in data else "-"))
        self.table.setItem(6, col, QTableWidgetItem(f"{data.get('ctx_time', 0):.3f} s" if 'ctx_time' in data else "-"))

    def update_results(self, pure_data: dict, bias_data: dict, post_data: dict):
        self._fill_col(1, pure_data)
        self._fill_col(2, bias_data)
        self._fill_col(3, post_data)
