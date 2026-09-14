# Báo cáo Benchmark Tập Dữ Liệu (tiny.en)

**Thời gian xuất báo cáo:** 2026-09-14 16:11:35  
**Tổng số lượt test:** 52 lượt (DATASET_BATCH: 52 câu)  

## 1. Tóm tắt hiệu quả của Prompt (So sánh: Không Prompt vs Có Prompt)

| Chỉ số | Số lượng | Tỷ lệ (%) |
|---|---:|---:|
| 🟢 **Tốt hơn (Prompt giúp sửa đúng)** | **34** | **65.4%** |
| 🔴 **Xấu hơn (Prompt gây ảo giác/sai)** | **4** | **7.7%** |
| ⚪ **Không đổi (Cả hai cùng đúng/sai)** | **14** | **26.9%** |

## 2. Bảng kết quả chi tiết từng lượt test

| Thời gian | Nguồn | Câu chuẩn (Reference) | 1. Không Prompt | 2. Global Prompt | 3. Global + Logit Bias | Đánh giá |
|---|:---:|---|---|---|---|:---:|
| 15:52:22 | `DATASET_BATCH` | Wake me up at 7 AM. | Wake me up at 7 a.m. *(33.3%)* | Wake me up at 7am. *(33.3%)* | Wake me up at 7am. *(33.3%)* | ⚪ KHÔNG ĐỔI |
| 15:52:26 | `DATASET_BATCH` | Turn on the lights and Turn off the TV. | Turn on the line and turn off the TV. *(11.1%)* | Turn on the line and turn off the TV. *(11.1%)* | Turn on the line and turn off the TV. *(11.1%)* | ⚪ KHÔNG ĐỔI |
| 15:52:29 | `DATASET_BATCH` | Is the router connected to the internet | Is the router connected to the internet? *(0.0%)* | Use the router connected to the internet. *(14.3%)* | Use the router connected to the internet. *(14.3%)* | 🔴 XẤU HƠN |
| 15:52:34 | `DATASET_BATCH` | Why is the Wi-Fi so slow on my phone today? | Why is a Wi-Fi so slow on my phone today? *(10.0%)* | Wi-Fi is Wi-Fi. So slow on my phone today. *(20.0%)* | Wi-Fi is Wi-Fi so slow on my phone today. *(20.0%)* | 🔴 XẤU HƠN |
| 16:10:21 | `DATASET_BATCH` | enable the guest Wi-Fi | Anybows cast Wi-Fi. *(75.0%)* | Enable the guest Wi-Fi. *(0.0%)* | Enable guest Wi-Fi. *(25.0%)* | 🟢 TỐT HƠN |
| 16:10:25 | `DATASET_BATCH` | Please turn the guest Wi‑Fi on | Please, do the cast Wi-Fi on. *(33.3%)* | Please do the guest Wi-Fi on. *(16.7%)* | Please do the guest Wi-Fi on. *(16.7%)* | 🟢 TỐT HƠN |
| 16:10:29 | `DATASET_BATCH` | Limit the phone to 50 Mbps. | Limit the phone to 50MBP. *(33.3%)* | Limit the phone to 50 Mbps. *(0.0%)* | Limit the phone to 50 Mbps. *(0.0%)* | 🟢 TỐT HƠN |
| 16:10:34 | `DATASET_BATCH` | Optimize gaming for the PC. | Happy making me to follow the PC. *(100.0%)* | How do you make gaming for the PC? *(80.0%)* | How do you make gaming for the PC? *(80.0%)* | 🟢 TỐT HƠN |
| 16:10:38 | `DATASET_BATCH` | Boost YouTube on my laptop. | post youtube on my laptop *(20.0%)* | Boost YouTube on my laptop. *(0.0%)* | Boost YouTube on my laptop. *(0.0%)* | 🟢 TỐT HƠN |
| 16:10:41 | `DATASET_BATCH` | Block YouTube for the tablet. | Blops you too, before they start playing. *(140.0%)* | Block YouTube for the tablet. *(0.0%)* | Block YouTube for the tablet. *(0.0%)* | 🟢 TỐT HƠN |
| 16:10:44 | `DATASET_BATCH` | Prevent gaming on the laptop. | pretty well giving me on the laptop *(80.0%)* | Prevent gaming on the laptop. *(0.0%)* | Prevent gaming on the laptop. *(0.0%)* | 🟢 TỐT HƠN |
| 16:10:46 | `DATASET_BATCH` | Disable internet access on the guest laptop. | This is the whole internet access and the guest laptop. *(71.4%)* | Instable internet access to the guest laptop. *(28.6%)* | Instable internet access to the guest laptop. *(28.6%)* | 🟢 TỐT HƠN |
| 16:10:49 | `DATASET_BATCH` | Restore Wi‑Fi access to my phone. | restow if I was asked to my phone *(83.3%)* | Restore Wi-Fi access to my phone. *(0.0%)* | Restore Wi-Fi access to my phone. *(0.0%)* | 🟢 TỐT HƠN |
| 16:10:52 | `DATASET_BATCH` | Let the laptop connect to the internet | Last, we'll have to connect to the internet. *(57.1%)* | Last laptop connect to the internet. *(28.6%)* | Less laptop connectivity internet. *(71.4%)* | 🔴 XẤU HƠN |
| 16:10:55 | `DATASET_BATCH` | Who is video call  right now? | Oh, it's a video call right now. *(50.0%)* | Oh, it's a video call right now. *(50.0%)* | Oh, it's a video call right now. *(50.0%)* | ⚪ KHÔNG ĐỔI |
| 16:10:57 | `DATASET_BATCH` | List the devices currently using Wi‑Fi. | list the defect currently using Wi-Fi. *(16.7%)* | List the device currently using Wi-Fi. *(16.7%)* | List the device currently using Wi-Fi. *(16.7%)* | ⚪ KHÔNG ĐỔI |
| 16:11:00 | `DATASET_BATCH` | Check the router status. | check the router's data. *(50.0%)* | Check the router status. *(0.0%)* | Check the router status. *(0.0%)* | 🟢 TỐT HƠN |
| 16:11:02 | `DATASET_BATCH` | Show my gateway information. | Show my good-good information. *(25.0%)* | Show my gateway information. *(0.0%)* | Show my gateway information. *(0.0%)* | 🟢 TỐT HƠN |
| 16:11:05 | `DATASET_BATCH` | What is the router uptime? | What is the router uptime? *(0.0%)* | What is the router uptime? *(0.0%)* | What is the router uptime? *(0.0%)* | ⚪ KHÔNG ĐỔI |
| 16:11:07 | `DATASET_BATCH` | Show device info for the tablet. | Show the defying forward with the top left. *(100.0%)* | Show the device info for the tablet. *(16.7%)* | Show the device info for the tablet. *(16.7%)* | 🟢 TỐT HƠN |
| 16:11:10 | `DATASET_BATCH` | Get the connection details for my phone. | Get the condition detailed for my phone. *(28.6%)* | Get the connection details for my phone. *(0.0%)* | Get the connection details for my phone. *(0.0%)* | 🟢 TỐT HƠN |
| 16:11:13 | `DATASET_BATCH` | What are the IP and status of the laptop? | What are the IP status of the laptop? *(11.1%)* | What are the IP and status of the laptop? *(0.0%)* | What are the IP and status of the laptop? *(0.0%)* | 🟢 TỐT HƠN |
| 16:11:15 | `DATASET_BATCH` | How is the network today? | How is the network today? *(0.0%)* | How is the network today? *(0.0%)* | How is the network today? *(0.0%)* | ⚪ KHÔNG ĐỔI |
| 16:11:18 | `DATASET_BATCH` | Check the internet connection quality. | Check the internet condition quality. *(20.0%)* | Check the internet connection quality. *(0.0%)* | Check the internet connection quality. *(0.0%)* | 🟢 TỐT HƠN |
| 16:11:20 | `DATASET_BATCH` | Is the Wi‑Fi stable? | is the way fast stable. *(50.0%)* | Is the Wi-Fi stable? *(0.0%)* | Is the Wi-Fi stable? *(0.0%)* | 🟢 TỐT HƠN |
| 16:11:23 | `DATASET_BATCH` | What time is it and what's the weather today? | What time is it and what is the weather today? *(22.2%)* | What time is it? And what is the weather today? *(22.2%)* | What time is it? And what is the Wi-Fi today? *(33.3%)* | 🔴 XẤU HƠN |
| 16:11:26 | `DATASET_BATCH` | Wake me up at 7 AM. | Wake me up at 7 a.m. *(33.3%)* | Wake me up at 7am. *(33.3%)* | Wake me up at 7am. *(33.3%)* | ⚪ KHÔNG ĐỔI |
| 16:11:29 | `DATASET_BATCH` | Turn on the lights and Turn off the TV. | Turn on the line and turn off the TV. *(11.1%)* | Turn on the line and turn off the TV. *(11.1%)* | Turn on the line and turn off the TV. *(11.1%)* | ⚪ KHÔNG ĐỔI |
| 16:11:32 | `DATASET_BATCH` | Is the router connected to the internet | Is the router connected to the internet? *(0.0%)* | Is the router connected to the internet? *(0.0%)* | Is the router connected to the internet? *(0.0%)* | ⚪ KHÔNG ĐỔI |
| 16:11:35 | `DATASET_BATCH` | Why is the Wi-Fi so slow on my phone today? | Why is a Wi-Fi so slow on my phone today? *(10.0%)* | Why is the Wi-Fi so slow on my phone today? *(0.0%)* | Why is the Wi-Fi so slow on my phone today? *(0.0%)* | 🟢 TỐT HƠN |