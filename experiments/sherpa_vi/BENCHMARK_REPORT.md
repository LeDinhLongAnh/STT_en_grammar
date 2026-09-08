# Báo cáo Benchmark Tự Động: TTS + Sherpa-ONNX

| STT | Câu gốc (TTS) | Ô 1: Không Prompt | Ô 3: Auto Scenario (Phonetic Biasing) | Kịch bản chốt hạ |
|---|---|---|---|---|
| 1 | Bật wifi khách | MẬT OAI PHAI KHÁCH | **MẬT WIFI KHÁCH** | ✅ `guest_wifi` |
| 2 | Tắt mạng khách đi | TẮT MẠNG KHÁCH ĐI | **TẮT MẠNG KHÁCH ĐI** | ✅ `guest_wifi` |
| 3 | Mở wifi phụ giúp tôi | MỞ WIFI PHỤ GIÚP TÔI | **MỞ WIFI PHỤ GIÚP TÔI** | ✅ `guest_wifi` |
| 4 | Giới hạn băng thông điện thoại xuống 50 Mbps | GIỚI HẠN BẰNG THÔNG ĐIỆN THOẠI XUỐNG NĂM MƯƠI MEGAP PERSEN | **GIỚI HẠN BẰNG THÔNG ĐIỆN THOẠI XUỐNG NĂM MƯƠI MEGAP PERSEN** | ❌ `None` |
| 5 | Đặt tốc độ laptop ở mức 20 Mbps | ĐẶT TỐC ĐỘ LAPTOP Ở MỨC HAI MƯƠI MEGABIS PERSE CẦN | **ĐẶT TỐC ĐỘ LAPTOP Ở MỨC HAI MƯƠI MEGABITS PERSON** | ✅ `bandwidth_limit` |
| 6 | Bóp băng thông máy tính bảng còn 10 Mbps | BÓP BĂNG THÔNG MÁY TÍNH BẢNG CÒN MƯỜI MECCA SECOND | **BÓP BĂNG THÔNG MÁY TÍNH BẢNG CÒN MƯỜI MEGA SECOND** | ✅ `bandwidth_limit` |
| 7 | Tối ưu game cho máy tính | TỐI ƯU GHẸM CHO MÁY TÍNH | **TỐI ƯU GAME CHO MÁY TÍNH** | ✅ `optimize_app` |
| 8 | Tăng tốc YouTube trên laptop | TĂNG TỐC YOUTUBE TRÊN LAPTOP | **TĂNG TỐC YOUTUBE TRÊN LAPTOP** | ✅ `optimize_app` |
| 9 | Ưu tiên Netflix cho tivi thông minh | ƯU TIÊN NETFLIX CHO THI VỊ THÔNG MINH | **ƯU TIÊN NETFLIX CHO THI VỊ THÔNG MINH** | ✅ `optimize_app` |
| 10 | Chặn YouTube trên máy tính bảng | DẠNG YOUTUBE TRÊN MÁY TÍNH BẢNG | **DẠNG YOUTUBE TRÊN MÁY TÍNH BẢNG** | ❌ `None` |
| 11 | Cấm TikTok trên điện thoại của con | CẤM TIKTOK TRÊN ĐIỆN THOẠI CỦA CON | **CẤM TIKTOK TRÊN ĐIỆN THOẠI CỦA CON** | ✅ `block_application` |
| 12 | Chặn game trên laptop | CHẶN GAME TRÊN LAPTOP | **CHẶN GAME TRÊN LAPTOP** | ✅ `block_application` |
| 13 | Bỏ chặn YouTube trên máy tính bảng | BỎ CHẶN YOUTUBE TRÊN MÁY TÍNH BẢNG | **BỎ CHẶN YOUTUBE TRÊN MÁY TÍNH BẢNG** | ✅ `unblock_application` |
| 14 | Cho phép TikTok trên điện thoại lại | CHO PHÉP TIKTOK TRÊN ĐIỆN THOẠI LẠI | **CHO PHÉP TIKTOK TRÊN ĐIỆN THOẠI LẠI** | ❌ `None` |
| 15 | Gỡ chặn game trên laptop | GỬI CHẶN GAME TRÊN LAPTOP | **GỬI CHẶN GAME TRÊN LAPTOP** | ✅ `block_application` |
| 16 | Chặn mạng cho máy tính bảng | CHẶN MẠNG CHO MÁY TÍNH BẢNG | **CHẶN MẠNG CHO MÁY TÍNH BẢNG** | ✅ `block_internet` |
| 17 | Tắt Wi-Fi trên điện thoại của con | CÁC WIFI TRÊN ĐIỆN THOẠI CỦA CON | **CÁC WIFI TRÊN ĐIỆN THOẠI CỦA CON** | ❌ `None` |
| 18 | Cắt truy cập internet của laptop khách | CÁC TRUY CẬP INTERNET CỦA LAPTOP KHÁCH | **CÁC TRUY CẬP INTERNET CỦA LAPTOP KHÁCH** | ❌ `None` |
| 19 | Mở mạng cho máy tính bảng | MỞ MẠNG CHO MÁY TÍNH BẢNG | **MỞ MẠNG CHO MÁY TÍNH BẢNG** | ❌ `None` |
| 20 | Cho điện thoại kết nối Wi-Fi lại | CHO ĐIỆN THOẠI KẾT NỐI OAI PHAI LẠI | **CHO ĐIỆN THOẠI KẾT NỐI OAI PHAI LẠI** | ❌ `None` |
| 21 | Cho laptop vào internet bình thường | CHO APPORT VÀ INTERNET BÌNH THƯỜNG | **CHO APPORT VÀ INTERNET BÌNH THƯỜNG** | ❌ `None` |
| 22 | Ai đang chơi game | AI ĐANG CHƠI GAME | **AI ĐANG CHƠI GAME** | ✅ `active_sessions` |
| 23 | Thiết bị nào đang chơi game | THIẾT BỊ NÀO ĐANG CHƠI GAME | **THIẾT BỊ NÀO ĐANG CHƠI GAME** | ❌ `None` |
| 24 | Cho tôi xem các phiên chơi game đang hoạt động | CHO TÔI XEM CÁC PHIÊN CHƠI GAME ĐANG HOẠT ĐỘNG | **CHO TÔI XEM CÁC PHIÊN CHƠI GAME ĐANG HOẠT ĐỘNG** | ❌ `None` |
| 25 | Có những thiết bị nào đang kết nối | CÓ NHỮNG THIẾT BỊ NÀO ĐANG KẾT NỐI | **CÓ NHỮNG THIẾT BỊ NÀO ĐANG KẾT NỐI** | ✅ `online_devices` |