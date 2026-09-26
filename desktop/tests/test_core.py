"""Transactions use a temporary fake config and mocked Windows discovery only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import core
import community


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

    def test_state_reports_installed_version_and_consumes_update_result(self):
        status = self.lab.data / 'update-status.txt'
        status.write_text('updated', encoding='utf-8')
        first = self.lab.state()
        self.assertEqual(first['appVersion'], core.APP_VERSION)
        self.assertEqual(first['updateStatus'], 'updated')
        self.assertIsNone(self.lab.state()['updateStatus'])

    def profile_data(self, settings=None, hardware=None):
        settings = {"limit_total_0": 45, "limit_fast_1": 90} if settings is None else settings
        return {
            "schemaVersion": 1, "name": "Imported test", "notes": "", "settings": settings,
            "settingsHash": core.digest(settings), "hardware": copy.deepcopy(hardware or HARDWARE),
            "activeMode": 0, "ghelperVersion": "test-version",
        }

    def import_profile(self, **kwargs):
        return self.lab.import_profile(self.profile_data(**kwargs))

    def result_file(self, name="history.3dmark-result", graphics=13000):
        path = self.results / name
        xml = ("<Result><TimeSpyPerformance3DMarkScore>12000</TimeSpyPerformance3DMarkScore>"
               f"<TimeSpyPerformanceGraphicsScore>{graphics}</TimeSpyPerformanceGraphicsScore>"
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

    def test_historical_scan_stays_unbound_until_explicitly_linked(self):
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

    def test_manual_result_link_requires_attestation_and_keeps_public_provenance(self):
        profile = self.lab.capture("Measured settings")
        self.result_file()
        run = self.lab.scan()["runs"][0]
        config_before = self.config_path.read_bytes()
        for mode, confirmed in ((3, True), (0, False), (True, True)):
            with self.subTest(mode=mode, confirmed=confirmed), self.assertRaises(ValueError):
                self.lab.link_result(run["id"], profile["id"], mode, confirmed)
        self.assertEqual(run["binding"], "unbound")
        linked = self.lab.link_result(run["id"], profile["id"], 1, True)
        self.assertEqual((linked["binding"], linked["mode"], linked["settingsHash"]),
                         ("manual", 1, profile["settingsHash"]))
        self.lab.annotate(run["id"], notes="사용자가 적은 메모")
        bundle = self.lab.share_bundle(profile["id"], [run["id"]], "User")
        self.assertTrue(bundle["runs"][0]["notes"].startswith("[직접 연결 · 측정 당시 설정 미검증]"))
        self.assertIn("사용자가 적은 메모", bundle["runs"][0]["notes"])
        self.assertEqual(community._bundle(bundle)["runs"][0]["notes"], bundle["runs"][0]["notes"])
        self.assertEqual(self.config_path.read_bytes(), config_before)
        other = self.import_profile(settings=profile["settings"])
        with self.assertRaises(ValueError):
            self.lab.share_bundle(other["id"], [run["id"]], "User")
        with self.assertRaises(ValueError):
            self.lab.link_result(run["id"], other["id"], 1, True)

    def test_public_bundle_requires_exact_matching_settings_hash(self):
        profile = self.lab.capture("Current")
        run = self.lab._import_result(self.result_file(), profile, 0)
        self.assertEqual(run["binding"], "captured")
        with self.assertRaises(ValueError):
            self.lab.link_result(run["id"], profile["id"], 0, True)
        other = self.import_profile(settings={"limit_total_0": 46})
        with self.assertRaises(ValueError):
            self.lab.share_bundle(other["id"], [run["id"]], "User")
        bundle = self.lab.share_bundle(profile["id"], [run["id"]], "User")
        self.assertEqual(bundle["runs"][0]["settingsHash"], profile["settingsHash"])
        self.assertEqual(bundle["runs"][0]["notes"], "")
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

    def mode_captures(self):
        captures = {}
        for mode, watts in ((2, 25), (0, 45), (1, 85)):
            values = {f'limit_total_{m}': 10 + mode if m != mode else watts for m in (2, 0, 1)}
            self.write_config({**values, 'performance_mode': mode, 'm4': 'private/local/path'})
            profile = self.lab.capture(str(mode))
            run = self.lab._import_result(self.result_file(str(mode)+'.3dmark-result',13000+mode),profile,mode)
            captures[mode] = (profile,run)
        return captures

    def test_share_three_modes_merges_only_each_measured_mode_and_preserves_original_hashes(self):
        captures = self.mode_captures()
        ids = {str(m): p['id'] for m,(p,r) in captures.items()}
        before = copy.deepcopy(self.lab.db)
        bundle = self.lab.share_bundle(captures[2][0]['id'],[r['id'] for p,r in captures.values()],'User',ids)
        self.assertEqual(bundle['profile']['settings'], {'limit_total_2':25,'limit_total_0':45,'limit_total_1':85})
        self.assertEqual(bundle['profile']['settingsHash'],core.digest(bundle['profile']['settings']))
        self.assertEqual([r['mode'] for r in bundle['runs']],[2,0,1])
        for r in bundle['runs']:
            self.assertEqual(r['settingsHash'],bundle['profile']['settingsHash'])
            self.assertEqual(r['measuredSettingsHash'],captures[r['mode']][1]['settingsHash'])
            self.assertEqual(r['measuredSettings'],captures[r['mode']][0]['settings'])
        self.assertEqual(community._bundle(bundle),bundle)
        self.assertEqual(self.lab.db,before)
        self.assertNotIn('private/local/path',json.dumps(bundle))
        self.assertNotIn('profileId',json.dumps(bundle))
        imported = self.lab.import_profile(bundle)
        self.assertEqual(imported['settings'],bundle['profile']['settings'])

    def test_share_metadata_changes_only_public_copy_and_keeps_scores_and_hashes(self):
        captures=self.mode_captures(); ids={str(m):p['id'] for m,(p,r) in captures.items()}
        base=captures[2][0]; base['notes']='Private saved note'
        runs=[r['id'] for p,r in captures.values()]; before=copy.deepcopy(self.lab.db)
        original=self.lab.share_bundle(base['id'],runs,'User',ids)
        bundle=self.lab.share_bundle(base['id'],runs,'User',ids,{'name':'  My laptop  ','notes':''})
        self.assertEqual(bundle['profile']['name'],'My laptop')
        self.assertEqual(bundle['profile']['notes'],'')
        self.assertNotIn('Private saved note',json.dumps(bundle))
        self.assertEqual(bundle['profile']['settingsHash'],original['profile']['settingsHash'])
        self.assertEqual(bundle['runs'],original['runs'])
        self.assertEqual(community._bundle(bundle),bundle)
        self.assertEqual(self.lab.db,before)

    def test_invalid_public_metadata_is_rejected_without_altering_saved_profile(self):
        p=self.lab.capture('Saved'); before=copy.deepcopy(self.lab.db)
        for details in ([],{}, {'name':'','notes':''},{'name':' '*3,'notes':''},
                        {'name':'x'*81,'notes':''},{'name':'x','notes':'x'*2001},
                        {'name':42,'notes':''},{'name':'x','notes':'a\x00b'},
                        {'name':'x','notes':'','hardware':{}}):
            with self.subTest(details=details),self.assertRaises(ValueError):
                self.lab.share_bundle(p['id'],[],'User',shareDetails=details)
        self.assertEqual(self.lab.db,before)

    def test_three_mode_share_rejects_wrong_settings_foreign_hardware_and_duplicate_modes(self):
        captures = self.mode_captures()
        ids = {str(m): p['id'] for m,(p,r) in captures.items()}
        base = captures[2][0]['id']; runs = [r['id'] for p,r in captures.values()]
        changed = self.import_profile(settings={'limit_total_0':46})
        foreign = self.import_profile(settings={'limit_total_0':45},hardware={**HARDWARE,'model':'OTHER'})
        for mappings in ({'0':ids['0']},{**ids,'0':changed['id']},{**ids,'0':foreign['id']}):
            with self.subTest(mapping=mappings),self.assertRaises(ValueError):
                self.lab.share_bundle(base,runs,'User',mappings)
        with self.assertRaises(ValueError): self.lab.share_bundle(base,[runs[0],runs[0]],'User',ids)
        captures[0][1]['settingsHash']='0'*64
        with self.assertRaises(ValueError): self.lab.share_bundle(base,runs,'User',ids)

    def test_three_mode_share_marks_manual_records_and_allows_settings_without_scores(self):
        captures = self.mode_captures()
        ids = {str(m):p['id'] for m,(p,r) in captures.items()}
        p,r = captures[0]; r['binding']='manual';r['notes']='User note'
        bundle = self.lab.share_bundle(captures[2][0]['id'],[r['id']],'User',ids)
        self.assertTrue(bundle['runs'][0]['notes'].startswith('[직접 연결 · 측정 당시 설정 미검증]'))
        self.assertIn('User note',bundle['runs'][0]['notes'])
        empty = self.lab.share_bundle(captures[2][0]['id'],[],'User',ids)
        self.assertEqual(empty['runs'],[])
        self.assertEqual(set(empty['profile']['settings']),{'limit_total_0','limit_total_1','limit_total_2'})

    def test_community_checks_mode_projection_and_measurement_hash_in_combined_bundle(self):
        captures = self.mode_captures(); ids={str(m):p['id'] for m,(p,r) in captures.items()}
        bundle=self.lab.share_bundle(captures[2][0]['id'],[captures[2][1]['id']],'User',ids)
        for field in ('measuredSettings','measuredSettingsHash'):
            altered=copy.deepcopy(bundle); del altered['runs'][0][field]
            with self.subTest(field=field),self.assertRaises(ValueError): community._bundle(altered)
        altered=copy.deepcopy(bundle); r=altered['runs'][0];r['measuredSettings']['limit_total_2']=26
        r['measuredSettingsHash']=core.digest(r['measuredSettings'])
        with self.assertRaises(ValueError): community._bundle(altered)

    def test_config_duplicate_keys_and_nonfinite_json_are_rejected(self):
        for text in ('{"performance_mode":0,"performance_mode":1}', '{"limit_total_0":NaN}'):
            self.config_path.write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.lab.config()


if __name__ == "__main__":
    unittest.main()
