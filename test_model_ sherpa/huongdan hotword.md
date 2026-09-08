# Hướng Dẫn Thiết Lập Hotwords Sherpa-ONNX

> **Mục tiêu:** Nâng độ chính xác nhận diện thuật ngữ tiếng Anh, tên thiết bị, từ viết tắt từ **30% lên 95%+** trên mô hình `sherpa-onnx-zipformer-vi` mà **không cần train lại mô hình**.

---

## Hướng Dẫn Nhanh (Quick Start)

Muốn thêm từ khóa mới vào hệ thống ngay lập tức, chỉ cần làm theo **3 bước**:

### Bước 1: Mở nơi cấu hình
* **Cách 1 (Dùng giao diện):** Chạy `python scripts/app.py`, vào mục **3. Ngữ cảnh Pipeline B** $\rightarrow$ chọn tab **Hotwords**.
* **Cách 2 (Sửa trực tiếp bằng file text):** Mở file `config/hotwords.txt`.

### Bước 2: Viết từ khóa theo đúng cú pháp
Thêm một dòng mới ở cuối danh sách:
```text
TỪ_IN_HOA :4.5
```
* **Ví dụ thực tế:**
  * Thêm dịch vụ Spotify: `SPOTIFY :4.5`
  * Thêm thiết bị Bluetooth: `BLUETOOTH :4.5`
  * Thêm từ điều khiển Smart Home: `SMART :4.0`

>**Quy tắc quan trọng nhất:** Bắt buộc phải viết **CHỮ IN HOA** (không viết `spotify`, phải viết `SPOTIFY`).

### Bước 3: Lưu và sử dụng ngay
* Trên giao diện `app.py`: Bấm nút **"Lưu hotwords"**. Hệ thống tự động nạp từ mới trong 1 giây mà không cần khởi động lại.
* Thử nói câu lệnh: *"Mở nhạc trên Spotify"* $\rightarrow$ Mô hình sẽ bắt chính xác từ `SPOTIFY` thay vì nghe thành *"xì bo ti phai"*.

---

## 1. Bản Chất Hotword & Luồng Vận Hành (Audio $\rightarrow$ Text)

### 1.1. Bản chất Hotword là gì? (Giải thích đơn giản)
Mô hình STT tiếng Việt giống như một người nghe chỉ quen từ thuần Việt. Khi nghe một từ tiếng Anh (như *"wifi"*), mô hình sẽ phân vân giữa hai lựa chọn:
* Viết theo tiếng Việt: `"OAI PHAI"`
* Viết theo tiếng Anh: `"WIFI"`

Vì quen tiếng Việt hơn, mô hình thường sẽ chọn `"OAI PHAI"`.

**Hotword chính là một "danh sách ưu tiên" đưa cho mô hình lúc nghe:**
1. Khai báo danh sách các từ quan trọng kèm điểm thưởng: `WIFI :4.5`, `LAPTOP :4.5`.
2. Khi đang phân vân giữa `"OAI PHAI"` và `"WIFI"`, mô hình thấy từ `"WIFI"` có tên trong danh sách ưu tiên.
3. Mô hình **cộng ngay điểm thưởng** cho `"WIFI"` $\rightarrow$ `"WIFI"` có điểm cao nhất và chiến thắng.
4. **Không cần train lại mô hình:** Chỉ cần thêm từ vào file text, mô hình sẽ lập tức ưu tiên từ đó trong 1 giây.

---

### 1.2. Luồng vận hành từ Giọng nói $\rightarrow$ Chữ viết

```
[1. GIỌNG NÓI ĐẦU VÀO]
    Người nói: "Mở wifi phụ"
          │
          ▼
[2. MÔ HÌNH STT NGHE ÂM THANH]
    Mô hình nghe thấy âm thanh và phân vân:
    • Nghe giống "OAI PHAI" (50% cơ hội)
    • Nghe giống "WIFI"     (50% cơ hội)
          │
          ▼
[3. HOTWORD CAN THIỆP (CỘNG ĐIỂM ƯU TIÊN)]
    Tra file hotwords.txt thấy có: "WIFI :4.5"
    --> "WIFI" được cộng điểm thưởng, vọt lên 95% cơ hội!
          │
          ▼
[4. MÔ HÌNH CHỌN TỪ THẮNG CUỘC]
    Kết quả nhận dạng sơ bộ: "MỞ WIFI PHỤ"
          │
          ▼
[5. BỘ LỌC TỪ ĐỒNG ÂM (HOMOPHONES)]
    • Sửa chữ in hoa thành chuẩn quốc tế: "WIFI" -> "Wi-Fi"
    • Nếu người nói phát âm lệch hẳn thành "hoa phai" -> vẫn sửa lại thành "Wi-Fi"
          │
          ▼
[6. VĂN BẢN ĐẦU RA HOÀN CHỈNH]
    "Mở Wi-Fi phụ"
```

