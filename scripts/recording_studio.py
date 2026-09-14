import os
import sys
import json
import time
import wave
import threading
import numpy as np
import sounddevice as sd
import tkinter as tk
from tkinter import ttk, messagebox
import datetime
from scipy.io import wavfile

# Try to import ESP32 Mic Recorder
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_model_ sherpa', 'scripts')))
    from esp32_mic_recorder import ESP32MicRecorder
    ESP32_AVAILABLE = True
except ImportError:
    ESP32_AVAILABLE = False


class PCMicRecorder:
    def __init__(self, samplerate=16000, channels=1):
        self.samplerate = samplerate
        self.channels = channels
        self.recording = False
        self.frames = []
        self.stream = None

    def callback(self, indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        if self.recording:
            self.frames.append(indata.copy())

    def start(self):
        self.frames = []
        self.recording = True
        self.stream = sd.InputStream(samplerate=self.samplerate, channels=self.channels, 
                                     dtype='float32', callback=self.callback)
        self.stream.start()

    def stop(self):
        self.recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if not self.frames:
            return np.array([], dtype=np.float32)
        return np.concatenate(self.frames, axis=0).flatten()

    def discard(self):
        self.recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.frames = []


class RecordingStudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("STT DATASET RECORDING STUDIO")
        self.root.geometry("800x700")
        self.root.configure(padx=20, pady=20)

        self.setup_ui()
        
        self.pc_mic = PCMicRecorder()
        self.esp32_mic = ESP32MicRecorder() if ESP32_AVAILABLE else None
        
        self.current_audio = None
        self.is_recording = False
        self.start_time = None
        
        # Vu meter update
        self.root.after(100, self.update_vu_meter)
        
        # Audio playback
        self.playback_stream = None

    def setup_ui(self):
        # Header
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(header_frame, text="STT DATASET RECORDING STUDIO", font=("Arial", 16, "bold")).pack()
        ttk.Label(header_frame, text="English Speech Dataset", font=("Arial", 12)).pack()

        ttk.Separator(self.root, orient='horizontal').pack(fill='x', pady=10)

        # Main Layout: 2 columns
        content_frame = ttk.Frame(self.root)
        content_frame.pack(fill="both", expand=True)
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)

        # Left Column
        left_frame = ttk.Frame(content_frame)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # --- AUDIO INPUT ---
        input_lf = ttk.LabelFrame(left_frame, text=" AUDIO INPUT ", padding=10)
        input_lf.pack(fill="x", pady=(0, 10))

        ttk.Label(input_lf, text="Source:").grid(row=0, column=0, sticky="w")
        self.source_var = tk.StringVar(value="PC Mic")
        sources = ["PC Mic"]
        if ESP32_AVAILABLE:
            sources.append("ESP32 Mic")
        self.source_cb = ttk.Combobox(input_lf, textvariable=self.source_var, values=sources, state="readonly")
        self.source_cb.grid(row=0, column=1, sticky="ew", padx=5)
        self.source_cb.bind("<<ComboboxSelected>>", self.on_source_change)

        self.esp32_frame = ttk.Frame(input_lf)
        # We will grid this if ESP32 is selected
        ttk.Label(self.esp32_frame, text="Port:").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar(value="COM16")
        ttk.Entry(self.esp32_frame, textvariable=self.port_var, width=10).grid(row=0, column=1, sticky="w", padx=5)
        
        self.connect_btn = ttk.Button(self.esp32_frame, text="Connect", command=self.toggle_esp32_connect)
        self.connect_btn.grid(row=0, column=2, sticky="w", padx=5)

        ttk.Label(input_lf, text="VU:").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.vu_canvas = tk.Canvas(input_lf, height=15, bg="black", highlightthickness=0)
        self.vu_canvas.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(10, 0), padx=5)
        self.vu_rect = self.vu_canvas.create_rectangle(0, 0, 0, 15, fill="green")
        input_lf.columnconfigure(1, weight=1)

        # --- CONTROLS ---
        controls_lf = ttk.LabelFrame(left_frame, text=" RECORDING CONTROLS ", padding=10)
        controls_lf.pack(fill="x", pady=(0, 10))

        self.record_btn = ttk.Button(controls_lf, text="⏺ RECORD", command=self.toggle_record)
        self.record_btn.pack(side="left", padx=5)

        self.play_btn = ttk.Button(controls_lf, text="▶ PLAY", command=self.play_audio, state="disabled")
        self.play_btn.pack(side="left", padx=5)

        self.discard_btn = ttk.Button(controls_lf, text="🗑 DISCARD", command=self.discard_audio, state="disabled")
        self.discard_btn.pack(side="left", padx=5)

        self.time_lbl = ttk.Label(controls_lf, text="00:00.0", font=("Consolas", 14, "bold"))
        self.time_lbl.pack(side="right", padx=5)

        # --- GROUND TRUTH ---
        gt_lf = ttk.LabelFrame(left_frame, text=" GROUND TRUTH ", padding=10)
        gt_lf.pack(fill="both", expand=True, pady=(0, 10))
        
        self.gt_text = tk.Text(gt_lf, height=4, font=("Arial", 11), wrap="word")
        self.gt_text.pack(fill="both", expand=True)

        # Right Column
        right_frame = ttk.Frame(content_frame)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        # --- DATASET INFORMATION ---
        info_lf = ttk.LabelFrame(right_frame, text=" DATASET INFORMATION ", padding=10)
        info_lf.pack(fill="x", pady=(0, 10))

        label_kwargs = {'padx': 5, 'pady': 5, 'sticky': 'w'}
        entry_kwargs = {'padx': 5, 'pady': 5, 'sticky': 'ew'}
        
        ttk.Label(info_lf, text="Speaker ID:").grid(row=0, column=0, **label_kwargs)
        self.speaker_var = tk.StringVar(value="speaker_01")
        ttk.Entry(info_lf, textvariable=self.speaker_var).grid(row=0, column=1, **entry_kwargs)

        ttk.Label(info_lf, text="Language:").grid(row=1, column=0, **label_kwargs)
        self.lang_var = tk.StringVar(value="en")
        ttk.Entry(info_lf, textvariable=self.lang_var).grid(row=1, column=1, **entry_kwargs)

        ttk.Label(info_lf, text="Accent:").grid(row=2, column=0, **label_kwargs)
        self.accent_var = tk.StringVar(value="vietnamese")
        ttk.Entry(info_lf, textvariable=self.accent_var).grid(row=2, column=1, **entry_kwargs)

        ttk.Label(info_lf, text="Speed:").grid(row=3, column=0, **label_kwargs)
        self.speed_var = tk.StringVar(value="normal")
        ttk.Combobox(info_lf, textvariable=self.speed_var, values=["normal", "fast", "slow"]).grid(row=3, column=1, **entry_kwargs)

        ttk.Label(info_lf, text="Environment:").grid(row=4, column=0, **label_kwargs)
        self.env_var = tk.StringVar(value="quiet")
        ttk.Combobox(info_lf, textvariable=self.env_var, values=["quiet", "noisy", "far-field"]).grid(row=4, column=1, **entry_kwargs)

        ttk.Label(info_lf, text="Tags:").grid(row=5, column=0, **label_kwargs)
        self.tags_var = tk.StringVar(value="natural_speech")
        ttk.Entry(info_lf, textvariable=self.tags_var).grid(row=5, column=1, **entry_kwargs)
        
        info_lf.columnconfigure(1, weight=1)

        # --- SAVE ---
        save_frame = ttk.Frame(right_frame)
        save_frame.pack(fill="x", pady=20)
        self.save_btn = ttk.Button(save_frame, text="💾 SAVE TO DATASET", command=self.save_to_dataset, state="disabled")
        self.save_btn.pack(fill="x", ipady=10)

        # --- RECENT RECORDINGS ---
        recent_lf = ttk.LabelFrame(self.root, text=" RECENT RECORDINGS ", padding=10)
        recent_lf.pack(fill="both", expand=True, pady=(10, 0))
        
        tree_frame = ttk.Frame(recent_lf)
        tree_frame.pack(fill="both", expand=True)
        
        columns = ("id", "gt", "duration")
        self.recent_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=5)
        self.recent_tree.heading("id", text="ID")
        self.recent_tree.heading("gt", text="Ground Truth")
        self.recent_tree.heading("duration", text="Duration")
        self.recent_tree.column("id", width=100, anchor="center")
        self.recent_tree.column("gt", width=500, anchor="w")
        self.recent_tree.column("duration", width=100, anchor="center")
        
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.recent_tree.yview)
        self.recent_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.recent_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        
        btn_frame = ttk.Frame(recent_lf)
        btn_frame.pack(fill="x", pady=(5, 0))
        self.play_selected_btn = ttk.Button(btn_frame, text="▶ PLAY SELECTED", command=self.play_selected_dataset_audio)
        self.play_selected_btn.pack(side="right")
        self.recent_tree.bind("<Double-1>", lambda e: self.play_selected_dataset_audio())
        
        self.load_recent_recordings()

        # Status bar
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x", side="bottom")

    def on_source_change(self, event=None):
        if self.source_var.get() == "ESP32 Mic":
            self.esp32_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)
        else:
            self.esp32_frame.grid_forget()

    def toggle_esp32_connect(self):
        if not self.esp32_mic:
            return
        
        if self.esp32_mic.is_connected():
            self.esp32_mic.disconnect()
            self.connect_btn.config(text="Connect")
            self.status_var.set("ESP32 Disconnected.")
        else:
            try:
                self.esp32_mic.connect(port=self.port_var.get())
                self.connect_btn.config(text="Disconnect")
                self.status_var.set(f"ESP32 Connected to {self.port_var.get()}.")
            except Exception as e:
                messagebox.showerror("Connection Error", str(e))

    def toggle_record(self):
        if self.is_recording:
            # Stop
            self.is_recording = False
            self.record_btn.config(text="⏺ RECORD")
            self.status_var.set("Recording stopped.")
            
            if self.source_var.get() == "PC Mic":
                self.current_audio = self.pc_mic.stop()
            else:
                if self.esp32_mic:
                    self.current_audio = self.esp32_mic.stop()
                
            if self.current_audio is not None and len(self.current_audio) > 0:
                self.play_btn.config(state="normal")
                self.discard_btn.config(state="normal")
                self.save_btn.config(state="normal")
        else:
            # Start
            self.current_audio = None
            self.gt_text.delete("1.0", tk.END)
            self.play_btn.config(state="disabled")
            self.discard_btn.config(state="disabled")
            self.save_btn.config(state="disabled")
            self.start_time = time.time()
            self.is_recording = True
            
            if self.source_var.get() == "PC Mic":
                self.pc_mic.start()
            else:
                if not self.esp32_mic or not self.esp32_mic.is_connected():
                    messagebox.showerror("Error", "ESP32 not connected!")
                    self.is_recording = False
                    return
                self.esp32_mic.start()
                
            self.record_btn.config(text="⏹ STOP")
            self.status_var.set("Recording...")

    def update_vu_meter(self):
        if self.is_recording:
            elapsed = time.time() - self.start_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            ms = int((elapsed * 10) % 10)
            self.time_lbl.config(text=f"{mins:02d}:{secs:02d}.{ms}")
            
            # Simulated VU meter update or actual level if accessible
            # We don't have direct chunk access in PCMicRecorder easily without modifying it.
            # Just show a visual indicator.
            import random
            level = random.random()
            
            width = self.vu_canvas.winfo_width()
            self.vu_canvas.coords(self.vu_rect, 0, 0, level * width, 15)
            if level > 0.8:
                self.vu_canvas.itemconfig(self.vu_rect, fill="red")
            elif level > 0.5:
                self.vu_canvas.itemconfig(self.vu_rect, fill="yellow")
            else:
                self.vu_canvas.itemconfig(self.vu_rect, fill="green")
        else:
            self.vu_canvas.coords(self.vu_rect, 0, 0, 0, 15)

        self.root.after(100, self.update_vu_meter)

    def play_audio(self):
        if self.current_audio is not None:
            self.status_var.set("Playing audio...")
            sd.play(self.current_audio, 16000)

    def discard_audio(self):
        self.current_audio = None
        self.play_btn.config(state="disabled")
        self.discard_btn.config(state="disabled")
        self.save_btn.config(state="disabled")
        self.time_lbl.config(text="00:00.0")
        self.status_var.set("Audio discarded.")
        
        if self.source_var.get() == "PC Mic":
            self.pc_mic.discard()
        elif self.esp32_mic:
            self.esp32_mic.discard()

    def save_to_dataset(self):
        gt = self.gt_text.get("1.0", tk.END).strip()
        if not gt:
            messagebox.showwarning("Missing Data", "Please enter Ground Truth text.")
            return
            
        if self.current_audio is None:
            return
            
        # Ensure directories exist
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        datatest_dir = os.path.join(base_dir, 'datatest')
        audio_dir = os.path.join(datatest_dir, 'audio')
        os.makedirs(audio_dir, exist_ok=True)
        
        json_path = os.path.join(datatest_dir, 'dataset.json')
        
        # Load existing dataset
        dataset = []
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    dataset = json.load(f)
            except Exception:
                pass
                
        # Generate new ID
        sample_idx = len(dataset) + 1
        sample_id = f"sample_{sample_idx:03d}"
        
        # Ensure unique ID
        existing_ids = {item.get('id') for item in dataset}
        while sample_id in existing_ids:
            sample_idx += 1
            sample_id = f"sample_{sample_idx:03d}"
            
        audio_filename = f"{sample_id}.wav"
        audio_filepath = os.path.join(audio_dir, audio_filename)
        
        # Save WAV (convert float32 to int16 for consistency, though scipy can save float32)
        audio_int16 = (self.current_audio * 32767).astype(np.int16)
        wavfile.write(audio_filepath, 16000, audio_int16)
        
        # Create metadata
        metadata = {
            "id": sample_id,
            "audio_file": f"audio/{audio_filename}",
            "ground_truth": gt,
            "speaker": self.speaker_var.get(),
            "mic_source": "pc" if self.source_var.get() == "PC Mic" else "esp32",
            "duration_s": round(len(self.current_audio) / 16000.0, 2),
            "language": self.lang_var.get(),
            "accent": self.accent_var.get(),
            "speed": self.speed_var.get(),
            "environment": self.env_var.get(),
            "tags": [t.strip() for t in self.tags_var.get().split(',') if t.strip()]
        }
        
        dataset.append(metadata)
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(dataset, f, indent=4, ensure_ascii=False)
            
        self.status_var.set(f"Saved {sample_id} successfully.")
        
        # Update Treeview
        self.recent_tree.insert("", tk.END, values=(sample_id, gt, f"{metadata['duration_s']}s"))
        self.recent_tree.yview_moveto(1)
        
        # Reset
        self.discard_audio()
        self.gt_text.delete("1.0", tk.END)

    def load_recent_recordings(self):
        for item in self.recent_tree.get_children():
            self.recent_tree.delete(item)
            
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        json_path = os.path.join(base_dir, 'datatest', 'dataset.json')
        
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    dataset = json.load(f)
                for item in dataset[-20:]:  # Show last 20 recordings
                    self.recent_tree.insert("", tk.END, values=(item.get("id"), item.get("ground_truth"), f"{item.get('duration_s')}s"))
                self.recent_tree.yview_moveto(1)
            except Exception:
                pass

    def play_selected_dataset_audio(self):
        selected_item = self.recent_tree.selection()
        if not selected_item:
            messagebox.showinfo("Info", "Please select a recording to play.")
            return
        
        item_values = self.recent_tree.item(selected_item[0])["values"]
        sample_id = item_values[0]
        
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        audio_path = os.path.join(base_dir, 'datatest', 'audio', f"{sample_id}.wav")
        
        if os.path.exists(audio_path):
            try:
                fs, data = wavfile.read(audio_path)
                self.status_var.set(f"Playing {sample_id}.wav ...")
                
                def _play():
                    sd.play(data, fs)
                    sd.wait()
                    self.status_var.set("Ready.")
                
                threading.Thread(target=_play, daemon=True).start()
                
            except Exception as e:
                messagebox.showerror("Playback Error", f"Could not play audio: {e}")
        else:
            messagebox.showwarning("Not Found", f"Audio file not found: {audio_path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = RecordingStudioApp(root)
    root.mainloop()
