# Thử nghiệm Whisper base.en với `initial_prompt`

Thư mục này là một experiment độc lập. Nó không thay đổi pipeline C++/sherpa-onnx
đang dùng để ship lên router.

## Vì sao phải tách riêng?

`SherpaOnnxOfflineWhisperModelConfig` của sherpa-onnx 1.13.6 trong project không
có trường `initial_prompt`. Model ONNX hiện có vì vậy không thể nhận prompt qua C
API. Experiment dùng implementation `openai-whisper` và checkpoint `base.en`
nguyên bản.

`initial_prompt` chỉ condition xác suất sinh text. Nó không phải forced hotword,
không có `hotwords_score`, và có thể làm transcript xấu hơn hoặc lặp/hallucinate.
Vì vậy mỗi WAV luôn được chạy ba lần:

1. `none`: không prompt, làm baseline;
2. `global`: toàn bộ từ vựng router trong một prompt;
3. `scenario`: chỉ prompt sát với kịch bản của clip.

Kết luận phải đọc `worsened` trước rồi mới nhìn WER trung bình.

## Cài đặt

Yêu cầu Windows x64 và Python 3.12. Máy không cần FFmpeg vì runner chỉ nhận WAV
PCM 16-bit, 16 kHz, mono/stereo.

```powershell
cd experiments\whisper_initial_prompt
.\setup.ps1 -DownloadModel
```

Checkpoint PyTorch của Whisper được lưu ở `.models/`. Nó khác định dạng với file
ONNX trong `models/sherpa-onnx-whisper-base.en`, nên không thể dùng lại file đó.

## Chuẩn bị corpus

Thu đúng các câu trong `manifest.tsv`, lưu vào `audio/`. Nên thu mỗi câu nhiều
lần: giọng bình thường, nhanh, nhỏ và đứng xa microphone. Reference là câu người
dùng định nói, không phải câu ASR nghe ra.

Danh sách hiện có 12 kịch bản đúng theo nội dung được cung cấp. Khi có kịch bản
13–14, thêm object vào `scenarios.json` và thêm dòng vào `manifest.tsv`; runner
không cần sửa.

## Chạy

### Dashboard trực quan

Từ thư mục gốc, double-click hoặc chạy:

```bat
scripts\whisper_prompt_dashboard.bat
```

Dashboard chính có hai workspace: contextual hotwords dùng `vcc_engine` và
Whisper `initial_prompt` dùng Python/PyTorch. Cảnh báo `biasing unavailable`
trong workspace sherpa vẫn đúng; nó không áp dụng cho workspace Whisper. Trong
tab **Whisper base.en — Initial Prompt**:

1. chọn một kịch bản;
2. bấm **Dùng TTS mẫu**, **Chọn WAV** hoặc **Thu âm**;
3. nhập reference đúng với câu bạn định nói;
4. sửa prompt nếu cần và bấm **Chạy so sánh 3 mode**.

Khi thu microphone, waveform và dBFS chạy trực tiếp. Audio được đổi từ sample
rate native về mono float32 16 kHz và giữ trong RAM để decode; dashboard không
tạo hay lưu file `live-*.wav`.

`Prompt strength` lặp riêng scenario prompt 1×, 2× hoặc 3×; mặc định 2×. Decoder
dùng beam search 5 paths. Đây vẫn là conditioning chứ không phải forced boost:
luôn kiểm tra cột no-prompt và các clip bị làm xấu trước khi chọn 3×.

Ba cột hiển thị transcript, WER, RTF của no prompt, global prompt và scenario
prompt. Model chỉ load ở lượt đầu, những lượt sau dùng lại model trong RAM.

### Command line

Toàn bộ corpus:

```powershell
.\.venv\Scripts\python.exe .\run.py --manifest .\manifest.tsv --output .\results\latest.json
```

Smoke test ngay bằng 20 câu TTS sạch đã có trong project:

```powershell
.\.venv\Scripts\python.exe .\run.py `
  --manifest .\manifest-synthetic.tsv `
  --output .\results\synthetic.json
```

Corpus này chỉ xác nhận plumbing và tạo mức sàn trên giọng Mỹ sạch. Không dùng
nó để kết luận prompt có ích cho accent Việt/Ấn.

Một file:

```powershell
.\.venv\Scripts\python.exe .\run.py `
  --wav .\audio\guest-wifi-01.wav `
  --scenario guest_wifi `
  --reference "turn on guest wifi"
```

Chỉ so baseline với prompt theo scenario:

```powershell
.\.venv\Scripts\python.exe .\run.py --manifest .\manifest.tsv --modes none scenario
```

## Nguyên tắc prompt

- Viết prompt giống một đoạn transcript đúng, không viết “Please recognize…”.
- Prompt theo scenario thường an toàn hơn nhét mọi từ vào global prompt.
- Tên người, thiết bị, ứng dụng và giá trị bandwidth nằm trong `scenarios.json`.
- Metric coi `50`/`fifty` và `100`/`one hundred` là cùng một numeric slot; đổi
  cách viết số không được tính là lợi ích của prompt.
- Không đánh giá trên một clip. Prompt có thể sửa một homophone nhưng làm hỏng
  clip khác.
- Hai kịch bản application vẫn giữ transcript người dùng nói; việc quy chúng về
  block/unblock internet thuộc tầng intent bên ngoài project STT.

Kiểm tra logic không cần model:

```powershell
py -3.12 -m pip install numpy
py -3.12 -m unittest discover -s . -p "test_*.py"
```
