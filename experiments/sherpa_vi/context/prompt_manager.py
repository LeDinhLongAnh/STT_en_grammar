import os
import tempfile
from typing import List

class PromptManager:
    """
    Quản lý việc tạo file hotwords tạm thời cho Sherpa-ONNX.
    Sherpa-ONNX hỗ trợ contextual biasing thông qua tham số hotwords_file.
    """
    
    def __init__(self, score: float = 1.5):
        self.default_score = score
        self._temp_files = []

    def generate_hotwords_file(self, context_list: List[str]) -> str:
        """
        Nhận vào danh sách các ngữ cảnh (chuỗi dài có thể phân cách bởi xuống dòng),
        tách ra thành từng từ/cụm từ và ghi vào file tạm cho Sherpa-ONNX.
        Trả về đường dẫn tuyệt đối tới file vừa tạo.
        Nếu context rỗng, trả về string rỗng (báo cho mô hình biết không dùng hotwords).
        """
        import re, tempfile
        
        hotwords = []
        seen = set()
        for ctx in context_list:
            # Tách theo xuống dòng (chính) hoặc dấu phẩy (fallback)
            parts = re.split(r'[\n,]', ctx)
            for p in parts:
                p = p.strip()
                p = p.rstrip('.;:?!')
                # → Uppercase vì model viết HOA (bộ BPE vocab của model dùng chữ HOA)
                p = p.upper()
                if p and p not in seen:
                    seen.add(p)
                    hotwords.append(p)
                    
        if not hotwords:
            return ""
            
        # Ghi ra file tạm - dùng mode 'w' với encoding='utf-8' để đảm bảo tiếng Việt không bị lỗi
        import os
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="sherpa_hotwords_")
        os.close(fd)  # Đóng file descriptor gốc
        with open(path, 'w', encoding='utf-8') as f:
            for hw in hotwords:
                f.write(f"{hw} {self.default_score}\n")
                
        self._temp_files.append(path)
        return path
        
    def cleanup(self):
        """Xóa các file tạm sau khi benchmark xong"""
        for path in self._temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        self._temp_files.clear()
