#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# esp32_mic_recorder.py
# Nhan du lieu PCM 16-bit tu ESP32 qua Serial, chuyen sang float32 16kHz mono.

import struct
import threading
import time
import numpy as np

try:
    import serial
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False


class ESP32MicRecorder:
    def __init__(self, port: str = "COM16", baudrate: int = 2000000):
        self._port = port
        self._baudrate = baudrate
        self._serial = None
        self._connected = False
        
        self._recording = False
        self._thread = None
        self._lock = threading.Lock()
        
        # Buffer luu cac chunk float32
        self._audio_buffer: list[np.ndarray] = []

    def connect(self, port: str | None = None, baudrate: int | None = None) -> None:
        if not _SERIAL_AVAILABLE:
            raise RuntimeError("Chua cai thu vien pyserial. Chay: pip install pyserial")
            
        if port:
            self._port = port
        if baudrate:
            self._baudrate = baudrate
            
        if self._connected and self._serial and self._serial.is_open:
            return

        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=0.5
            )
            self._connected = True
        except Exception as e:
            self._connected = False
            self._serial = None
            raise RuntimeError(f"Khong the ket noi toi cong {self._port}: {e}")

    def disconnect(self) -> None:
        self.stop()
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self._connected = False

    def is_connected(self) -> bool:
        return bool(self._connected and self._serial and self._serial.is_open)

    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        if not self.is_connected():
            raise RuntimeError("Chua ket noi voi ESP32. Vui long bam 'Ket noi ESP32' truoc.")
        
        if self._recording:
            return
            
        with self._lock:
            self._audio_buffer = []
            
        self._recording = True
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()

    def stop(self) -> np.ndarray:
        if not self._recording:
            return np.array([], dtype=np.float32)
            
        self._recording = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            
        with self._lock:
            if not self._audio_buffer:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._audio_buffer, axis=0)
            self._audio_buffer = []
            
        return audio.astype(np.float32)

    def discard(self) -> None:
        if self._recording:
            self._recording = False
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=1.0)
        with self._lock:
            self._audio_buffer = []

    def _read_exact(self, n: int) -> bytes:
        """Doc chinh xac n bytes tu serial, cho den khi du hoac timeout."""
        data = bytearray()
        while len(data) < n and self._recording and self.is_connected():
            try:
                chunk = self._serial.read(n - len(data))
                if not chunk:
                    break
                data.extend(chunk)
            except Exception:
                break
        return bytes(data)

    def _receive_loop(self) -> None:
        # Xoa sach buffer rac trong serial truoc khi doc frame moi
        try:
            if self._serial and self._serial.in_waiting > 0:
                self._serial.read(self._serial.in_waiting)
        except Exception:
            pass
            
        # Frame Protocol: [0xAA, 0xBB] + [Length: 2 bytes] + [PCM] + [Checksum: 1 byte]
        state = 0
        payload_len = 0
        
        while self._recording and self.is_connected():
            try:
                # Tim Magic Byte 1 (0xAA)
                if state == 0:
                    b = self._serial.read(1)
                    if not b:
                        continue
                    if b[0] == 0xAA:
                        state = 1
                
                # Tim Magic Byte 2 (0xBB)
                elif state == 1:
                    b = self._serial.read(1)
                    if not b:
                        state = 0
                        continue
                    if b[0] == 0xBB:
                        state = 2
                    elif b[0] == 0xAA:
                        state = 1  # Giu tiep vi co the lech byte
                    else:
                        state = 0
                        
                # Doc Length (2 bytes, little endian)
                elif state == 2:
                    len_bytes = self._read_exact(2)
                    if len(len_bytes) < 2:
                        state = 0
                        continue
                    payload_len = struct.unpack('<H', len_bytes)[0]
                    
                    if payload_len == 0 or payload_len > 4096:
                        state = 0
                        continue
                        
                    state = 3
                    
                # Doc Payload PCM va Checksum
                elif state == 3:
                    data_to_read = payload_len + 1
                    payload_data = self._read_exact(data_to_read)
                    
                    if len(payload_data) < data_to_read:
                        state = 0
                        continue
                        
                    pcm_bytes = payload_data[:-1]
                    received_checksum = payload_data[-1]
                    
                    # Tinh XOR checksum
                    calculated_checksum = 0
                    for byte in pcm_bytes:
                        calculated_checksum ^= byte
                        
                    if calculated_checksum == received_checksum:
                        # Parse PCM data int16 -> float32 (-1.0 den 1.0)
                        samples_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
                        samples_float32 = samples_int16.astype(np.float32) / 32768.0
                        
                        with self._lock:
                            self._audio_buffer.append(samples_float32)
                    
                    state = 0  # Quay lai doc frame tiep theo
                    
            except serial.SerialException:
                print("[ESP32Mic] Mat ket noi Serial.")
                self._connected = False
                break
            except Exception as e:
                print(f"[ESP32Mic] Loi khi doc du lieu: {e}")
                time.sleep(0.05)
                state = 0
