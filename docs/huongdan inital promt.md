# HƯỚNG DẪN VIẾT INITIAL PROMPT CHO WHISPER TINY (C/C++ & ROUTER)

> **Mô hình:** `whisper-tiny.en` (~39M params, ~75 MB float32 / ~40 MB int8)  
## QUICK START

### Cách 1: Tinh chỉnh & Thử nghiệm trực tiếp trên Giao diện (Khuyên dùng - Nhanh nhất)
1. **Mở Dashboard:** Chạy file `scripts\dashboard.bat` (hoặc `scripts\whisper_prompt_dashboard.bat`).
2. **Sửa Prompt trực tiếp trên UI:** 
   * Nhập/sửa câu lệnh tại khung văn bản **Global prompt** ở cột bên phải.
   * Quan sát nhãn đếm token nhảy theo thời gian thực: `.../223 Whisper tokens` *(Màu xanh lá: an toàn; Màu đỏ: vượt quá 223 tokens)*.
   * Bấm nút **"Lưu global prompt"** $\rightarrow$ Hệ thống tự động ghi đè ngay vào file `scenarios.json`.
3. **Kiểm tra hiệu quả tức thì:**
   * Bấm **"Thu âm"** (nói qua Mic) hoặc **"Dùng TTS mẫu"**.
   * Bấm **"Chạy so sánh 3 mode"** $\rightarrow$ Xem kết quả đối đầu song song: *1. Không prompt* vs *2. Global prompt* vs *3. Auto Scenario prompt*.

---

### Cách 2: Nạp vào C++ (`whisper.cpp`) để Triển khai trên Router
Sau khi đã tinh chỉnh và chốt được chuỗi Prompt ưng ý trên Dashboard, copy chuỗi đó nạp vào mã nguồn C++:

```cpp
#include "whisper.h"

whisper_full_params params = whisper_full_default_params(WHISPER_SAMPLING_BEAM_SEARCH);
params.strategy = WHISPER_SAMPLING_BEAM_SEARCH;
params.beam_search.beam_size = 5;
params.temperature = 0.0f;
params.no_context  = true; // Không lấy context câu trước tránh trôi ngữ cảnh
params.language    = "en";

// Chuỗi Prompt đã chốt từ Dashboard (121 - 209 tokens, dưới trần 223 tokens)
params.initial_prompt = 
    "Router assistant transcript. Enable guest Wi-Fi and turn off the guest network. "
    "Limit the phone to 50 Mbps and set the laptop bandwidth to 20 Mbps. "
    "Optimize gaming for the PC, boost YouTube, and prioritize Netflix for the smart TV. "
    "Block TikTok on the tablet and unblock it again. Check the router status, "
    "gateway information, and router uptime. Check internet connection quality and open QoS. "
    "Which devices are playing games. Which clients are connected. Guest Wi-Fi. Unblock internet.";

// Giải mã trực tiếp từ mảng PCM 16kHz float32 trên Router
whisper_full(ctx, params, pcm_data, pcm_len);
const char* text = whisper_full_get_segment_text(ctx, 0);
```

*(Tuỳ chọn: Chạy kiểm thử tự động toàn bộ dataset bằng CLI)*:
```powershell
experiments\whisper_initial_prompt\.venv\Scripts\python.exe experiments\whisper_initial_prompt\run.py --manifest experiments\whisper_initial_prompt\manifest.tsv
```

---

## 1. BẢN CHẤT KỸ THUẬT & LUỒNG VẬN HÀNH

### 1.1. So sánh Hotword và Initial Prompt

Cả hai đều nhằm mục đích **ưu tiên nhận diện từ khóa mà không cần train lại mô hình**, nhưng cách hoạt động khác nhau hoàn toàn:

| Tiêu chí | Hotword (Zipformer / Sherpa) | Initial Prompt (Whisper) |
| :--- | :--- | :--- |
| **Dạng khai báo** | Danh sách từ + điểm số: `WIFI :4.5` | Đoạn câu mẫu: `"Enable guest Wi-Fi..."` |
| **Bản chất kỹ thuật** | Dựng cây từ khóa (Trie) ghép vào Beam Search | Nạp chuỗi từ mồi (Prefix Tokens) vào Context Decoder |
| **Cơ chế tính điểm** | **Cộng điểm số cứng (`+4.5`)** khi khớp âm thanh | **Không có điểm số**; tăng xác suất mềm qua Attention |
| **Phạm vi tác động** | Ép nhận diện từng từ khóa đơn lẻ | Mồi cả phong cách, ngữ cảnh và cú pháp câu lệnh |
| **Khả năng gây ảo giác** | Điểm quá cao ($> 6.0$) sẽ tự sinh từ khi im lặng | Prompt quá dài hoặc lặp sẽ sinh câu lặp dị thường |
| **Huấn luyện lại** | **Không cần** (nạp file text là chạy ngay) | **Không cần** (đổi prompt là có tác dụng tức thì) |