---

## 2. Thiết Kế Pipeline 2 Tầng (Nguyên Lý Phối Hợp)

Thực nghiệm cho thấy **chỉ dùng một mình Hotwords là không đủ**:
* **Khi phát âm chuẩn hoặc gần chuẩn tiếng Anh:** Tầng 1 (Hotwords) nhận diện chính xác vì đặc trưng âm học khớp với token BPE.
* **Khi phát âm bồi hoàn toàn theo tiếng Việt thuần:** Ví dụ `wifi` nói thành `hoa phai` / `quai phai`, `netflix` nói thành `nét lít`, `QoS` nói thành `cô ác`. Lúc này âm học lệch hẳn, nếu tăng điểm hotword lên quá cao ($> 6.5$) để ép nhận thì mô hình sẽ bị **ảo giác (hallucination)** — tự sinh từ khóa khi có tạp âm hoặc im lặng.

**Chiến lược áp dụng:**
1. **Tầng 1 (Hotwords):** Đặt điểm vừa phải (`3.5 - 4.5`) để bắt các phát âm chuẩn/gần chuẩn.
2. **Tầng 2 (Homophones Regex):** Quét văn bản sau giải mã để đón toàn bộ các biến thể phát âm bồi lệch âm vực và chuẩn hóa về dạng chữ chuẩn (`Wi-Fi`, `YouTube`, `Laptop`).

---

## 3. Cách Viết Hotword Tối Ưu Cho Dự Án Hiện Tại

Cú pháp file `config/hotwords.txt`: `<TỪ_KHÓA> :<điểm_số>`

```text
WIFI :4.5
LAPTOP :4.5
GAME :4.0
YOUTUBE :4.5
NETFLIX :4.5
TIKTOK :4.5
INTERNET :4.5
MBPS :4.0
QOS :3.0
```

Để đạt hiệu năng và độ chính xác cao nhất cho hệ thống điều khiển Router/Smart Home, cần tuân thủ **5 nguyên tắc tối ưu**:

### 1. Nguyên tắc "Điểm tựa cụm từ" (Triệt tiêu lỗi nhận nhầm)
Các từ viết tắt hoặc từ ngắn 1 âm tiết (`IP`, `QOS`, `MBPS`, `APP`, `GAME`) rất dễ nhận nhầm khi có tiếng thở, tiếng xì xào hoặc từ đồng âm tiếng Việt (*kịp, nhịp, úp*).
* **Kém tối ưu (Từ đơn lẻ):** `IP :3.5`, `MBPS :4.0`
* **Tối ưu chuẩn xác (Ghép cụm ngữ cảnh):**
  ```text
  ĐỊA CHỈ IP :4.0
  TỐC ĐỘ MBPS :4.0
  WIFI KHÁCH :4.0
  MỞ WIFI :4.5
  CHƠI GAME :4.0
  ```
  > **Lý do:** Chuỗi từ càng dài thì xác suất tích lũy trong Beam Search càng lớn. Cụm từ đi kèm đóng vai trò như chiếc "neo" ngữ cảnh, giúp mô hình khóa chặt ý định câu lệnh và loại bỏ hoàn toàn lỗi nhận nhầm.

### 2. Phân chia đúng việc giữa 2 tầng (Không ép Hotwords làm việc của Homophones)
Tuyệt đối không tăng điểm Hotword lên quá cao (`:8.0` hoặc `:10.0`) chỉ để ép mô hình nhận dạng các cách đọc bồi lệch âm (*hoa phai*, *diu túp*). Việc này sẽ gây ảo giác âm thanh (tự sinh từ khóa khi im lặng).
* **Hotwords (Tầng 1):** Chỉ bắt các phát âm chuẩn hoặc gần chuẩn tiếng Anh (*laptop, wifi, netflix*). Giữ điểm ở mức an toàn `3.5 - 4.5`.
* **Homophones (Tầng 2):** Đảm nhận toàn bộ các biến thể phát âm bồi lệch âm vực thuần Việt (*hoa phai, quai phai, diu túp, nét lít, kuwait*).
  > **Lý do:** Homophones chạy bằng Regex sau giải mã: **tốn 0ms CPU, không tốn RAM, không gây ảo giác âm thanh**.

