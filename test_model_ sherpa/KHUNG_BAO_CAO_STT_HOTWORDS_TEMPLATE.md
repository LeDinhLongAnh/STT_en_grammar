# [TÊN DỰ ÁN] - KHUNG BÁO CÁO & HƯỚNG DẪN MỚM NGỮ CẢNH (CONTEXTUAL BIASING / HOTWORDS)

> **Mô hình áp dụng:** [Tên mô hình ASR - ví dụ: Sherpa-ONNX Zipformer / Whisper / Conformer]  
> **Nền tảng đích:** [Desktop / Server / Thiết bị nhúng ARM / Router / MCU]  
> **Mục tiêu:** [Nâng độ chính xác nhận diện từ khóa miền từ X% lên Y% mà không cần train lại mô hình]

---

## ⚡ Hướng Dẫn Nhanh (Quick Start)

Dành cho người vận hành muốn thêm từ mới và sử dụng ngay:

* **Bước 1 (Mở nơi cấu hình):** [Đường dẫn file cấu hình hoặc vị trí tab trên UI]
* **Bước 2 (Cú pháp thêm từ):**
  ```text
  [TỪ_KHÓA_ĐÚNG_ĐỊNH_DẠNG] :[ĐIỂM_SỐ]
  ```
  *(Ví dụ: `TU_KHOA_MAU :4.5`)*
* **Bước 3 (Lưu và Kiểm thử):** [Cách reload mô hình và câu lệnh kiểm tra]

---

## 1. Bản Chất Kỹ Thuật & Luồng Vận Hành

### 1.1. Bản chất cơ chế (Contextual Biasing)
* Không can thiệp hoặc thay đổi trọng số mạng học sâu (No Retraining).
* Bản chất là kỹ thuật bù điểm xác suất lúc giải mã (Inference-time Shallow Fusion):
  1. Từ khóa được chuyển đổi thành cấu trúc tìm kiếm (Trie / FST Graph).
  2. Khi bộ giải mã (Beam Search) phân vân giữa từ phổ thông và từ khóa chuyên ngành, từ khóa có trong danh sách sẽ được **cộng thêm điểm thưởng**.
  3. Từ khóa vượt lên dẫn đầu xác suất và được chọn làm kết quả.

### 1.2. Sơ đồ luồng vận hành (Input $\rightarrow$ Output)
```
[1. ÂM THANH ĐẦU VÀO]
    (Ví dụ câu lệnh chứa từ mượn / tên riêng)
          │
          ▼
[2. MÔ HÌNH ASR LẮNG NGHE & PHÂN VÂN]
    Phân vân giữa cách phát âm bản địa và từ khóa chuyên ngành
          │
          ▼
[3. CAN THIỆP TẦNG 1: MỚM TỪ KHÓA (HOTWORDS)]
    Tra danh sách ưu tiên -> CỘNG ĐIỂM THƯỞNG cho từ khóa mục tiêu
          │
          ▼
[4. KẾT QUẢ SƠ BỘ TỪ BỘ GIẢI MÃ]
    Mô hình chọn từ khóa có điểm cao nhất
          │
          ▼
[5. CAN THIỆP TẦNG 2: CHUẨN HÓA VĂN BẢN (POST-PROCESSING)]
    • Sửa lỗi chính tả / định dạng hoa thường quốc tế
    • Hứng và sửa các ca phát âm bồi / chệch âm nặng
          │
          ▼
[6. VĂN BẢN ĐẦU RA CHUẨN XÁC]
```

---

## 2. Kiến Trúc Pipeline Phối Hợp Đa Tầng

* **Vì sao 1 tầng là chưa đủ?**  
  * Hotwords chỉ kéo được các phát âm chuẩn hoặc gần chuẩn.
  * Khi gặp phát âm lệch âm vực hoàn toàn, việc ép tăng điểm Hotword sẽ gây ra **Ảo giác (Hallucination)** khi có tiếng ồn hoặc im lặng.
* **Chiến lược phân chia nhiệm vụ:**
  * **Tầng 1 (In-decoding Biasing):** Giữ điểm an toàn (`3.5 - 4.5`), phụ trách từ phát âm chuẩn/gần chuẩn.
  * **Tầng 2 (Post-processing Regex / Homophones):** Phụ trách toàn bộ các biến thể phát âm bồi, nói lóng, chệch âm địa phương. Tốn 0ms CPU, không gây ảo giác âm thanh.

---

## 3. Bộ Nguyên Tắc Viết Từ Khóa Tối Ưu

