# -*- coding: utf-8 -*-
"""Entry point for STT Clean Architecture Dashboard."""

import sys
import os
import torch
from pathlib import Path
from PyQt5.QtWidgets import QApplication

# Add project root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    
    # Set global style
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
