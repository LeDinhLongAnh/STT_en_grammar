# -*- coding: utf-8 -*-
"""Batch Runner for evaluating multiple sentences asynchronously."""

import time
import uuid
import numpy as np
from typing import List, Dict, Any, Optional
from PyQt5.QtCore import QThread, pyqtSignal

from core.audio_manager import AudioSample
from core.tts_engine import TTSEngine
from core.stt_engine import STTEngine
from core.context_engine import ContextEngine
from utils.metrics import calculate_wer, calculate_rtf

class BatchRunnerWorker(QThread):
    progress_update = pyqtSignal(int, int, str)  # current, total, status_text
    result_emitted = pyqtSignal(dict) # result dict for one sample
    completed = pyqtSignal(str) # summary report path
    failed = pyqtSignal(str)

    def __init__(self, dataset_config: List[Dict[str, Any]], 
                 tts_voices: List[str], 
                 speeds: List[float],
                 stt_engine: STTEngine,
                 context_engine: ContextEngine,
                 global_hotwords: str,
                 parent=None):
        super().__init__(parent)
        self.dataset_config = dataset_config
        self.tts_voices = tts_voices
        self.speeds = speeds
        self.stt_engine = stt_engine
        self.context_engine = context_engine
        self.global_hotwords = global_hotwords
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            tts_engine = TTSEngine.get_instance()
            
            # 1. Flatten dataset into test cases
            test_cases = []
            for scenario in self.dataset_config:
                scen_id = scenario.get("scenario_id")
                for intent in scenario.get("intents", []):
                    int_id = intent.get("intent")
                    for example in intent.get("examples", []):
                        for voice in self.tts_voices:
                            for speed in self.speeds:
                                test_cases.append({
                                    "text": example,
                                    "voice": voice,
                                    "speed": speed,
                                    "ground_truth_scenario": scen_id,
                                    "ground_truth_intent": int_id
                                })
            
            total_cases = len(test_cases)
            if total_cases == 0:
                self.completed.emit("No test cases found in configuration.")
                return

            all_results = []

            for i, case in enumerate(test_cases):
                if self._is_cancelled:
                    self.failed.emit("Batch test cancelled by user.")
                    return
                    
                text = case["text"]
                voice = case["voice"]
                speed = case["speed"]
                
                self.progress_update.emit(i+1, total_cases, f"Synthesizing ({voice}, {speed}x): {text[:30]}...")
                
                # 1. TTS
                samples, duration = tts_engine.synthesize(text, voice, speed)
                
                self.progress_update.emit(i+1, total_cases, f"Transcribing...")
                
                # 2. Pipeline A: Pure STT
                raw_text, inf_time = self.stt_engine.transcribe(samples)
                rtf = calculate_rtf(duration, inf_time)
                wer_a, _, _ = calculate_wer(text, raw_text)
                
                # 3. Pipeline B: Context STT
                ctx_final = self.context_engine.process(raw_text)
                wer_b, _, _ = calculate_wer(text, ctx_final.final_semantic_result)
                
                # Collect Result
                res_dict = {
                    "id": i + 1,
                    "text": text,
                    "voice": voice,
                    "speed": speed,
                    "gt_scenario": case["ground_truth_scenario"],
                    "gt_intent": case["ground_truth_intent"],
                    "pure_raw": raw_text,
                    "pure_wer": wer_a,
                    "inf_time": inf_time,
                    "rtf": rtf,
                    "ctx_scenario": ctx_final.detected_scenario,
                    "ctx_scenario_conf": ctx_final.scenario_confidence,
                    "ctx_intent": ctx_final.detected_intent,
                    "ctx_intent_conf": ctx_final.intent_confidence,
                    "ctx_semantic": ctx_final.final_semantic_result,
                    "ctx_wer": wer_b,
                    "correction": ctx_final.correction_type
                }
                
                all_results.append(res_dict)
                self.result_emitted.emit(res_dict)
                
            # Generate Markdown report
            report_path = self._generate_markdown_report(all_results)
            self.completed.emit(report_path)

        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.failed.emit(str(exc))

    def _generate_markdown_report(self, results: List[Dict]) -> str:
        """Generate a markdown report of the batch run."""
        from pathlib import Path
        import os
        
        root = Path(self.stt_engine.model_dir).parents[1]
        report_dir = root / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        
        report_path = report_dir / f"batch_report_{int(time.time())}.md"
        
        lines = [
            "# Batch Evaluation Report",
            "",
            "## Summary",
            f"- **Total Samples:** {len(results)}",
            f"- **Avg RTF:** {np.mean([r['rtf'] for r in results]):.3f}",
            f"- **Avg Pure WER:** {np.mean([r['pure_wer'] for r in results])*100:.1f}%",
            f"- **Avg Context Semantic WER:** {np.mean([r['ctx_wer'] for r in results])*100:.1f}%",
            "",
            "## Detailed Results",
            "| ID | Text | Pure STT | Context STT | Scenario | Correction |",
            "|---|---|---|---|---|---|"
        ]
        
        for r in results:
            lines.append(f"| {r['id']} | {r['text']} | {r['pure_raw']} | {r['ctx_semantic']} | {r['ctx_scenario']} | {r['correction']} |")
            
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            
        return str(report_path)