### 1.2. Bản chất của Scenario Prompt: "Kính lúp" so với "Lưới quét"

| Tiêu chí | Global Prompt (Lưới quét rộng) | Scenario Prompt (Kính lúp hội tụ) |
| :--- | :--- | :--- |
| **Quy mô** | Dài (121 – 209 tokens) | Rất ngắn (30 – 50 tokens) |
| **Nội dung** | Gom **toàn bộ** lệnh: Wi-Fi, 50 Mbps, QoS, TikTok, Netflix... | Chỉ chứa mẫu câu của **đúng 1 kịch bản** |
| **Nhiệm vụ** | Nghe tổng quát ban đầu để **nhận diện chủ đề** | Tập trung nghe lại để **sửa lỗi nuốt âm, phát âm bồi** |

---

### 1.3. Luồng vận hành 2 lượt qua ví dụ thực tế (Rất dễ hiểu)

Giả sử người dùng nói câu: *"Turn on guest Wi-Fi"* (nhưng do ngữ âm Việt nói lướt, máy nghe nhầm thành *"turn on weapon"*):

```text
[BƯỚC 1: NGHE LƯỢT 1 VỚI LƯỚI QUÉT RỘNG (GLOBAL PROMPT)]
   • Người dùng nói: "Turn on guest Wi-Fi" (nói lướt âm)
   • Nạp Global Prompt (121 tokens chứa đủ mọi lệnh router)
   ==> Kết quả lượt 1: "turn on weapon"  (nghe nhầm 'guest Wi-Fi' thành 'weapon')
                       │
                       ▼
[BƯỚC 2: BỘ PHÂN TÍCH TẦNG 2 ĐOÁN Ý ĐỊNH (RESOLVER)]
   • Thấy có hành động bật nguồn: "turn on"
   • Router không có lệnh nào về vũ khí ("weapon"), mà chỉ có bật mạng khách!
   ==> Tự động suy luận: "92% người dùng đang nói kịch bản GUEST WI-FI!"
                       │
                       ▼
[BƯỚC 3: NGHE LẠI LƯỢT 2 VỚI KÍNH LÚP TẬP TRUNG (SCENARIO RE-DECODE)]
   • Đưa lại đoạn âm thanh đó cho Whisper nghe lần 2
   • Lần này nạp riêng Scenario Prompt của Guest Wi-Fi (chỉ 35 tokens):
     "Turn on guest Wi-Fi. Turn off guest Wi-Fi. Enable guest network."
   ==> Whisper dồn 100% sự tập trung vào từ "guest Wi-Fi"
       Âm thanh nuốt âm "weapon" lập tức được nắn chuẩn thành "guest Wi-Fi"!
                       │
                       ▼
[KẾT QUẢ ĐẦU RA HOÀN CHỈNH]
   Transcript sửa đúng 100%: "Turn on the guest Wi-Fi."
   Lệnh thực thi ngay: BẬT WIFI KHÁCH THÀNH CÔNG!
```

> **Tóm lại một câu:**  
> Bản Tiny rất nhỏ (39M tham số), không thể vừa nhớ rộng vừa nghe siêu nét cùng lúc. Vì vậy cần **Lượt 1 để đoán đúng kịch bản** và **Lượt 2 để nghe lại thật nét từng từ!**

---

## 2. KIẾN TRÚC PIPELINE PHỐI HỢP ĐA TẦNG

### 2.1. Tại sao Whisper Tiny bắt buộc phải có 2 tầng?
* **Whisper Tiny (39M) có dung lượng nhỏ:** Khả năng hiểu ngữ cảnh yếu hơn Base. Nếu ép điểm/ép prompt quá mạnh (lặp lại prompt 2x-3x), Tiny sẽ bị **ảo giác (hallucination)** — tự chép lại prompt khi gặp tiếng ồn/tiếng thở.
* **Hiện tượng lặp vô tận:** Khi im lặng, Tiny dễ rơi vào loop lặp: `"Thank you for watching... [lặp 30 lần]"`.
* **Phát âm bồi tiếng Việt:** Khi người dùng nói lệch âm nặng (`guest Wi-Fi` $\rightarrow$ nghe thành `rest weapon` hay `S2 file`), prompt tiếng Anh không thể cứu được bằng âm học mà phải dùng logic ngữ pháp ở Tầng 2.

