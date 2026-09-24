"""Session-local Windows single-instance guard and show-window notification."""

import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import threading


_ERROR_ALREADY_EXISTS = 183
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258
_WAIT_FAILED = 0xFFFFFFFF


def _kernel32():
    if os.name != "nt":
        raise OSError("The single-instance guard requires Windows.")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateMutexW.restype = wintypes.HANDLE
    api.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateEventW.restype = wintypes.HANDLE
    api.SetEvent.argtypes = [wintypes.HANDLE]
    api.SetEvent.restype = wintypes.BOOL
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


def _error(operation, code=None):
    code = ctypes.get_last_error() if code is None else code
    # Do not put the user's data directory or other identifying text in errors.
    return OSError(code, f"{operation} failed (Windows error {code}).")


class InstanceGuard:
    """Keep one owner per resolved data directory in the current Windows session.

    Call acquire_or_signal before creating application state or a server. A False
    result means the existing owner was signaled and this launch should exit.
    The owner polls wait_for_show and opens its window when it returns True.
    close must follow stopping the poller; it also safely serializes an active
    bounded wait. The guard can be used as a context manager for cleanup.
    """

    def __init__(self, data_path):
        canonical = os.path.normcase(str(Path(data_path).resolve()))
        digest = hashlib.sha256(canonical.encode("utf-8", "surrogatepass")).hexdigest()
        self._mutex_name = "Local\\GHelperProfileLab.Instance." + digest
        self._event_name = "Local\\GHelperProfileLab.Show." + digest
        self._api = _kernel32()
        self._mutex = None
        self._event = None
        self._owner = False
        self._attempted = False
        self._closed = False
        self._lock = threading.Lock()

    def acquire_or_signal(self):
        """Return True for the owner, or notify the owner and return False."""
        with self._lock:
            if self._closed:
                raise RuntimeError("The single-instance guard is closed.")
            if self._attempted:
                return self._owner
            try:
                # Create/open the event first: an overlapping second launch can
                # signal even before the owner starts its notification thread.
                self._event = self._api.CreateEventW(None, False, False, self._event_name)
                if not self._event:
                    raise _error("CreateEventW")
                ctypes.set_last_error(0)
                # Keeping the first-created mutex handle alive establishes the
                # owner. No thread owns the mutex, so cleanup can occur on any
                # thread and no ReleaseMutex/abandonment handling is necessary.
                self._mutex = self._api.CreateMutexW(None, False, self._mutex_name)
                creation_error = ctypes.get_last_error()
                if not self._mutex:
                    raise _error("CreateMutexW", creation_error)
                self._owner = creation_error != _ERROR_ALREADY_EXISTS
                if not self._owner:
                    if not self._api.SetEvent(self._event):
                        raise _error("SetEvent")
                    self._close_handles()
                self._attempted = True
                return self._owner
            except BaseException:
                self._owner = False
                try:
                    self._close_handles()
                except OSError:
                    pass  # Preserve the operation error after trying every handle.
                raise

    def wait_for_show(self, timeout_ms=500):
        """Consume one show notification, or return False after a finite wait."""
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
            raise ValueError("The notification timeout must be an integer.")
        if not 0 <= timeout_ms < _WAIT_FAILED:
            raise ValueError("The notification timeout must be finite and nonnegative.")
        with self._lock:
            if self._closed or not self._owner or not self._event:
                return False
            result = self._api.WaitForSingleObject(self._event, timeout_ms)
            if result == _WAIT_OBJECT_0:
                return True
            if result == _WAIT_TIMEOUT:
                return False
            if result == _WAIT_FAILED:
                raise _error("WaitForSingleObject")
            raise OSError(f"WaitForSingleObject returned unexpected status {result}.")

    def _close_handles(self):
        first_error = None
        # Release the singleton before the show event. Both handles are attempted
        # even if one close reports an error; never double-close a reused handle.
        for attribute in ("_mutex", "_event"):
            handle = getattr(self, attribute)
            setattr(self, attribute, None)
            if handle and not self._api.CloseHandle(handle) and first_error is None:
                first_error = _error("CloseHandle")
        if first_error is not None:
            raise first_error

    def close(self):
        """Close native handles. Repeated calls have no effect."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._owner = False
            self._close_handles()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.close()
        else:
            try:
                self.close()
            except OSError:
                pass
