import re

# Định nghĩa các intent dựa trên từ khoá (Regex)
INTENT_RULES = {
    "GUEST_WIFI": [r"wifi khách", r"mạng khách", r"guest wifi"],
    "BANDWIDTH_LIMIT": [r"giới hạn băng thông", r"bóp băng thông", r"tốc độ.*mbps"],
    "OPTIMIZE_APP": [r"tối ưu", r"ưu tiên", r"tăng tốc"],
    "BLOCK_APP": [r"(chặn|cấm|khóa).*(youtube|tiktok|netflix|game)"],
    "UNBLOCK_APP": [r"(bỏ chặn|mở lại|gỡ).*(youtube|tiktok|netflix|game)"],
    "BLOCK_INTERNET_ACCESS": [r"(chặn|cắt).*(mạng|internet|wifi)"],
    "UNBLOCK_INTERNET_ACCESS": [r"(mở|bỏ chặn).*(mạng|internet|wifi)"],
    "ACTIVE_SESSIONS": [r"phiên hoạt động", r"session"],
    "ONLINE_DEVICES": [r"thiết bị đang kết nối", r"đang online"],
    "ROUTER_INFORMATION": [r"trạng thái router", r"thông tin router"],
    "WIFI_DEVICE_DETAILS": [r"thông tin thiết bị", r"địa chỉ ip"],
    "NETWORK_INFORMATION": [r"mạng có ổn định không", r"wifi.*ổn định", r"tình trạng mạng", r"kết nối.*mạng"]
}

ENTITY_RULES = {
    "Device": [r"điện thoại", r"laptop", r"tablet", r"máy tính bảng", r"pc", r"tv", r"tivi"],
    "Application": [r"youtube", r"tiktok", r"netflix", r"game", r"gaming"],
    "Network": [r"wi-fi", r"wifi", r"internet", r"mạng", r"guest wifi", r"wifi khách", r"mạng khách"],
    "Bandwidth": [r"\d+\s*mbps", r"\d+\s*megabit"]
}

# Ánh xạ từ Intent (NLU) sang Scenario ID (Prompts)
INTENT_TO_SCENARIO = {
    "GUEST_WIFI": "guest_wifi",
    "BANDWIDTH_LIMIT": "bandwidth_limit",
    "OPTIMIZE_APP": "optimize_app",
    "BLOCK_APP": "block_app",
    "UNBLOCK_APP": "unblock_app",
    "BLOCK_INTERNET_ACCESS": "block_internet",
    "UNBLOCK_INTERNET_ACCESS": "unblock_internet",
    "ACTIVE_SESSIONS": "active_sessions",
    "ONLINE_DEVICES": "online_devices",
    "ROUTER_INFORMATION": "router_info",
    "WIFI_DEVICE_DETAILS": "device_details",
    "NETWORK_INFORMATION": "network_info"
}

def predict_scenario(transcript: str) -> str | None:
    """
    Phân tích văn bản thô (thường từ lượt chạy Global Prompt)
    và dự đoán Scenario ID thích hợp nhất để chạy lượt 2.
    Trả về None nếu không tìm thấy intent nào khớp.
    """
    text = transcript.lower()
    for intent, patterns in INTENT_RULES.items():
        for pat in patterns:
            if re.search(pat, text):
                return INTENT_TO_SCENARIO.get(intent)
    return None

def evaluate_intent(transcript: str, expected_intents: str) -> dict:
    """
    So sánh các intent bắt được từ transcript so với expected_intents.
    expected_intents có thể là chuỗi phân cách bởi dấu phẩy: "BLOCK_APP, ROUTER_INFORMATION"
    """
    text = transcript.lower()
    detected = set()
    
    for intent, patterns in INTENT_RULES.items():
        for pat in patterns:
            if re.search(pat, text):
                detected.add(intent)
                break
                
    expected = {i.strip() for i in expected_intents.split(",") if i.strip()}
    
    # Nếu expected trống thì coi như pass nếu detected cũng trống
    if not expected:
        return {
            "expected": expected,
            "detected": detected,
            "pass": len(detected) == 0,
            "accuracy": 1.0 if len(detected) == 0 else 0.0
        }
        
    correct = expected.intersection(detected)
    accuracy = len(correct) / len(expected)
    
    return {
        "expected": list(expected),
        "detected": list(detected),
        "pass": accuracy == 1.0,
        "accuracy": accuracy
    }

def extract_entities(text: str) -> dict:
    text = text.lower()
    entities = {}
    for ent_type, patterns in ENTITY_RULES.items():
        matches = []
        for pat in patterns:
            found = re.findall(pat, text)
            matches.extend(found)
        if matches:
            entities[ent_type] = list(set(matches))
    return entities

def evaluate_entities(transcript: str, reference: str) -> dict:
    """
    So sánh entity trích xuất được từ transcript và reference (chuẩn).
    """
    ref_ents = extract_entities(reference)
    hyp_ents = extract_entities(transcript)
    
    if not ref_ents:
        return {"pass": True, "ref": ref_ents, "hyp": hyp_ents}
        
    total = 0
    correct = 0
    
    for ent_type, ref_vals in ref_ents.items():
        total += len(ref_vals)
        hyp_vals = hyp_ents.get(ent_type, [])
        for val in ref_vals:
            if val in hyp_vals:
                correct += 1
                
    return {
        "pass": correct == total,
        "ref": ref_ents,
        "hyp": hyp_ents,
        "accuracy": correct / total if total > 0 else 1.0
    }
