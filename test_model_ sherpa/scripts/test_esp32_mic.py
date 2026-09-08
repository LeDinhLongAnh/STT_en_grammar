#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_esp32_mic.py
Kiem tra nhanh ket noi va doc audio tu ESP32 INMP441 qua COM port.
"""

import sys
import time
from pathlib import Path
import numpy as np

SCRIPTS_DIR = Path(__file__).parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audio_utils as au
from esp32_mic_recorder import ESP32MicRecorder

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM16"
    baudrate = 2000000
    
    print(f"=== TEST ESP32-S3 INMP441 MIC TREN CONG {port} ===")
    rec = ESP32MicRecorder(port=port, baudrate=baudrate)
    
    try:
        print(f"1. Dang ket noi toi {port}...")
        rec.connect()
        print("   -> Ket noi thanh cong!")
    except Exception as e:
        print(f"   -> [LOI KET NOI]: {e}")
        print("   Luu y: Hay dam bao ban da DONG cua so Serial Monitor tren Arduino IDE!")
        return

    try:
        print("\n2. Bat dau ghi am thu nghiem trong 3 giay (hay noi thu vao mic)...")
        rec.start()
        for i in range(3, 0, -1):
            print(f"   Ghi am... con {i} giay")
            time.sleep(1.0)
            
        print("\n3. Dung ghi am va lay du lieu...")
        samples = rec.stop()
        
        print(f"   -> So luong mau (samples): {len(samples)}")
        if len(samples) == 0:
            print("   -> [CANH BAO] Khong nhan duoc du lieu nao!")
            return
            
        dur = len(samples) / 16000.0
        max_amp = float(np.max(np.abs(samples)))
        rms = float(np.sqrt(np.mean(samples**2)))
        
        print(f"   -> Thoi luong thu duoc : {dur:.2f} giay (ky vong ~3.0s)")
        print(f"   -> Bien do lon nhat   : {max_amp:.4f} (khoang -1.0 den 1.0)")
        print(f"   -> Cuong do am (RMS)   : {rms:.4f}")
        print(f"   -> Dtype               : {samples.dtype}")
        
        # Luu ra file wav de kiem tra
        recordings_dir = SCRIPTS_DIR.parent / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)
        out_wav = recordings_dir / "test_esp32_inmp441.wav"
        au.save_wav(str(out_wav), samples, 16000)
        print(f"\n4. Da luu file test tai: {out_wav}")
        print("   -> Ban co the mo file nay len de nghe thu giong noi!")
        print("\n=== TEST PHAN 2 HOAN TOAN THANH CONG! ===")
        
    finally:
        rec.disconnect()

if __name__ == "__main__":
    main()
