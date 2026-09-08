import os
import json
import wave
import io
import pyaudio
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QComboBox, QFileDialog, QGroupBox, QTableWidget, 
    QTableWidgetItem, QHeaderView, QMessageBox, QProgressBar, QTextEdit,
    QRadioButton, QButtonGroup, QDialog, QFormLayout, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont

from models.sherpa_zipformer_vi import SherpaZipformerVI
from benchmark.runner import BenchmarkRunner
from benchmark.dataset_manager import DatasetManager
from audio.recorder import MicrophoneRecorder
from audio.analyzer import AudioAnalyzer

class ResultColumn(QGroupBox):
    def __init__(self, title):
        super().__init__(title)
        layout = QVBoxLayout()
        
        self.transcript_box = QTextEdit()
        self.transcript_box.setReadOnly(True)
        self.transcript_box.setMinimumHeight(80)
        
        self.metrics_label = QLabel("Acc: -- | WER: -- | CER: --\nIntent: -- | Entity: --\nRTF: -- | Infer: -- ms")
        self.metrics_label.setStyleSheet("font-weight: bold;")
        
        self.context_effect_label = QLabel("")
        self.context_effect_label.setStyleSheet("color: blue; font-weight: bold;")
        
        layout.addWidget(QLabel("Transcript:"))
        layout.addWidget(self.transcript_box)
        layout.addWidget(self.metrics_label)
        layout.addWidget(self.context_effect_label)
        
        self.setLayout(layout)
        
    def clear(self):
        self.transcript_box.clear()
        self.metrics_label.setText("Acc: -- | WER: -- | CER: --\nIntent: -- | Entity: --\nRTF: -- | Infer: -- ms")
        self.context_effect_label.setText("")
        self.setStyleSheet("")

    def set_result(self, res_dict):
        self.transcript_box.setText(res_dict.get("transcript", ""))
        
        wer = res_dict.get("wer", 0)
        cer = res_dict.get("cer", 0)
        acc = max(0.0, 1.0 - wer)
        rtf = res_dict.get("rtf", 0)
        infer_ms = res_dict.get("inference_time", 0) * 1000
        
        intent_pass = res_dict.get("intent_eval", {}).get("pass", False)
        entity_pass = res_dict.get("entity_eval", {}).get("pass", False)
        
        metrics_text = (
            f"Acc: {acc:.2%} | WER: {wer:.2%} | CER: {cer:.2%}\n"
            f"Intent: {'✅' if intent_pass else '❌'} | Entity: {'✅' if entity_pass else '❌'}\n"
            f"RTF: {rtf:.3f} | Infer: {infer_ms:.1f} ms"
        )
        
        predicted = res_dict.get("predicted_scenario")
        if predicted:
            metrics_text += f"\nPredicted: {predicted}"
            
        self.metrics_label.setText(metrics_text)
        
        effect = res_dict.get("context_effect", "")
        if effect:
            self.context_effect_label.setText(f"Effect: {effect}")
            if "HARM" in effect or "DEGRADED" in effect:
                self.setStyleSheet("QGroupBox { border: 2px solid red; }")
            elif "IMPROVED" in effect:
                self.setStyleSheet("QGroupBox { border: 2px solid green; }")
            else:
                self.setStyleSheet("")

class MetadataDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Test Case")
        self.layout = QFormLayout(self)
        
        self.env_input = QComboBox()
        self.env_input.addItems(["Quiet", "Office", "Living Room", "Traffic", "Other"])
        self.dist_input = QComboBox()
        self.dist_input.addItems(["20 cm", "50 cm", "1 m", "2 m"])
        self.notes_input = QLineEdit()
        
        self.layout.addRow("Environment:", self.env_input)
        self.layout.addRow("Distance:", self.dist_input)
        self.layout.addRow("Notes:", self.notes_input)
        
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        self.layout.addRow(btn_layout)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sherpa-ONNX Zipformer VI – Real-world Benchmark")
        self.resize(1200, 900)
        
        self.model = None
        self.test_cases = []
        self.audio_bytes = None
        
        self.dataset_manager = DatasetManager()
        self.recorder = MicrophoneRecorder()
        self.recorder.level_updated.connect(self.update_level_meter)
        
        # Audio Player
        self.pa = pyaudio.PyAudio()
        self.player_stream = None
        
        self.init_ui()
        self.load_test_cases()
        self.load_microphones()
        
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 1. Header & Model
        model_group = QGroupBox("1. Model Configuration")
        model_layout = QHBoxLayout()
        self.model_path_input = QComboBox()
        self.model_path_input.setEditable(True)
        default_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "models", "sherpa-onnx-zipformer-vi"))
        self.model_path_input.addItem(default_path)
        self.model_path_input.setMinimumWidth(300)
        
        btn_load = QPushButton("Load Model")
        btn_load.clicked.connect(self.load_model)
        
        self.lbl_model_status = QLabel("Status: Not loaded")
        self.lbl_model_status.setStyleSheet("color: red;")
        
        model_layout.addWidget(QLabel("Path:"))
        model_layout.addWidget(self.model_path_input)
        model_layout.addWidget(btn_load)
        model_layout.addWidget(self.lbl_model_status)
        model_layout.addStretch()
        model_group.setLayout(model_layout)
        main_layout.addWidget(model_group)
        
        # 2. Test Source
        source_group = QGroupBox("2. Test Source")
        source_layout = QHBoxLayout()
        self.radio_wav = QRadioButton("○ WAV File Dataset")
        self.radio_mic = QRadioButton("● Real-world Microphone")
        self.radio_wav.setChecked(True)
        
        self.source_group_btn = QButtonGroup()
        self.source_group_btn.addButton(self.radio_wav, 1)
        self.source_group_btn.addButton(self.radio_mic, 2)
        self.source_group_btn.buttonClicked.connect(self.toggle_source)
        
        source_layout.addWidget(self.radio_wav)
        source_layout.addWidget(self.radio_mic)
        source_layout.addStretch()
        source_group.setLayout(source_layout)
        main_layout.addWidget(source_group)
        
        # 3. Scenario & Audio
        scenario_group = QGroupBox("3. Input & Audio")
        scenario_layout = QVBoxLayout()
        
        row1 = QHBoxLayout()
        self.combo_scenario = QComboBox()
        self.combo_scenario.currentIndexChanged.connect(self.on_scenario_changed)
        row1.addWidget(QLabel("Scenario:"))
        row1.addWidget(self.combo_scenario, 1)
        self.txt_reference = QLineEdit()
        self.txt_reference.setPlaceholderText("Nhập câu chuẩn (reference) vào đây...")
        self.txt_reference.setFont(QFont("Arial", 11, QFont.Bold))
        
        row_ref = QHBoxLayout()
        row_ref.addWidget(QLabel("Reference:"))
        row_ref.addWidget(self.txt_reference, 1)
        scenario_layout.addLayout(row_ref)
        
        # WAV File UI
        self.wav_widget = QWidget()
        wav_layout = QHBoxLayout(self.wav_widget)
        btn_browse_audio = QPushButton("Choose WAV")
        btn_browse_audio.clicked.connect(self.browse_audio)
        self.lbl_audio = QLabel("No audio selected")
        wav_layout.addWidget(btn_browse_audio)
        wav_layout.addWidget(self.lbl_audio)
        wav_layout.addStretch()
        wav_layout.setContentsMargins(0, 0, 0, 0)
        scenario_layout.addWidget(self.wav_widget)
        
        # Microphone UI
        self.mic_widget = QWidget()
        mic_layout = QVBoxLayout(self.mic_widget)
        
        mic_row = QHBoxLayout()
        self.combo_mic = QComboBox()
        mic_row.addWidget(QLabel("Microphone:"))
        mic_row.addWidget(self.combo_mic, 1)
        mic_layout.addLayout(mic_row)
        
        # Level Meter
        self.meter_bar = QProgressBar()
        self.meter_bar.setRange(-60, 0) # dBFS range
        self.meter_bar.setValue(-60)
        self.meter_bar.setTextVisible(True)
        self.meter_bar.setFormat("Level: %v dBFS")
        mic_layout.addWidget(self.meter_bar)
        
        # Rec Controls
        rec_controls = QHBoxLayout()
        self.btn_rec = QPushButton("● Thu âm")
        self.btn_rec.setStyleSheet("color: red; font-weight: bold;")
        self.btn_rec.clicked.connect(self.start_record)
        
        self.btn_stop = QPushButton("■ Stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_record)
        
        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self.play_audio)
        
        self.lbl_rec_time = QLabel("00:00.00")
        
        rec_controls.addWidget(self.btn_rec)
        rec_controls.addWidget(self.btn_stop)
        rec_controls.addWidget(self.btn_play)
        rec_controls.addWidget(self.lbl_rec_time)
        rec_controls.addStretch()
        mic_layout.addLayout(rec_controls)
        
        self.lbl_quality = QLabel("Audio Quality: --")
        self.lbl_quality.setStyleSheet("font-weight: bold;")
        mic_layout.addWidget(self.lbl_quality)
        
        self.mic_widget.setVisible(False)
        self.mic_widget.setContentsMargins(0, 0, 0, 0)
        scenario_layout.addWidget(self.mic_widget)
        
        scenario_group.setLayout(scenario_layout)
        main_layout.addWidget(scenario_group)
        
        # 4. Controls
        control_layout = QHBoxLayout()
        self.btn_run_all = QPushButton("RUN 3-MODE BENCHMARK")
        self.btn_run_all.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 10px;")
        self.btn_run_all.clicked.connect(self.run_benchmark)
        self.btn_run_all.setEnabled(False)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        
        control_layout.addWidget(self.btn_run_all)
        control_layout.addWidget(self.progress_bar)
        main_layout.addLayout(control_layout)
        
        # 5. Results Columns
        results_layout = QHBoxLayout()
        self.col_baseline = ResultColumn("1. BASELINE / NO CONTEXT")
        self.col_global = ResultColumn("2. GLOBAL CONTEXT")
        self.col_scenario = ResultColumn("3. AUTO SCENARIO (2-PASS)")
        
        results_layout.addWidget(self.col_baseline)
        results_layout.addWidget(self.col_global)
        results_layout.addWidget(self.col_scenario)
        main_layout.addLayout(results_layout)
        
        # 6. Prompts Editor & Actions
        editor_group = QGroupBox("Prompts Editor (prompts.py) & Actions")
        editor_layout = QVBoxLayout()
        
        split_layout = QHBoxLayout()
        
        # Global Prompt
        global_layout = QVBoxLayout()
        global_layout.addWidget(QLabel("Global Prompt:"))
        self.global_editor = QTextEdit()
        self.global_editor.setMinimumHeight(150)
        self.global_editor.setFont(QFont("Consolas", 10))
        global_layout.addWidget(self.global_editor)
        split_layout.addLayout(global_layout)
        
        # Scenario Prompts
        scenario_layout = QVBoxLayout()
        scenario_layout.addWidget(QLabel("Scenario Prompts (Dạng tự do):"))
        self.scenario_editor = QTextEdit()
        self.scenario_editor.setMinimumHeight(150)
        self.scenario_editor.setFont(QFont("Consolas", 10))
        scenario_layout.addWidget(self.scenario_editor)
        split_layout.addLayout(scenario_layout)
        
        editor_layout.addLayout(split_layout)
        
        action_layout = QHBoxLayout()
        self.btn_save_prompts = QPushButton("Save Prompts")
        self.btn_save_prompts.setStyleSheet("background-color: #007bff; color: white; font-weight: bold;")
        self.btn_save_prompts.clicked.connect(self.save_prompts_file)
        
        self.btn_save_case = QPushButton("Save Test Case")
        self.btn_save_case.clicked.connect(self.save_test_case)
        self.btn_save_case.setEnabled(False)
        
        action_layout.addStretch()
        action_layout.addWidget(self.btn_save_prompts)
        action_layout.addWidget(self.btn_save_case)
        editor_layout.addLayout(action_layout)
        
        editor_group.setLayout(editor_layout)
        main_layout.addWidget(editor_group)
        
        self.load_prompts_file()
        
    def load_test_cases(self):
        cases_file = os.path.join(os.path.dirname(__file__), "..", "test_cases.json")
        if os.path.exists(cases_file):
            with open(cases_file, 'r', encoding='utf-8') as f:
                self.test_cases = json.load(f)
            self.combo_scenario.clear()
            for c in self.test_cases:
                self.combo_scenario.addItem(f"{c['scenario']} - {c['id']}", c)
                
    def load_microphones(self):
        try:
            mics = MicrophoneRecorder.get_devices()
            for idx, name in mics:
                self.combo_mic.addItem(name, idx)
        except Exception as e:
            self.combo_mic.addItem(f"Error: {str(e)}")

    def toggle_source(self):
        if self.radio_wav.isChecked():
            self.wav_widget.setVisible(True)
            self.mic_widget.setVisible(False)
        else:
            self.wav_widget.setVisible(False)
            self.mic_widget.setVisible(True)
        self.check_ready()
            
    def on_scenario_changed(self):
        case = self.combo_scenario.currentData()
        if case:
            self.txt_reference.setText(case.get("reference", ""))
            
    def load_model(self):
        path = self.model_path_input.currentText()
        try:
            self.lbl_model_status.setText("Loading...")
            self.model = SherpaZipformerVI(path)
            self.lbl_model_status.setText("✓ Model loaded successfully")
            self.lbl_model_status.setStyleSheet("color: green;")
            self.check_ready()
        except Exception as e:
            self.lbl_model_status.setText("Load failed!")
            self.lbl_model_status.setStyleSheet("color: red;")
            QMessageBox.critical(self, "Error", str(e))
            self.model = None
            self.check_ready()
            
    def browse_audio(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Audio", "", "WAV Files (*.wav)")
        if file:
            with open(file, "rb") as f:
                self.audio_bytes = f.read()
            self.lbl_audio.setText(os.path.basename(file))
            self.check_ready()
            
    def start_record(self):
        idx = self.combo_mic.currentData()
        if idx is None:
            QMessageBox.warning(self, "Warning", "No microphone selected!")
            return
            
        self.btn_rec.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_play.setEnabled(False)
        self.btn_run_all.setEnabled(False)
        
        try:
            self.recorder.start_recording(device_id=idx)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot open microphone: {str(e)}")
            self.btn_rec.setEnabled(True)
            self.btn_stop.setEnabled(False)
            
    def stop_record(self):
        np_audio = self.recorder.stop_recording()
        self.btn_rec.setEnabled(True)
        self.btn_stop.setEnabled(False)
        
        if np_audio is not None and len(np_audio) > 0:
            self.audio_bytes = self.recorder.get_wav_bytes(np_audio)
            
            # Analyze
            quality_info = AudioAnalyzer.analyze(np_audio)
            if quality_info:
                qual_str = quality_info["quality"]
                color = "green" if "GOOD" in qual_str else "red"
                dur = quality_info["duration"]
                self.lbl_quality.setText(f"Audio Quality: {qual_str} | {dur:.2f}s")
                self.lbl_quality.setStyleSheet(f"font-weight: bold; color: {color};")
            
            # Save temporary
            case = self.combo_scenario.currentData()
            scenario_name = case.get("scenario", "unknown") if case else "unknown"
            self.dataset_manager.save_recording(self.audio_bytes, scenario_name)
            
            self.btn_play.setEnabled(True)
            self.check_ready()

    def play_audio(self):
        if not self.audio_bytes:
            return
            
        wf = wave.open(io.BytesIO(self.audio_bytes), 'rb')
        
        def callback(in_data, frame_count, time_info, status):
            data = wf.readframes(frame_count)
            return (data, pyaudio.paContinue)
            
        self.player_stream = self.pa.open(
            format=self.pa.get_format_from_width(wf.getsampwidth()),
            channels=wf.getnchannels(),
            rate=wf.getframerate(),
            output=True,
            stream_callback=callback
        )
        self.player_stream.start_stream()
        
    def update_level_meter(self, rms_db, peak_db, duration):
        val = int(max(-60, min(0, rms_db)))
        self.meter_bar.setValue(val)
        self.lbl_rec_time.setText(f"00:{duration:05.2f}")
            
    def check_ready(self):
        if self.model and self.audio_bytes and self.combo_scenario.currentData():
            self.btn_run_all.setEnabled(True)
        else:
            self.btn_run_all.setEnabled(False)
            
    def run_benchmark(self):
        case = self.combo_scenario.currentData()
        if not case or not self.audio_bytes or not self.model:
            return
            
        self.btn_run_all.setEnabled(False)
        self.progress_bar.setValue(0)
        self.col_baseline.clear()
        self.col_global.clear()
        self.col_scenario.clear()
        
        self.runner = BenchmarkRunner(self.model, self.audio_bytes, case, randomize=True)
        # Update the reference in case the user edited it
        self.runner.test_case["reference"] = self.txt_reference.text().strip()
        self.runner.progress.connect(self.update_progress)
        self.runner.result_ready.connect(self.on_benchmark_done)
        self.runner.error_occurred.connect(self.on_benchmark_error)
        self.runner.start()
        
    def update_progress(self, val, msg):
        self.progress_bar.setValue(val)
        self.progress_bar.setFormat(f"%p% - {msg}")
        
    def on_benchmark_done(self, results):
        self.btn_run_all.setEnabled(True)
        self.btn_save_case.setEnabled(True)
        self.progress_bar.setFormat("Done!")
        
        if "BASELINE" in results: self.col_baseline.set_result(results["BASELINE"])
        if "GLOBAL" in results: self.col_global.set_result(results["GLOBAL"])
        if "SCENARIO" in results: self.col_scenario.set_result(results["SCENARIO"])
            
    def load_prompts_file(self):
        try:
            import importlib
            import sys
            import json
            
            # Đảm bảo thư mục hiện tại có trong sys.path
            exp_dir = os.path.dirname(__file__)
            parent_dir = os.path.abspath(os.path.join(exp_dir, ".."))
            if parent_dir not in sys.path:
                sys.path.append(parent_dir)
                
            import prompts
            importlib.reload(prompts)
            
            self.global_editor.setText(prompts.GLOBAL_PROMPT)
            
            # Format as INI-like string
            scen_text = ""
            for k, v in prompts.SCENARIO_PROMPTS.items():
                scen_text += f"[{k}]\n{v}\n\n"
            self.scenario_editor.setText(scen_text.strip())
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Cannot load prompts:\\n{e}")
                
    def save_prompts_file(self):
        prompts_path = os.path.join(os.path.dirname(__file__), "..", "prompts.py")
        glob_text = self.global_editor.toPlainText().strip()
        scen_text = self.scenario_editor.toPlainText().strip()
        
        try:
            import json
            
            # Parse INI-like string back to dict
            scen_dict = {}
            current_key = None
            current_lines = []
            for line in scen_text.split('\n'):
                line = line.strip()
                if line.startswith('[') and line.endswith(']'):
                    if current_key:
                        scen_dict[current_key] = '\n'.join(current_lines).strip()
                    current_key = line[1:-1]
                    current_lines = []
                elif line and current_key:
                    current_lines.append(line)
            if current_key:
                scen_dict[current_key] = '\n'.join(current_lines).strip()
            
            template = '''# -*- coding: utf-8 -*-
"""
Các prompt dùng để ghép ngữ cảnh khi test model NLU router/Wi-Fi.
Sửa nội dung trực tiếp trong file này — script test_model.py sẽ import từ đây.
"""

SYSTEM_PROMPT = """Bạn là trợ lý điều khiển router / Wi-Fi gia đình.
Đọc câu hỏi tiếng Việt của người dùng, xác định intent và entity, CHỈ trả lời bằng đúng 1 dòng JSON, không thêm chữ nào khác:
{"intent": "...", "device": "...", "app": "...", "value": ""}
Nếu không có thông tin thì để chuỗi rỗng "". Không giải thích, không thêm câu chào."""

# Global Prompt: áp dụng cho MỌI câu hỏi, không phân biệt kịch bản.
GLOBAL_PROMPT = (
    """%s"""
)

# Scenario Prompt: chỉ nạp SAU KHI đã xác định đúng category
SCENARIO_PROMPTS = %s

def build_prompt(question: str, category_id: str | None) -> str:
    """Ghép System + Global + Scenario (nếu có category) + câu hỏi."""
    parts = [SYSTEM_PROMPT, "", "GLOBAL CONTEXT:", GLOBAL_PROMPT]
    if category_id and category_id in SCENARIO_PROMPTS:
        parts += ["", f"SCENARIO CONTEXT ({category_id}):", SCENARIO_PROMPTS[category_id]]
    parts += ["", f'USER: "{question}"']
    return "\\n".join(parts)

def build_prompt_no_context(question: str) -> str:
    """Chỉ System Prompt + câu hỏi — dùng để so sánh baseline không ngữ cảnh."""
    return f'{SYSTEM_PROMPT}\\n\\nUSER: "{question}"'
'''
            new_content = template % (glob_text, json.dumps(scen_dict, ensure_ascii=False, indent=4))
            with open(prompts_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            QMessageBox.information(self, "Success", "Saved prompts.py successfully!")
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Syntax Error", f"Scenario Prompts must be valid JSON.\\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save prompts.py:\\n{str(e)}")
            
    def on_benchmark_error(self, err):
        self.btn_run_all.setEnabled(True)
        self.progress_bar.setFormat("Error!")
        QMessageBox.critical(self, "Benchmark Error", err)
        
    def save_test_case(self):
        if not self.audio_bytes:
            return
            
        case = self.combo_scenario.currentData()
        
        dialog = MetadataDialog(self)
        if dialog.exec_():
            metadata = {
                "scenario": case.get("scenario"),
                "intent": case.get("intent"),
                "reference": self.txt_reference.text().strip(),
                "environment": dialog.env_input.currentText(),
                "distance": dialog.dist_input.currentText(),
                "notes": dialog.notes_input.text()
            }
            
            case_id = self.dataset_manager.save_test_case(self.audio_bytes, metadata)
            QMessageBox.information(self, "Success", f"Saved to real_world_dataset as {case_id}")
