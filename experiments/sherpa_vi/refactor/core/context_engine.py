# -*- coding: utf-8 -*-
"""Context Engine for STT Semantic Processing (Pipeline B)."""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional

from utils.text_normalizer import replace_aliases_with_canonical, normalize_basic, get_phonetic_hotwords


class ContextResult:
    """Dataclass holding the result of the Context Engine."""
    def __init__(self):
        self.raw_transcript: str = ""
        self.scenario_candidates: List[Dict[str, Any]] = []
        self.detected_scenario: Optional[str] = None
        self.scenario_confidence: float = 0.0
        
        self.detected_intent: Optional[str] = None
        self.intent_confidence: float = 0.0
        
        self.extracted_slots: Dict[str, str] = {}
        
        self.correction_type: str = "none"
        self.canonical_output: str = ""
        self.final_semantic_result: str = ""


class ContextEngine:
    """
    Handles Semantic Analysis, Hotwords extraction, Slot filling, and Contextual Canonicalization.
    It strictly adheres to the rule of preserving raw transcript if confidence is low.
    """
    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        self.config: List[Dict[str, Any]] = []
        self.global_hotwords: List[str] = []
        self.load_config()

    def load_config(self):
        """Load scenarios configuration and global hotwords."""
        scenarios_path = self.config_dir / "scenarios_vi.json"
        if scenarios_path.exists():
            with open(scenarios_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = []
            
        global_path = self.config_dir / "global_hotwords.txt"
        if global_path.exists():
            with open(global_path, "r", encoding="utf-8") as f:
                self.global_hotwords = [line.strip() for line in f if line.strip()]
        else:
            self.global_hotwords = []

    def get_global_hotwords_list(self) -> List[str]:
        return self.global_hotwords
        
    def get_scenario_hotwords_list(self, scenario_id: str) -> List[str]:
        """Return raw list of hotwords for a specific scenario."""
        words = set()
        for scen in self.config:
            if scen.get("scenario_id") == scenario_id:
                for intent in scen.get("intents", []):
                    for hw in intent.get("hotwords", []):
                        words.add(hw)
        return list(words)

    def get_global_hotwords_string(self) -> str:
        """Return global hotwords as multiline string for biasing."""
        return "\n".join(self.global_hotwords)

    def get_scenario_hotwords_string(self, scenario_id: str) -> str:
        """Extract phonetic hotwords for Biasing."""
        unified = {"intents": []}
        for scen in self.config:
            if scen.get("scenario_id") == scenario_id:
                unified["intents"].extend(scen.get("intents", []))
        return get_phonetic_hotwords(scenario_id, unified)

    def process(self, raw_transcript: str, predefined_scenario: Optional[str] = None) -> ContextResult:
        """
        Process the raw transcript through the NLP context pipeline.
        predefined_scenario: if the user manually selected a scenario in the UI.
        """
        res = ContextResult()
        res.raw_transcript = raw_transcript
        
        if not raw_transcript.strip():
            res.final_semantic_result = ""
            return res

        # 1. Text Normalization
        # Here we just apply basic unit/number normalization if needed, 
        # but for intent matching we use lowercased normalized string.
        norm_text = normalize_basic(raw_transcript)
        
        # 2. Detect Scenario
        self._detect_scenario(norm_text, res, predefined_scenario)
        
        # 3. Detect Intent & Extract Slots
        if res.detected_scenario:
            self._detect_intent_and_slots(norm_text, res)
            
        # 4. Canonicalize (Decision Making)
        self._canonicalize(res)
        
        return res

    def _detect_scenario(self, norm_text: str, res: ContextResult, predefined_scenario: Optional[str]):
        """Detect the scenario based on hotword overlap."""
        if predefined_scenario:
            res.detected_scenario = predefined_scenario
            res.scenario_confidence = 1.0
            return

        candidates = []
        if isinstance(self.config, list):
            for scen in self.config:
                sid = scen.get("scenario_id")
                score = 0.0
                intents = scen.get("intents", [])
                for intent in intents:
                    hw_list = intent.get("hotwords", [])
                    matches = sum(1 for hw in hw_list if hw.lower() in norm_text)
                    if len(hw_list) > 0:
                        intent_score = matches / min(len(hw_list), 3) # Max out easily
                        score = max(score, intent_score)
                candidates.append({"scenario_id": sid, "score": min(1.0, score)})
                
        candidates.sort(key=lambda x: x["score"], reverse=True)
        res.scenario_candidates = candidates
        
        if candidates and candidates[0]["score"] >= 0.3:
            res.detected_scenario = candidates[0]["scenario_id"]
            res.scenario_confidence = candidates[0]["score"]

    def _detect_intent_and_slots(self, norm_text: str, res: ContextResult):
        """Find specific intent and extract slots."""
        if not isinstance(self.config, list):
            return
            
        # Find the scenario object
        scenario = next((s for s in self.config if s.get("scenario_id") == res.detected_scenario), None)
        if not scenario:
            return
            
        best_intent = None
        best_score = 0.0
        
        for intent in scenario.get("intents", []):
            hw_list = intent.get("hotwords", [])
            matches = [hw for hw in hw_list if hw.lower() in norm_text]
            score = len(matches) / float(max(1, len(hw_list)))
            # Boost score if action words are found
            if any(w in norm_text for w in ["bật", "mở", "tắt", "chặn", "cấm", "đặt"]):
                score += 0.3
                
            if score > best_score:
                best_score = score
                best_intent = intent
                
        if best_intent and best_score >= 0.4:
            res.detected_intent = best_intent.get("intent")
            res.intent_confidence = min(1.0, best_score)
            
            # Very basic slot extraction for demonstration
            # In production, use Regex or NER model
            req_slots = best_intent.get("required_slots", [])
            if "device" in req_slots:
                devices = ["điện thoại", "laptop", "máy tính bảng", "tivi", "máy tính"]
                for d in devices:
                    if d in norm_text:
                        res.extracted_slots["device"] = d
                        break
            
            if "application" in req_slots:
                apps = ["youtube", "tiktok", "netflix", "facebook", "game"]
                # Include phonetic aliases in search
                app_aliases = {"du túp": "youtube", "tích tốc": "tiktok", "phây búc": "facebook"}
                for a in apps:
                    if a in norm_text:
                        res.extracted_slots["application"] = a
                        break
                if "application" not in res.extracted_slots:
                    for alias, a in app_aliases.items():
                        if alias in norm_text:
                            res.extracted_slots["application"] = a
                            break
                            
            if "value" in req_slots:
                import re
                match = re.search(r'\b(một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|hai mươi|ba mươi|năm mươi|một trăm|\d+)\b', norm_text)
                if match:
                    res.extracted_slots["value"] = match.group(1)

    def _canonicalize(self, res: ContextResult):
        """Decide whether to modify the output based on confidence."""
        # Configurable thresholds
        SCENARIO_TH = 0.5
        INTENT_TH = 0.6
        
        # 1. Phonetic Text Normalization (Always safe to apply if confidence is decent)
        unified = {"intents": []}
        if isinstance(self.config, list):
            for scen in self.config:
                unified["intents"].extend(scen.get("intents", []))
        
        norm_text = replace_aliases_with_canonical(res.raw_transcript, unified)
        
        if norm_text != res.raw_transcript:
            res.correction_type = "text_normalization"
            res.canonical_output = norm_text
            res.final_semantic_result = norm_text
        else:
            res.canonical_output = res.raw_transcript
            res.final_semantic_result = res.raw_transcript

        # 2. Semantic Canonicalization (Only if highly confident)
        if (res.scenario_confidence >= SCENARIO_TH and 
            res.intent_confidence >= INTENT_TH):
            
            scenario = next((s for s in self.config if s.get("scenario_id") == res.detected_scenario), None)
            if scenario:
                intent = next((i for i in scenario.get("intents", []) if i.get("intent") == res.detected_intent), None)
                if intent and intent.get("canonical_templates"):
                    template = intent["canonical_templates"][0]
                    # Fill template with slots
                    output = template
                    missing_slot = False
                    for slot in intent.get("required_slots", []):
                        if slot in res.extracted_slots:
                            output = output.replace(f"{{{slot}}}", res.extracted_slots[slot])
                        else:
                            missing_slot = True
                            
                    if not missing_slot:
                        res.correction_type = "intent_based_canonicalization"
                        res.canonical_output = output
                        res.final_semantic_result = output
        
        # If confidence too low and no normalization happened
        if res.correction_type == "none":
            res.final_semantic_result = f"[Low confidence - Raw output preserved] {res.raw_transcript}"
            # Clean it up for actual UI display
            res.final_semantic_result = res.raw_transcript
