# Báo cáo thử nghiệm: Whisper Prompt vs Không Prompt

**Thời gian xuất báo cáo:** 2026-09-08 14:47:05  
**Tổng số lượt test:** 223 lượt (ESP32_INMP441: 116 câu, MIC: 94 câu, TTS_KOKORO: 13 câu)  

## 1. Tóm tắt hiệu quả của Prompt (So sánh: Không Prompt vs Có Prompt)

| Chỉ số | Số lượng | Tỷ lệ (%) |
|---|---:|---:|
| 🟢 **Tốt hơn (Prompt giúp sửa đúng)** | **107** | **48.0%** |
| 🔴 **Xấu hơn (Prompt gây ảo giác/sai)** | **14** | **6.3%** |
| ⚪ **Không đổi (Cả hai cùng đúng/sai)** | **102** | **45.7%** |

## 2. Bảng kết quả chi tiết từng lượt test

| Thời gian | Nguồn | Kịch bản | Câu chuẩn (Reference) | 1. Không Prompt | 2. Có Prompt | Đánh giá |
|---|:---:|---|---|---|---|:---:|
| 14:34:12 | `ESP32_INMP441` | network_status | Stop TikTok on my child's phone. | Just don't think that one might try the phone. *(133.3%)* | Stock TikTok on my childhood phone. *(33.3%)* | 🟢 TỐT HƠN |
| 14:34:21 | `ESP32_INMP441` | network_status | Stop TikTok on my child's phone. | Stop the tuck on my sharpened phone. *(50.0%)* | Stop TikTok on my child's phone. *(0.0%)* | 🟢 TỐT HƠN |
| 14:34:34 | `ESP32_INMP441` | network_status | Stop TikTok on my child's phone. | Blocked you tool for the template. *(100.0%)* | Block YouTube for the tablet. *(100.0%)* | ⚪ KHÔNG ĐỔI |
| 14:34:44 | `ESP32_INMP441` | network_status | Stop TikTok on my child's phone. | varieties are in the plate for the smat TV. *(150.0%)* | For IoT side, Netflix for the smart TV. *(133.3%)* | 🟢 TỐT HƠN |
| 14:34:52 | `ESP32_INMP441` | network_status | Stop TikTok on my child's phone. | priority sign *(100.0%)* | Prior design. *(100.0%)* | ⚪ KHÔNG ĐỔI |
| 14:35:29 | `ESP32_INMP441` | network_status | Stop TikTok on my child's phone. | by a retired *(100.0%)* | Pay a retail. *(100.0%)* | ⚪ KHÔNG ĐỔI |
| 14:35:35 | `ESP32_INMP441` | network_status | Stop TikTok on my child's phone. | Brioree's tie. *(100.0%)* | Brio restai. *(100.0%)* | ⚪ KHÔNG ĐỔI |
| 14:36:03 | `ESP32_INMP441` | network_status | Stop TikTok on my child's phone. | both YouTube on my laptop. *(66.7%)* | Both YouTube on my laptop. *(66.7%)* | ⚪ KHÔNG ĐỔI |
| 14:36:10 | `ESP32_INMP441` | network_status | Stop TikTok on my child's phone. | both YouTube on my laptop. *(66.7%)* | Boost YouTube on my laptop. *(66.7%)* | ⚪ KHÔNG ĐỔI |
| 14:36:21 | `ESP32_INMP441` | network_status | Stop TikTok on my child's phone. | up to my gaming for that PC *(116.7%)* | Optimize gaming for the PC. *(100.0%)* | 🟢 TỐT HƠN |
| 14:40:29 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | I'll re-tie, template for the Smat TV. *(66.7%)* | Cry over time. Netflix for the smart TV. *(50.0%)* | 🟢 TỐT HƠN |
| 14:40:41 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | pry or retype, Netflix for the Smat TV. *(66.7%)* | Try or restart Netflix for the smart TV. *(50.0%)* | 🟢 TỐT HƠN |
| 14:40:48 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | But I'll restate. *(100.0%)* | But I already stay. *(100.0%)* | ⚪ KHÔNG ĐỔI |
| 14:41:14 | `TTS_KOKORO` | network_status | Prioritize Netflix for the smart TV. | Prioritize Netflix for the smart TV. *(0.0%)* | Prioritize Netflix for the smart TV. *(0.0%)* | ⚪ KHÔNG ĐỔI |
| 14:41:35 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | but I will do a tiny flick for this active V. *(166.7%)* | Browse your tiny Netflix for the smart TV. *(50.0%)* | 🟢 TỐT HƠN |
| 14:41:45 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | I always tie the plate for the Smart TV. *(83.3%)* | Try always time and play for the smart TV. *(83.3%)* | ⚪ KHÔNG ĐỔI |
| 14:42:24 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | I'll see you in the next video, I'll see you in the next video, I'll see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, see you in the next video, *(3133.3%)* | Optimizing for the PC. *(66.7%)* | 🟢 TỐT HƠN |
| 14:42:51 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | I'll see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the next video, see you guys in the *(3233.3%)* | Optimize gaming for the PC. *(66.7%)* | 🟢 TỐT HƠN |
| 14:43:12 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | and block internet for the entire plate. *(83.3%)* | And Block internet for the tablet. *(83.3%)* | ⚪ KHÔNG ĐỔI |
| 14:43:20 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | and below internet for the top left. *(83.3%)* | Unblock internet for the tablet. *(66.7%)* | 🟢 TỐT HƠN |
| 14:44:00 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | I advertise gaming for the PC. *(83.3%)* | Prioritize gaming for the PC. *(50.0%)* | 🟢 TỐT HƠN |
| 14:44:11 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | right or right I'm aiming for the PC *(116.7%)* | Ride or retargeting for the PC. *(83.3%)* | 🟢 TỐT HƠN |
| 14:44:19 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | but I always tell you we have been for the B.C. *(166.7%)* | But I always tell you we have been for the PC. *(166.7%)* | ⚪ KHÔNG ĐỔI |
| 14:44:40 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | And they will guess if I end up in the QA pit. *(183.3%)* | Enable guest Wi-Fi and open the key Wi-Fi. *(116.7%)* | 🟢 TỐT HƠN |
| 14:44:52 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | below you took on the tablet and check it out as stated *(183.3%)* | Blow you took on the tablet and check your router status. *(166.7%)* | 🟢 TỐT HƠN |
| 14:45:09 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | limit on light game and so on lighty right *(150.0%)* | Limit online game and so on. Let me write. *(150.0%)* | ⚪ KHÔNG ĐỔI |
| 14:45:25 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | leave me on my game and show on lydivite *(150.0%)* | Limit online game and show online device. *(116.7%)* | 🟢 TỐT HƠN |
| 14:45:47 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | Tap, tap, tap, tap, tap, tap, tap, tap, tap, tap, tap, tap, tap, tap, tap, tap, tap, *(283.3%)* | Tap the tablet and make a beat post here. *(150.0%)* | 🟢 TỐT HƠN |
| 14:45:59 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | Cut the template a 10 megapit per second. *(133.3%)* | Copy the tablet at 10 Mbps. *(100.0%)* | 🟢 TỐT HƠN |
| 14:46:12 | `ESP32_INMP441` | network_status | Prioritize Netflix for the smart TV. | I'm going to tap the top left at 10 mb per second. *(183.3%)* | Type the tablet at 10 Mbps. *(100.0%)* | 🟢 TỐT HƠN |