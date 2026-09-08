# -*- coding: utf-8 -*-
"""Audio Queue Panel for managing loaded audio samples."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                             QPushButton, QListWidget, QListWidgetItem)
from PyQt5.QtCore import Qt, pyqtSignal

from core.audio_manager import AudioManager

class AudioQueuePanel(QWidget):
    # Emitted when an audio is double-clicked or "Set Current" is clicked
    audio_selected = pyqtSignal(object) 
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_manager = AudioManager.get_instance()
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        group = QGroupBox("AUDIO QUEUE")
        vbox = QVBoxLayout()
        
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        vbox.addWidget(self.list_widget)
        
        hbox = QHBoxLayout()
        self.btn_set = QPushButton("Set Current")
        self.btn_set.clicked.connect(self._set_current)
        
        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.clicked.connect(self._clear_queue)
        
        hbox.addWidget(self.btn_set)
        hbox.addWidget(self.btn_clear)
        vbox.addLayout(hbox)
        
        group.setLayout(vbox)
        layout.addWidget(group)
        self.setLayout(layout)
        
    def refresh_list(self):
        self.list_widget.clear()
        for i, sample in enumerate(self.audio_manager.samples):
            # Format: 001 | MIC | filename | duration
            source = sample.source.upper()
            if sample.voice:
                source += f" ({sample.voice})"
            name = sample.path.split("\\")[-1].split("/")[-1] if sample.path else "In-Memory"
            text = f"[{i+1:03d}] {source} | {name} | {sample.duration:.1f}s"
            
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, i)
            self.list_widget.addItem(item)
            
            if i == self.audio_manager.current_index:
                item.setBackground(Qt.yellow)
                
    def _on_item_double_clicked(self, item):
        idx = item.data(Qt.UserRole)
        self.audio_manager.set_current_index(idx)
        self.refresh_list()
        sample = self.audio_manager.get_current_sample()
        self.audio_selected.emit(sample)
        
    def _set_current(self):
        curr_item = self.list_widget.currentItem()
        if curr_item:
            self._on_item_double_clicked(curr_item)
            
    def _clear_queue(self):
        self.audio_manager.clear()
        self.refresh_list()
        self.audio_selected.emit(None)
