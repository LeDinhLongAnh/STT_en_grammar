# -*- coding: utf-8 -*-
"""Main Window for STT Dashboard - Phase 2."""

import time
from pathlib import Path

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTabWidget, QLabel, QPushButton, QComboBox,
                             QStatusBar, QMessageBox, QGroupBox, QPlainTextEdit,
                             QScrollArea)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

from core.audio_manager import AudioManager
from core.stt_engine import STTEngine
from core.context_engine import ContextEngine

from ui.model_loader import ModelLoaderPanel
from ui.audio_input_panel import AudioInputPanel
from ui.audio_queue import AudioQueuePanel
from ui.audio_player import AudioPlayerWidget
from ui.expected_text_panel import ExpectedTextPanel
from ui.context_config_panel import ContextConfigPanel
from ui.context_result_panel import ContextResultPanel
from ui.comparison_summary import ComparisonSummaryPanel

from utils.metrics import calculate_wer, calculate_rtf, calculate_normalized_match, is_exact_match

class InferenceWorker(QThread):
    progress = pyqtSignal(str)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, sample, expected_text, stt_engine, context_engine, config, parent=None):
        super().__init__(parent)
        self.sample = sample
        self.expected_text = expected_text
        self.stt_engine = stt_engine
        self.context_engine = context_engine
        self.config = config

    def run(self):
        try:
            results = {}
            
            # --- 1. PIPELINE A: PURE STT ---
            self.progress.emit("Running Pipeline A: Pure STT...")
            t0 = time.time()
            raw_text, inf_time_a = self.stt_engine.transcribe(self.sample.samples)
            t1 = time.time()
            
            wer_a, _, _ = calculate_wer(self.expected_text, raw_text)
            results["pure_data"] = {
                "raw_transcript": raw_text,
                "stt_time": inf_time_a,
                "rtf": calculate_rtf(self.sample.duration, inf_time_a),
                "wer": wer_a,
                "exact": is_exact_match(self.expected_text, raw_text),
                "norm": calculate_normalized_match(self.expected_text, raw_text)
            }
            
            # --- 2. PIPELINE B: CONTEXTUAL BIASING ---
            if self.config.get("run_bias"):
                self.progress.emit("Running Pipeline B: Contextual Biasing...")
                hw_str = ""
                if self.config.get("use_global"):
                    hw_str += self.context_engine.get_global_hotwords_string() + "\n"
                if self.config.get("use_scenario"):
                    scen_mode = self.config.get("scenario_mode")
                    if scen_mode == "auto":
                        # Auto mode: we might just dump all scenario hotwords for biasing, but let's just do it
                        for s in self.context_engine.config:
                            hw_str += self.context_engine.get_scenario_hotwords_string(s.get("scenario_id")) + "\n"
                    else:
                        hw_str += self.context_engine.get_scenario_hotwords_string(scen_mode) + "\n"
                        
                t_b0 = time.time()
                bias_text, inf_time_b = self.stt_engine.transcribe(self.sample.samples, hotwords=hw_str, hotwords_score=1.5)
                t_b1 = time.time()
                
                wer_b, _, _ = calculate_wer(self.expected_text, bias_text)
                results["bias_data"] = {
                    "raw_transcript": bias_text,
                    "stt_time": inf_time_b,
                    "rtf": calculate_rtf(self.sample.duration, inf_time_b),
                    "wer": wer_b,
                    "exact": is_exact_match(self.expected_text, bias_text),
                    "norm": calculate_normalized_match(self.expected_text, bias_text)
                }
            
            # --- 3. PIPELINE C: POST-PROCESSING ---
            if self.config.get("run_post"):
                self.progress.emit("Running Pipeline C: Post-processing NLP...")
                t_c0 = time.time()
                scen_mode = self.config.get("scenario_mode")
                predefined = scen_mode if scen_mode != "auto" else None
                # Always process based on RAW TEXT (Pipeline A)
                ctx_res = self.context_engine.process(raw_text, predefined_scenario=predefined)
                t_c1 = time.time()
                
                wer_c, _, _ = calculate_wer(self.expected_text, ctx_res.final_semantic_result)
                results["post_data"] = {
                    "raw_transcript": raw_text,
                    "final_output": ctx_res.final_semantic_result,
                    "ctx_result": ctx_res,
                    "ctx_time": t_c1 - t_c0,
                    "wer": wer_c,
                    "exact": is_exact_match(self.expected_text, ctx_res.final_semantic_result),
                    "norm": calculate_normalized_match(self.expected_text, ctx_res.final_semantic_result)
                }
            
            self.completed.emit(results)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("STT Dashboard - Clean Architecture (Phase 2)")
        self.resize(1400, 900)
        
        self.audio_manager = AudioManager.get_instance()
        self.stt_engine = STTEngine() # Loaded via UI
        
        root = Path(__file__).resolve().parents[1]
        config_path = root / "data" / "scenarios_v2.json"
        self.context_engine = ContextEngine(str(config_path))
        
        self.worker = None
        self.init_ui()
        
    def init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        self.tabs = QTabWidget()
        
        # --- TAB 1: SINGLE INFERENCE (6 STEPS) ---
        single_tab = QWidget()
        single_layout = QVBoxLayout(single_tab)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        # STEP 1: MODEL LOADER
        self.model_loader = ModelLoaderPanel(self.stt_engine)
        self.model_loader.model_loaded.connect(self.on_model_loaded)
        scroll_layout.addWidget(self.model_loader)
        
        # STEP 2: AUDIO SOURCE
        step2_group = QGroupBox("STEP 2: AUDIO SOURCE")
        step2_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        step2_layout = QHBoxLayout()
        
        self.audio_input = AudioInputPanel()
        self.audio_input.audio_added.connect(self.on_audio_added)
        step2_layout.addWidget(self.audio_input, stretch=2)
        
        self.audio_queue = AudioQueuePanel()
        self.audio_queue.audio_selected.connect(self.on_audio_selected)
        step2_layout.addWidget(self.audio_queue, stretch=1)
        
        step2_group.setLayout(step2_layout)
        scroll_layout.addWidget(step2_group)
        
        # Player is part of Step 2
        self.audio_player = AudioPlayerWidget()
        scroll_layout.addWidget(self.audio_player)
        
        # STEP 3: EXPECTED TEXT
        self.expected_text_panel = ExpectedTextPanel()
        scroll_layout.addWidget(self.expected_text_panel)
        
        # STEP 4: CONTEXT CONFIG
        self.context_config = ContextConfigPanel(self.context_engine)
        scroll_layout.addWidget(self.context_config)
        
        # STEP 5: RUN COMPARISON
        self.run_btn = QPushButton("🚀 RUN COMPARISON (3 PIPELINES)")
        self.run_btn.setStyleSheet("font-size: 18px; font-weight: bold; background-color: #2563eb; color: white; padding: 15px;")
        self.run_btn.setEnabled(False) # Wait for model
        self.run_btn.clicked.connect(self.run_comparison)
        scroll_layout.addWidget(self.run_btn)
        
        # STEP 6: RESULTS
        self.context_result = ContextResultPanel()
        scroll_layout.addWidget(self.context_result)
        
        self.summary_table = ComparisonSummaryPanel()
        scroll_layout.addWidget(self.summary_table)
        
        scroll.setWidget(scroll_content)
        single_layout.addWidget(scroll)
        self.tabs.addTab(single_tab, "Single Inference Workflow")
        
        # --- TAB 2: BATCH EVALUATION ---
        from ui.batch_evaluation import BatchEvaluationPanel
        # We can implement a dummy func for global hotwords as it's not used in Phase 2 requirement directly
        self.batch_panel = BatchEvaluationPanel(self.stt_engine, self.context_engine, lambda: "")
        self.tabs.addTab(self.batch_panel, "Batch Evaluation")
        
        main_layout.addWidget(self.tabs)
        self.setCentralWidget(central_widget)
        
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready.")
        
    def on_model_loaded(self, success):
        self.run_btn.setEnabled(success)
        
    def on_audio_added(self, sample):
        self.audio_queue.refresh_list()
        self.audio_player.update_ui()
        if sample.text:
            self.expected_text_panel.set_text(sample.text)
        
    def on_audio_selected(self, sample):
        self.audio_player.update_ui()
        if sample and sample.text:
            self.expected_text_panel.set_text(sample.text)
            
    def run_comparison(self):
        sample = self.audio_manager.get_current_sample()
        if not sample:
            QMessageBox.warning(self, "Warning", "Please select an audio sample first.")
            return
            
        expected = self.expected_text_panel.get_text()
        if not expected:
            QMessageBox.warning(self, "Warning", "Please enter Expected Text for comparison.")
            return
            
        self.run_btn.setEnabled(False)
        self.context_result.clear()
        
        config = self.context_config.get_config()
        
        self.worker = InferenceWorker(sample, expected, self.stt_engine, self.context_engine, config)
        self.worker.progress.connect(self.statusBar().showMessage)
        self.worker.completed.connect(self.on_inference_completed)
        self.worker.failed.connect(self.on_inference_failed)
        self.worker.start()
        
    def on_inference_completed(self, results):
        self.run_btn.setEnabled(True)
        self.statusBar().showMessage("Processing complete.")
        
        pure_data = results.get("pure_data")
        bias_data = results.get("bias_data")
        post_data = results.get("post_data")
        
        expected = self.expected_text_panel.get_text()
        
        from utils.text_diff import highlight_diff_html
        diff_a = highlight_diff_html(expected, pure_data.get("raw_transcript", ""))
        diff_b = highlight_diff_html(expected, bias_data.get("raw_transcript", "")) if bias_data else ""
        diff_c = highlight_diff_html(expected, post_data.get("final_output", "")) if post_data else ""
        
        self.context_result.update_context(pure_data, bias_data, post_data, diff_a, diff_b, diff_c)
        self.summary_table.update_results(pure_data, bias_data, post_data)
        
    def on_inference_failed(self, err):
        self.run_btn.setEnabled(True)
        QMessageBox.critical(self, "Inference Error", err)
        self.statusBar().showMessage(f"Failed: {err}")
