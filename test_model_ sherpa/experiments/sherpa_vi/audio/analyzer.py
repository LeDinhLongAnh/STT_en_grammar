import numpy as np

class AudioAnalyzer:
    @staticmethod
    def analyze(np_audio, sample_rate=16000):
        if np_audio is None or len(np_audio) == 0:
            return None
            
        frames = len(np_audio)
        duration = frames / sample_rate
        
        # Calculate RMS & Peak (np_audio is float32 [-1, 1])
        rms = np.sqrt(np.mean(np_audio**2))
        peak = np.max(np.abs(np_audio))
        
        rms_dbfs = 20 * np.log10(rms) if rms > 0 else -100
        peak_dbfs = 20 * np.log10(peak) if peak > 0 else -100
        
        # Clipping: tỷ lệ phần trăm mẫu xấp xỉ mức cực đại (ví dụ >= 0.99)
        clipping_threshold = 0.99
        clipping_samples = np.sum(np.abs(np_audio) >= clipping_threshold)
        clipping_pct = (clipping_samples / frames) * 100
        
        # Silence: tỷ lệ phần trăm mẫu dưới -40 dBFS (~0.01)
        silence_threshold = 0.01
        silence_samples = np.sum(np.abs(np_audio) < silence_threshold)
        silence_pct = (silence_samples / frames) * 100
        
        # Quality assessment
        quality = "GOOD"
        if clipping_pct > 1.0:
            quality = "WARNING: Audio clipping detected. Reduce microphone input volume."
        elif peak_dbfs < -30:
            quality = "WARNING: Microphone level is very low. Consider moving closer."
            
        return {
            "duration": duration,
            "sample_rate": sample_rate,
            "channels": 1,
            "rms_dbfs": rms_dbfs,
            "peak_dbfs": peak_dbfs,
            "clipping_pct": clipping_pct,
            "silence_pct": silence_pct,
            "quality": quality
        }
