# -*- coding: utf-8 -*-
"""Batch Evaluation UI Panel."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QLabel, QPushButton, QProgressBar, QTextEdit,
                             QCheckBox, QComboBox, QFormLayout)
from PyQt5.QtCore import Qt

from core.tts_engine import TTSEngine
from core.batch_runner import BatchRunnerWorker

class BatchEvaluationPanel(QWidget):
    def __init__(self, stt_engine, context_engine, global_hotwords_func, parent=None):
        super().__init__(parent)
        self.stt_engine = stt_engine
        self.context_engine = context_engine
        self.global_hotwords_func = global_hotwords_func
        
        self.worker = None
        self.tts_engine = TTSEngine.get_instance()
        self.tts_engine.ensure_loaded()
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # 1. Config Group
        config_group = QGroupBox("Batch Configuration")
        config_layout = QFormLayout()
        
        self.scenario_cb = QComboBox()
        self.scenario_cb.addItem("All Scenarios")
        for scen in self.context_engine.config:
            self.scenario_cb.addItem(scen.get("name", scen.get("scenario_id")))
        config_layout.addRow("Scenario to Test:", self.scenario_cb)
        
        self.speed_cb = QComboBox()
        self.speed_cb.addItems(["1.0x Only", "All Variations (0.8x, 1.0x, 1.2x)"])
        config_layout.addRow("Speeds:", self.speed_cb)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # 2. Progress Group
        prog_group = QGroupBox("Execution Progress")
        prog_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        prog_layout.addWidget(self.progress_bar)
        
        self.status_lbl = QLabel("Ready")
        prog_layout.addWidget(self.status_lbl)
        
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        prog_layout.addWidget(self.log_edit)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("▶ Start Batch Evaluation")
        self.start_btn.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; padding: 8px;")
        self.start_btn.clicked.connect(self.start_batch)
        
        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_batch)
        
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        
        prog_layout.addLayout(btn_layout)
        prog_group.setLayout(prog_layout)
        
        layout.addWidget(prog_group)
        self.setLayout(layout)
        
    def start_batch(self):
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log_edit.clear()
        
        # Build config
        dataset = []
        sel_idx = self.scenario_cb.currentIndex()
        if sel_idx == 0:
            dataset = self.context_engine.config
        else:
            dataset = [self.context_engine.config[sel_idx - 1]]
            
        voices = [self.tts_engine.voices[0]] if self.tts_engine.voices else ["Default"]
        
        speeds = [1.0]
        if self.speed_cb.currentIndex() == 1:
            speeds = [0.8, 1.0, 1.2]
            
        ghw = self.global_hotwords_func()
        
        self.worker = BatchRunnerWorker(
            dataset_config=dataset,
            tts_voices=voices,
            speeds=speeds,
            stt_engine=self.stt_engine,
            context_engine=self.context_engine,
            global_hotwords=ghw
        )
        self.worker.progress_update.connect(self.on_progress)
        self.worker.result_emitted.connect(self.on_result)
        self.worker.completed.connect(self.on_completed)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()
        
    def stop_batch(self):
        if self.worker:
            self.worker.cancel()
            self.status_lbl.setText("Cancelling...")
            self.stop_btn.setEnabled(False)
            
    def on_progress(self, curr, total, text):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(curr)
        self.status_lbl.setText(f"[{curr}/{total}] {text}")
        
    def on_result(self, res):
        log_line = f"[{res['id']}] {res['text']} -> {res['ctx_semantic']} (WER: {res['ctx_wer']*100:.1f}%)"
        self.log_edit.append(log_line)
        
    def on_completed(self, report_path):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_lbl.setText("Completed.")
        self.log_edit.append(f"\n✅ Batch report saved to:\n{report_path}")
        
    def on_failed(self, err):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_lbl.setText("Failed.")
        self.log_edit.append(f"\n❌ Error: {err}")
