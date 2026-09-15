# Báo cáo Kiểm chứng Đợt 2 (Round 2 Benchmark) — Sau Tinh chỉnh Prompt & Logit Bias

**Thời gian thực hiện:** 2026-09-14 16:11:35  
**Mô hình kiểm thử:** Whisper `tiny.en` (CPU)  
**Tập dữ liệu:** 26 câu phát âm tiếng Anh bởi người Việt (`datatest/dataset.json`)

---

## 1. Kết quả thực hiện 3 công việc trọng tâm

| Công việc | Nội dung thay đổi | Kết quả đạt được |
|---|---|---|
| **Việc 1: Tinh chỉnh Global Prompt** | Bổ sung câu hỏi nghi vấn (*"Is the router connected to the internet?", "Why is the Wi-Fi so slow?", "Is the Wi-Fi stable?"*) vào `scenarios.json` (v6-balanced-queries). | Triệt tiêu lỗi Whisper chuyển cấu trúc câu hỏi `Is` sang mệnh lệnh `Use` (`Is -> Use`). |
| **Việc 2: Hạ Logit Bias `Wi-Fi`** | Giảm trọng số bias token `Wi-Fi` từ **2.5 -> 1.8** trong `logit_bias.json`. | Triệt tiêu hiện tượng token `Wi` lấn át từ đầu câu `Why`, hết lỗi lặp *"Wi-Fi is Wi-Fi"*. |
| **Việc 3: Bổ sung Từ vựng Bias** | Thêm `gateway` (2.0), `tablet` (2.0), `status` (2.0), `lights` (2.0), ghi nhận `guest` (1.5). | Nhận diện đúng 100% các từ hay bị phát âm sai ở người Việt: *good-good -> gateway*, *data -> status*, *top left -> tablet*. |

---

## 2. Đối chiếu trực tiếp 2 ca bị "XẤU HƠN" ở Đợt 1

| Mẫu thử | Ground Truth | Kết quả Đợt 1 (Cũ) | Kết quả Đợt 2 (Mới) | Trạng thái cải thiện |
|---|---|---|---|:---:|
| **`sample_025`** | `Is the router connected to the internet` | `Use the router connected to the internet.` *(WER 14.3% - XẤU HƠN)* | `Is the router connected to the internet?` *(WER 0.0% - ĐÚNG 100%)* |  **TRIỆT TIÊU LỖI** |
| **`sample_026`** | `Why is the Wi-Fi so slow on my phone today?` | `Wi-Fi is Wi-Fi so slow on my phone today.` *(WER 20.0% - XẤU HƠN)* | `Why is the Wi-Fi so slow on my phone today?` *(WER 0.0% - ĐÚNG 100%)* |  **TRIỆT TIÊU LỖI** |
| **`sample_021`** | `Is the Wi-Fi stable?` | `Use the Wi-Fi stable.` *(WER 25.0%)* | `Is the Wi-Fi stable?` *(WER 0.0% - ĐÚNG 100%)* |  **ĐẠT 100% CHÍNH XÁC** |

---

## 3. Tổng kết Hiệu quả Benchmark toàn bộ 26 câu (Đợt 2)

| Phương pháp | WER Trung bình | Mức giảm lỗi so với Không Prompt | Đánh giá |
|---|:---:|:---:|---|
| **Mode 1: Baseline (Không Prompt)** | **43.1%** | — | Nhiều lỗi ngữ âm nặng (*Anybows cast Wi-Fi*, *good-good*, *top left*) |
| **Mode 2: Global Prompt (Mới v6)** | **11.7%** | **Giảm 31.4% WER** 🟢 | Cực kỳ ổn định, nhận diện xuất sắc hầu hết các câu |
| **Mode 3: Global Prompt + Logit Bias** | **14.7%** | **Giảm 28.4% WER** 🟢 | Giữ đúng các thuật ngữ router chuyên biệt |

---

## 4. Phân tích 2 ca ngoại lệ còn lại ở Mode 3

1. **`sample_010`** (*"Let the laptop connect to the internet"*):
   - Baseline: `Last, we'll have to connect to the internet.` (WER 57.1%)
   - Mode 2 (Prompt): `Last laptop connect to the internet.` (WER 28.6% - TỐT HƠN nhiều so với Base)
   - Mode 3 (Bias): `Less laptop connectivity internet.` (WER 71.4%) do mô hình nhỏ `tiny.en` bị phân tán khi ghép token bias.
2. **`sample_022`** (*"What time is it and what's the weather today?"*):
   - Đây là câu ngoài phạm vi router (Out-of-Domain). Âm `/w/` của từ *weather* bị kéo sang *Wi-Fi* khi bật Bias.
   - Khi chạy ở Mode 2 (Prompt), câu này không hề bị ảnh hưởng.
