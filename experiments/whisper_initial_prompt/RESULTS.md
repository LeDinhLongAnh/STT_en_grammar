# Baseline kết quả experiment

Ngày chạy: 2026-08-23  
Model: `openai-whisper` `base.en`, CPU, PyTorch 2.13.0  
Corpus: `manifest-synthetic.tsv`, 20 câu TTS tiếng Anh Mỹ sạch

| Mode | WER | Mean RTF | Improved | Worsened | Unchanged |
|---|---:|---:|---:|---:|---:|
| Không prompt | 5.00% | 0.525 | — | — | — |
| Global prompt | 0.00% | 0.557 | 2 | 0 | 18 |
| Scenario prompt | 0.00% | 0.528 | 2 | 0 | 18 |

Hai lỗi baseline được sửa:

- `on Block Internet for my son` → `Unblock internet for my son`
- `on Block Facebook` → `Unblock Facebook`

`50`/`fifty`, `100`/`one hundred` và `Wi-Fi`/`wifi` được canonicalize trước
khi tính WER vì đây là cùng numeric/lexical slot của hệ thống.

Đây chỉ là kiểm tra plumbing và mức sàn. Chưa thể kết luận initial prompt tốt hơn
trên giọng Việt/Ấn cho tới khi `manifest.tsv` có các bản thu thật. Cần ưu tiên
`worsened = 0`; prompt sửa được `unblock` trên TTS không bảo đảm nó không gây
hallucination ở âm thanh nhiễu hoặc accent mạnh.