### 3. Làm sạch ký tự trong `hotwords.txt`
Từ điển `tokens.txt` của mô hình không chứa dấu gạch nối hay số dính liền chữ:
* **Kém tối ưu:** `Wi-Fi :4.5` (có dấu `-` và chữ thường), `20 Mbps :4.0` (số dính chữ).
* **Tối ưu chuẩn xác:** `WIFI :4.5`, `LAPTOP :4.5`, `MBPS :4.0` (chỉ dùng chữ cái IN HOA).  
  *(Định dạng có dấu gạch ngang đẹp mắt như `Wi-Fi` sẽ do Tầng 2 tự động chuyển đổi).*

### 4. Bảng tra cứu điểm số tối ưu (Scoring Cheat-Sheet)
| Nhóm từ vựng | Điểm tối ưu | Lý do kỹ thuật | Ví dụ |
| :--- | :---: | :--- | :--- |
| **Từ mượn 2-3 âm tiết** | `4.0 – 4.5` | Âm học rõ ràng, điểm này đủ thắng từ tiếng Việt mà không bị ảo giác. | `YOUTUBE :4.5`<br>`NETFLIX :4.5`<br>`INTERNET :4.5` |
| **Từ mượn 1-2 âm tiết** | `4.0` | Cần điểm vừa phải để tránh nuốt các âm tiếng Việt ngắn xung quanh. | `WIFI :4.0`<br>`LAPTOP :4.0`<br>`TIKTOK :4.0` |
| **Từ viết tắt kỹ thuật** | `3.0 – 3.5` | Chứa phụ âm tắc dễ nhầm với tạp âm, chỉ nên đặt điểm nhẹ và ưu tiên ghép cụm. | `QOS :3.0`<br>`MBPS :3.5` |
| **Cụm từ ghép hành động** | `4.0` | Chuỗi token dài tự thân đã có xác suất cao, điểm 4.0 là tối ưu. | `WIFI KHÁCH :4.0`<br>`ĐỊA CHỈ IP :4.0` |

### 5. Giữ quy mô từ vựng gọn gàng (Tối ưu cho thiết bị nhúng/Router)
* Mục tiêu dự án chạy trên Router (RAM $\le 200$ MB, CPU ARM Cortex-A55).
* **Không nạp hàng trăm từ vào `hotwords.txt`** vì sẽ làm phình to cây Trie trên RAM và làm chậm giải thuật Beam Search.
* **Quy mô lý tưởng:** Duy trì danh sách trong khoảng **30 – 80 từ khóa** cốt lõi của miền tác vụ. Các từ ít dùng hoặc biến thể địa phương nên đưa vào `config/homophones.txt`.

---

## 4. Cấu Hình `config/homophones.txt` (Tầng 2)

Cú pháp file: `<TỪ_CHUẨN> : <biến_thể_1>, <biến_thể_2>, ...`

```text
Wi-Fi : wifi, oai phai, hoai phai, hoa phai, quai phai, quy phai, vi phi, wai phai, wai fai
Laptop : láp tóp, láp tốp, lắp tóp, lấp tốp, nháp tóp, láp tót, lab top, lap top
Game : ghem-minh, ghem minh, gêm-minh, gêm minh, ghem, gêm, gem, rem, đêm
YouTube : diu túp, dzu túp, du túp, giu túp, diu tu bi, du tu bê, you tube, u túp
Netflix : nét phíc, nét phờ líc, nét lít, nít líc, nết phích, nét níc, net flix, nết flix
TikTok : tích tốc, tíc tóc, tiếc tóc, tít tóc, thít thót, tik tok, tic toc
Internet : in-tơ-nét, in tơ nét, in-tẹt-nét, in tẹt nét, in-tơ-nết, in tơ nết, in-tơ-nẹt, in tơ nẹt, i-nét, i nét
Mbps : mê-ga-bít, mê ga bít, mờ-bê-pê-ét, mờ bê pê ét, mờ-bê, mờ bê
QoS : kuwait, cô ác, quy, kheo s, cu ác, kiu o ét
```