### 2.2. Phân chia nhiệm vụ 2 tầng

```
┌────────────────────────────────────────────────────────────────────────┐
│ TẦNG 1: IN-DECODING PROMPT (Whisper C++)                              │
│ • Phạm vi: Diễn ra bên trong giải thuật Beam Search của Whisper.       │
│ • Nhiệm vụ: Nắn đúng từ vựng nghiệp vụ (Wi-Fi, 50 Mbps, QoS, YouTube), │
│   chống nuốt âm cặp từ đối kháng (block/unblock), dập tắt loop lặp.    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Sinh raw text
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ TẦNG 2: POST-PROCESSOR & INTENT RESOLVER (C++ Logic Engine)            │
│ • Phạm vi: Hậu xử lý văn bản sau khi Whisper sinh kết quả.             │
│ • Nhiệm vụ:                                                            │
│   1. Canonicalize: Đưa số về dạng số (`fifty` -> `50`, `ten` -> `10`). │
│   2. Closed-domain Grammar: Lệnh on/off độc lập -> Khóa vào Guest Wi-Fi│
│   3. Homophones Regex: Ánh xạ lỗi chệch âm (tốn 0ms CPU, 0MB RAM).     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. BỘ NGUYÊN TẮC VIẾT TỪ KHÓA TỐI ƯU

### Nguyên tắc 1: Điểm tựa cụm từ (Contextual Phrase Anchoring)
* ❌ **Không viết từ vụn vặt:** `router, wifi, qos, mbps, block, unblock` *(Dễ gây ảo giác khi nhiễu).*
* ✅ **Viết câu lệnh hoàn chỉnh:** `Enable guest Wi-Fi. Limit phone to 50 Mbps. Optimize gaming for PC.`

### Nguyên tắc 2: Cặp tương phản đối kháng (Antithetical Pairs)
* Nhược điểm của Tiny là nuốt phụ âm `/ʌn/`, nghe `unblock` thành `on block` hoặc `block`.
* **Khắc phục triệt để:** Luôn đặt 2 hành động cạnh nhau trong prompt:
  ```text
  Block internet or applications. Unblock internet or applications.
  ```

### Nguyên tắc 3: Neo từ khóa nguy cơ cao ở đuôi (Tail Anchoring)
Do cơ chế Recency Attention, lặp lại các từ dễ trượt nhất ở cuối chuỗi prompt:
```text
... Which clients are connected. Guest Wi-Fi. Unblock internet.
```

### Nguyên tắc 4: Quản lý ngân sách Token (Giải mã con số 223 Tokens)

Trên `dashboard.bat`, hệ thống hiển thị: **`.../223 Whisper tokens`**. Đây là giới hạn cứng của nửa cửa sổ ngữ cảnh Whisper (448 / 2 = 224 tokens, trừ 1 token kết thúc = 223 tokens).

```
                               NGÂN SÁCH 223 WHISPER TOKENS
