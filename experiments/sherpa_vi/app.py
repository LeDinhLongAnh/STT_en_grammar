import sys
import os

# Đảm bảo đường dẫn experiments/sherpa_vi nằm trong sys.path để import dễ dàng
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow

def main():
    app = QApplication(sys.path)
    
    # Thiết lập style đơn giản
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
