"""Bridge the isolated Whisper prompt experiment into the main dashboard."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from PyQt5.QtCore import Qt


MODULE_NAME = "_vcc_whisper_prompt_experiment"


def create_whisper_prompt_dashboard(root: Path, parent: Any = None) -> Any:
    """Load the experiment by absolute path, without making it production code."""
    module = sys.modules.get(MODULE_NAME)
    if module is None:
        experiment_dir = root / "experiments" / "whisper_initial_prompt"
        source = experiment_dir / "dashboard.py"
        if not source.is_file():
            raise RuntimeError(f"Whisper prompt dashboard not found: {source}")
        sys.path.insert(0, str(experiment_dir))
        spec = importlib.util.spec_from_file_location(MODULE_NAME, source)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {source}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[MODULE_NAME] = module
        spec.loader.exec_module(module)

    window = module.WhisperPromptDashboard()
    window.setParent(parent)
    window.setWindowFlags(Qt.Widget)
    return window
