# Báo cáo thử nghiệm: Sherpa VI Hotwords vs Không Hotwords

**Thời gian xuất báo cáo:** 2026-09-03 16:06:04  
**Tổng số lượt test:** 39 lượt (MIC: 19 câu, TTS_VIENEU: 20 câu)  

## 1. Tóm tắt hiệu quả của Prompt (So sánh: Không Prompt vs Có Prompt)

| Chỉ số | Số lượng | Tỷ lệ (%) |
|---|---:|---:|
| 🟢 **Tốt hơn (Prompt giúp sửa đúng)** | **1** | **2.6%** |
| 🔴 **Xấu hơn (Prompt gây ảo giác/sai)** | **0** | **0.0%** |
| ⚪ **Không đổi (Cả hai cùng đúng/sai)** | **38** | **97.4%** |

## 2. Bảng kết quả chi tiết từng lượt test

| Thời gian | Nguồn | Kịch bản | Câu chuẩn (Reference) | 1. Không Prompt | 2. Có Prompt | Đánh giá |
|---|:---:|---|---|---|---|:---:|
| 13:51:24 | `TTS_VIENEU` | network_status | Kiểm tra ai đang chơi freefire | KIỂM TRA AI ĐANG CHƠI FREEFIER *(16.7%)* | KIỂM TRA AI ĐANG CHƠI FREEFIER *(16.7%)* | ⚪ KHÔNG ĐỔI |
| 13:54:34 | `TTS_VIENEU` | network_status | Bật wifi khách.
Tắt mạng khách đi.
Mở wifi phụ giúp tôi. | BẬT NGOÀI FILE KHÁCH TẮT MẢNG KHÁCH ĐI MỞ NGOẠI PHỤ GIÚP TÔI *(58.3%)* | BẬT NGOÀI FILE KHÁCH TẮT MẢNG KHÁCH ĐI MỞ NGOẠI PHỤ GIÚP TÔI *(58.3%)* | ⚪ KHÔNG ĐỔI |
| 13:54:57 | `TTS_VIENEU` | network_status | Bật wifi khách | BẬT OAI PHAI KHÁCH *(66.7%)* | BẬT OAI PHAI KHÁCH *(66.7%)* | ⚪ KHÔNG ĐỔI |
| 13:58:34 | `TTS_VIENEU` | network_status | Bật wifi khách. | BẬT WIFI KHÁCH *(33.3%)* | BẬT WIFI KHÁCH *(33.3%)* | ⚪ KHÔNG ĐỔI |
| 14:05:39 | `TTS_VIENEU` | network_status | bật điều hoà phòng khách | BẬT ĐIỀU HÒA PHÒNG KHÁCH *(20.0%)* | BẬT ĐIỀU HÒA PHÒNG KHÁCH *(20.0%)* | ⚪ KHÔNG ĐỔI |
| 14:06:22 | `TTS_VIENEU` | network_status | mở bài hát độ ta không độ nàng | MỞ BÀI HÁT ĐỘ TA KHÔNG ĐỘ NÀNG *(0.0%)* | MỞ BÀI HÁT ĐỘ TA KHÔNG ĐỘ NÀNG *(0.0%)* | ⚪ KHÔNG ĐỔI |
| 14:07:00 | `TTS_VIENEU` | network_status | đặt băng thông ở mức mười mê ga bít | ĐẶT BĂNG THÔNG Ở MỨC NGƯỜI MEGABIT *(44.4%)* | ĐẶT BĂNG THÔNG Ở MỨC NGƯỜI MEGABIT *(44.4%)* | ⚪ KHÔNG ĐỔI |
| 14:13:32 | `TTS_VIENEU` | network_status | Trang thai wifi hien tai the nao? | TRẠNG THÁI WIFI HIỆN TẠI THẾ NÀO *(85.7%)* | TRẠNG THÁI WIFI HIỆN TẠI THẾ NÀO *(85.7%)* | ⚪ KHÔNG ĐỔI |
| 14:14:23 | `TTS_VIENEU` | network_status | Bật mạng khách | BẬT MẠNG KHÁCH *(0.0%)* | BẬT MẠNG KHÁCH *(0.0%)* | ⚪ KHÔNG ĐỔI |
| 14:14:57 | `TTS_VIENEU` | network_status | Bật wifi khách.
Tắt mạng khách đi.
Mở wifi phụ giúp tôi. | BẬT WIFI KHÁCH TẮT MẠNG KHÁCH ĐI MỞ WIFI PHỤ GIÚP TÔI *(25.0%)* | BẬT WIFI KHÁCH TẮT MẠNG KHÁCH ĐI MỞ WIFI PHỤ GIÚP TÔI *(25.0%)* | ⚪ KHÔNG ĐỔI |
| 14:23:44 | `TTS_VIENEU` | network_status | Kiểm tra trạng thái mạng hiện tại | KIỂM TRA TRẠNG THÁI MẠNG HIỆN TẠI *(0.0%)* | KIỂM TRA TRẠNG THÁI MẠNG HIỆN TẠI *(0.0%)* | ⚪ KHÔNG ĐỔI |
| 14:24:45 | `TTS_VIENEU` | network_status | Giới hạn băng thông điện thoại xuống 50 Mbps.
Đặt tốc độ laptop ở mức 20 Mbps.
Bóp băng thông máy tính bảng còn 10 Mbps. | GIỚI HẠN BĂNG THÔNG ĐIỆN THOẠI XUỐNG NĂM MƯƠI MEGABIS PERSEN ĐẶT TỐC ĐỘ LAPTOP Ở MỨC HAI MƯƠI MEGABIS PERSEN BÓP BĂNG THÔNG MÁY TÍNH BẢNG CÒN NGƯỜI MEGABIC PERSEN *(42.3%)* | GIỚI HẠN BĂNG THÔNG ĐIỆN THOẠI XUỐNG NĂM MƯƠI MEGABITS PERSEN ĐẶT TỐC ĐỘ LAPTOP Ở MỨC HAI MƯƠI MEGABIS PERSEN BÓP BĂNG THÔNG MÁY TÍNH BẢNG CÒN NGƯỜI MEGABIT PERSEN *(42.3%)* | ⚪ KHÔNG ĐỔI |
| 14:25:20 | `TTS_VIENEU` | network_status | Giới hạn băng thông điện thoại xuống 50.
Đặt tốc độ laptop ở mức 20.
Bóp băng thông máy tính bảng còn 10 | GIỚI HẠN BĂNG THÔNG ĐIỆN THOẠI XUỐNG NĂM MƯƠI ĐẶT TỐC ĐỘ LAPTOP Ở MỨC HAI MƯƠI BÓP BĂNG THÔNG MÁY TÍNH BẢNG CÒN MƯỜI *(21.7%)* | GIỚI HẠN BĂNG THÔNG ĐIỆN THOẠI XUỐNG NĂM MƯƠI ĐẶT TỐC ĐỘ LAPTOP Ở MỨC HAI MƯƠI BÓP BĂNG THÔNG MÁY TÍNH BẢNG CÒN MƯỜI *(21.7%)* | ⚪ KHÔNG ĐỔI |
| 14:26:03 | `TTS_VIENEU` | network_status | Tối ưu game cho máy tính.
Tăng tốc YouTube trên laptop.
Ưu tiên Netflix cho tivi thông minh. | TỐI ƯU GAME CHO MÁY TÍNH TĂNG TỐC ADU TRÊN LAPTOP ƯU TIÊN NETFLIX CHO TV THÔNG MINH *(27.8%)* | TỐI ƯU GAME CHO MÁY TÍNH TĂNG TỐC ALL YOUTUBE TRÊN LAPTOP ƯU TIÊN NETFLIX CHO TV THÔNG MINH *(27.8%)* | ⚪ KHÔNG ĐỔI |
| 14:27:14 | `TTS_VIENEU` | network_status | Tăng tốc YouTube trên laptop. | TĂNG TỐC YOUTUBE TRÊN LAPTOP *(20.0%)* | TĂNG TỐC YOUTUBE TRÊN LAPTOP *(20.0%)* | ⚪ KHÔNG ĐỔI |
| 14:28:04 | `TTS_VIENEU` | network_status | Chặn YouTube trên máy tính bảng.
Cấm TikTok trên điện thoại của con.
Chặn game trên laptop. | CHẶN YOUTUBE TRÊN MÁY TÍNH BẢNG CẮM TIKTOK TRÊN ĐIỆN THOẠI CỦA CON CHẶN GAME TRÊN LAPTOP *(23.5%)* | CHẶN YOUTUBE TRÊN MÁY TÍNH BẢNG CẮM TIKTOK TRÊN ĐIỆN THOẠI CỦA CON CHẶN GAME TRÊN LAPTOP *(23.5%)* | ⚪ KHÔNG ĐỔI |
| 14:28:32 | `MIC` | network_status | Chặn YouTube trên máy tính bảng.
Cấm TikTok trên điện thoại của con.
Chặn game trên laptop. | CẤM TIKTOK CHIA TAY CỦA CON *(82.4%)* | CẤM TIKTOK CHIA TAY CỦA CON *(82.4%)* | ⚪ KHÔNG ĐỔI |
| 14:28:47 | `MIC` | network_status | Chặn YouTube trên máy tính bảng.
Cấm TikTok trên điện thoại của con.
Chặn game trên laptop. | CẤM TIKTOK CHƯA ĐIỆN THOẠI CỦA CON *(70.6%)* | CẤM TIKTOK CHƯA ĐIỆN THOẠI CỦA CON *(70.6%)* | ⚪ KHÔNG ĐỔI |
| 14:29:53 | `MIC` | active_sessions | Ai dang choi game bay gio? | BỎ CHẶN YOUTUBE TRÊN MÁY TÍNH BẢNG *(116.7%)* | BỎ CHẶN YOUTUBE TRÊN MÁY TÍNH BẢNG *(116.7%)* | ⚪ KHÔNG ĐỔI |
| 14:30:22 | `MIC` | active_sessions | Ai dang choi game bay gio? | LIỆT KÊ THIẾT BỊ TA DÙNG WHI FILE *(133.3%)* | LIỆT KÊ THIẾT BỊ TA DÙNG WHI FILE *(133.3%)* | ⚪ KHÔNG ĐỔI |
| 14:41:31 | `MIC` | network_status | Trang thai mang hien tai the nao? | KHOAI PHAI KHÁCH *(100.0%)* | KHWIFI KHÁCH *(100.0%)* | ⚪ KHÔNG ĐỔI |
| 14:41:43 | `MIC` | network_status | Trang thai mang hien tai the nao? | KHOAI FILE KHÁCH *(100.0%)* | KHOAI FILE KHÁCH *(100.0%)* | ⚪ KHÔNG ĐỔI |
| 14:41:52 | `MIC` | network_status | Trang thai mang hien tai the nao? | KHOAI KHOAI KHÁCH *(100.0%)* | KHOAI KHOAI KHÁCH *(100.0%)* | ⚪ KHÔNG ĐỔI |
| 14:42:15 | `MIC` | guest_wifi | Bat wifi khach. | NGOÀI FILE KHÁCH *(100.0%)* | NGOÀI FILE KHÁCH *(100.0%)* | ⚪ KHÔNG ĐỔI |
| 14:42:27 | `MIC` | guest_wifi | Bat wifi khach. | WIFI *(66.7%)* | WIFI *(66.7%)* | ⚪ KHÔNG ĐỔI |
| 14:42:35 | `MIC` | guest_wifi | Bat wifi khach. | NGOÀI FILE KHÁCH *(100.0%)* | NGOÀI FI KHÁCH *(100.0%)* | ⚪ KHÔNG ĐỔI |
| 14:42:46 | `MIC` | guest_wifi | Bat wifi khach. | WIFI KHÁCH *(66.7%)* | WIFI KHÁCH *(66.7%)* | ⚪ KHÔNG ĐỔI |
| 14:52:48 | `MIC` | guest_wifi | Bat wifi khach. | ĐẶT TỐC ĐỘ BẰNG ĐỒNG ĐIỆN THOẠI Ở MỨC HAI MƯƠI MEGAM BEAT PERCI CÂN *(500.0%)* | ĐẶT TỐC ĐỘ BẰNG ĐỒNG ĐIỆN THOẠI Ở MỨC HAI MƯƠI MEGABIT PERCED *(433.3%)* | 🟢 TỐT HƠN |
| 14:53:13 | `MIC` | guest_wifi | Bat wifi khach. | ĐẶT TỐC ĐỘ BẰNG THÔNG ĐIỆN THOẠI Ở MỨC HAI MƯƠI MEGABIT BIRSEN *(433.3%)* | ĐẶT TỐC ĐỘ BẰNG THÔNG ĐIỆN THOẠI Ở MỨC HAI MƯƠI MEGABIT BIRSEN *(433.3%)* | ⚪ KHÔNG ĐỔI |
| 16:05:33 | `TTS_VIENEU` | network_status | kiểm tra chất lượng kết nói in tơ nét | KIỂM TRA CHẤT LƯỢNG KẾT NỐI INTERNET *(44.4%)* | KIỂM TRA CHẤT LƯỢNG KẾT NỐI INTERNET *(44.4%)* | ⚪ KHÔNG ĐỔI |