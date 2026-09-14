# Báo cáo thử nghiệm: Whisper Prompt vs Không Prompt

**Thời gian xuất báo cáo:** 2026-09-14 15:48:16  
**Tổng số lượt test:** 26 lượt (DATASET_BATCH: 26 câu)  

## 1. Tóm tắt hiệu quả của Prompt (So sánh: Không Prompt vs Có Prompt)

| Chỉ số | Số lượng | Tỷ lệ (%) |
|---|---:|---:|
| 🟢 **Tốt hơn (Prompt giúp sửa đúng)** | **15** | **57.7%** |
| 🔴 **Xấu hơn (Prompt gây ảo giác/sai)** | **4** | **15.4%** |
| ⚪ **Không đổi (Cả hai cùng đúng/sai)** | **7** | **26.9%** |

## 2. Bảng kết quả chi tiết từng lượt test

| Thời gian | Nguồn | Câu chuẩn (Reference) | 1. Không Prompt | 2. Global Prompt | 3. Global + Logit Bias | Đánh giá |
|---|:---:|---|---|---|---|:---:|
| 15:46:09 | `DATASET_BATCH` | enable the guest Wi-Fi | And it blows against Wi-Fi. *(100.0%)* | Enable guest Wi-Fi. *(25.0%)* | Enable guest Wi-Fi. *(25.0%)* | 🟢 TỐT HƠN |
| 15:46:14 | `DATASET_BATCH` | Please turn the guest Wi‑Fi on | Please, don't cast Wi-Fi on. *(50.0%)* | Please turn the guest Wi-Fi on. *(0.0%)* | Please turn the guest Wi-Fi on. *(0.0%)* | 🟢 TỐT HƠN |
| 15:46:18 | `DATASET_BATCH` | Limit the phone to 50 Mbps. | Limit the phone to 50 MBBN. *(16.7%)* | Limit the phone to 50 Mbps. *(0.0%)* | Limit the phone to 50 Mbps. *(0.0%)* | 🟢 TỐT HƠN |
| 15:46:23 | `DATASET_BATCH` | Optimize gaming for the PC. | automatic aiming to follow the PC. *(80.0%)* | Optimize gaming for the PC. *(0.0%)* | Optimize gaming for the PC. *(0.0%)* | 🟢 TỐT HƠN |
| 15:46:27 | `DATASET_BATCH` | Boost YouTube on my laptop. | Post YouTube on my laptop. *(20.0%)* | Boost YouTube on my laptop. *(0.0%)* | Boost YouTube on my laptop. *(0.0%)* | 🟢 TỐT HƠN |
| 15:46:32 | `DATASET_BATCH` | Block YouTube for the tablet. | Blocked YouTube for the top plate. *(60.0%)* | Block YouTube for the tablet. *(0.0%)* | Block YouTube for the tablet. *(0.0%)* | 🟢 TỐT HƠN |
| 15:46:36 | `DATASET_BATCH` | Prevent gaming on the laptop. | preview and gaming on the laptop *(40.0%)* | Prevent gaming on the laptop. *(0.0%)* | Prevent gaming on the laptop. *(0.0%)* | 🟢 TỐT HƠN |
| 15:46:48 | `DATASET_BATCH` | Disable internet access on the guest laptop. | Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, Instagram, *(742.9%)* | Listable internet access and the guest laptop. *(28.6%)* | Listable internet access and guest laptop. *(42.9%)* | 🟢 TỐT HƠN |
| 15:46:53 | `DATASET_BATCH` | Restore Wi‑Fi access to my phone. | Re-style I file a set to my phone. *(83.3%)* | Restore Wi-Fi access to my phone. *(0.0%)* | Restore Wi-Fi access to my phone. *(0.0%)* | 🟢 TỐT HƠN |
| 15:46:57 | `DATASET_BATCH` | Let the laptop connect to the internet | Let the laptop connect to the internet. *(0.0%)* | Last laptop connect to the internet. *(28.6%)* | Let's laptop connect to internet. *(42.9%)* | 🔴 XẤU HƠN |
| 15:47:02 | `DATASET_BATCH` | Who is video call  right now? | All is video code right now. *(33.3%)* | All is video code right now. *(33.3%)* | All is video code right now. *(33.3%)* | ⚪ KHÔNG ĐỔI |
| 15:47:07 | `DATASET_BATCH` | List the devices currently using Wi‑Fi. | List the device currently using Wi-Fi. *(16.7%)* | List the device currently using Wi-Fi. *(16.7%)* | List the device currently using Wi-Fi. *(16.7%)* | ⚪ KHÔNG ĐỔI |
| 15:47:11 | `DATASET_BATCH` | Check the router status. | Check the router's data. *(50.0%)* | Check the router status. *(0.0%)* | Check the router status. *(0.0%)* | 🟢 TỐT HƠN |
| 15:47:15 | `DATASET_BATCH` | Show my gateway information. | Show my good quality information. *(50.0%)* | Show my gateway information. *(0.0%)* | Show my gateway information. *(0.0%)* | 🟢 TỐT HƠN |
| 15:47:20 | `DATASET_BATCH` | What is the router uptime? | One is the router uptime. *(20.0%)* | One is router uptime. *(40.0%)* | What is the router uptime? *(0.0%)* | 🟢 TỐT HƠN |
| 15:47:25 | `DATASET_BATCH` | Show device info for the tablet. | Show the defi in 4 for the top lead. *(100.0%)* | Show the device info for the tablet. *(16.7%)* | Show device info for the tablet. *(0.0%)* | 🟢 TỐT HƠN |
| 15:47:30 | `DATASET_BATCH` | Get the connection details for my phone. | That's the connection detail for my phone. *(28.6%)* | Get the connection details for my phone. *(0.0%)* | Get the connection details for my phone. *(0.0%)* | 🟢 TỐT HƠN |
| 15:47:35 | `DATASET_BATCH` | What are the IP and status of the laptop? | What are the IP status of laptop? *(22.2%)* | What are the IP and status of the laptop? *(0.0%)* | What are the IP and status of laptop? *(11.1%)* | 🟢 TỐT HƠN |
| 15:47:39 | `DATASET_BATCH` | How is the network today? | How is the network today? *(0.0%)* | How is the network today? *(0.0%)* | How is the network today? *(0.0%)* | ⚪ KHÔNG ĐỔI |
| 15:47:44 | `DATASET_BATCH` | Check the internet connection quality. | Check the internet connection quality. *(0.0%)* | Check the internet connection quality. *(0.0%)* | Check internet connection quality. *(20.0%)* | 🔴 XẤU HƠN |
| 15:47:49 | `DATASET_BATCH` | Is the Wi‑Fi stable? | Use the Wi-Fi Stable. *(25.0%)* | Use the Wi-Fi stable. *(25.0%)* | Use the Wi-Fi stable. *(25.0%)* | ⚪ KHÔNG ĐỔI |
| 15:47:54 | `DATASET_BATCH` | What time is it and what's the weather today? | What time is it and what is the weather today? *(22.2%)* | What time is it and what is the weather today? *(22.2%)* | What time is it and what is the weather today? *(22.2%)* | ⚪ KHÔNG ĐỔI |
| 15:47:59 | `DATASET_BATCH` | Wake me up at 7 AM. | wake me up at 7am *(33.3%)* | Wake me up at 7am. *(33.3%)* | Wake me up at 7am. *(33.3%)* | ⚪ KHÔNG ĐỔI |
| 15:48:05 | `DATASET_BATCH` | Turn on the lights and Turn off the TV. | Turn on the line and turn off the TV. *(11.1%)* | Turn on the line and turn off the TV. *(11.1%)* | Turn on the line and turn off the TV. *(11.1%)* | ⚪ KHÔNG ĐỔI |
| 15:48:10 | `DATASET_BATCH` | Is the router connected to the internet | Is the router connected to the internet? *(0.0%)* | Is the router connected to the internet? *(0.0%)* | Is the router connected to internet? *(14.3%)* | 🔴 XẤU HƠN |
| 15:48:16 | `DATASET_BATCH` | Why is the Wi-Fi so slow on my phone today? | Why is a Wi-Fi so slow on my phone today? *(10.0%)* | Why is a Wi-Fi so slow on my phone today? *(10.0%)* | Wi is a Wi-Fi. So slow on my phone today. *(20.0%)* | 🔴 XẤU HƠN |