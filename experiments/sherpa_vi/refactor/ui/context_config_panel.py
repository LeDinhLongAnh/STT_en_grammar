# -*- coding: utf-8 -*-
"""Context Configuration Panel for Phase 3."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QLabel, QCheckBox, QComboBox, QListWidget, QGridLayout, QFormLayout)
from PyQt5.QtCore import Qt

class ContextConfigPanel(QWidget):
    def __init__(self, context_engine, parent=None):
        super().__init__(parent)
        self.context_engine = context_engine
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        group = QGroupBox("STEP 4: CONTEXT CONFIGURATION")
        group.setStyleSheet("QGroupBox { font-weight: bold; }")
        
        main_vbox = QVBoxLayout()
        
        # --- PIPELINE CONFIG ---
        pipe_group = QGroupBox("Context Pipeline")
        pipe_layout = QVBoxLayout()
        
        self.chk_pure = QCheckBox("Pure STT (Baseline)")
        self.chk_pure.setChecked(True)
        self.chk_pure.setEnabled(False) # Always on
        
        self.chk_bias = QCheckBox("Contextual Biasing (Decoder-level)")
        self.chk_bias.setChecked(True)
        self.chk_bias.toggled.connect(self._update_ui)
        
        self.chk_post = QCheckBox("Context-aware Post-processing (NLP-level)")
        self.chk_post.setChecked(True)
        
        pipe_layout.addWidget(self.chk_pure)
        pipe_layout.addWidget(self.chk_bias)
        pipe_layout.addWidget(self.chk_post)
        pipe_group.setLayout(pipe_layout)
        main_vbox.addWidget(pipe_group)
        
        # --- HOTWORDS CONFIG ---
        hw_group = QGroupBox("Context Sources")
        hw_layout = QHBoxLayout()
        
        # Left: Global
        global_vbox = QVBoxLayout()
        self.chk_global = QCheckBox("Enable Global Context")
        self.chk_global.setChecked(True)
        self.chk_global.toggled.connect(self._update_lists)
        global_vbox.addWidget(self.chk_global)
        
        self.lbl_global_count = QLabel("Loaded: 0 words")
        global_vbox.addWidget(self.lbl_global_count)
        
        self.list_global = QListWidget()
        global_vbox.addWidget(self.list_global)
        hw_layout.addLayout(global_vbox)
        
        # Right: Scenario
        scenario_vbox = QVBoxLayout()
        
        scen_hbox = QHBoxLayout()
        self.chk_scenario = QCheckBox("Enable Scenario Context")
        self.chk_scenario.setChecked(True)
        self.chk_scenario.toggled.connect(self._update_lists)
        scen_hbox.addWidget(self.chk_scenario)
        
        self.cb_scenario = QComboBox()
        self.cb_scenario.addItem("Auto Detect", "auto")
        for scen in self.context_engine.config:
            self.cb_scenario.addItem(scen.get("name", scen.get("scenario_id")), scen.get("scenario_id"))
        self.cb_scenario.currentIndexChanged.connect(self._update_lists)
        scen_hbox.addWidget(self.cb_scenario)
        
        scenario_vbox.addLayout(scen_hbox)
        
        self.lbl_scenario_count = QLabel("Loaded: 0 words")
        scenario_vbox.addWidget(self.lbl_scenario_count)
        
        self.list_scenario = QListWidget()
        scenario_vbox.addWidget(self.list_scenario)
        hw_layout.addLayout(scenario_vbox)
        
        hw_group.setLayout(hw_layout)
        main_vbox.addWidget(hw_group)
        
        group.setLayout(main_vbox)
        layout.addWidget(group)
        self.setLayout(layout)
        
        self._update_lists()
        
    def _update_ui(self):
        # Enable/Disable Hotword selection based on Biasing checkbox?
        # Actually Biasing uses Hotwords, but Post-processing ALSO uses scenarios to match.
        pass

    def _update_lists(self):
        # Update Global
        self.list_global.clear()
        if self.chk_global.isChecked():
            words = self.context_engine.get_global_hotwords_list()
            self.list_global.addItems(words)
            self.lbl_global_count.setText(f"Loaded: {len(words)} words")
        else:
            self.lbl_global_count.setText("Loaded: 0 words")
            
        # Update Scenario
        self.list_scenario.clear()
        if self.chk_scenario.isChecked():
            scen_id = self.cb_scenario.currentData()
            if scen_id == "auto":
                self.lbl_scenario_count.setText("Auto-detect: All scenario hotwords available")
                # Add all
                words = set()
                for scen in self.context_engine.config:
                    words.update(self.context_engine.get_scenario_hotwords_list(scen.get("scenario_id")))
                self.list_scenario.addItems(list(words))
            else:
                words = self.context_engine.get_scenario_hotwords_list(scen_id)
                self.list_scenario.addItems(words)
                self.lbl_scenario_count.setText(f"Loaded: {len(words)} words")
        else:
            self.lbl_scenario_count.setText("Loaded: 0 words")

    def get_config(self) -> dict:
        return {
            "run_pure": self.chk_pure.isChecked(),
            "run_bias": self.chk_bias.isChecked(),
            "run_post": self.chk_post.isChecked(),
            "use_global": self.chk_global.isChecked(),
            "use_scenario": self.chk_scenario.isChecked(),
            "scenario_mode": self.cb_scenario.currentData()
        }
