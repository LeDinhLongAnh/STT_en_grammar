"""Supervision of the vcc_engine child process.

The failure mode this module exists to prevent: a leaked engine process holding
the microphone open after the dashboard is gone. On Windows that means the mic
stays busy until the user finds it in Task Manager. So the process is killed on
window close, on exception, and at interpreter exit, and the class is usable as a
context manager.
"""

from __future__ import annotations

import atexit
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import List, Optional

from .client import EngineClient, EngineError


def find_repo_root(start: Optional[Path] = None) -> Optional[Path]:
    """Walk up looking for config/app.ini, the marker the engine also uses."""
    here = (start or Path(__file__).resolve()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "config" / "app.ini").is_file():
            return candidate
    return None


def find_engine_binary(root: Path) -> Optional[Path]:
    names = ["vcc_engine.exe", "vcc_engine"]
    for sub in ("build/bin", "build/Release/bin", "build"):
        for name in names:
            candidate = root / sub / name
            if candidate.is_file():
                return candidate
    return None


def free_port() -> int:
    """Ask the OS for an unused port.

    Binding to 0 and reading the assignment races with the engine binding it a
    moment later, but the window is microseconds on loopback and the alternative
    -- a fixed port -- collides with a second dashboard or a leftover engine,
    which happens far more often in practice.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class EngineProcess:
    """Launches vcc_engine and owns its lifetime."""

    def __init__(self, binary: Path, root: Path, port: Optional[int] = None,
                 extra_args: Optional[List[str]] = None) -> None:
        self.binary = Path(binary)
        self.root = Path(root)
        self.port = port or free_port()
        self.extra_args = list(extra_args or [])
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._proc: Optional[subprocess.Popen] = None
        self._log: List[str] = []
        self._log_lock = threading.Lock()
        self._reader: Optional[threading.Thread] = None
        self._workdir: Optional[Path] = None
        atexit.register(self.stop)

    # -- lifecycle ---------------------------------------------------------

    def start(self, copy_binaries: bool = True) -> None:
        """Start the engine.

        ``copy_binaries`` runs it from a temp copy of build/bin. That matters
        while somebody is rebuilding the C++ side: on Windows a running exe is
        locked, so launching from build/bin makes their link step fail. Copying
        costs ~20 MB of temp space and removes the whole class of problem.
        """
        if self.running:
            return

        binary = self.binary
        if copy_binaries:
            binary = self._stage_binaries()

        args = [str(binary), "--port", str(self.port), "--root", str(self.root),
                *self.extra_args]
        creation = 0
        if os.name == "nt":
            # No console window, and its own process group so our Ctrl-C does
            # not race with our own shutdown path.
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) | \
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        self._proc = subprocess.Popen(
            args,
            cwd=str(self.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creation,
        )
        self._reader = threading.Thread(target=self._drain, daemon=True)
        self._reader.start()

    def _stage_binaries(self) -> Path:
        self._workdir = Path(tempfile.mkdtemp(prefix="vcc-engine-"))
        src = self.binary.parent
        for item in src.iterdir():
            if item.suffix.lower() in (".exe", ".dll", ".so", ".dylib") or \
                    ".so." in item.name:
                shutil.copy2(item, self._workdir / item.name)
        staged = self._workdir / self.binary.name
        return staged if staged.is_file() else self.binary

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def exit_code(self) -> Optional[int]:
        return None if self._proc is None else self._proc.poll()

    def stop(self, timeout: float = 5.0) -> None:
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    pass
        if self._workdir is not None:
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None

    def __enter__(self) -> "EngineProcess":
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()

    # -- readiness and logs ------------------------------------------------

    def wait_ready(self, timeout: float = 60.0) -> EngineClient:
        """Poll /api/state until the engine answers.

        Loading a model takes a couple of seconds, so the timeout is generous.
        A dead process short-circuits with its own log attached -- when a model
        fails to load, that text is the only explanation the user gets.
        """
        client = EngineClient(self.base_url, timeout=5.0)
        deadline = time.monotonic() + timeout
        last: Optional[str] = None
        while time.monotonic() < deadline:
            if not self.running:
                raise EngineError(
                    f"the engine exited with status {self.exit_code}\n\n"
                    + self.log_text())
            try:
                client.state()
                return client
            except EngineError as exc:
                last = str(exc)
                time.sleep(0.15)
        raise EngineError(
            f"the engine did not answer within {timeout:.0f}s ({last})\n\n"
            + self.log_text())

    def _drain(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            with self._log_lock:
                self._log.append(line.rstrip("\r\n"))
                # Bounded: a debug-enabled engine is extremely chatty and this
                # is a diagnostic pane, not an archive.
                if len(self._log) > 2000:
                    del self._log[:1000]

    def log_text(self) -> str:
        with self._log_lock:
            return "\n".join(self._log)

    def log_lines(self, since: int = 0) -> tuple[list[str], int]:
        """Lines added after index ``since``, plus the new index."""
        with self._log_lock:
            return list(self._log[since:]), len(self._log)


def resolve_engine(root: Optional[str], engine: Optional[str]) -> tuple[Path, Path]:
    """Work out the repo root and engine binary, with actionable errors."""
    repo = Path(root).resolve() if root else find_repo_root()
    if repo is None or not (repo / "config" / "app.ini").is_file():
        raise EngineError(
            "cannot find the project root (looked for config/app.ini). "
            "Pass --root <dir>.")

    if engine:
        binary = Path(engine).resolve()
        if not binary.is_file():
            raise EngineError(f"engine binary not found: {binary}")
        return repo, binary

    found = find_engine_binary(repo)
    if found is None:
        raise EngineError(
            "vcc_engine not built. Build it first:\n"
            "    scripts\\build.bat Release\n"
            f"(looked under {repo / 'build' / 'bin'})")
    return repo, found


def python_hint() -> str:
    return f"{sys.executable} (Python {sys.version.split()[0]})"
