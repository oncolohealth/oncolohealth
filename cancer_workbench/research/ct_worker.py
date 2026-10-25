"""Bounded CT worker: input/output only, with an independent owner/deadline guard."""
import argparse
import json
import os
from pathlib import Path
import threading
import time


def start_guard(parent_pid: int, limit_seconds: float = 600):
    """Stop this process if its owning app exits, even while Torch is running."""
    if parent_pid <= 0 or parent_pid == os.getpid():
        raise ValueError('A distinct live owning app PID is required.')
    stop = threading.Event()
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, parent_pid)  # SYNCHRONIZE
        if not handle:
            raise RuntimeError('Cannot monitor the owning app; CT worker will not start.')
        def alive():
            return kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT
        def close():
            kernel.CloseHandle(handle)
    else:
        def alive():
            if os.getppid() != parent_pid:
                return False
            try:
                os.kill(parent_pid, 0)
                return True
            except ProcessLookupError:
                return False
        def close():
            pass
    deadline = time.monotonic() + limit_seconds
    def watch():
        try:
            while not stop.is_set():
                if not alive():
                    os._exit(125)
                if time.monotonic() >= deadline:
                    os._exit(124)
                stop.wait(.25)
        finally:
            close()
    threading.Thread(target=watch, daemon=True, name='ct-owner-deadline').start()
    return stop


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--parent-pid', type=int, required=True)
    args = parser.parse_args()
    guard = start_guard(args.parent_pid)
    try:
        from . import ct
        result = ct.run(args.input, args.out)
        (args.out/'detector-result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    finally:
        guard.set()


if __name__ == '__main__':
    main()
