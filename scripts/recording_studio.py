import os
import sys
import json
import time
import wave
import threading
import math
import numpy as np
import sounddevice as sd
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import datetime
import csv
from scipy.io import wavfile
from scipy.signal import resample_poly

try:
    from kokoro_onnx import Kokoro
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False

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


class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width)
        )

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        widget = event.widget
        if isinstance(widget, (ttk.Treeview, tk.Text, tk.Listbox)):
            return
            
        if self.winfo_ismapped():
            x, y = self.winfo_pointerxy()
            rx, ry = self.winfo_rootx(), self.winfo_rooty()
            rw, rh = self.winfo_width(), self.winfo_height()
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

class RecordingStudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("STT DATASET RECORDING STUDIO")
        self.root.geometry("1100x950")
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
        ttk.Label(header_frame, text="🎙 STT DATASET RECORDING STUDIO", font=("Arial", 16, "bold")).pack()
        ttk.Label(header_frame, text="Router / Wi-Fi Speech Dataset Development", font=("Arial", 12)).pack()

        ttk.Separator(self.root, orient='horizontal').pack(fill='x', pady=10)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x", side="bottom")

        # Notebook for Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, pady=(0, 10))
        
        # Tab 1: REAL RECORDING
        self.real_rec_wrapper = ScrollableFrame(self.notebook)
        self.notebook.add(self.real_rec_wrapper, text="REAL RECORDING")
        self.setup_real_recording_tab(self.real_rec_wrapper.scrollable_frame)

        # Tab 2: BATCH TTS GENERATOR
        self.batch_tts_wrapper = ScrollableFrame(self.notebook)
        self.notebook.add(self.batch_tts_wrapper, text="BATCH TTS GENERATOR")
        self.setup_batch_tts_tab(self.batch_tts_wrapper.scrollable_frame)

    def setup_real_recording_tab(self, parent):
        # Main Layout: 2 columns
        content_frame = ttk.Frame(parent)
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
        recent_lf = ttk.LabelFrame(parent, text=" RECENT RECORDINGS ", padding=10)
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

    def setup_batch_tts_tab(self, parent):
        pad_kwargs = {'padx': 10, 'pady': 5}
        
        # --- PHRASE DATASET ---
        dataset_lf = ttk.LabelFrame(parent, text=" PHRASE DATASET ", padding=10)
        dataset_lf.pack(fill="x", pady=(0, 10))
        
        ttk.Label(dataset_lf, text="Dataset file:").grid(row=0, column=0, sticky="w", **pad_kwargs)
        self.tts_dataset_var = tk.StringVar()
        ttk.Entry(dataset_lf, textvariable=self.tts_dataset_var, width=50).grid(row=0, column=1, sticky="ew", **pad_kwargs)
        ttk.Button(dataset_lf, text="Browse", command=self.browse_tts_dataset).grid(row=0, column=2, **pad_kwargs)
        
        ttk.Label(dataset_lf, text="Number of phrases:").grid(row=1, column=0, sticky="w", **pad_kwargs)
        self.tts_num_phrases_var = tk.StringVar(value="50")
        ttk.Combobox(dataset_lf, textvariable=self.tts_num_phrases_var, values=["5", "10", "20", "50", "100", "500", "1000", "2000", "5000", "All"]).grid(row=1, column=1, sticky="w", **pad_kwargs)
        
        dataset_lf.columnconfigure(1, weight=1)
        
        # --- PREVIEW/LOADED PHRASES ---
        preview_lf = ttk.LabelFrame(parent, text=" LOADED PHRASES PREVIEW ", padding=10)
        preview_lf.pack(fill="both", expand=True, pady=(0, 10))
        
        columns = ("id", "intent", "text")
        self.phrase_tree = ttk.Treeview(preview_lf, columns=columns, show="headings", height=5)
        self.phrase_tree.heading("id", text="ID")
        self.phrase_tree.heading("intent", text="Intent")
        self.phrase_tree.heading("text", text="Text Phrase")
        self.phrase_tree.column("id", width=100, anchor="center")
        self.phrase_tree.column("intent", width=150, anchor="center")
        self.phrase_tree.column("text", width=450, anchor="w")
        
        p_scroll = ttk.Scrollbar(preview_lf, orient="vertical", command=self.phrase_tree.yview)
        self.phrase_tree.configure(yscrollcommand=p_scroll.set)
        
        self.phrase_tree.pack(side="left", fill="both", expand=True)
        p_scroll.pack(side="right", fill="y")
        
        self.phrase_tree.bind("<<TreeviewSelect>>", self.on_phrase_select)
        
        self.phrases_data = [] # List of dicts loaded from file
        
        # --- TTS MODEL ---
        tts_model_lf = ttk.LabelFrame(parent, text=" TTS CONFIGURATION ", padding=10)
        tts_model_lf.pack(fill="x", pady=(0, 10))
        
        ttk.Label(tts_model_lf, text="Engine:").grid(row=0, column=0, sticky="w", **pad_kwargs)
        self.tts_engine_var = tk.StringVar(value="Kokoro")
        self.tts_engine_combo = ttk.Combobox(tts_model_lf, textvariable=self.tts_engine_var, values=["Kokoro", "VieNeu-TTS", "v_tts"], state="readonly", width=15)
        self.tts_engine_combo.grid(row=0, column=1, sticky="w", **pad_kwargs)
        self.tts_engine_combo.bind("<<ComboboxSelected>>", self._on_engine_change)

        ttk.Label(tts_model_lf, text="Model folder:").grid(row=1, column=0, sticky="w", **pad_kwargs)
        self.tts_model_var = tk.StringVar(value="models/kokoro")
        ttk.Entry(tts_model_lf, textvariable=self.tts_model_var, width=50).grid(row=1, column=1, sticky="ew", **pad_kwargs)
        ttk.Button(tts_model_lf, text="Browse", command=self.browse_tts_model).grid(row=1, column=2, **pad_kwargs)
        
        ttk.Label(tts_model_lf, text="Voice:").grid(row=2, column=0, sticky="w", **pad_kwargs)
        self.tts_voice_var = tk.StringVar(value="random")
        ttk.Entry(tts_model_lf, textvariable=self.tts_voice_var).grid(row=2, column=1, sticky="w", **pad_kwargs)
        
        ttk.Label(tts_model_lf, text="Speed:").grid(row=3, column=0, sticky="w", **pad_kwargs)
        self.tts_speed_var = tk.StringVar(value="1.00")
        ttk.Entry(tts_model_lf, textvariable=self.tts_speed_var).grid(row=3, column=1, sticky="w", **pad_kwargs)
        
        self.engine_hint_label = ttk.Label(tts_model_lf, text="Uses local Kokoro ONNX; WAV output is 16 kHz / 16-bit / mono.")
        self.engine_hint_label.grid(row=4, column=0, columnspan=3, sticky="w", **pad_kwargs)
        
        tts_model_lf.columnconfigure(1, weight=1)
        
        # --- OUTPUT & GENERATION ---
        output_lf = ttk.LabelFrame(parent, text=" OUTPUT & GENERATION ", padding=10)
        output_lf.pack(fill="x", pady=(0, 10))
        
        ttk.Label(output_lf, text="Output Folder:").grid(row=0, column=0, sticky="w", **pad_kwargs)
        self.tts_output_var = tk.StringVar(value="datatest/synthetic_router_wifi/")
        ttk.Entry(output_lf, textvariable=self.tts_output_var, width=50).grid(row=0, column=1, sticky="ew", **pad_kwargs)
        ttk.Button(output_lf, text="Browse", command=self.browse_tts_output).grid(row=0, column=2, **pad_kwargs)
        
        btn_frame2 = ttk.Frame(output_lf)
        btn_frame2.grid(row=1, column=0, columnspan=3, pady=15)
        
        self.start_tts_btn = ttk.Button(btn_frame2, text="▶ START GENERATION", command=self.start_batch_generation)
        self.start_tts_btn.pack(side="left", padx=10, ipady=5)
        
        self.stop_tts_btn = ttk.Button(btn_frame2, text="⏹ STOP", command=self.stop_batch_generation, state="disabled")
        self.stop_tts_btn.pack(side="left", padx=10, ipady=5)

        self.tts_generated_count_var = tk.StringVar(value="Generated audio: 0")
        ttk.Label(btn_frame2, textvariable=self.tts_generated_count_var, font=("Arial", 10, "bold")).pack(
            side="left", padx=(15, 0)
        )

        # --- GENERATED AUDIO ---
        # Kept directly beneath the Start/Stop controls so new output can be
        # reviewed while the batch is still running.
        generated_lf = ttk.LabelFrame(output_lf, text=" GENERATED AUDIO FILES ", padding=10)
        generated_lf.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))

        generated_tree_frame = ttk.Frame(generated_lf)
        generated_tree_frame.pack(fill="both", expand=True)

        generated_columns = ("file", "text", "duration")
        self.tts_audio_tree = ttk.Treeview(
            generated_tree_frame, columns=generated_columns, show="headings", height=6
        )
        self.tts_audio_tree.heading("file", text="Audio file")
        self.tts_audio_tree.heading("text", text="Text")
        self.tts_audio_tree.heading("duration", text="Duration")
        self.tts_audio_tree.column("file", width=180, anchor="w")
        self.tts_audio_tree.column("text", width=420, anchor="w")
        self.tts_audio_tree.column("duration", width=80, anchor="center")

        generated_scroll = ttk.Scrollbar(generated_tree_frame, orient="vertical", command=self.tts_audio_tree.yview)
        self.tts_audio_tree.configure(yscrollcommand=generated_scroll.set)
        self.tts_audio_tree.pack(side="left", fill="both", expand=True)
        generated_scroll.pack(side="right", fill="y")

        generated_buttons = ttk.Frame(generated_lf)
        generated_buttons.pack(fill="x", pady=(5, 0))
        ttk.Button(generated_buttons, text="Refresh", command=self.refresh_generated_tts_audio).pack(side="right")
        ttk.Button(generated_buttons, text="▶ Play selected", command=self.play_selected_tts_audio).pack(side="right", padx=(0, 5))
        self.tts_audio_tree.bind("<Double-1>", lambda _event: self.play_selected_tts_audio())
        self.tts_audio_paths = {}
        
        output_lf.columnconfigure(1, weight=1)
        
        # --- PROGRESS UI ---
        prog_frame = ttk.Frame(parent)
        prog_frame.pack(fill="x", pady=(0, 10))
        
        self.tts_progress_lbl = ttk.Label(prog_frame, text="Progress: 0 / 0", font=("Arial", 10, "bold"))
        self.tts_progress_lbl.pack(anchor="w")
        
        self.tts_progress_bar = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        self.tts_progress_bar.pack(fill="x", pady=5)
        
        self.tts_stats_lbl = ttk.Label(prog_frame, text="Generated: 0   Skipped: 0   Failed: 0")
        self.tts_stats_lbl.pack(anchor="w")
        
        self.tts_current_lbl = ttk.Label(prog_frame, text="Current phrase: --", wraplength=700)
        self.tts_current_lbl.pack(anchor="w", pady=5)

        # Setup vars for background thread
        self.tts_stop_event = threading.Event()
        self.tts_thread = None
        self.tts_stats = {"generated": 0, "skipped": 0, "failed": 0, "total": 0}
        self.refresh_generated_tts_audio(update_status=False)

    def _on_engine_change(self, event=None):
        engine = self.tts_engine_var.get()
        if engine == "Kokoro":
            self.tts_model_var.set("models/kokoro")
            self.engine_hint_label.config(text="Uses local Kokoro ONNX; WAV output is 16 kHz / 16-bit / mono.")
        elif engine == "VieNeu-TTS":
            self.tts_model_var.set(r"models\VieNeu-TTS")
            self.engine_hint_label.config(text="Uses VieNeu-TTS Engine (Vietnamese). Speed ignores if not supported.")
        elif engine == "v_tts":
            self.tts_model_var.set(r"models\v_tts")
            self.engine_hint_label.config(text="v_tts is an ONNX VITS model. Requires custom inference script.")

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

    def browse_tts_dataset(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON/JSONL/CSV/TXT", "*.json *.jsonl *.csv *.txt"), ("All Files", "*.*")])
        if file_path:
            self.tts_dataset_var.set(file_path)
            self.load_phrase_dataset(file_path)

    def browse_tts_model(self):
        path = filedialog.askdirectory(title="Select TTS Model Folder")
        if path:
            self.tts_model_var.set(path)

    def browse_tts_output(self):
        path = filedialog.askdirectory(title="Select Output Folder")
        if path:
            self.tts_output_var.set(path)
            self.refresh_generated_tts_audio()

    def _resolve_tts_output_dir(self, output_dir=None):
        output_dir = output_dir or self.tts_output_var.get().strip() or "datatest/synthetic_router_wifi/"
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        return os.path.abspath(output_dir if os.path.isabs(output_dir) else os.path.join(base_dir, output_dir))

    def refresh_generated_tts_audio(self, output_dir=None, update_status=True):
        """Populate the scrollable list with WAVs in the current TTS output folder."""
        for item in self.tts_audio_tree.get_children():
            self.tts_audio_tree.delete(item)
        self.tts_audio_paths = {}

        output_dir = self._resolve_tts_output_dir(output_dir)
        if not os.path.isdir(output_dir):
            if update_status:
                self.status_var.set("No generated TTS audio folder yet.")
            return

        text_by_audio = {}
        metadata_path = os.path.join(output_dir, "synthetic_dataset.json")
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            if isinstance(metadata, list):
                text_by_audio = {
                    os.path.basename(entry.get("audio", "")): entry.get("text", "")
                    for entry in metadata if isinstance(entry, dict)
                }
        except (OSError, json.JSONDecodeError):
            pass

        wav_paths = sorted(
            (
                os.path.join(output_dir, filename)
                for filename in os.listdir(output_dir)
                if filename.lower().endswith(".wav")
            ),
            key=os.path.getmtime,
            reverse=True,
        )
        for audio_path in wav_paths:
            filename = os.path.basename(audio_path)
            self._insert_generated_tts_audio(audio_path, text_by_audio.get(filename, ""))

        if update_status:
            self.status_var.set(f"Loaded {len(wav_paths)} generated TTS audio file(s).")

    def _format_wav_duration(self, audio_path):
        try:
            with wave.open(audio_path, "rb") as wav_file:
                duration = wav_file.getnframes() / wav_file.getframerate()
            return f"{duration:.2f}s"
        except (wave.Error, OSError, ZeroDivisionError):
            return "--"

    def _insert_generated_tts_audio(self, audio_path, text, prepend=False):
        """Add or replace one item in the generated-audio list."""
        normalized_path = os.path.normcase(os.path.abspath(audio_path))
        for item_id, existing_path in list(self.tts_audio_paths.items()):
            if os.path.normcase(os.path.abspath(existing_path)) == normalized_path:
                self.tts_audio_tree.delete(item_id)
                del self.tts_audio_paths[item_id]

        item_id = self.tts_audio_tree.insert(
            "",
            0 if prepend else tk.END,
            values=(os.path.basename(audio_path), text, self._format_wav_duration(audio_path)),
        )
        self.tts_audio_paths[item_id] = audio_path
        if prepend:
            self.tts_audio_tree.yview_moveto(0)

    def play_selected_tts_audio(self):
        selected = self.tts_audio_tree.selection()
        if not selected:
            messagebox.showinfo("Select audio", "Select a generated audio file to play.")
            return

        audio_path = self.tts_audio_paths.get(selected[0])
        if not audio_path or not os.path.isfile(audio_path):
            messagebox.showwarning("Not found", "The selected audio file no longer exists. Refresh the list and try again.")
            return

        try:
            sample_rate, audio_data = wavfile.read(audio_path)
        except Exception as e:
            messagebox.showerror("Playback error", f"Could not read audio: {e}")
            return

        self.status_var.set(f"Playing {os.path.basename(audio_path)} ...")

        def play():
            try:
                sd.play(audio_data, sample_rate)
                sd.wait()
                self.root.after(0, lambda: self.status_var.set("Ready."))
            except Exception as e:
                error = str(e)
                self.root.after(0, lambda: messagebox.showerror("Playback error", f"Could not play audio: {error}"))

        threading.Thread(target=play, daemon=True).start()

    def load_phrase_dataset(self, file_path):
        for item in self.phrase_tree.get_children():
            self.phrase_tree.delete(item)
        self.phrases_data = []
        
        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.phrases_data = data
                    elif isinstance(data, dict):
                        # Some datasets might be a dict with a list inside
                        for k, v in data.items():
                            if isinstance(v, list):
                                self.phrases_data = v
                                break
            elif ext == '.jsonl':
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            self.phrases_data.append(json.loads(line))
            elif ext == '.csv':
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.phrases_data.append(row)
            else: # txt
                with open(file_path, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        line = line.strip()
                        if line:
                            self.phrases_data.append({
                                "id": f"phrase_{i+1:06d}",
                                "text": line,
                                "intent": "unknown",
                                "domain": "unknown"
                            })
            
            # Populate treeview
            for i, p in enumerate(self.phrases_data[:100]):
                p_id = p.get("id", f"idx_{i}")
                intent = p.get("intent", "N/A")
                text = p.get("text", "")
                self.phrase_tree.insert("", tk.END, values=(p_id, intent, text))
            
            self.status_var.set(f"Loaded {len(self.phrases_data)} phrases from {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not load dataset: {e}")

    def on_phrase_select(self, event):
        selected = self.phrase_tree.selection()
        if not selected:
            return
        values = self.phrase_tree.item(selected[0])["values"]
        if len(values) >= 3:
            intent = values[1]
            text = values[2]
            self.tts_current_lbl.config(text=f"Selected phrase: {text} | Intent: {intent}")

    def start_batch_generation(self):
        if not self.phrases_data:
            messagebox.showwarning("Warning", "No phrases loaded! Please load a dataset first.")
            return

        engine = self.tts_engine_var.get()
        if engine == "Kokoro" and not KOKORO_AVAILABLE:
            messagebox.showerror(
                "Kokoro unavailable",
                "The kokoro_onnx package is required for Kokoro TTS."
            )
            return
            
        if engine == "v_tts":
            messagebox.showwarning("Chưa hỗ trợ v_tts", "v_tts (ONNX VITS model gồm 4 file) chưa có python inference script chuẩn.\nVui lòng chạy Kokoro hoặc VieNeu-TTS tạm thời.")
            return

        model_dir = self.tts_model_var.get().strip()
        if not model_dir:
            messagebox.showwarning("TTS model required", "Select the folder containing the TTS model.")
            return

        try:
            speed = float(self.tts_speed_var.get())
            if speed <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid speed", "TTS speed must be a positive number.")
            return
            
        limit_str = self.tts_num_phrases_var.get()
        if limit_str == "All":
            num_phrases = len(self.phrases_data)
        else:
            try:
                num_phrases = int(limit_str)
            except ValueError:
                num_phrases = 100
                
        num_phrases = min(num_phrases, len(self.phrases_data))
        selected_phrases = self.phrases_data[:num_phrases]
        
        out_dir = self.tts_output_var.get()
        if not out_dir.strip():
            out_dir = "datatest/synthetic_router_wifi/"
            
        full_out_dir = self._resolve_tts_output_dir(out_dir)
        os.makedirs(full_out_dir, exist_ok=True)
        
        self.tts_stats = {"generated": 0, "skipped": 0, "failed": 0, "total": num_phrases}
        self.tts_generated_count_var.set(f"Generated audio: 0 / {num_phrases}")
        self.tts_progress_bar["maximum"] = num_phrases
        self.tts_progress_bar["value"] = 0
        
        self.start_tts_btn.config(state="disabled")
        self.stop_tts_btn.config(state="normal")
        self.tts_stop_event.clear()
        
        self.tts_thread = threading.Thread(
            target=self._tts_worker,
            args=(engine, selected_phrases, full_out_dir, model_dir, self.tts_voice_var.get().strip(), speed),
            daemon=True,
        )
        self.tts_thread.start()

    def stop_batch_generation(self):
        if self.tts_thread and self.tts_thread.is_alive():
            self.tts_stop_event.set()
            self.status_var.set("Stopping generation gracefully...")
            self.stop_tts_btn.config(state="disabled")

    def _tts_worker(self, engine_name, phrases, out_dir, model_dir, voice, speed):
        try:
            tts = self._init_tts_engine(engine_name, model_dir, voice)
        except Exception as e:
            self.tts_stats["failed"] = self.tts_stats["total"]
            error = str(e)

            def show_startup_error():
                self.start_tts_btn.config(state="normal")
                self.stop_tts_btn.config(state="disabled")
                self.status_var.set("TTS could not start.")
                self.tts_current_lbl.config(text="TTS setup failed.")
                self.tts_stats_lbl.config(text=f"Generated: 0   Skipped: 0   Failed: {self.tts_stats['failed']}")
                messagebox.showerror("TTS setup failed", error)

            self.root.after(0, show_startup_error)
            return

        metadata_path = os.path.join(out_dir, "synthetic_dataset.json")
        metadata = []
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except Exception:
                pass
                
        if not isinstance(metadata, list):
            metadata = []
        metadata_by_audio = {
            os.path.basename(item.get("audio", "")): item
            for item in metadata
            if isinstance(item, dict) and item.get("audio")
        }
        
        for i, phrase in enumerate(phrases):
            if self.tts_stop_event.is_set():
                break
                
            current_engine = getattr(tts, "engine_name", "kokoro")
            prefix = current_engine.lower().replace("-", "_").replace(" ", "_")
            
            p_id = phrase.get("id", f"synth_{i:06d}")
            if not p_id.startswith(prefix):
                p_id = f"{prefix}_{p_id}"
                
            text = phrase.get("text", "")
            intent = phrase.get("intent", "unknown")
            domain = phrase.get("domain", "router_wifi")
            
            wav_filename = f"{p_id}.wav"
            wav_path = os.path.join(out_dir, wav_filename)
            
            def update_ui_current(c_text=text, c_idx=i+1):
                self.tts_current_lbl.config(text=f"Current phrase ({c_idx}/{self.tts_stats['total']}): {c_text}")
                self.tts_progress_lbl.config(text=f"Progress: {c_idx-1} / {self.tts_stats['total']}")
            self.root.after(0, update_ui_current)
            
            existing_entry = metadata_by_audio.get(wav_filename)
            current_engine = getattr(tts, "engine_name", "kokoro_onnx")
            
            # Skip only if the file was previously generated by the SAME engine
            if (
                existing_entry
                and existing_entry.get("tts_engine") == current_engine
                and os.path.isfile(wav_path)
            ):
                self.tts_stats["skipped"] += 1
            elif not existing_entry and os.path.exists(wav_path):
                # Preserve an audio file that was not created by this batch.
                self.tts_stats["skipped"] += 1
            else:
                try:
                    if tts.selected_voice.lower() == "random":
                        import random
                        current_voice = random.choice(tts.available_voices)
                    else:
                        current_voice = tts.selected_voice
                        
                    self._generate_tts_audio(tts, text, speed, wav_path, current_voice)
                    self.tts_stats["generated"] += 1
                    
                    meta_entry = {
                        "id": p_id,
                        "audio": wav_filename,
                        "text": text,
                        "intent": intent,
                        "domain": domain,
                        "source": "tts",
                        "speaker": current_voice,
                        "accent": "synthetic",
                        "tts_engine": getattr(tts, "engine_name", "kokoro_onnx"),
                        "tts_model": os.path.basename(tts.model_path),
                        "sample_rate": 16000,
                    }
                    metadata_by_audio[wav_filename] = meta_entry
                    self.root.after(
                        0,
                        lambda path=wav_path, phrase_text=text: self._insert_generated_tts_audio(
                            path, phrase_text, prepend=True
                        ),
                    )
                except Exception as e:
                    print(f"Failed to generate {p_id}: {e}")
                    self.tts_stats["failed"] += 1
            
            def update_ui_progress():
                self.tts_progress_bar["value"] += 1
                self.tts_stats_lbl.config(text=f"Generated: {self.tts_stats['generated']}   Skipped: {self.tts_stats['skipped']}   Failed: {self.tts_stats['failed']}")
                self.tts_generated_count_var.set(
                    f"Generated audio: {self.tts_stats['generated']} / {self.tts_stats['total']}"
                )
            self.root.after(0, update_ui_progress)
            
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(list(metadata_by_audio.values()), f, indent=4, ensure_ascii=False)
            
        def update_ui_final():
            self.start_tts_btn.config(state="normal")
            self.stop_tts_btn.config(state="disabled")
            self.refresh_generated_tts_audio(out_dir, update_status=False)
            msg = "Generation completed." if not self.tts_stop_event.is_set() else "Generation stopped."
            msg += f" Total: {self.tts_stats['total']}  Gen: {self.tts_stats['generated']}  Skip: {self.tts_stats['skipped']}  Fail: {self.tts_stats['failed']}"
            self.status_var.set(msg)
            self.tts_current_lbl.config(text="Done.")
            self.tts_progress_lbl.config(text=f"Progress: {self.tts_stats['total']} / {self.tts_stats['total']}")
        self.root.after(0, update_ui_final)

    def _create_kokoro_tts(self, model_dir, voice):
        """Load one Kokoro model for the entire batch, not once per phrase."""
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        model_dir = os.path.abspath(model_dir if os.path.isabs(model_dir) else os.path.join(base_dir, model_dir))
        if not os.path.isdir(model_dir):
            raise RuntimeError(f"Kokoro model folder not found: {model_dir}")

        model_files = [
            name for name in os.listdir(model_dir)
            if name.lower().endswith('.onnx') and os.path.isfile(os.path.join(model_dir, name))
        ]
        if not model_files:
            raise RuntimeError(f"No .onnx model found in: {model_dir}")

        voices_path = os.path.join(model_dir, "voices.bin")
        if not os.path.isfile(voices_path):
            raise RuntimeError(f"Kokoro voice file not found: {voices_path}")

        tts = Kokoro(os.path.join(model_dir, model_files[0]), voices_path)
        available_voices = tts.get_voices()
        selected_voice = voice.strip() or "random"
        if selected_voice.lower() != "random" and selected_voice not in available_voices:
            available = ", ".join(available_voices)
            raise RuntimeError(f"Unknown Kokoro voice '{selected_voice}'. Available voices: {available}, or 'random'")

        # Attach the selected voice and model name to the engine. This keeps the
        # generator API compact while preserving them in the metadata.
        tts.engine_name = "Kokoro"
        tts.available_voices = list(available_voices)
        tts.selected_voice = selected_voice
        tts.model_path = os.path.join(model_dir, model_files[0])
        return tts

    def _init_tts_engine(self, engine_name, model_dir, voice):
        if engine_name == "Kokoro":
            return self._create_kokoro_tts(model_dir, voice)
        elif engine_name == "VieNeu-TTS":
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            model_dir = os.path.abspath(model_dir if os.path.isabs(model_dir) else os.path.join(base_dir, model_dir))
            src_path = os.path.join(model_dir, "src")
            if src_path not in sys.path:
                sys.path.insert(0, src_path)
            
            try:
                from vieneu import Vieneu
            except ImportError:
                raise RuntimeError(f"Could not import vieneu from {src_path}.")
                
            tts = Vieneu(backend="onnx")
            available_voices_tuples = tts.list_preset_voices()
            available_voices = [t[1] for t in available_voices_tuples]
            
            selected_voice = voice.strip() or "random"
            if selected_voice.lower() != "random" and selected_voice not in available_voices:
                available = ", ".join(available_voices)
                raise RuntimeError(f"Unknown VieNeu-TTS voice '{selected_voice}'. Available: {available}, or 'random'")
            
            tts.engine_name = engine_name
            tts.available_voices = available_voices
            tts.selected_voice = selected_voice
            tts.model_path = model_dir
            return tts
            
        raise NotImplementedError(f"Engine {engine_name} not supported.")

    def _generate_tts_audio(self, tts, text, speed, output_path, voice=None):
        if not text or not text.strip():
            raise ValueError("Phrase text is empty.")

        use_voice = voice if voice else tts.selected_voice
        engine_name = getattr(tts, "engine_name", "Kokoro")
        
        if engine_name == "Kokoro":
            audio_data, sample_rate = tts.create(text.strip(), voice=use_voice, speed=speed)
            audio_data = np.asarray(audio_data, dtype=np.float32).flatten()
            if audio_data.size == 0:
                raise RuntimeError("Kokoro generated an empty audio buffer.")
        elif engine_name == "VieNeu-TTS":
            audio_data = tts.infer(text.strip(), voice=use_voice)
            sample_rate = 48000
            if audio_data is None or len(audio_data) == 0:
                raise RuntimeError("VieNeu-TTS generated an empty audio buffer.")
        else:
            raise NotImplementedError(f"Engine {engine_name} generation not implemented.")

        target_sample_rate = 16000
        if sample_rate != target_sample_rate:
            divisor = math.gcd(int(sample_rate), target_sample_rate)
            audio_data = resample_poly(audio_data, target_sample_rate // divisor, int(sample_rate) // divisor)

        # Add 0.5s of silence to prevent audio from being cut off at the end
        silence_samples = int(0.5 * target_sample_rate)
        audio_data = np.concatenate([audio_data, np.zeros(silence_samples, dtype=audio_data.dtype)])

        audio_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
        temporary_path = output_path + ".tmp"
        wavfile.write(temporary_path, target_sample_rate, audio_int16)
        os.replace(temporary_path, output_path)

if __name__ == "__main__":
    root = tk.Tk()
    app = RecordingStudioApp(root)
    root.mainloop()
