import ctypes
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import windows_bridge as bridge


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config.json"
        self.config.write_text('{"performance_mode":0}', encoding="utf-8")

    def test_hardware_excludes_virtual_adapters_and_identifiers(self):
        data = {"manufacturer": "ASUS", "model": "Model", "cpu": ["CPU"], "ram_bytes": 32 * 1024**3,
                "bios": "123", "gpu": [{"Name": "NVIDIA RTX", "Physical": True},
                    {"Name": "Virtual GPU", "Physical": True}, {"Name": "Remote GPU", "Physical": False}]}
        with patch.object(bridge, "_powershell_json", return_value=data):
            result = bridge.detect_hardware()
        self.assertEqual(result["gpu"], ["NVIDIA RTX"])
        self.assertEqual(result["ram_gb"], 32)
        self.assertEqual(set(result), {"manufacturer", "model", "cpu", "gpu", "ram_gb", "bios"})

    def _discovery(self, snapshot, log_paths=None):
        with patch.object(bridge, "_installation_snapshot", return_value=snapshot), \
             patch.object(bridge, "_log_evidence", return_value=log_paths or []), \
             patch.object(bridge, "_find_benchmarks", return_value=(None, None)), \
             patch.object(bridge, "_file_version", return_value=None), \
             patch.dict(os.environ, {"APPDATA": str(self.root), "PROGRAMDATA": str(self.root)}):
            return bridge.discover()

    def test_running_elevated_process_can_have_null_path(self):
        result = self._discovery({"processes": [{"ExecutablePath": None}]}, [self.config])
        self.assertTrue(result["ghelper_running"])
        self.assertIsNone(result["ghelper_exe"])
        self.assertTrue(result["config_verified"])
        self.assertTrue(result["warnings"])

    def test_running_portable_config_is_verified(self):
        exe = self.root / "GHelper.exe"
        exe.touch()
        result = self._discovery({"processes": [{"ExecutablePath": str(exe)}]})
        self.assertTrue(result["config_verified"])
        self.assertEqual(result["config_path"], str(self.config))

    def test_scheduled_task_path_alone_is_not_verified(self):
        exe = self.root / "GHelper.exe"
        exe.touch()
        result = self._discovery({"processes": [], "task_exes": [str(exe)]})
        self.assertFalse(result["config_verified"])
        self.assertIn(str(self.config), result["config_candidates"])

    def test_latest_log_load_has_priority_over_portable(self):
        exe = self.root / "GHelper.exe"
        exe.touch()
        log_config = self.root / "other" / "config.json"
        log_config.parent.mkdir()
        log_config.write_text('{"performance_mode":1}', encoding="utf-8")
        result = self._discovery({"processes": [{"ExecutablePath": str(exe)}]}, [log_config])
        self.assertEqual(result["config_path"], str(log_config))

    def test_backup_load_does_not_verify_live_target(self):
        backup = self.root / "config.json.bak"
        backup.write_text('{"performance_mode":1}', encoding="utf-8")
        result = self._discovery({"processes": [{"ExecutablePath": None}]}, [backup])
        self.assertFalse(result["config_verified"])

    def test_log_parser_uses_last_load_and_preserves_spaces(self):
        log = self.root / "log.txt"
        latest = self.root / "space folder" / "config.json"
        log.write_text(f"date: Config loaded from {self.config}\nother\ndate: Config loaded from {latest}\n", encoding="utf-8")
        self.assertEqual(bridge._log_evidence([log]), [latest])

    def test_mode_key_defaults_and_configured_function_key(self):
        self.assertEqual(bridge._configured_chord({}, 0), (0x80, [0x11, 0x10, 0x12]))
        self.assertEqual(bridge._configured_chord({"keybind_profile_0": 0x87, "modifier_keybind_alt": "Alt-Control-Shift"}, 0)[0], 0x87)

    def test_rejects_disabled_unsafe_unknown_and_duplicate_hotkeys(self):
        for config in ({"skip_hotkeys": 1}, {"keybind_profile_0": 0}, {"keybind_profile_0": True},
                       {"modifier_keybind_alt": "control-alt-invalid"}, {"modifier_keybind_alt": "win"},
                       {"keybind_profile_0": 0x81}, {"keybind_profile_0": 0x74}):
            with self.subTest(config=config), self.assertRaises(RuntimeError):
                bridge._configured_chord(config, 0)

    def test_input_layout_uses_full_union_for_64_bit_sendinput(self):
        self.assertEqual(ctypes.sizeof(bridge._INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        self.assertEqual(ctypes.sizeof(bridge._KEYBDINPUT), 24 if ctypes.sizeof(ctypes.c_void_p) == 8 else 16)

    def test_sendinput_key_order_and_release_without_real_input(self):
        native = Mock()
        native.GetAsyncKeyState.return_value = 0
        sent = []

        def capture(count, events, size):
            sent.append([(events[i].ki.wVk, events[i].ki.dwFlags) for i in range(count)])
            self.assertEqual(size, ctypes.sizeof(bridge._INPUT))
            return count

        native.SendInput.side_effect = capture
        with patch.object(bridge.os, "name", "nt"), patch.object(bridge.ctypes, "WinDLL", return_value=native, create=True):
            bridge._send_hotkey(0x80, [0x11, 0x10, 0x12])
        self.assertEqual(sent, [[(0x11, 0), (0x10, 0), (0x12, 0), (0x80, 0),
                                (0x80, 2), (0x12, 2), (0x10, 2), (0x11, 2)]])

    def test_partial_sendinput_releases_keys_and_fails_without_retry(self):
        native = Mock()
        native.GetAsyncKeyState.return_value = 0
        native.SendInput.side_effect = [2, 4]
        with patch.object(bridge.os, "name", "nt"), patch.object(bridge.ctypes, "WinDLL", return_value=native, create=True):
            with self.assertRaises(RuntimeError):
                bridge._send_hotkey(0x80, [0x11, 0x10, 0x12])
        self.assertEqual(native.SendInput.call_count, 2)
        releases = native.SendInput.call_args.args[1]
        self.assertTrue(all(event.ki.dwFlags == 2 for event in releases))

    def test_ac_status_handles_unknown_without_assuming_mains(self):
        for code, expected in [(0, False), (1, True), (255, None)]:
            native = Mock()

            def fill(pointer):
                ctypes.cast(pointer, ctypes.POINTER(bridge._SYSTEM_POWER_STATUS)).contents.ACLineStatus = code
                return 1

            native.GetSystemPowerStatus.side_effect = fill
            with self.subTest(code=code), patch.object(bridge.os, "name", "nt"), \
                 patch.object(bridge.ctypes, "WinDLL", return_value=native, create=True):
                self.assertIs(bridge.ac_connected(), expected)

    def test_switch_requires_verified_path_before_input(self):
        with patch.object(bridge, "ghelper_running", return_value=True), \
             patch.object(bridge, "discover", return_value={"config_verified": False}), \
             patch.object(bridge, "_send_hotkey") as send:
            with self.assertRaises(RuntimeError):
                bridge.switch_mode(1, str(self.config))
            send.assert_not_called()

    def test_switch_reads_back_mode_without_writing_configuration(self):
        before = self.config.read_bytes()
        state = {"config_verified": True, "config_path": str(self.config)}
        with patch.object(bridge, "ghelper_running", return_value=True), \
             patch.object(bridge, "discover", return_value=state), \
             patch.object(bridge, "_read_config", side_effect=[{"performance_mode": 0}, {"performance_mode": 1}]), \
             patch.object(bridge, "_send_hotkey") as send:
            bridge.switch_mode(1, str(self.config))
            send.assert_called_once_with(0x81, [0x11, 0x10, 0x12])
        self.assertEqual(before, self.config.read_bytes())

    def test_mode_readback_timeout_is_a_failure(self):
        with patch.object(bridge, "ghelper_running", return_value=True), \
             patch.object(bridge, "discover", return_value={"config_verified": True, "config_path": str(self.config)}), \
             patch.object(bridge, "_send_hotkey"), patch.object(bridge.time, "monotonic", side_effect=[0, 13]):
            with self.assertRaisesRegex(RuntimeError, "확인하지 못"):
                bridge.switch_mode(1, str(self.config))

    def test_only_engine_is_running_benchmark(self):
        with patch.object(bridge, "_running_names", return_value=["3DMark.exe", "3DMarkCmd.exe", "3DMarkLauncher.exe"]):
            self.assertFalse(bridge.get_benchmark_running())
        with patch.object(bridge, "_running_names", return_value=["3DMarkTimeSpy.exe"]):
            self.assertTrue(bridge.get_benchmark_running())

    def test_guided_opens_only_ui(self):
        exe = self.root / "3DMark.exe"
        exe.touch()
        with patch.object(bridge, "get_benchmark_running", return_value=False), patch.object(bridge.subprocess, "Popen") as popen:
            self.assertIsNone(bridge.start_benchmark("guided", {"benchmark_exe": str(exe)}, "unused"))
            self.assertEqual(popen.call_args.args[0], [str(exe)])

    def test_enterprise_uses_official_fixed_arguments(self):
        exe = self.root / "3DMarkCmd.exe"
        exe.touch()
        (self.root / "timespy.3dmdef").touch()
        out = self.root / "new.3dmark-result"
        with patch.object(bridge, "get_benchmark_running", return_value=False), patch.object(bridge.subprocess, "Popen") as popen:
            result = bridge.start_benchmark("enterprise", {"cli_exe": str(exe)}, str(out))
            self.assertIs(result, popen.return_value)
            self.assertEqual(popen.call_args.args[0], [str(exe), "--definition=timespy.3dmdef", "--out=" + str(out)])
            self.assertEqual(popen.call_args.kwargs["cwd"], str(self.root))

    def test_missing_definition_does_not_launch(self):
        exe = self.root / "3DMarkCmd.exe"
        exe.touch()
        with patch.object(bridge, "get_benchmark_running", return_value=False), patch.object(bridge.subprocess, "Popen") as popen:
            with self.assertRaises(RuntimeError):
                bridge.start_benchmark("enterprise", {"cli_exe": str(exe)}, str(self.root / "new.3dmark-result"))
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
