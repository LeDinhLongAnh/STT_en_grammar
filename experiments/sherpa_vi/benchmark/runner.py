import time
from PyQt5.QtCore import QThread, pyqtSignal

from models.sherpa_zipformer_vi import SherpaZipformerVI
from context.prompt_manager import PromptManager
from evaluation.metrics import calculate_wer, calculate_cer, evaluate_context_harm
from evaluation.intent_entity import evaluate_intent, evaluate_entities, predict_scenario

class BenchmarkRunner(QThread):
    progress = pyqtSignal(int, str)  # % progress, status message
    result_ready = pyqtSignal(dict)  # final combined results
    error_occurred = pyqtSignal(str)

    def __init__(self, model: SherpaZipformerVI, audio_bytes: bytes, test_case: dict, randomize: bool = False):
        super().__init__()
        self.model = model
        self.audio_bytes = audio_bytes
        self.test_case = test_case
        self.randomize = randomize
        self.prompt_manager = PromptManager(score=1.5)

    def run(self):
        try:
            self.progress.emit(10, "Warm-up model...")
            self.model.transcribe(self.audio_bytes, "")
            
            self.progress.emit(20, "Preparing contexts...")
            try:
                import prompts
                global_context = [prompts.GLOBAL_PROMPT]
            except ImportError:
                global_context = self.test_case.get("global_context", [])
            
            hw_global = self.prompt_manager.generate_hotwords_file(global_context)
            
            results = {}
            reference = self.test_case.get("reference", "")
            expected_intent = self.test_case.get("intent", "")
            
            # 1. BASELINE
            self.progress.emit(30, "Running BASELINE (No context)...")
            res_base = self.model.transcribe(self.audio_bytes, "")
            res_base["wer"] = calculate_wer(reference, res_base["transcript"])
            res_base["cer"] = calculate_cer(reference, res_base["transcript"])
            res_base["intent_eval"] = evaluate_intent(res_base["transcript"], expected_intent)
            res_base["entity_eval"] = evaluate_entities(res_base["transcript"], reference)
            results["BASELINE"] = res_base
            
            # 2. GLOBAL
            self.progress.emit(50, "Running GLOBAL (1st Pass)...")
            res_glob = self.model.transcribe(self.audio_bytes, hw_global)
            res_glob["wer"] = calculate_wer(reference, res_glob["transcript"])
            res_glob["cer"] = calculate_cer(reference, res_glob["transcript"])
            res_glob["intent_eval"] = evaluate_intent(res_glob["transcript"], expected_intent)
            res_glob["entity_eval"] = evaluate_entities(res_glob["transcript"], reference)
            results["GLOBAL"] = res_glob
            
            # 3. AUTO SCENARIO (2nd Pass)
            self.progress.emit(70, "Predicting intent & Running SCENARIO (2nd Pass)...")
            # --- TỰ ĐỘNG 2 LƯỢT ---
            # Dùng transcript của Global để đoán scenario
            predicted_key = predict_scenario(res_glob["transcript"])
            scenario_context = []
            try:
                import prompts
                if predicted_key and predicted_key in prompts.SCENARIO_PROMPTS:
                    scenario_context = [prompts.SCENARIO_PROMPTS[predicted_key]]
            except Exception:
                pass
                
            hw_scenario = self.prompt_manager.generate_hotwords_file(global_context + scenario_context)
            res_scen = self.model.transcribe(self.audio_bytes, hw_scenario)
            res_scen["wer"] = calculate_wer(reference, res_scen["transcript"])
            res_scen["cer"] = calculate_cer(reference, res_scen["transcript"])
            res_scen["intent_eval"] = evaluate_intent(res_scen["transcript"], expected_intent)
            res_scen["entity_eval"] = evaluate_entities(res_scen["transcript"], reference)
            res_scen["predicted_scenario"] = predicted_key # Lưu lại để UI hiển thị
            results["SCENARIO"] = res_scen
            
            # Calculate context benefit
            results["GLOBAL"]["context_effect"] = evaluate_context_harm(
                results["BASELINE"]["wer"], results["GLOBAL"]["wer"]
            )
            results["SCENARIO"]["context_effect"] = evaluate_context_harm(
                results["BASELINE"]["wer"], results["SCENARIO"]["wer"]
            )
            
            self.progress.emit(100, "Done!")
            self.result_ready.emit(results)
            
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.prompt_manager.cleanup()