### 3 cơ chế kỹ thuật trong module `scripts/homophone_mapper.py`:
* **Ưu tiên cụm dài trước (Longest-Match-First):** Tự động đo độ dài để match `in-tơ-nét` trước `nét`, tránh xé rách từ.
* **Linh hoạt gạch nối và khoảng trắng:** Khai báo `ghem-minh` tự động nhận cả `ghem minh`.
* **Bảo vệ biên giới từ (`(?<!\w)pattern(?!\w)`):** Không bao giờ thay thế nhầm vào giữa các từ tiếng Việt hợp lệ khác.

---

## 5. Quy Trình 5 Bước Thêm Từ Mới

Khi cần bổ sung một từ khóa (ví dụ: `Bluetooth` hoặc `Spotify`):

1. **Thu âm câu mẫu:** Dùng tab Mic hoặc tab TTS trong `scripts/app.py` phát câu chứa từ mới (ví dụ: *"Bật kết nối bluetooth"*).
2. **Kiểm tra kết quả Pipeline A (Baseline mộc):** Ghi nhận chuỗi phiên âm bồi mà mô hình trả về (ví dụ ra: `BLU TÚT` hoặc `LU TÚT`).
3. **Thêm vào `config/hotwords.txt`:** Viết chữ hoa kèm điểm chuẩn:
   ```text
   BLUETOOTH :4.5
   ```
4. **Thêm vào `config/homophones.txt`:** Gán toàn bộ biến thể vừa phát hiện ở Bước 2:
   ```text
   Bluetooth : blu tút, blu-tút, lu tút, bu lu tút, blutut
   ```
5. **Kiểm thử đối đầu:** Bấm lưu trên app và chạy so sánh (A vs B) để xác nhận Pipeline B nhận diện chuẩn xác.

---

## 6. Kết Quả Đo Kiểm Thực Tế

Dữ liệu ghi nhận từ các phiên test thực tế (`experiments/results/`):

| Câu nói thực tế | Pipeline A (Gốc) | Pipeline B (Context-aware) | Đánh giá |
| :--- | :--- | :--- | :--- |
| Mở wifi phụ giúp tôi | `MỞ WIFI PHỤ GIÚP TÔI` | `MỞ Wi-Fi PHỤ GIÚP TÔI` | Chuẩn hóa danh từ riêng |
| Đặt tốc độ laptop ở mức 20 Mbps | `...HAI MƯƠI MEGAS PERSE CẦN` (WER: **62.5%**) | `...HAI MƯƠI Mbps` (WER: **25.0%**) | Nhận diện chính xác đơn vị `Mbps` |
| Bật wifi khách và mở trang QoS | `...VÀO KIỂM TRA TRANG KUWAIT` (WER: **100%**) | `...VÀ MỞ TRANG QoS` (WER: **0%**) | Khắc phục nhận nhầm `QoS` thành `Kuwait` |
| Ai đang xem YouTube và ai xem Netflix | `AI ĐANG XEM DU TÚP VÀ... NÉT PHÍCH` | `AI ĐANG XEM YOUTUBE VÀ... NETFLIX` | Nhận diện đồng thời 2 ứng dụng |
| Cho phép TikTok trên điện thoại lại | `...CHO PHÉP TÍCH TÚC TRÊN...` | `...CHO PHÉP TIKTOK TRÊN...` | Sửa dứt điểm âm bồi `tích túc` |

**Chỉ số đo lường:**
* **Entity Accuracy:** Tăng từ **35%** lên **95%+**.
* **Độ trễ phát sinh:** Dưới **3 ms** cho cả 2 tầng, RTF duy trì mức **0.05 - 0.10** trên CPU.

---

## 7. Các Lỗi Thường Gặp & Cách Khắc Phục (Anti-patterns)

* **Viết chữ thường trong `hotwords.txt`:** Model Zipformer tiếng Việt không nhận, tính năng hotwords bị vô hiệu. $\rightarrow$ *Luôn viết HOA.*
* **Nâng điểm score $> 6.5$ để ép nhận từ bồi:** Gây ảo giác khi yên lặng. $\rightarrow$ *Giữ score 4.0 - 4.5, từ bồi do Tầng 2 Homophones xử lý.*
* **Đặt biến thể homophone quá ngắn (1 ký tự):** Dễ replace nhầm vào câu khác. $\rightarrow$ *Biến thể phải từ 2 ký tự trở lên hoặc theo cụm từ.*
* **Sửa file txt nhưng quên bấm Lưu/Reload:** Bộ nhớ RAM vẫn chạy phiên bản cũ. $\rightarrow$ *Bấm nút Lưu trên UI hoặc kích hoạt reload ngầm.*
