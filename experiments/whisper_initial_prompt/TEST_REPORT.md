# Báo cáo thử nghiệm: Whisper Prompt vs Không Prompt

**Thời gian xuất báo cáo:** 2026-09-08 11:04:44  
**Tổng số lượt test:** 116 lượt (ESP32_INMP441: 11 câu, MIC: 94 câu, TTS_KOKORO: 11 câu)  

## 1. Tóm tắt hiệu quả của Prompt (So sánh: Không Prompt vs Có Prompt)

| Chỉ số | Số lượng | Tỷ lệ (%) |
|---|---:|---:|
| 🟢 **Tốt hơn (Prompt giúp sửa đúng)** | **45** | **38.8%** |
| 🔴 **Xấu hơn (Prompt gây ảo giác/sai)** | **13** | **11.2%** |
| ⚪ **Không đổi (Cả hai cùng đúng/sai)** | **58** | **50.0%** |

## 2. Bảng kết quả chi tiết từng lượt test

| Thời gian | Nguồn | Kịch bản | Câu chuẩn (Reference) | 1. Không Prompt | 2. Có Prompt | Đánh giá |
|---|:---:|---|---|---|---|:---:|
| 14:28:03 | `MIC` | network_status | Get the connection detail for my phone | That's the condition detail for my phone. *(28.6%)* | Write the connection detail for my phone. *(14.3%)* | 🟢 TỐT HƠN |
| 14:29:02 | `MIC` | network_status | Get the connection detail for my phone | What has IP and data of the laptop? *(114.3%)* | What has an IP administrator of the laptop? *(114.3%)* | ⚪ KHÔNG ĐỔI |
| 14:29:24 | `MIC` | network_status | Get the connection detail for my phone | What are the IP and state that looks like so? *(128.6%)* | router IP and status of laptop. *(100.0%)* | 🟢 TỐT HƠN |
| 14:30:20 | `TTS_KOKORO` | network_status | what are the ip and status of the laptop | What are the IP and status of the laptop? *(0.0%)* | What are the IP and status of the laptop? *(0.0%)* | ⚪ KHÔNG ĐỔI |
| 14:30:51 | `MIC` | network_status | what are the ip and status of the laptop | What are the, what are the IP and state of the drop-up? *(55.6%)* | What are the, what are the IP and state of the laptop? *(44.4%)* | 🟢 TỐT HƠN |
| 14:31:16 | `MIC` | network_status | what are the ip and status of the laptop | What are the, what are the IP and state of the drop-up? *(55.6%)* | What are the, what are the IP and state of the laptop? *(44.4%)* | 🟢 TỐT HƠN |
| 14:31:39 | `MIC` | network_status | what are the ip and status of the laptop | What are the, what are the IP and state of the drop-up? *(55.6%)* | laptop. What are the, what are the IP and status of the laptop? *(44.4%)* | 🟢 TỐT HƠN |
| 14:31:58 | `MIC` | network_status | what are the ip and status of the laptop | What are the IPS Day 3 Pro Selector? *(66.7%)* | app. What are the IPS data? Selector. *(77.8%)* | 🔴 XẤU HƠN |
| 14:32:22 | `MIC` | network_status | what are the ip and status of the laptop | How is it going today? *(100.0%)* | How is network today? *(100.0%)* | ⚪ KHÔNG ĐỔI |
| 14:32:51 | `MIC` | network_status | what are the ip and status of the laptop | Check the internal connoisseur quality. *(88.9%)* | Check the internal condition quality. *(88.9%)* | ⚪ KHÔNG ĐỔI |
| 14:33:13 | `MIC` | network_status | what are the ip and status of the laptop | See the Wi-Fi stable. *(88.9%)* | Wi‑Fi stable. *(100.0%)* | 🔴 XẤU HƠN |
| 14:33:47 | `MIC` | network_status | Limit online game  and show online devices. | Libis online game and so online to fire. *(57.1%)* | release online game and so online to fire. *(57.1%)* | ⚪ KHÔNG ĐỔI |
| 14:34:09 | `MIC` | network_status | Limit online game  and show online devices. | leave it or like give and so on i leave i *(142.9%)* | Libid, online gig, and so online. DeFi. *(57.1%)* | 🟢 TỐT HƠN |
| 14:35:06 | `MIC` | network_status | Limit online game  and show online devices. | enable against Wi-Fi and up on QOSP *(85.7%)* | Open QoS. Open QoS page. *(100.0%)* | 🔴 XẤU HƠN |
| 14:35:35 | `MIC` | network_status | Limit online game  and show online devices. | What is the IP and state of the laptop? *(114.3%)* | What are the IP and Status of the laptop? *(114.3%)* | ⚪ KHÔNG ĐỔI |
| 14:35:56 | `MIC` | network_status | Limit online game  and show online devices. | Get the conditioning detail for my phone. *(100.0%)* | device. Get the connection detail for my phone. *(114.3%)* | 🔴 XẤU HƠN |
| 14:36:18 | `MIC` | network_status | Limit online game  and show online devices. | Optimal dimming for the PC *(100.0%)* | HDMI gaming for the PC. *(100.0%)* | ⚪ KHÔNG ĐỔI |
| 14:36:30 | `MIC` | network_status | Limit online game  and show online devices. | optimally give me for the PC *(100.0%)* | software. Optimize gaming for the PC. *(100.0%)* | ⚪ KHÔNG ĐỔI |
| 14:41:06 | `MIC` | network_status | Limit online game  and show online devices. | What is against my fire passport? *(100.0%)* | What is a guest Wi-Fi a past book? *(114.3%)* | 🔴 XẤU HƠN |
| 10:26:13 | `ESP32_INMP441` | network_status | What is my network status? | Anybody get Wi-Fi, turn up the get, network, fleet, turn the get Wi-Fi on. *(260.0%)* | Enable guest Wi-Fi. Turn off the guest network. Fleet turn the guest Wi-Fi on. *(260.0%)* | ⚪ KHÔNG ĐỔI |
| 10:26:43 | `ESP32_INMP441` | network_status | Enable guest Wi‑Fi.
Turn off the guest network.
Please turn the guest Wi‑Fi on. | Anybody get Wi-Fi, turn up the get, network, fleet, turn the get Wi-Fi on. *(62.5%)* | Enable guest Wi-Fi. Turn off the guest network. Fleet turn the guest Wi-Fi on. *(31.2%)* | 🟢 TỐT HƠN |
| 10:27:27 | `ESP32_INMP441` | network_status | Enable guest Wi‑Fi.
Turn off the guest network.
Please turn the guest Wi‑Fi on. | But it turns out I'll get my fire on. *(93.8%)* | Delete turn the guest Wi-Fi on. *(75.0%)* | 🟢 TỐT HƠN |
| 10:27:37 | `ESP32_INMP441` | network_status | Enable guest Wi‑Fi.
Turn off the guest network.
Please turn the guest Wi‑Fi on. | Please turn the get right back on. *(75.0%)* | Please turn the guest Wi-Fi on. *(68.8%)* | 🟢 TỐT HƠN |
| 10:28:58 | `ESP32_INMP441` | network_status | Enable guest Wi‑Fi.
Turn off the guest network.
Please turn the guest Wi‑Fi on. | Please turn the cast Wi-Fi on. *(75.0%)* | Please turn the guest Wi-Fi on. *(68.8%)* | 🟢 TỐT HƠN |
| 10:33:01 | `ESP32_INMP441` | network_status | Please turn the guest Wi‑Fi on. | Please turn the cast Wi-Fi on. *(42.9%)* | Please turn the guest Wi-Fi on. *(28.6%)* | 🟢 TỐT HƠN |
| 10:33:41 | `ESP32_INMP441` | network_status | Please turn the guest Wi‑Fi on. | leave the phone to 50 MBBS this is the laptop bandwidth to 20 MBBS come to the tablet to make a bit second. Let's try. *(342.9%)* | Limit the phone to fifty and BBS. Set the laptop bandwidth to twenty and BBS. Come to the tablet to make a bit. *(314.3%)* | 🟢 TỐT HƠN |
| 10:34:29 | `ESP32_INMP441` | network_status | Limit the phone to 50 Mbps.
Set the laptop bandwidth to 20 Mbps.
Cap the tablet at 10 megabits per second. | Limit the phone to 50 MBBS, set it up, run with to 20 MBBS, camp the tablet at 10 megabits per second *(33.3%)* | Limit the phone to fifty. Limit to twenty. Limit the tablet at ten. Limit per second. *(38.1%)* | 🔴 XẤU HƠN |
| 11:00:51 | `ESP32_INMP441` | network_status | How is the network today? | It enables a gateway phase to in hopes of getting it work. Please turn the gateway fire on. *(340.0%)* | Enable guest Wi-Fi. Turn off guest network. Please turn the guest Wi-Fi on. *(240.0%)* | 🟢 TỐT HƠN |
| 11:03:33 | `ESP32_INMP441` | network_status | How is the network today? | Leave me the phone to 50 MBBS, set the laptop when we do 20 MBBS, tap the top left 10 megabits per second. *(440.0%)* | Limit the phone to 50 Mbps. Set the laptop bandwidth to 20 Mbps. Cap the tablet at 10 Mbps. *(360.0%)* | 🟢 TỐT HƠN |
| 11:04:24 | `ESP32_INMP441` | network_status | Optimize gaming for the PC.
Boost YouTube on my laptop.
Prioritize Netflix for the smart TV. | I'll take my gaming for the PC, boost YouTube on my laptop, Cryos, dear eye, nep, quick, to fall smarty-bee. *(68.8%)* | Optimize gaming for the PC, boost YouTube on my laptop, prioritize, derive Netflix for smart TV. *(12.5%)* | 🟢 TỐT HƠN |