import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import single_instance as single


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private-user-directory"
        self.api = Mock()
        self.api.CreateEventW.return_value = 0x123456780001
        self.api.CreateMutexW.return_value = 0x123456780002
        self.api.SetEvent.return_value = True
        self.api.CloseHandle.return_value = True
        self.api.WaitForSingleObject.return_value = single._WAIT_TIMEOUT
        self.patch = patch.object(single, "_kernel32", return_value=self.api)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        ctypes.set_last_error(0)

    def guard(self):
        guard = single.InstanceGuard(self.path)
        self.addCleanup(guard.close)
        return guard

    def existing_mutex(self, *_):
        ctypes.set_last_error(single._ERROR_ALREADY_EXISTS)
        return 0x123456780002

    def test_names_resolve_aliases_without_disclosing_paths(self):
        first = self.guard()
        second = single.InstanceGuard(self.path / ".." / self.path.name)
        self.addCleanup(second.close)
        self.assertEqual(first._mutex_name, second._mutex_name)
        self.assertEqual(first._event_name, second._event_name)
        self.assertTrue(first._mutex_name.startswith("Local\\GHelperProfileLab.Instance."))
        self.assertNotIn(self.path.name, first._mutex_name)
        self.assertNotEqual(first._event_name, first._mutex_name)

    def test_owner_keeps_full_width_handles_and_closes_once(self):
        guard = self.guard()
        self.assertTrue(guard.acquire_or_signal())
        self.assertTrue(guard.acquire_or_signal())
        self.assertEqual(self.api.CreateMutexW.call_count, 1)
        self.assertEqual(self.api.method_calls[0][0], "CreateEventW")
        self.assertEqual(self.api.CreateEventW.call_args.args[1:3], (False, False))
        self.api.SetEvent.assert_not_called()
        guard.close()
        guard.close()
        self.assertEqual([c.args[0] for c in self.api.CloseHandle.call_args_list],
                         [0x123456780002, 0x123456780001])
        self.assertFalse(guard.wait_for_show(0))

    def test_duplicate_signals_and_closes_both_handles(self):
        self.api.CreateMutexW.side_effect = self.existing_mutex
        guard = self.guard()
        self.assertFalse(guard.acquire_or_signal())
        self.api.SetEvent.assert_called_once_with(0x123456780001)
        self.assertEqual(self.api.CloseHandle.call_count, 2)
        self.assertFalse(guard.wait_for_show(0))
        self.api.WaitForSingleObject.assert_not_called()

    def test_failed_event_has_no_handle_to_close(self):
        self.api.CreateEventW.return_value = None
        guard = self.guard()
        with self.assertRaisesRegex(OSError, "CreateEventW") as raised:
            guard.acquire_or_signal()
        self.assertNotIn(str(self.path), str(raised.exception))
        self.api.CreateMutexW.assert_not_called()
        self.api.CloseHandle.assert_not_called()

    def test_failed_mutex_closes_event(self):
        self.api.CreateMutexW.return_value = None
        guard = self.guard()
        with self.assertRaisesRegex(OSError, "CreateMutexW"):
            guard.acquire_or_signal()
        self.api.CloseHandle.assert_called_once_with(0x123456780001)

    def test_failed_signal_closes_handles_and_does_not_claim_success(self):
        self.api.CreateMutexW.side_effect = self.existing_mutex
        self.api.SetEvent.return_value = False
        guard = self.guard()
        with self.assertRaisesRegex(OSError, "SetEvent"):
            guard.acquire_or_signal()
        self.assertEqual(self.api.CloseHandle.call_count, 2)

    def test_waits_distinguish_notifications_timeouts_and_failures(self):
        guard = self.guard()
        self.assertFalse(guard.wait_for_show(0))
        self.assertTrue(guard.acquire_or_signal())
        self.api.WaitForSingleObject.side_effect = [single._WAIT_OBJECT_0,
                                                   single._WAIT_TIMEOUT,
                                                   single._WAIT_FAILED, 100]
        self.assertTrue(guard.wait_for_show())
        self.api.WaitForSingleObject.assert_called_with(0x123456780001, 500)
        self.assertFalse(guard.wait_for_show(0))
        with self.assertRaisesRegex(OSError, "WaitForSingleObject"):
            guard.wait_for_show(0)
        with self.assertRaisesRegex(OSError, "unexpected status 100"):
            guard.wait_for_show(0)

    def test_wait_rejects_infinite_and_invalid_timeouts(self):
        guard = self.guard()
        for invalid in (-1, 0xFFFFFFFF, 2 ** 40, True, 1.5, "500"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                guard.wait_for_show(invalid)

    def test_cleanup_attempts_both_handles_after_close_error(self):
        guard = self.guard()
        self.assertTrue(guard.acquire_or_signal())
        self.api.CloseHandle.side_effect = [False, True]
        with self.assertRaisesRegex(OSError, "CloseHandle"):
            guard.close()
        self.assertEqual(self.api.CloseHandle.call_count, 2)
        guard.close()
        self.assertEqual(self.api.CloseHandle.call_count, 2)

    def test_context_closes_on_application_failure(self):
        guard = self.guard()
        with self.assertRaisesRegex(RuntimeError, "application failure"):
            with guard:
                self.assertTrue(guard.acquire_or_signal())
                raise RuntimeError("application failure")
        self.assertEqual(self.api.CloseHandle.call_count, 2)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            guard.acquire_or_signal()


@unittest.skipUnless(os.name == "nt", "Windows named kernel objects")
class NativeGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def child(self, code, path=None):
        result = subprocess.run([sys.executable, "-c", code, str(path or self.path)],
                                cwd=Path(single.__file__).parent,
                                text=True, capture_output=True, timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_ctypes_uses_pointer_sized_handle_signatures(self):
        api = single._kernel32()
        self.assertIs(api.CreateMutexW.restype, wintypes.HANDLE)
        self.assertIs(api.CreateEventW.restype, wintypes.HANDLE)
        self.assertEqual(ctypes.sizeof(api.CreateMutexW.restype), ctypes.sizeof(ctypes.c_void_p))
        self.assertEqual(api.WaitForSingleObject.argtypes, [wintypes.HANDLE, wintypes.DWORD])

    def test_subprocess_duplicate_signal_autoreset_and_reacquisition(self):
        code = ("import sys; from single_instance import InstanceGuard; "
                "guard=InstanceGuard(sys.argv[1]); "
                "print(guard.acquire_or_signal()); guard.close()")
        with single.InstanceGuard(self.path) as owner:
            self.assertTrue(owner.acquire_or_signal())
            self.assertFalse(owner.wait_for_show(0))
            # The notification arrives before the owner begins waiting.
            self.assertEqual(self.child(code), "False")
            self.assertTrue(owner.wait_for_show(1000))
            self.assertFalse(owner.wait_for_show(0))
            self.assertEqual(self.child(code, self.path / "different"), "True")
            self.assertFalse(owner.wait_for_show(0))
        self.assertEqual(self.child(code), "True")

    def test_same_process_also_enforces_single_instance(self):
        with single.InstanceGuard(self.path) as first, single.InstanceGuard(self.path) as second:
            self.assertTrue(first.acquire_or_signal())
            self.assertFalse(second.acquire_or_signal())
            self.assertTrue(first.wait_for_show(1000))

    def test_process_exit_releases_guard_without_explicit_cleanup(self):
        code = ("import os,sys; from single_instance import InstanceGuard; "
                "guard=InstanceGuard(sys.argv[1]); "
                "print(guard.acquire_or_signal(), flush=True); os._exit(0)")
        self.assertEqual(self.child(code), "True")
        with single.InstanceGuard(self.path) as owner:
            self.assertTrue(owner.acquire_or_signal())


if __name__ == "__main__":
    unittest.main()
