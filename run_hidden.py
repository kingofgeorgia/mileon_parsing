import ctypes
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "relay_background.log"
PARSING_SCRIPT = PROJECT_ROOT / "parsing.py"
RESTART_DELAY_SECONDS = 10
MUTEX_NAME = "Global\\MileONParsingHiddenRunner"


def _acquire_single_instance_mutex() -> int | None:
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return None

    already_exists = ctypes.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    if already_exists:
        return None

    return handle


def _resolve_python_console_executable() -> str:
    current = Path(sys.executable)

    if current.name.lower() == "pythonw.exe":
        python_console = current.with_name("python.exe")
        if python_console.exists():
            return str(python_console)

    return str(current)


def _append_log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as log_stream:
        log_stream.write(f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n")


def main() -> None:
    mutex_handle = _acquire_single_instance_mutex()
    if mutex_handle is None:
        _append_log("Another runner instance is already active. Exiting this instance.")
        return

    if not PARSING_SCRIPT.exists():
        _append_log(f"ERROR: script not found: {PARSING_SCRIPT}")
        return

    python_executable = _resolve_python_console_executable()
    _append_log(f"Starting background runner. Python: {python_executable}")

    while True:
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        with LOG_FILE.open("a", encoding="utf-8") as output_stream:
            output_stream.write(
                f"\n[{datetime.now().isoformat(timespec='seconds')}] "
                "Starting parsing.py\n"
            )
            output_stream.flush()

            try:
                child_env = dict(os.environ)
                child_env["PYTHONIOENCODING"] = "utf-8"
                child_env["PYTHONUTF8"] = "1"

                process = subprocess.Popen(
                    [python_executable, "-X", "utf8", str(PARSING_SCRIPT)],
                    cwd=str(PROJECT_ROOT),
                    stdout=output_stream,
                    stderr=subprocess.STDOUT,
                    env=child_env,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception as error:
                _append_log(f"Failed to launch parsing.py: {error}")
                time.sleep(RESTART_DELAY_SECONDS)
                continue

            return_code = process.wait()

            output_stream.write(
                f"[{datetime.now().isoformat(timespec='seconds')}] "
                f"parsing.py exited with code: {return_code}\n"
            )
            output_stream.flush()

        _append_log(f"Restarting in {RESTART_DELAY_SECONDS} seconds...")
        time.sleep(RESTART_DELAY_SECONDS)


if __name__ == "__main__":
    main()