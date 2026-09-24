"""Transactions use a temporary fake config and mocked Windows discovery only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import core


HARDWARE = {
    "manufacturer": "ASUS", "model": "TEST-LAPTOP", "cpu": "Test CPU",
    "gpu": ["Test GPU"], "ram_gb": 32, "bios": "123",
}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config_path = self.root / "config.json"
        self.initial = {
            "performance_mode": 0, "limit_total_0": 35, "limit_fast_1": 80,
            "limit_slow_2": 20, "gpu_core_1": 25,
            "keybind_profile_0": 128, "modifier_keybind_alt": "shift-control-alt",
            "m4": "C:\\SyntheticPrivateFolder\\launch.exe", "language": "ko-KR",
            "charge_limit": 80, "unknown_future_setting": {"keep": True},
        }
        self.write_config(self.initial)
        self.results = self.root / "results"
        self.results.mkdir()
        discovery = {
            "config_path": str(self.config_path), "config_verified": True,
            "config_candidates": [str(self.config_path)], "ghelper_running": False,
            "ghelper_version": "test-version", "results_dir": str(self.results),
            "ghelper_exe": None, "benchmark_exe": None, "cli_exe": None,
        }
        for target, result in (("detect_hardware", copy.deepcopy(HARDWARE)), ("discover", discovery),
                               ("ghelper_running", False), ("get_benchmark_running", False), ("ac_connected", True)):
            patcher = patch.object(core.bridge, target, return_value=result)
            setattr(self, "mock_" + target, patcher.start())
            self.addCleanup(patcher.stop)
        for target in ("switch_mode", "start_benchmark"):
            patcher = patch.object(core.bridge, target, side_effect=AssertionError("No desktop actions during tests"))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.lab = core.Lab(self.root / "data", self.root / "assets")

    def write_config(self, data):
        self.config_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def profile_data(self, settings=None, hardware=None):
        settings = {"limit_total_0": 45, "limit_fast_1": 90} if settings is None else settings
        return {
            "schemaVersion": 1, "name": "Imported test", "notes": "", "settings": settings,
            "settingsHash": core.digest(settings), "hardware": copy.deepcopy(hardware or HARDWARE),
            "activeMode": 0, "ghelperVersion": "test-version",
        }

    def import_profile(self, **kwargs):
        return self.lab.import_profile(self.profile_data(**kwargs))

    def result_file(self, name="history.3dmark-result"):
        path = self.results / name
        xml = ("<Result><TimeSpyPerformance3DMarkScore>12000</TimeSpyPerformance3DMarkScore>"
               "<TimeSpyPerformanceGraphicsScore>13000</TimeSpyPerformanceGraphicsScore>"
               "<TimeSpyPerformanceCPUScore>10000</TimeSpyPerformanceCPUScore></Result>")
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("Result.xml", xml)
        return path

    def test_capture_exports_only_tuning_keys(self):
        profile = self.lab.capture("Current")
        self.assertEqual(profile["settings"], {
            "limit_total_0": 35, "limit_fast_1": 80, "limit_slow_2": 20, "gpu_core_1": 25,
        })
        self.assertEqual(profile["settingsHash"], core.digest(profile["settings"]))
        self.assertNotIn("SyntheticPrivateFolder", json.dumps(profile))
        self.assertNotIn("modifier_keybind_alt", profile["settings"])
        self.assertEqual(profile["activeMode"], 0)

    def test_capture_rejects_invalid_tuning_values(self):
        self.write_config({**self.initial, "limit_total_0": 10000})
        with self.assertRaises(ValueError):
            self.lab.capture("Unsafe")
        self.assertEqual(self.lab.db["profiles"], [])

    def test_import_rejects_hotkeys_executables_and_unsupported_settings(self):
        for key in ("keybind_profile_0", "modifier_keybind_alt", "m4", "command", "performance_mode",
                    "charge_limit", "limit_total_3", "limit_fast_1_extra", "cpu_undervolt_0"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.lab.import_profile(self.profile_data({key: 1}))
        self.assertEqual(self.lab.db["profiles"], [])

    def test_import_rejects_boolean_fraction_and_out_of_range(self):
        for value in (True, 45.5, "45", -1, 151, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.lab.import_profile(self.profile_data({"limit_total_0": value}))

    def test_import_rejects_bad_hash_and_empty_settings(self):
        bad = self.profile_data()
        bad["settingsHash"] = "0" * 64
        for profile in (bad, self.profile_data({})):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                self.lab.import_profile(profile)

    def test_fan_curve_requires_16_ordered_bytes_with_safe_range(self):
        curve = "14-1E-28-32-3C-46-50-5A-00-0A-14-1E-28-32-3C-46"
        self.assertEqual(core.checked_settings({"fan_profile_cpu_0": curve.lower()}), {"fan_profile_cpu_0": curve})
        imported = self.import_profile(settings={"fan_profile_cpu_0": curve})
        self.assertEqual(imported["settings"]["fan_profile_cpu_0"], curve)
        for bad in (curve.replace("14-1E", "1E-14", 1), curve.replace("5A", "FF"), "00-01"):
            with self.subTest(curve=bad), self.assertRaises(ValueError):
                self.lab.import_profile(self.profile_data({"fan_profile_cpu_0": bad}))

    def test_apply_preserves_non_tuning_and_removes_omitted_tuning(self):
        profile = self.import_profile(settings={"limit_total_0": 45})
        preview = self.lab.preview(profile["id"])
        self.assertTrue(preview["compatible"])
        self.assertIn({"key": "limit_fast_1", "before": 80, "after": None}, preview["changes"])
        outcome = self.lab.apply(profile["id"], preview["configHash"])
        expected = {k: v for k, v in self.initial.items() if not core.known_key(k)}
        expected["limit_total_0"] = 45
        self.assertEqual(core.load_json(self.config_path), expected)
        self.assertTrue(outcome["backupId"])
        self.assertEqual(self.lab.db["backups"][0]["sha256"], core.file_hash(self.lab.data / "backups" / (outcome["backupId"] + ".json")))

    def test_running_ghelper_blocks_apply_without_writes_or_backup(self):
        profile = self.import_profile()
        before = self.config_path.read_bytes()
        self.mock_ghelper_running.return_value = True
        with self.assertRaises(ValueError):
            self.lab.apply(profile["id"], core.file_hash(self.config_path))
        self.assertEqual(self.config_path.read_bytes(), before)
        self.assertEqual(self.lab.db["backups"], [])

    def test_ghelper_start_during_apply_blocks_final_write(self):
        profile = self.import_profile()
        before = self.config_path.read_bytes()
        self.mock_ghelper_running.side_effect = [False, True]
        with self.assertRaises(ValueError):
            self.lab.apply(profile["id"], core.file_hash(self.config_path))
        self.assertEqual(self.config_path.read_bytes(), before)

    def test_stale_preview_hash_blocks_apply(self):
        profile = self.import_profile()
        preview = self.lab.preview(profile["id"])
        self.write_config({**self.initial, "charge_limit": 75})
        before = self.config_path.read_bytes()
        with self.assertRaises(ValueError):
            self.lab.apply(profile["id"], preview["configHash"])
        self.assertEqual(self.config_path.read_bytes(), before)
        self.assertEqual(self.lab.db["backups"], [])

    def test_hardware_model_cpu_or_gpu_mismatch_blocks_apply(self):
        for key, value in (("model", "OTHER"), ("cpu", "OTHER"), ("gpu", ["OTHER"]), ("gpu", [])):
            with self.subTest(key=key, value=value):
                hardware = {**HARDWARE, key: value}
                profile = self.import_profile(hardware=hardware)
                preview = self.lab.preview(profile["id"])
                self.assertFalse(preview["compatible"])
                before = self.config_path.read_bytes()
                with self.assertRaises(ValueError):
                    self.lab.apply(profile["id"], preview["configHash"])
                self.assertEqual(self.config_path.read_bytes(), before)

    def test_unverified_config_blocks_preview_and_apply(self):
        profile = self.import_profile()
        self.lab.discovery["config_verified"] = False
        preview = self.lab.preview(profile["id"])
        self.assertFalse(preview["compatible"])
        with self.assertRaises(ValueError):
            self.lab.apply(profile["id"], preview["configHash"])

    def test_restore_recovers_original_bytes_exactly(self):
        # G-Helper may use its own indentation, Unicode, BOM and newline style.
        original = b'\xef\xbb\xbf{\r\n  "performance_mode": 0, "limit_total_0":35,\r\n  "language": "ko-KR"\r\n}\r\n'
        self.config_path.write_bytes(original)
        profile = self.import_profile()
        outcome = self.lab.apply(profile["id"], core.file_hash(self.config_path))
        saved = self.lab.data / "backups" / (outcome["backupId"] + ".json")
        self.assertEqual(saved.read_bytes(), original)
        self.lab.restore(outcome["backupId"])
        self.assertEqual(self.config_path.read_bytes(), original)

    def test_tampered_backup_cannot_be_restored(self):
        profile = self.import_profile()
        outcome = self.lab.apply(profile["id"], core.file_hash(self.config_path))
        before = self.config_path.read_bytes()
        saved = self.lab.data / "backups" / (outcome["backupId"] + ".json")
        saved.write_text('{"performance_mode":2}', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.lab.restore(outcome["backupId"])
        self.assertEqual(self.config_path.read_bytes(), before)

    def test_running_ghelper_blocks_restore(self):
        profile = self.import_profile()
        outcome = self.lab.apply(profile["id"], core.file_hash(self.config_path))
        before = self.config_path.read_bytes()
        self.mock_ghelper_running.return_value = True
        with self.assertRaises(ValueError):
            self.lab.restore(outcome["backupId"])
        self.assertEqual(self.config_path.read_bytes(), before)

    def test_historical_scan_stays_unbound_and_cannot_be_claimed_later(self):
        profile = self.lab.capture("Now")
        path = self.result_file()
        outcome = self.lab.scan()
        self.assertEqual(outcome["added"], 1)
        run = outcome["runs"][0]
        self.assertEqual(run["binding"], "unbound")
        self.assertIsNone(run["settingsHash"])
        self.assertIsNone(run["profileId"])
        self.assertIsNone(self.lab._import_result(path, profile, 0))
        self.assertEqual(self.lab.scan()["added"], 0)
        with self.assertRaises(ValueError):
            self.lab.share_bundle(profile["id"], [run["id"]], "User")

    def test_public_bundle_requires_exact_matching_settings_hash(self):
        profile = self.lab.capture("Current")
        run = self.lab._import_result(self.result_file(), profile, 0)
        self.assertEqual(run["binding"], "captured")
        other = self.import_profile(settings={"limit_total_0": 46})
        with self.assertRaises(ValueError):
            self.lab.share_bundle(other["id"], [run["id"]], "User")
        bundle = self.lab.share_bundle(profile["id"], [run["id"]], "User")
        self.assertEqual(bundle["runs"][0]["settingsHash"], profile["settingsHash"])
        self.assertNotIn("sourceFile", bundle["runs"][0])
        self.assertNotIn("profileId", bundle["runs"][0])
        self.assertNotIn("id", bundle["profile"])
        self.assertNotIn(str(self.root), json.dumps(bundle))

    def test_failed_captured_result_cannot_be_shared(self):
        profile = self.lab.capture("Current")
        run = self.lab._import_result(self.result_file(), profile, 0)
        run["status"] = "failed"
        with self.assertRaises(ValueError):
            self.lab.share_bundle(profile["id"], [run["id"]], "User")

    def test_config_duplicate_keys_and_nonfinite_json_are_rejected(self):
        for text in ('{"performance_mode":0,"performance_mode":1}', '{"limit_total_0":NaN}'):
            self.config_path.write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.lab.config()


if __name__ == "__main__":
    unittest.main()
