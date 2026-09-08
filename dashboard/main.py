#!/usr/bin/env python3
"""Dashboard for the contextual-biasing STT engine.

    python dashboard/main.py                    launch the engine and the UI
    python dashboard/main.py --attach URL       use an engine already running
    python dashboard/main.py --engine PATH      point at a specific binary

The engine is a C++ process that owns the model, the microphone and the filter.
This program launches it, talks HTTP to it, and renders what comes back. It never
decodes audio itself, so what you see here is exactly what the device would do.
"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

# Allow `python dashboard/main.py` from anywhere without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# The combined dashboard is launched from the experiment's Python 3.12 venv.
# Load Torch before PyQt modifies Windows' DLL search path; doing this in the
# opposite order can make torch/lib/c10.dll fail with WinError 1114.
EXPERIMENT_DIR = Path(__file__).resolve().parents[1] / "experiments" / \
    "whisper_initial_prompt"
sys.path.insert(0, str(EXPERIMENT_DIR))
try:
    import whisper as _whisper_preload  # noqa: F401,E402
except ImportError:
    _whisper_preload = None

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from vccui.client import EngineClient, EngineError  # noqa: E402
from vccui.engine import EngineProcess, python_hint, resolve_engine  # noqa: E402
from vccui.mainwindow import MainWindow  # noqa: E402


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dashboard", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--attach", metavar="URL",
                        help="use an engine already running at this base URL "
                             "instead of launching one")
    parser.add_argument("--engine", metavar="PATH",
                        help="path to the vcc_engine binary")
    parser.add_argument("--root", metavar="DIR",
                        help="project root (default: autodetected from this file)")
    parser.add_argument("--port", type=int,
                        help="port for the launched engine (default: a free one)")
    parser.add_argument("--model", metavar="ID", help="model to load at startup")
    parser.add_argument("--no-copy", action="store_true",
                        help="run the engine straight from build/bin instead of a "
                             "temp copy (a concurrent rebuild will then fail)")
    parser.add_argument("--timeout", type=float, default=90.0,
                        help="seconds to wait for the engine to answer (default: 90)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    # Ctrl-C in the launching terminal should close the window, not leave a
    # half-dead Qt app with an engine still holding the microphone.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Contextual-biasing STT")

    process: EngineProcess | None = None
    try:
        if args.attach:
            client = EngineClient(args.attach)
            client.state()  # fail fast and loudly if it is not there
            root = Path(args.root).resolve() if args.root else Path.cwd()
        else:
            root, binary = resolve_engine(args.root, args.engine)
            extra = ["--model", args.model] if args.model else []
            process = EngineProcess(binary, root, port=args.port, extra_args=extra)
            process.start(copy_binaries=not args.no_copy)
            client = process.wait_ready(timeout=args.timeout)
    except EngineError as exc:
        if process is not None:
            process.stop()
        QMessageBox.critical(None, "Cannot start the engine",
                             f"{exc}\n\nPython: {python_hint()}")
        return 1

    window = MainWindow(process, client, root if isinstance(root, Path) else Path.cwd())
    window.show()
    try:
        return app.exec_()
    finally:
        # closeEvent already does this; belt and braces for an exec_() that
        # unwinds through an exception.
        if process is not None:
            process.stop()


if __name__ == "__main__":
    sys.exit(main())
