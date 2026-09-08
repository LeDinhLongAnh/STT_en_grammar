import unittest

import numpy as np

import run


class ExperimentLogicTests(unittest.TestCase):
    def test_normalize_and_wer(self):
        self.assertEqual(run.normalize_words("Guest Wi-Fi!"), ["guest", "wifi"])
        self.assertEqual(run.edit_counts("turn on guest wifi", "turn on gas wifi"), (1, 4))
        self.assertEqual(run.edit_counts("turn on guest wifi", "Turn on guest Wi-Fi."), (0, 4))
        self.assertEqual(run.edit_counts("limit speed fifty", "Limit speed 50."), (0, 3))
        self.assertEqual(run.edit_counts("limit speed one hundred", "Limit speed 100."), (0, 3))

    def test_all_twelve_scenarios_are_unique(self):
        config = run.load_config(run.DEFAULT_CONFIG)
        scenarios = run.scenario_map(config)
        self.assertEqual(len(scenarios), 12)
        self.assertIn("block_application", scenarios)
        for scenario in scenarios.values():
            self.assertGreaterEqual(len(scenario["examples"]), 8)
            self.assertEqual(len(scenario["examples"]), len(set(scenario["examples"])))
            self.assertLessEqual(len(run.normalize_words(scenario["prompt"])), 100)
        global_words = run.normalize_words(config["global_prompt"])
        self.assertLessEqual(len(global_words), 160)
        for required in ("network", "router", "online", "gaming", "guest", "qos",
                         "bandwidth", "block", "unblock", "youtube", "tiktok"):
            self.assertIn(required, global_words)

    def test_manifest_is_valid(self):
        config = run.load_config(run.DEFAULT_CONFIG)
        rows = run.read_manifest(run.DEFAULT_MANIFEST, set(run.scenario_map(config)))
        self.assertEqual(len(rows), 24)
        synthetic = run.read_manifest(run.ROOT / "manifest-synthetic.tsv",
                                      set(run.scenario_map(config)))
        self.assertEqual(len(synthetic), 20)
        self.assertTrue(all(row.wav.is_file() for row in synthetic))

    def test_pcm16_loader(self):
        fixture = run.ROOT.parent.parent / "tests" / "data" / "tts" / "tts-0001.wav"
        loaded, duration = run.read_pcm16_mono_16k(fixture)
        self.assertEqual(loaded.dtype, np.float32)
        self.assertGreater(len(loaded), 0)
        self.assertAlmostEqual(duration, len(loaded) / 16000)

    def test_microphone_audio_is_resampled_and_quantized_for_the_model(self):
        native = np.linspace(-1.2, 1.2, 4800, dtype=np.float32)
        native[100] = np.nan
        model_audio = run.prepare_float32_16k(native, 48000.0)
        self.assertEqual(model_audio.dtype, np.float32)
        self.assertEqual(len(model_audio), 1600)
        self.assertTrue(np.isfinite(model_audio).all())
        pcm = run.prepare_pcm16_16k(native, 48000.0)
        self.assertEqual(pcm.dtype, np.dtype("<i2"))
        self.assertEqual(len(pcm), 1600)
        self.assertLessEqual(int(pcm.max()), 32767)
        self.assertGreaterEqual(int(pcm.min()), -32767)

    def test_prompt_strength_is_explicit_and_bounded(self):
        self.assertEqual(run.strengthen_prompt("Unblock internet.", 2),
                         "Unblock internet. Unblock internet.")
        self.assertIsNone(run.strengthen_prompt(None, 3))
        with self.assertRaises(ValueError):
            run.strengthen_prompt("test", 4)
        self.assertEqual(
            run.adaptive_scenario_strength(2, "guest_wifi", "turn on the rest wifi"), 3)
        self.assertEqual(
            run.adaptive_scenario_strength(2, "guest_wifi", "turn on guest wifi"), 2)
        self.assertEqual(
            run.adaptive_scenario_strength(2, "router_status", "router information"), 2)

    def test_decode_uses_beam_search_and_carries_the_initial_prompt(self):
        class FakeModel:
            options = None

            def transcribe(self, audio, **options):
                del audio
                self.options = options
                return {"text": "unblock internet"}

        model = FakeModel()
        text, _elapsed = run.transcribe(
            model, np.zeros(160, dtype=np.float32), "Unblock internet.")
        self.assertEqual(text, "unblock internet")
        self.assertEqual(model.options["beam_size"], 5)
        self.assertTrue(model.options["carry_initial_prompt"])
        self.assertEqual(model.options["initial_prompt"], "Unblock internet.")

    def test_partial_utterances_route_to_scenarios_and_extract_slots(self):
        config = run.load_config(run.DEFAULT_CONFIG)
        cases = {
            "who is online": "online_devices",
            "number of device online now": "online_devices",
            "speed test": "network_status",
            "check connection quality": "network_status",
            "router information": "router_status",
            "router status": "router_status",
            "gaming right now": "gaming_sessions",
            "block YouTube": "block_application",
            "unblock my son's internet": "unblock_internet",
            "limit to fifty": "bandwidth_limit",
            "guest wifi off": "guest_wifi",
            "show qos": "open_qos",
            "turn on the rest wifi": "guest_wifi",
            "turn off the best wifi": "guest_wifi",
            "turn on the west wifi": "guest_wifi",
            "turn off the next wifi": "guest_wifi",
            "turn on the rest weapon": "guest_wifi",
            "turn off the s2 file": "guest_wifi",
        }
        for utterance, expected in cases.items():
            with self.subTest(utterance=utterance):
                result = run.resolve_scenario(utterance, config)
                self.assertEqual(result.status, "matched")
                self.assertEqual(result.scenario_id, expected)
        blocked_app = run.resolve_scenario("block YouTube for my son", config)
        self.assertEqual(blocked_app.canonical_action, "block_internet")
        self.assertIn("YouTube", blocked_app.slots["applications"])
        self.assertIn("my son", blocked_app.slots["people"])
        bandwidth = run.resolve_scenario("limit to fifty", config)
        self.assertEqual(bandwidth.slots["bandwidth_value"], 50)
        conflicted = run.resolve_scenario("turn on turn off the best wifi", config)
        self.assertEqual(conflicted.slots["guest_wifi_state"], "ambiguous")

    def test_bare_object_does_not_trigger_an_action(self):
        config = run.load_config(run.DEFAULT_CONFIG)
        result = run.resolve_scenario("my son's phone", config)
        self.assertEqual(result.status, "no_match")
        self.assertIsNone(result.scenario_id)

    def test_every_configured_paraphrase_routes_to_its_declared_scenario(self):
        config = run.load_config(run.DEFAULT_CONFIG)
        for scenario in config["scenarios"]:
            for example in scenario["examples"]:
                with self.subTest(scenario=scenario["id"], example=example):
                    result = run.resolve_scenario(example, config)
                    self.assertEqual(result.status, "matched")
                    self.assertEqual(result.scenario_id, scenario["id"])


if __name__ == "__main__":
    unittest.main()
