import sys
import os
import time
from pathlib import Path

# Add experiments root to path
_EXP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_EXP_ROOT))

from tts_helpers import VieNeuEngine
import sherpa_vi.run_vi as experiment
import sherpa_onnx
import wave
import numpy as np

# Cấu hình đường dẫn
ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT.parents[1] / "models" / "sherpa-onnx-zipformer-vi"
TTS_MODEL_DIR = ROOT.parents[1] / "models" / "VieNeu-TTS"
CONFIG_PATH = ROOT / "scenarios_vi.json"
RECORDING_DIR = ROOT.parents[1] / "recordings" / "benchmark"
RECORDING_DIR.mkdir(parents=True, exist_ok=True)

# Đọc config JSON
import json
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

# Danh sách các câu cần test (từ ảnh của bạn)
TEST_SENTENCES = [
    "Bật wifi khách",
    "Tắt mạng khách đi",
    "Mở wifi phụ giúp tôi",
    
    "Giới hạn băng thông điện thoại xuống 50 Mbps",
    "Đặt tốc độ laptop ở mức 20 Mbps",
    "Bóp băng thông máy tính bảng còn 10 Mbps",
    
    "Tối ưu game cho máy tính",
    "Tăng tốc YouTube trên laptop",
    "Ưu tiên Netflix cho tivi thông minh",
    
    "Chặn YouTube trên máy tính bảng",
    "Cấm TikTok trên điện thoại của con",
    "Chặn game trên laptop",
    
    "Bỏ chặn YouTube trên máy tính bảng",
    "Cho phép TikTok trên điện thoại lại",
    "Gỡ chặn game trên laptop",
    
    "Chặn mạng cho máy tính bảng",
    "Tắt Wi-Fi trên điện thoại của con",
    "Cắt truy cập internet của laptop khách",
    
    "Mở mạng cho máy tính bảng",
    "Cho điện thoại kết nối Wi-Fi lại",
    "Cho laptop vào internet bình thường",
    
    "Ai đang chơi game",
    "Thiết bị nào đang chơi game",
    "Cho tôi xem các phiên chơi game đang hoạt động",
    
    "Có những thiết bị nào đang kết nối"
]

def load_sherpa_model():
    print(f"[*] Đang load model Sherpa-ONNX từ {MODEL_DIR}...")
    d = Path(MODEL_DIR)
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(d / "encoder.int8.onnx"),
        decoder=str(d / "decoder.onnx"),
        joiner=str(d / "joiner.int8.onnx"),
        tokens=str(d / "tokens.txt"),
        num_threads=2, sample_rate=16000, feature_dim=80,
        modeling_unit="bpe",
        bpe_vocab=str(d / "bpe.vocab") if (d / "bpe.vocab").exists() else "",
        decoding_method="modified_beam_search",
        hotwords_file="", hotwords_score=0.0,
    )
    return rec

def transcribe(samples, hotwords_text, score):
    import tempfile
    d = Path(MODEL_DIR)
    hw_file = ""
    tmp = None
    if hotwords_text.strip():
        # Đảm bảo IN HOA để khớp với bộ từ vựng Sherpa
        lines = [ln.strip().upper() for ln in hotwords_text.splitlines() if ln.strip()]
        if lines:
            fd, tmp = tempfile.mkstemp(suffix=".txt", prefix="sherpa_hw_")
            os.close(fd)
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            hw_file = tmp
    try:
        rec = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(d / "encoder.int8.onnx"),
            decoder=str(d / "decoder.onnx"),
            joiner=str(d / "joiner.int8.onnx"),
            tokens=str(d / "tokens.txt"),
            num_threads=2, sample_rate=16000, feature_dim=80,
            modeling_unit="bpe",
            bpe_vocab=str(d / "bpe.vocab") if (d / "bpe.vocab").exists() else "",
            decoding_method="modified_beam_search",
            hotwords_file=hw_file, hotwords_score=score,
        )
        stream = rec.create_stream()
        stream.accept_waveform(16000, samples)
        rec.decode_stream(stream)
        return stream.result.text.strip()
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)

def run_benchmark():
    print(f"[*] Bắt đầu chạy Benchmark tự động cho {len(TEST_SENTENCES)} câu lệnh...")
    engine = VieNeuEngine.get_instance()
    
    # Kết quả Markdown
    md_lines = [
        "# Báo cáo Benchmark Tự Động: TTS + Sherpa-ONNX",
        "",
        "| STT | Câu gốc (TTS) | Ô 1: Không Prompt | Ô 3: Auto Scenario (Phonetic Biasing) | Kịch bản chốt hạ |",
        "|---|---|---|---|---|"
    ]
    
    for i, sentence in enumerate(TEST_SENTENCES, 1):
        print(f"\n[{i}/{len(TEST_SENTENCES)}] Đang xử lý: '{sentence}'")
        
        # 1. Sinh TTS
        try:
            samples, _ = engine.synthesize(sentence)
            import soundfile as sf
            wav_path = RECORDING_DIR / f"test_{i:02d}.wav"
            sf.write(str(wav_path), samples, 16000, subtype="PCM_16")
        except Exception as e:
            print(f"  -> Lỗi sinh TTS: {e}")
            continue
            
        # 2. Ô 1: Không Prompt
        text_baseline = transcribe(samples, "", 0.0)
        res_base = experiment.resolve_scenario_vi(text_baseline, config)
        
        # 3. Luồng Ô 3: Auto Scenario (thử dò kịch bản từ baseline trước)
        scenario_prompt = ""
        auto_id = res_base.scenario_id
        if res_base.status == "matched":
            # Lấy phiên âm tiếng Việt để làm hotword
            scenario_prompt = experiment.get_phonetic_hotwords(auto_id, config)
            
            # Giải mã lại với Hotword
            text_scenario_raw = transcribe(samples, scenario_prompt, 1.5) # Dùng score 1.5
            
            # Chuẩn hóa (OAI PHAI -> WIFI)
            text_scenario = experiment.normalize_text(text_scenario_raw, config)
        else:
            text_scenario = text_baseline # Không nhận ra kịch bản thì giữ nguyên
            
        res_final = experiment.resolve_scenario_vi(text_scenario, config)
        
        print(f"  - Ô 1: {text_baseline}")
        print(f"  - Ô 3: {text_scenario}")
        print(f"  - Kịch bản: {res_final.scenario_id} ({res_final.status})")
        
        status_icon = "✅" if res_final.status == "matched" else "❌"
        md_lines.append(f"| {i} | {sentence} | {text_baseline} | **{text_scenario}** | {status_icon} `{res_final.scenario_id}` |")
        
    report_path = ROOT / "BENCHMARK_REPORT.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
        
    print(f"\n[*] Đã hoàn tất! Báo cáo được lưu tại: {report_path}")

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    run_benchmark()