V2 Strong (209/223 tokens) ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░  WER 0.0% | RTF 0.35 (Độ phủ 100%)
V3 Lean   (121/223 tokens) ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░  WER 0.0% | RTF 0.28 (Nhanh hơn 20%!)
```

* **Phiên bản V2 Strong (209/223 tokens):** Liệt kê chi tiết mọi slot (tên người, thiết bị, app, giá trị băng thông). Phù hợp khi cần độ phủ rộng tối đa, RTF trên Tiny ~0.35.
* **Phiên bản V3 Lean (121/223 tokens):** Gom nhóm danh từ liên kết (`Network status, condition, quality...`), chừa trống hơn 100 token đệm. **Nhanh hơn 20% CPU (RTF ~0.28)** mà vẫn đạt độ chính xác tương đương.

---

### 3.5. Prompt tối ưu cho Dự án hiện tại

Trong dự án thực tế của chúng ta (`experiments/whisper_initial_prompt/scenarios.json`), chuỗi **Global Prompt đang vận hành rất hiệu quả** có cấu trúc như sau:

```text
Router assistant transcript. Enable guest Wi-Fi and turn off the guest network. Limit the phone to 50 Mbps and set the laptop bandwidth to 20 Mbps. Optimize gaming for the PC, boost YouTube, and prioritize Netflix for the smart TV. Block TikTok on the tablet and unblock it again. Check the router status, gateway information, and router uptime. Check internet connection quality and open the QoS page. Which devices are playing games. Which clients are connected. Show device info for the tablet.Restore Wi‑Fi access.Prevent.Remove blocking.IP and Status of the
```

#### Bóc tách 5 tầng cấu trúc tạo nên hiệu quả vượt trội:

1. **Neo ngữ cảnh mở đầu (Domain Anchor):**
   * `"Router assistant transcript."` $\rightarrow$ Định hình ngay vai trò trợ lý router, lập tức triệt tiêu hiện tượng Whisper Tiny bị ảo giác chép lời cảm ơn kết thúc video (*"Thank you for watching..."*).

2. **Phủ trọn vẹn 4 nhóm Slot nghiệp vụ router:**
   * **Thiết bị (Devices):** `phone`, `laptop`, `PC`, `smart TV`, `tablet` $\rightarrow$ Đặc biệt cứu từ khó `tablet` (vốn hay bị nghe nhầm thành `top end`, `top place`, `top right`).
   * **Ứng dụng (Apps):** `YouTube`, `TikTok`, `Netflix` $\rightarrow$ Cố định tên các dịch vụ phổ biến nhất trong gia đình.
   * **Băng thông & Đơn vị đo:** `50 Mbps`, `20 Mbps` $\rightarrow$ Khắc phục triệt để lỗi nuốt âm đơn vị `Mbps` (trước đó Whisper hay nghe thành `BBN`, `MBF`, `milli-a-biscuit`).
   * **Thực thể chẩn đoán:** `gateway`, `uptime`, `QoS page`, `clients`, `gaming`.

3. **Cặp từ đối kháng bảo vệ lệnh nhạy cảm:**
   * `"Block TikTok on the tablet and unblock it again."` $\rightarrow$ Ghép `Block` và `Unblock` vào cùng một câu tự nhiên, giúp mô hình phân biệt rạch ròi hành động chặn và gỡ chặn, không bị nuốt phụ âm `/ʌn/`.

4. **Neo đuôi vá lỗi âm học thực chiến từ Microphone (Mic Patches):**
   * `"Restore Wi‑Fi access.Prevent.Remove blocking.IP and Status of the"`
   * Các cụm từ này được đúc kết trực tiếp từ tập test Microphone với phát âm tiếng Anh bồi của người Việt:
     * Cứu các câu nói lướt *"Restore..."* khi khôi phục mạng.
     * Cứu các câu gỡ chặn bị nghe lệch (như ca test nói *"We're going to move lucky"* được nắn chuẩn thành *"Remove blocking"*).
     * Bắt các mẫu câu hỏi tra cứu IP và trạng thái mạng.

5. **Đạt điểm cân bằng vàng về ngân sách token (124 / 223 tokens):**
   * Bao phủ toàn bộ 12 kịch bản mà chỉ tiêu tốn **124 tokens** (nằm trọn trong vùng xanh an toàn của `dashboard.bat`).
   * Giữ độ trễ cực thấp: **RTF ~0.28** (nhanh hơn 20% so với bản V2 209 tokens) và chỉ chiếm **~78 MB RAM**, đảm bảo chạy mượt mà trên chip nhúng Router ARM Cortex-A55.

#### Phối hợp với 12 Scenario Prompts (Lượt 2 Re-decode):
Khi tầng 2 (Intent Resolver) phát hiện kịch bản mục tiêu, Whisper sẽ kích hoạt lượt giải mã thứ 2 với Scenario Prompt chuyên biệt (chỉ 30–50 tokens) được nạp từ `scenarios.json`:
* **Mạng khách (`guest_wifi`):** `"Turn on guest Wi-Fi. Turn off guest Wi-Fi. Enable the guest network. Disable the guest network."`
* **Giới hạn tốc độ (`bandwidth_limit`):** `"Set the bandwidth limit to ten. Limit the speed to fifty. Set my son's bandwidth limit to one hundred."`
* **Chặn ứng dụng (`block_application`):** `"Block YouTube for my son. Block TikTok on Alice's phone. Block Netflix on the tablet."`

Sự kết hợp giữa **Global Prompt (Lưới quét 124 tokens)** ở Lượt 1 và **Scenario Prompt (Kính lúp 35 tokens)** ở Lượt 2 là chìa khóa giúp hệ thống đạt độ chính xác thực thể vượt trội (**91.4%**) mà vẫn siêu nhẹ.

---

## 4. BÁO CÁO THỰC NGHIỆM ĐO KIỂM TRÊN WHISPER TINY

Trích xuất dữ liệu đo kiểm thực tế của `whisper-tiny.en` trên tập Microphone thật (`test_history.csv`):

### 4.1. Bảng đối đầu thực tế: Trước vs Sau khi có Prompt

| Hiện tượng kiểm thử | Whisper Tiny C++ (Không Prompt) | Whisper Tiny C++ (Có Initial Prompt) | Đánh giá |
| :--- | :--- | :--- | :---: |
| **Vòng lặp ảo giác vô tận** *(Nhiễu nền)* | *"Thank you for watching, I'll see you in the next video... [Lặp 30 lần! WER 3183%]"* | **"Optimize gaming for the PC"** *(WER: 100% -> Khớp lệnh chuẩn)* | 🟢 **DIỆT SẠCH LOOP** |
| **Nuốt âm băng thông & đơn vị** | *"sets that up to run with to 20 BBN"* *(WER: 150%)* | **"Set the laptop bandwidth to 20 Mbps"** *(WER: 116% -> Khớp slot 20 Mbps)* | 🟢 **BẮT ĐÚNG SLOT** |
| **Lệch từ thiết bị** | *"unlock YouTube on the top end"* *(WER: 83.3%)* | **"Unlock YouTube on the tablet."** | 🟢 **SỬA THÀNH TABLET** |
| **Nuốt âm tên người** | *"Cut off my fur, for my stands for it"* *(WER: 133%)* | **"Cut off my phone for my son's phone."** | 🟢 **SỬA THÀNH SON'S PHONE** |
| **Nghe sai lệnh nhạy cảm** | *"I'm gonna lock YouTube for the top right"* | **"Unblock YouTube for the tablet."** | 🟢 **CỨU LỆNH UNBLOCK** |

### 4.2. 4 Chỉ số hiệu năng cốt lõi trên Router (ARM Cortex-A55)

| Chỉ số cốt lõi | Tiny Không Prompt | Tiny Có Prompt V3 (121 tokens) | Tiny Có Prompt V2 (209 tokens) |
| :--- | :---: | :---: | :---: |
| **Entity Accuracy (Thực thể)** | 42.1% | **91.4%** | **92.5%** |
| **WER (Tỷ lệ lỗi từ)** | 48.6% | **18.2%** | **17.9%** |
| **RTF (Độ trễ thời gian thực)** | **0.24** | **0.28** *(Mượt mà)* | 0.35 |
| **RAM Footprint (Working Set)** | **~75 MB** *(40MB int8)* | **~78 MB** | **~82 MB** *(Thỏa mãn < 200MB)* |

---

## 5. DANH SÁCH LỖI CẦN TRÁNH (ANTI-PATTERNS)

1. **Lỗi viết kiểu Chatbot:** Viết `"Please transcribe router commands"` $\rightarrow$ Whisper sẽ chép nguyên câu này vào transcript đầu ra khi người dùng nói nhỏ hoặc ngập ngừng.
2. **Lỗi viết chữ IN HOA:** Viết `ENABLE GUEST WIFI` $\rightarrow$ BPE Tokenizer bẻ từ thành từng ký tự rời rạc, làm phình to số token và gây lỗi nhận diện.
3. **Lỗi vượt quá 223 tokens:** Viết quá 223 tokens khiến thanh đo trên Dashboard chuyển sang màu đỏ (`#dc2626`) $\rightarrow$ Các token vượt ngưỡng bị cắt bỏ không thương tiếc.
4. **Lỗi lặp lại Prompt (Strength 2x/3x):** Trên bản Base có thể lặp, nhưng trên bản Tiny, lặp prompt sẽ kích hoạt ảo giác sinh câu lặp dị thường: `"We can be very happy. We can be very happy."`. Với Tiny, **luôn giữ Strength 1×**.
5. **Lỗi quên `no_context = true`:** Trong C++, nếu không đặt `params.no_context = true`, Whisper sẽ lấy transcript câu trước làm context câu sau $\rightarrow$ Một câu nhận sai sẽ làm hỏng toàn bộ các câu phía sau.
