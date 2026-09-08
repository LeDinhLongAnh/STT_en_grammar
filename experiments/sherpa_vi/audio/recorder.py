import sounddevice as sd
import numpy as np
import queue
import wave
import io
import time
from PyQt5.QtCore import QObject, pyqtSignal

class MicrophoneRecorder(QObject):
    # Phát tín hiệu mang thông tin (RMS, Peak, Duration) để cập nhật UI
    level_updated = pyqtSignal(float, float, float)
    
    def __init__(self, sample_rate=16000, channels=1):
        super().__init__()
        self.sample_rate = sample_rate
        self.channels = channels
        self.stream = None
        self.q = queue.Queue()
        self.recording = False
        self.start_time = 0
        self.audio_data = []

    @staticmethod
    def get_devices():
        devices = sd.query_devices()
        # Lọc các thiết bị có max_input_channels > 0
        mics = []
        for idx, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                # Trả về tuple (id, name)
                mics.append((idx, dev['name']))
        return mics

    def audio_callback(self, indata, frames, time_info, status):
        """Hàm callback gọi liên tục khi có block âm thanh."""
        if self.recording:
            # indata is numpy array, shape (frames, channels)
            self.q.put(indata.copy())
            
            # Tính RMS và Peak
            if indata.size > 0:
                rms = np.sqrt(np.mean(indata**2))
                peak = np.max(np.abs(indata))
                
                # Tránh chia cho 0 khi tính dB
                rms_db = 20 * np.log10(rms) if rms > 0 else -100
                peak_db = 20 * np.log10(peak) if peak > 0 else -100
                
                duration = time.time() - self.start_time
                self.level_updated.emit(rms_db, peak_db, duration)

    def start_recording(self, device_id=None):
        self.audio_data = []
        self.q = queue.Queue()
        self.recording = True
        self.start_time = time.time()
        
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            device=device_id,
            channels=self.channels,
            callback=self.audio_callback,
            dtype='float32' # Dùng float32 cho dễ tính toán
        )
        self.stream.start()

    def stop_recording(self):
        self.recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            
        # Gom tất cả data lại
        while not self.q.empty():
            self.audio_data.append(self.q.get())
            
        if not self.audio_data:
            return None
            
        # audio_data là list các mảng (frames, 1), ghép lại thành 1 mảng lớn
        full_audio = np.concatenate(self.audio_data, axis=0)
        return full_audio

    def get_wav_bytes(self, np_audio):
        """Chuyển numpy array (float32) thành bytes chuẩn WAV PCM 16-bit."""
        if np_audio is None or len(np_audio) == 0:
            return None
            
        # Convert float32 [-1.0, 1.0] -> int16
        audio_int16 = (np.clip(np_audio, -1.0, 1.0) * 32767).astype(np.int16)
        
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2) # 16-bit = 2 bytes
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_int16.tobytes())
            
        return buffer.getvalue()
