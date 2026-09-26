"""Bounded orchestration tests: temporary config/results, fake time, no desktop IO."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

import core


class FakeCancel:
    def __init__(self):
        self.flag = False
        self.waits = []
        self.on_wait = None

    def clear(self):
        self.flag = False

    def set(self):
        self.flag = True

    def is_set(self):
        return self.flag

    def wait(self, seconds):
        self.waits.append(seconds)
        if len(self.waits) > 100:
            raise AssertionError("Unexpected orchestration loop exceeds bounded test budget")
        if self.on_wait:
            self.on_wait(seconds)
        return self.flag


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config_path = self.root / "config.json"
        self.config_path.write_text(json.dumps({"performance_mode": 0, "limit_total_0": 35,
                                              "limit_total_1": 80, "limit_total_2": 20}), encoding="utf-8")
        self.results = self.root / "benchmark-results"
        self.results.mkdir()
        self.hardware = {"manufacturer": "ASUS", "model": "SYNTHETIC", "cpu": "Test CPU",
                         "gpu": ["Test GPU"], "ram_gb": 32, "bios": "000"}
        discovery = {"config_path": str(self.config_path), "config_verified": True,
                     "ghelper_running": True, "ghelper_version": "test", "results_dir": str(self.results),
                     "cli_exe": str(self.root / "3DMarkCmd.exe"), "benchmark_exe": str(self.root / "3DMark.exe")}
        for target, value in (("detect_hardware", self.hardware), ("discover", discovery),
                              ("ghelper_running", True), ("ac_connected", True), ("get_benchmark_running", False)):
            patcher = patch.object(core.bridge, target, return_value=value)
            setattr(self, "mock_" + target, patcher.start())
            self.addCleanup(patcher.stop)
        self.actions = []
        patcher = patch.object(core.bridge, "switch_mode", side_effect=self.switch_fake_mode)
        self.mock_switch = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(core.bridge, "start_benchmark", side_effect=self.launch_fake_benchmark)
        self.mock_launch = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(core.threading, "Thread")
        self.mock_thread = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(core.time, "sleep", side_effect=lambda seconds: self.actions.append(("sleep", seconds)))
        self.mock_sleep = patcher.start()
        self.addCleanup(patcher.stop)
        self.clock = 0
        self.clock_step = 1
        patcher = patch.object(core.time, "monotonic", side_effect=self.fake_time)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.lab = core.Lab(self.root / "data", self.root / "assets")
        self.event = FakeCancel()
        self.lab.cancel = self.event
        self.journal = self.lab.data / "benchmark-recovery.json"
        self.launch_count = 0
        self.poll_in_run = 0
        self.raw_results = []
        self.event.on_wait = self.default_wait

    def fake_time(self):
        self.clock += self.clock_step
        return self.clock

    def default_wait(self, seconds):
        if seconds == 2:
            self.poll_in_run += 1

    def update_fake_config(self, **updates):
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        data.update(updates)
        self.config_path.write_text(json.dumps(data), encoding="utf-8")

    def switch_fake_mode(self, mode, path):
        self.assertEqual(Path(path), self.config_path)
        self.actions.append(("switch", mode))
        self.update_fake_config(performance_mode=mode)

    def launch_fake_benchmark(self, driver, discovery, output_path, cancel_event=None):
        if driver == "steam":
            self.assertIs(cancel_event, self.event)
        self.launch_count += 1
        self.poll_in_run = 0
        self.actions.append(("launch", driver))
        path = Path(output_path) if driver == "enterprise" else self.results / f"run-{self.launch_count}.3dmark-result"
        xml = (f"<Result><TimeSpyPerformance3DMarkScore>{12000 + self.launch_count}</TimeSpyPerformance3DMarkScore>"
               "<TimeSpyPerformanceGraphicsScore>13000</TimeSpyPerformanceGraphicsScore>"
               "<TimeSpyPerformanceCPUScore>10000</TimeSpyPerformanceCPUScore></Result>")
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("Result.xml", xml)
        self.raw_results.append((path, path.read_bytes()))
        return Mock(poll=Mock(return_value=0)) if driver == "enterprise" else None

    def execute(self, driver="enterprise"):
        # start() must persist recovery metadata before a background worker runs.
        state = self.lab.start(driver, 30)
        self.assertEqual(state["status"], "running")
        self.assertTrue(self.journal.is_file())
        self.mock_thread.return_value.start.assert_called_once()
        self.lab._benchmark(driver, 30, 0)
        self.assertLessEqual(len(self.event.waits), 100)

    def assert_restored_without_bound_scores(self, status="failed"):
        self.assertEqual(self.lab.benchmark["status"], status)
        self.assertEqual(core.load_json(self.config_path)["performance_mode"], 0)
        self.assertEqual(self.lab.db["runs"], [])
        self.assertEqual(self.actions[-1], ("switch", 0))
        self.assertFalse(self.journal.exists())

    def test_three_mode_sequence_restores_original_and_archives_bound_raw_results(self):
        self.execute()
        self.assertEqual([entry[1] for entry in self.actions if entry[0] == "switch"], [2, 0, 1, 0])
        self.assertEqual(self.lab.benchmark["status"], "complete")
        self.assertEqual(self.lab.benchmark["completed"], 3)
        self.assertEqual(self.launch_count, 3)
        self.assertEqual([run["mode"] for run in reversed(self.lab.db["runs"])], [2, 0, 1])
        for run in self.lab.db["runs"]:
            profile = self.lab.profile(run["profileId"])
            self.assertEqual(run["settingsHash"], profile["settingsHash"])
            self.assertEqual(run["binding"], "captured")
            self.assertEqual(run["status"], "valid")
        for path, original_bytes in self.raw_results:
            archived = self.lab.data / "results" / (core.file_hash(path) + ".3dmark-result")
            self.assertEqual(archived.read_bytes(), original_bytes)
        self.assertEqual(core.load_json(self.config_path)["performance_mode"], 0)
        self.assertFalse(self.journal.exists())
        self.mock_sleep.assert_not_called()

    def test_guided_requires_observed_engine_then_captures_after_stop(self):
        self.mock_get_benchmark_running.side_effect = lambda: self.poll_in_run == 1
        self.execute("guided")
        self.assertEqual(self.lab.benchmark["status"], "complete")
        self.assertEqual(len(self.lab.db["runs"]), 3)
        self.assertEqual(self.launch_count, 3)

    def test_steam_auto_launches_each_mode_and_requires_observed_engine(self):
        self.mock_get_benchmark_running.side_effect = lambda: self.poll_in_run == 1
        self.execute("steam")
        self.assertEqual(self.lab.benchmark["status"], "complete")
        self.assertEqual([action for action in self.actions if action[0] == "launch"],
                         [("launch", "steam")] * 3)
        self.assertEqual(len(self.lab.db["runs"]), 3)

    def test_steam_launcher_only_install_fails_before_mode_change(self):
        self.lab.discovery["benchmark_exe"] = str(self.root / "3DMarkLauncher.exe")
        with self.assertRaisesRegex(ValueError, "3DMark.exe"):
            self.lab.start("steam", 30)
        self.assertFalse(self.journal.exists())
        self.mock_switch.assert_not_called()

    def test_guided_does_not_bind_new_result_without_engine_observation(self):
        self.clock_step = 500  # Bounded simulated timeout; no wall-clock waiting.
        self.execute("guided")
        self.assert_restored_without_bound_scores()
        self.assertEqual(self.launch_count, 1)
        self.assertGreaterEqual(self.event.waits.count(2), 2)

    def test_cancel_during_cooldown_restores_without_launching(self):
        def cancel_at_cooldown(seconds):
            if seconds == 30:
                self.event.set()
        self.event.on_wait = cancel_at_cooldown
        self.execute()
        self.assert_restored_without_bound_scores("cancelled")
        self.mock_launch.assert_not_called()
        self.assertEqual(self.lab.db["profiles"], [])

    def test_cooldown_state_has_deadline_then_clears_it_after_cancelled_restore(self):
        cooling_states = []

        def observe_and_cancel_cooldown(seconds):
            if seconds == 30:
                cooling_states.append(self.lab.state()["benchmark"])
                self.event.set()

        self.event.on_wait = observe_and_cancel_cooldown
        with patch.object(core.time, "time", return_value=1_700_000_000):
            self.execute("enterprise")

        self.assertEqual(len(cooling_states), 1)
        cooling = cooling_states[0]
        self.assertEqual(cooling["status"], "cooling")
        self.assertEqual(cooling["driver"], "enterprise")
        self.assertEqual(cooling["cooldownUntil"], 1_700_000_030)
        self.assertIs(cooling["engineRunning"], False)
        self.assert_restored_without_bound_scores("cancelled")
        restored = self.lab.state()["benchmark"]
        self.assertIs(restored["engineRunning"], False)
        self.assertIsNone(restored["cooldownUntil"])
        self.mock_launch.assert_not_called()

    def test_guided_state_reports_observed_engine_and_clears_it_after_restore(self):
        engine_states = []

        def observe_running_engine(seconds):
            self.default_wait(seconds)
            if seconds == 2 and self.poll_in_run == 2:
                # The first poll observed the engine; the next one observes it stop.
                engine_states.append(self.lab.state()["benchmark"])

        self.event.on_wait = observe_running_engine
        self.mock_get_benchmark_running.side_effect = lambda: self.poll_in_run == 1
        self.execute("guided")

        self.assertEqual([state["mode"] for state in engine_states], [2, 0, 1])
        for state in engine_states:
            with self.subTest(mode=state["mode"]):
                self.assertEqual(state["status"], "waiting")
                self.assertEqual(state["driver"], "guided")
                self.assertIs(state["engineRunning"], True)
                self.assertIsNone(state["cooldownUntil"])
        restored = self.lab.state()["benchmark"]
        self.assertEqual(restored["status"], "complete")
        self.assertEqual(restored["completed"], 3)
        self.assertIs(restored["engineRunning"], False)
        self.assertIsNone(restored["cooldownUntil"])
        self.assertEqual(core.load_json(self.config_path)["performance_mode"], 0)
        self.assertFalse(self.journal.exists())

    def test_cancel_waits_for_engine_stop_before_restoring(self):
        def cancel_second_poll(seconds):
            self.default_wait(seconds)
            if self.poll_in_run == 2:
                self.event.set()
        self.event.on_wait = cancel_second_poll
        # start preflight; first result poll; finalizer waits once, then stopped.
        self.mock_get_benchmark_running.side_effect = [False, True, True, False]
        self.execute("guided")
        self.assert_restored_without_bound_scores("cancelled")
        self.mock_sleep.assert_called_once_with(3)
        self.assertEqual(self.actions[-2:], [("sleep", 3), ("switch", 0)])

    def test_ac_loss_during_wait_refuses_binding_and_restores(self):
        # Preflight and first mode preparation succeed, first result poll loses AC.
        self.mock_ac_connected.side_effect = [True, True, False]
        self.execute()
        self.assert_restored_without_bound_scores()
        self.assertEqual(self.launch_count, 1)

    def test_settings_or_mode_change_during_wait_refuses_binding(self):
        for updates in ({"limit_total_0": 46}, {"performance_mode": 1}):
            with self.subTest(updates=updates):
                # Use independent Lab state to keep both safety scenarios isolated.
                self.lab.db["runs"].clear()
                self.lab.benchmark["status"] = "idle"
                self.mock_thread.reset_mock()
                self.actions.clear()
                self.event.clear()
                self.poll_in_run = 0
                self.update_fake_config(performance_mode=0, limit_total_0=35)

                def mutate_on_first_poll(seconds):
                    self.default_wait(seconds)
                    if seconds == 2 and self.poll_in_run == 1:
                        self.update_fake_config(**updates)

                self.event.on_wait = mutate_on_first_poll
                self.execute()
                self.assert_restored_without_bound_scores()

    def test_cli_launch_error_restores_without_binding(self):
        self.mock_launch.side_effect = RuntimeError("Synthetic license failure")
        self.execute()
        self.assert_restored_without_bound_scores()
        self.assertIn("Synthetic license failure", self.lab.benchmark["message"])

    def test_nonzero_cli_exit_refuses_even_a_parseable_result(self):
        def failed_process(driver, discovery, output):
            self.launch_fake_benchmark(driver, discovery, output)
            return Mock(poll=Mock(return_value=2))
        self.mock_launch.side_effect = failed_process
        self.execute()
        self.assert_restored_without_bound_scores()

    def test_failed_restore_retains_original_recovery_journal(self):
        def fail_only_restoration(mode, path):
            if mode == 0:
                raise RuntimeError("Synthetic restore failure")
            self.switch_fake_mode(mode, path)
        self.mock_switch.side_effect = fail_only_restoration
        self.mock_launch.side_effect = RuntimeError("Synthetic execution failure")
        self.execute()
        self.assertEqual(self.lab.benchmark["status"], "recovery")
        self.assertEqual(self.lab.db["runs"], [])
        self.assertEqual(core.load_json(self.journal)["originalMode"], 0)
        self.assertIn("Synthetic restore failure", self.lab.benchmark["message"])

    def test_start_writes_journal_before_scheduling_background_worker(self):
        self.event.set()
        self.lab.start("enterprise", 30)
        self.assertFalse(self.event.is_set())
        self.assertEqual(core.load_json(self.journal)["originalMode"], 0)
        self.mock_thread.assert_called_once_with(target=self.lab._benchmark, args=("enterprise", 30, 0), daemon=True)
        self.mock_thread.return_value.start.assert_called_once()
        self.mock_switch.assert_not_called()
        self.mock_launch.assert_not_called()

    def test_start_preflight_failure_creates_no_journal_or_worker(self):
        cases = [(self.mock_ac_connected, False), (self.mock_ac_connected, None),
                 (self.mock_ghelper_running, False), (self.mock_get_benchmark_running, True)]
        for mock, value in cases:
            original = mock.return_value
            mock.return_value = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.lab.start("enterprise", 30)
            mock.return_value = original
            self.assertFalse(self.journal.exists())
            self.mock_thread.assert_not_called()
        self.mock_switch.assert_not_called()
        self.mock_launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
