# -*- coding: utf-8 -*-
"""Context Result Panel with Text Logs for Phase 3."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QTextEdit)
from PyQt5.QtCore import Qt

class ContextResultPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        group = QGroupBox("STEP 6: TEXT LOGS & ANALYSIS")
        group.setStyleSheet("QGroupBox { font-weight: bold; }")
        vbox = QVBoxLayout()
        
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setStyleSheet("font-family: Consolas, monospace; font-size: 14px; background-color: #1e1e1e; color: #d4d4d4;")
        vbox.addWidget(self.log_edit)
        
        group.setLayout(vbox)
        layout.addWidget(group)
        self.setLayout(layout)
        
    def update_context(self, pure_data: dict, bias_data: dict, post_data: dict, diff_a: str, diff_b: str, diff_c: str):
        log = ""
        
        log += "===============================\n"
        log += "A. PURE STT (BASELINE)\n"
        log += "===============================\n"
        log += f"Context: NONE\n"
        log += f"Output:\n{pure_data.get('raw_transcript', '')}\n\n"
        
        if bias_data:
            log += "===============================\n"
            log += "B. CONTEXTUAL BIASING (ACOUSTIC)\n"
            log += "===============================\n"
            log += f"Output:\n{bias_data.get('raw_transcript', '')}\n\n"
            
        if post_data:
            ctx_res = post_data.get('ctx_result')
            log += "===============================\n"
            log += "C. POST PROCESSING (NLP)\n"
            log += "===============================\n"
            log += f"Raw Input: {post_data.get('raw_transcript', '')}\n"
            if ctx_res:
                log += f"Matched Scenario: {ctx_res.detected_scenario}\n"
                log += f"Confidence: {ctx_res.scenario_confidence:.2f}\n"
                log += f"Correction Type: {ctx_res.correction_type}\n"
                log += f"Extracted Slots: {ctx_res.extracted_slots}\n"
            log += f"\nFinal Output:\n{post_data.get('final_output', '')}\n\n"
            
        # Append HTML diffs at the end
        html_log = f"<pre style='color: #d4d4d4; font-family: Consolas;'>{log}</pre>"
        html_log += "<hr><h3 style='color: white;'>DIFF ANALYSIS</h3>"
        html_log += f"<b>A. PURE STT:</b><br/>{diff_a}<br/><br/>"
        if bias_data:
            html_log += f"<b>B. CONTEXTUAL BIASING:</b><br/>{diff_b}<br/><br/>"
        if post_data:
            html_log += f"<b>C. POST PROCESSING:</b><br/>{diff_c}<br/><br/>"
            
        self.log_edit.setHtml(html_log)

    def clear(self):
        self.log_edit.clear()
