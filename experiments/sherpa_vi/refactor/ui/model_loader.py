# -*- coding: utf-8 -*-
"""Model Loader UI Panel."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QLabel, QLineEdit, QPushButton, QFileDialog)
from PyQt5.QtCore import Qt, pyqtSignal
from pathlib import Path

class ModelLoaderPanel(QWidget):
    # Signal emitted when model is successfully loaded
    model_loaded = pyqtSignal(bool)
    
    def __init__(self, stt_engine, parent=None):
        super().__init__(parent)
        self.stt_engine = stt_engine
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        group = QGroupBox("STEP 1: MODEL LOADER")
        group.setStyleSheet("QGroupBox { font-weight: bold; }")
        vbox = QVBoxLayout()
        
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("STT Engine:"))
        hbox.addWidget(QLabel("<b>[ Sherpa-ONNX Zipformer ]</b>"))
        hbox.addStretch()
        
        self.status_lbl = QLabel("🔴 NOT LOADED")
        self.status_lbl.setStyleSheet("color: red; font-weight: bold;")
        hbox.addWidget(self.status_lbl)
        vbox.addLayout(hbox)
        
        hbox2 = QHBoxLayout()
        hbox2.addWidget(QLabel("Model Path:"))
        self.path_edit = QLineEdit()
        
        # Pre-fill if known
        root = Path(__file__).resolve().parents[4]
        default_model = root / "models" / "sherpa-onnx-zipformer-vi"
        if default_model.exists():
            self.path_edit.setText(str(default_model))
        else:
            # Fallback hardcoded path just in case
            self.path_edit.setText(r"d:\esp\STT_EN_Grammar\STT_EN_Grammar\models\sherpa-onnx-zipformer-vi")
            
        hbox2.addWidget(self.path_edit)
        
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self.browse_model)
        hbox2.addWidget(self.browse_btn)
        
        self.load_btn = QPushButton("Load Model")
        self.load_btn.setStyleSheet("background-color: #059669; color: white;")
        self.load_btn.clicked.connect(self.load_model)
        hbox2.addWidget(self.load_btn)
        
        vbox.addLayout(hbox2)
        group.setLayout(vbox)
        layout.addWidget(group)
        self.setLayout(layout)
        
        # Auto load if path exists
        if self.path_edit.text():
            self.load_model()
        
    def browse_model(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Sherpa-ONNX Model Directory")
        if dir_path:
            self.path_edit.setText(dir_path)
            
    def load_model(self):
        path = self.path_edit.text().strip()
        if not path:
            return
            
        self.load_btn.setEnabled(False)
        self.status_lbl.setText("⏳ LOADING...")
        self.status_lbl.setStyleSheet("color: orange; font-weight: bold;")
        
        try:
            self.stt_engine.load_model(path)
            self.status_lbl.setText("🟢 READY")
            self.status_lbl.setStyleSheet("color: green; font-weight: bold;")
            self.model_loaded.emit(True)
        except Exception as e:
            self.status_lbl.setText("🔴 ERROR")
            self.status_lbl.setStyleSheet("color: red; font-weight: bold;")
            self.model_loaded.emit(False)
            import traceback
            traceback.print_exc()
        finally:
            self.load_btn.setEnabled(True)
