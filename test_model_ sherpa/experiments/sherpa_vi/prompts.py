# -*- coding: utf-8 -*-
"""
Các prompt dùng để ghép ngữ cảnh khi test model NLU router/Wi-Fi.
Sửa nội dung trực tiếp trong file này — script test_model.py sẽ import từ đây.
"""

SYSTEM_PROMPT = """Bạn là trợ lý điều khiển router / Wi-Fi gia đình.
Đọc câu hỏi tiếng Việt của người dùng, xác định intent và entity, CHỈ trả lời bằng đúng 1 dòng JSON, không thêm chữ nào khác:
{"intent": "...", "device": "...", "app": "...", "value": ""}
Nếu không có thông tin thì để chuỗi rỗng "". Không giải thích, không thêm câu chào."""

# Global Prompt: áp dụng cho MỌI câu hỏi, không phân biệt kịch bản.
GLOBAL_PROMPT = (
    """bật
tắt
mở
wifi khách
mạng khách
wifi phụ
giới hạn
bóp băng thông
đặt tốc độ
10
20
50
mbps
megabit
tối ưu
tăng tốc
ưu tiên
chặn
cấm
cắt
bỏ chặn
gỡ chặn
cho phép
cắt mạng
internet
truy cập
kết nối
bình thường
lại
ai đang chơi
xem video
thiết bị nào
phiên hoạt động
có những
liệt kê
kiểm tra trạng thái
thông tin
bộ định tuyến
router
chi tiết
ip
hôm nay thế nào
chất lượng
ổn định không
máy tính bảng
điện thoại
laptop
tivi thông minh
youtube
tiktok
netflix
game
liên quân
free fire
FiFa
và
rồi
sau đó
tiếp theo"""
)

# Scenario Prompt: chỉ nạp SAU KHI đã xác định đúng category
SCENARIO_PROMPTS = {
    "guest_wifi": "wifi khách\nmạng khách\nwifi phụ\nbật wifi\ntắt mạng\nmở wifi",
    "bandwidth_limit": "giới hạn băng thông\nbóp băng thông\nđặt tốc độ\n10 20 50 mbps\nmegabit",
    "optimize_app": "tối ưu\ntăng tốc\nưu tiên",
    "block_app": "chặn\ncấm",
    "unblock_app": "bỏ chặn\ngỡ chặn\ncho phép lại",
    "block_internet": "chặn mạng\ntắt wifi\ncắt truy cập internet",
    "unblock_internet": "mở mạng\nkết nối lại\nvào internet bình thường",
    "active_sessions": "ai đang\nchơi game\nxem video\nphiên hoạt động",
    "online_devices": "có những ai\nthiết bị nào\nđang kết nối\nđang dùng\nliệt kê",
    "router_info": "trạng thái\nthông tin\nbộ định tuyến\nrouter",
    "device_details": "chi tiết kết nối\nđịa chỉ ip\ntrạng thái",
    "network_info": "mạng hôm nay thế nào\nchất lượng kết nối\nổn định không",
    "multi_intent": "và\nrồi\nsau đó"
}

def build_prompt(question: str, category_id: str | None) -> str:
    """Ghép System + Global + Scenario (nếu có category) + câu hỏi."""
    parts = [SYSTEM_PROMPT, "", "GLOBAL CONTEXT:", GLOBAL_PROMPT]
    if category_id and category_id in SCENARIO_PROMPTS:
        parts += ["", f"SCENARIO CONTEXT ({category_id}):", SCENARIO_PROMPTS[category_id]]
    parts += ["", f'USER: "{question}"']
    return "\n".join(parts)

def build_prompt_no_context(question: str) -> str:
    """Chỉ System Prompt + câu hỏi — dùng để so sánh baseline không ngữ cảnh."""
    return f'{SYSTEM_PROMPT}\n\nUSER: "{question}"'
