import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import json
import re
from pathlib import Path
import sys

# Thêm thư mục mẹ vào sys.path để import whisper và tts_helpers nếu cần
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_EXP_ROOT = _ROOT / "experiments" / "whisper_initial_prompt"
if str(_EXP_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXP_ROOT))

try:
    import whisper
    import logit_bias
except ImportError as e:
    messagebox.showerror("Import Error", f"Lỗi import: {e}. Vui lòng chạy script này trong môi trường ảo (.venv) có chứa whisper.")
    sys.exit(1)


class LogitBiasTunerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Logit Bias Auto-Tuner")
        self.geometry("900x600")
        self.report_path = _EXP_ROOT / "TEST_REPORT.md"
        self.logit_bias_path = _EXP_ROOT / "logit_bias.json"
        
        self.tokenizer = whisper.tokenizer.get_tokenizer(multilingual=False, language="en", task="transcribe")
        self.missing_words = {} # dict mapping word -> count
        
        self.create_widgets()
        
    def create_widgets(self):
        # Header
        header_frame = tk.Frame(self, padx=10, pady=10)
        header_frame.pack(fill=tk.X)
        
        tk.Label(header_frame, text="Logit Bias Auto-Tuner", font=("Arial", 16, "bold")).pack(side=tk.LEFT)
        
        # File selection
        file_frame = tk.Frame(self, padx=10, pady=5)
        file_frame.pack(fill=tk.X)
        
        self.lbl_file = tk.Label(file_frame, text=f"Báo cáo: {self.report_path.name}", width=50, anchor="w")
        self.lbl_file.pack(side=tk.LEFT)
        
        tk.Button(file_frame, text="Chọn Báo Cáo Khác", command=self.select_report).pack(side=tk.LEFT, padx=5)
        tk.Button(file_frame, text="Phân Tích Báo Cáo", command=self.analyze_report, bg="#0ea5e9", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=10)
        
        # Select All / Deselect All
        sel_frame = tk.Frame(self, padx=10)
        sel_frame.pack(fill=tk.X)
        tk.Label(sel_frame, text="* Mẹo: Giữ Ctrl hoặc Shift để chọn nhiều dòng bằng chuột.", fg="#64748b").pack(side=tk.LEFT)
        tk.Button(sel_frame, text="Chọn tất cả", command=self.select_all).pack(side=tk.RIGHT, padx=5)
        tk.Button(sel_frame, text="Bỏ chọn tất cả", command=self.deselect_all).pack(side=tk.RIGHT)
        
        # Treeview cho danh sách từ
        tree_frame = tk.Frame(self, padx=10, pady=10)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ("word", "count", "tokens", "current_bias", "suggested_bias")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("word", text="Từ Bị Thiếu (Reference)")
        self.tree.heading("count", text="Số Lần Sai")
        self.tree.heading("tokens", text="Token IDs")
        self.tree.heading("current_bias", text="Bias Hiện Tại")
        self.tree.heading("suggested_bias", text="Đề Xuất Bias")
        
        self.tree.column("word", width=200)
        self.tree.column("count", width=80, anchor=tk.CENTER)
        self.tree.column("tokens", width=130)
        self.tree.column("current_bias", width=100, anchor=tk.CENTER)
        self.tree.column("suggested_bias", width=100, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Footer
        footer_frame = tk.Frame(self, padx=10, pady=10)
        footer_frame.pack(fill=tk.X)
        
        tk.Label(footer_frame, text="* Smart Bias: Phân tích chéo 3 chế độ (Baseline, Prompt, Bias) để đề xuất +/ - điểm. Tối đa +4.0").pack(side=tk.LEFT)
        tk.Button(footer_frame, text="Approve & Save (Lưu vào logit_bias.json)", command=self.approve_and_save, bg="#10b981", fg="white", font=("Arial", 12, "bold"), padx=10).pack(side=tk.RIGHT)

    def select_all(self):
        for item in self.tree.get_children():
            self.tree.selection_add(item)
            
    def deselect_all(self):
        for item in self.tree.get_children():
            self.tree.selection_remove(item)

    def select_report(self):
        path = filedialog.askopenfilename(initialdir=_EXP_ROOT, title="Chọn file TEST_REPORT.md", filetypes=(("Markdown files", "*.md"), ("All files", "*.*")))
        if path:
            self.report_path = Path(path)
            self.lbl_file.config(text=f"Báo cáo: {self.report_path.name}")

    def clean_word(self, word):
        # Xóa dấu câu, giữ lại chữ, số và dấu gạch ngang
        cleaned = re.sub(r'[^a-zA-Z0-9\-]', '', word)
        return cleaned

    def analyze_report(self):
        if not self.report_path.is_file():
            messagebox.showerror("Lỗi", f"Không tìm thấy file: {self.report_path}")
            return
            
        try:
            content = self.report_path.read_text(encoding="utf-8")
        except Exception as e:
            messagebox.showerror("Lỗi đọc file", str(e))
            return
            
        # Tìm bảng kết quả
        lines = content.split('\n')
        in_table = False
        
        self.missing_words.clear()
        # Xóa dữ liệu cũ
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Tự động parse Markdown table (Rất basic, dựa vào format của file TEST_REPORT.md)
        # Các cột: 0: Thời gian, 1: Nguồn, 2: Câu chuẩn, 3: Không prompt, 4: Global, 5: Global + Bias, 6: Đánh giá
        for line in lines:
            line = line.strip()
            if line.startswith('| Thời gian | Nguồn'):
                in_table = True
                continue
            if line.startswith('|---'):
                continue
                
            if in_table and line.startswith('|'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 8: # | col1 | col2 | ... |
                    ref_raw = parts[3]
                    none_raw = parts[4]
                    glob_raw = parts[5]
                    bias_raw = parts[6]
                    verdict_raw = parts[7]
                    
                    def clean_hyp(text):
                        clean = re.sub(r'\*\([0-9.]+%\)\*', '', text).strip()
                        if clean == '—': return []
                        return [self.clean_word(w).lower() for w in clean.split() if w]
                        
                    hyp_none = clean_hyp(none_raw)
                    hyp_glob = clean_hyp(glob_raw)
                    hyp_bias = clean_hyp(bias_raw)
                    
                    ref_words = [self.clean_word(w) for w in ref_raw.split() if w]
                    
                    for ref_word in ref_words:
                        rw_lower = ref_word.lower()
                        in_none = rw_lower in hyp_none
                        in_glob = rw_lower in hyp_glob
                        in_bias = rw_lower in hyp_bias
                        
                        if not in_bias:
                            if ref_word not in self.missing_words:
                                self.missing_words[ref_word] = {"count": 0, "boost": 0.0}
                                
                            self.missing_words[ref_word]["count"] += 1
                            
                            # Thuật toán đối chiếu 3 ô
                            if not in_none and not in_glob:
                                # Rất khó, 3 chế độ đều trượt -> Tăng mạnh
                                self.missing_words[ref_word]["boost"] += 1.0
                            elif in_glob:
                                # Global Prompt đúng, nhưng Bias sai -> Ảo giác do xung đột -> Phạt
                                self.missing_words[ref_word]["boost"] -= 0.5
                            elif in_none:
                                # Không Prompt đúng, nhưng Bias sai -> Phạt
                                self.missing_words[ref_word]["boost"] -= 0.5
                            else:
                                self.missing_words[ref_word]["boost"] += 0.5
        
        # Load cấu hình hiện tại để cộng dồn
        existing_bias = {}
        if self.logit_bias_path.is_file():
            try:
                cfg = json.loads(self.logit_bias_path.read_text(encoding="utf-8"))
                for term in cfg.get("global", {}).keys():
                    existing_bias[term.lower()] = float(cfg["global"][term].get("bias", 0.0))
            except:
                pass
                
        # Thêm vào treeview
        sorted_missing = sorted(self.missing_words.items(), key=lambda x: x[1]["count"], reverse=True)
        count_added = 0
        for word, data in sorted_missing:
            word_lower = word.lower()
            count = data["count"]
            avg_boost = data["boost"] / count if count > 0 else 0.0
            
            current_b = 0.0
            if word_lower in existing_bias:
                current_b = existing_bias[word_lower]
                suggested = current_b + avg_boost
            else:
                suggested = 2.0 + avg_boost
                
            # Giới hạn bias [0.0, 4.0] và làm tròn 1 chữ số
            suggested = max(0.0, min(suggested, 4.0))
            suggested = round(suggested, 1)
            
            tokens = logit_bias.tokenize_term(self.tokenizer, word)
            token_str = str(tokens)
            
            self.tree.insert("", tk.END, values=(word, count, token_str, current_b, suggested))
            count_added += 1
            
        if count_added == 0:
            messagebox.showinfo("Hoàn tất", "Không tìm thấy từ mới nào bị thiếu.")
        else:
            messagebox.showinfo("Hoàn tất", f"Đã phân tích xong! Tìm thấy {count_added} từ bị thiếu tiềm năng.")

    def approve_and_save(self):
        items = self.tree.get_children()
        if not items:
            messagebox.showwarning("Cảnh báo", "Không có từ nào để lưu.")
            return
            
        # Đọc cấu hình cũ
        if self.logit_bias_path.is_file():
            try:
                cfg = json.loads(self.logit_bias_path.read_text(encoding="utf-8"))
            except Exception as e:
                messagebox.showerror("Lỗi đọc file json", str(e))
                return
        else:
            cfg = {"enabled": True, "global": {}, "scenario": {}, "phrase_aware": {}}
            
        if "global" not in cfg:
            cfg["global"] = {}
            
        # Chỉ lấy những dòng được user select. Nếu không select gì thì lưu tất cả (hoặc hiện cảnh báo)
        selected_items = self.tree.selection()
        if not selected_items:
            answer = messagebox.askyesno("Xác nhận", "Bạn chưa chọn từ nào (bôi xanh). Bạn có muốn LƯU TẤT CẢ các từ trong danh sách không?")
            if answer:
                selected_items = items
            else:
                return
                
        added_words = []
        for item in selected_items:
            values = self.tree.item(item, "values")
            word = values[0]
            tokens_str = values[2] # "[123, 456]"
            bias = float(values[4]) # suggested bias is now at index 4
            
            try:
                tokens = json.loads(tokens_str)
            except:
                tokens = logit_bias.tokenize_term(self.tokenizer, word)
                
            # Keep original exact casing if it already existed (though user might get a new casing if it's missing)
            # To be safe, we just use the word casing from the Reference (which is `word` here)
            # Find if there is an existing key with different casing and replace it
            for k in list(cfg["global"].keys()):
                if k.lower() == word.lower():
                    word = k
                    break
                    
            cfg["global"][word] = {
                "bias": bias,
                "tokens": tokens,
                "_note": "auto-updated from tuner"
            }
            added_words.append(word)
            
        # Ghi lại file
        try:
            with open(self.logit_bias_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Thành công", f"Đã lưu {len(added_words)} từ vào logit_bias.json thành công!\nCác từ: {', '.join(added_words)}")
            
            # Xóa các dòng đã lưu khỏi UI
            for item in selected_items:
                self.tree.delete(item)
                
        except Exception as e:
            messagebox.showerror("Lỗi ghi file", str(e))

if __name__ == "__main__":
    app = LogitBiasTunerApp()
    app.mainloop()