### Nguyên tắc 1: "Điểm tựa cụm từ" (Contextual Phrase Biasing)
* Từ đơn lẻ quá ngắn dễ bị nhận nhầm do tạp âm.
* **Giải pháp:** Ghép thêm từ ngữ cảnh/hành động đi liền trước hoặc sau:
  * *Kém tối ưu:* `[TỪ_NGẮN] :3.5`
  * *Tối ưu:* `[HÀNH_ĐỘNG] [TỪ_NGẮN] :4.0`

### Nguyên tắc 2: Chuẩn hóa định dạng chuỗi
* Bắt buộc tuân thủ bảng token của mô hình (ví dụ: chữ HOA, không dấu gạch nối, không dính số).
* Dấu gạch ngang, ký tự đặc biệt sẽ do Tầng 2 hậu xử lý đảm nhận.

### Nguyên tắc 3: Bảng tra cứu điểm số chuẩn (Scoring Cheat-Sheet)
| Nhóm từ vựng | Điểm khuyến nghị | Lưu ý kỹ thuật |
| :--- | :---: | :--- |
| Từ dài ($\ge 3$ âm tiết) | `4.0 – 4.5` | Dễ phân biệt, điểm này đủ để thắng mà không bị ảo giác |
| Từ ngắn (1 - 2 âm tiết) | `4.0` | Cần điểm vừa phải để không nuốt âm xung quanh |
| Từ viết tắt / âm gió | `3.0 – 3.5` | Dễ nhầm với xì xào, ưu tiên ghép cụm từ |
| Cụm từ ghép | `4.0` | Chuỗi token dài tự thân có xác suất cao |

### Nguyên tắc 4: Giới hạn quy mô từ vựng
* Giữ danh sách trong ngưỡng tối ưu cho phần cứng mục tiêu (ví dụ: 30 – 100 từ cho thiết bị nhúng).
* Không nạp toàn bộ từ điển vào bộ giải mã.

---

## 4. Quy Trình Thao Tác Chuẩn (SOP - Thêm Từ Mới)

```
[BƯỚC 1: THU ÂM CÂU MẪU]
       │
       ▼
[BƯỚC 2: CHẠY THỬ MODEL GỐC (BASELINE)]
       │  --> Ghi nhận các chuỗi phiên âm sai / bồi mà mô hình nghe ra
       ▼
[BƯỚC 3: THÊM HOTWORD (TẦNG 1)]
       │  --> Viết từ khóa chuẩn kèm điểm số khuyến nghị
       ▼
[BƯỚC 4: THÊM BỘ CHUẨN HÓA (TẦNG 2)]
       │  --> Đưa toàn bộ các chuỗi nghe sai ở Bước 2 vào danh sách quy đổi
       ▼
[BƯỚC 5: KIỂM THỬ ĐỐI ĐẦU & TINH CHỈNH]
          --> So sánh Baseline vs Context-aware để xác nhận kết quả
```

---

## 5. Kết Quả Đo Kiểm Thực Tế (Benchmark & Metrics)

### 5.1. Bảng đối đầu mẫu
| Câu nói thực tế | Mô hình gốc (Baseline) | Sau khi áp dụng 2 tầng | Đánh giá cải thiện |
| :--- | :--- | :--- | :--- |
| [Câu test 1] | [Kết quả sai] | [Kết quả đúng] | [Mô tả sửa lỗi] |
| [Câu test 2] | [Kết quả sai] | [Kết quả đúng] | [Mô tả sửa lỗi] |

### 5.2. Các chỉ số hiệu năng
* **Độ chính xác từ khóa (Entity Accuracy):** [Tăng từ A% lên B%]
* **Tỷ lệ lỗi từ (WER):** [Giảm từ X% xuống Y%]
* **Độ trễ phát sinh (Overhead Latency):** [< X ms]
* **Mức tiêu thụ tài nguyên (RAM / CPU / RTF):** [Thông số đo thực tế trên phần cứng]

---

## 6. Danh Sách Lỗi Cần Tránh (Anti-patterns)

* **Lỗi định dạng:** Viết sai chữ hoa/thường hoặc dính ký tự lạ khiến bộ tách từ (Tokenizer) bỏ qua.
* **Lỗi điểm số cực đoan:** Đặt điểm $> 6.5$ gây ảo giác âm thanh tự sinh từ khóa khi im lặng.
* **Biến thể chuẩn hóa quá ngắn:** Chuẩn hóa từ 1 ký tự dễ gây thay thế nhầm vào giữa các từ hợp lệ khác.
* **Quên nạp lại bộ nhớ (Reload Cache):** Sửa file nhưng chưa cập nhật phiên làm việc của bộ giải mã trên RAM.
