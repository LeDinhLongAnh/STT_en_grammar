import os
import json
import datetime
import wave

class DatasetManager:
    def __init__(self, base_dir="real_world_dataset"):
        self.base_dir = base_dir
        self.audio_dir = os.path.join(self.base_dir, "audio")
        self.metadata_file = os.path.join(self.base_dir, "metadata.json")
        
        # Tạo thư mục nếu chưa có
        os.makedirs(self.audio_dir, exist_ok=True)
        if not os.path.exists(self.metadata_file):
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=4)
                
    def save_recording(self, audio_bytes, scenario_name):
        """Lưu file wav tạm thời (tự động)"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = scenario_name.replace(" ", "_").lower()
        filename = f"{timestamp}_{safe_name}.wav"
        
        # Lưu vào thư mục tạm recordings/
        rec_dir = "recordings"
        os.makedirs(rec_dir, exist_ok=True)
        filepath = os.path.join(rec_dir, filename)
        
        with open(filepath, "wb") as f:
            f.write(audio_bytes)
            
        return filepath

    def save_test_case(self, audio_bytes, metadata):
        """Lưu vĩnh viễn vào real_world_dataset (khi người dùng bấm Save Test Case)"""
        # Tạo ID
        case_id = metadata.get("id")
        if not case_id:
            scenario = metadata.get("scenario", "unknown").replace(" ", "_").lower()
            idx = 1
            while True:
                case_id = f"{scenario}_{idx:03d}"
                if not os.path.exists(os.path.join(self.audio_dir, f"{case_id}.wav")):
                    break
                idx += 1
                
        # Lưu audio
        audio_filename = f"{case_id}.wav"
        audio_path = os.path.join(self.audio_dir, audio_filename)
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)
            
        # Cập nhật metadata
        metadata["id"] = case_id
        metadata["audio"] = f"audio/{audio_filename}"
        
        # Đọc metadata cũ
        with open(self.metadata_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        data.append(metadata)
        
        # Ghi lại
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
        return case_id
