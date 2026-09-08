"""Bridge: nạp experiment Sherpa-ONNX VI vào dashboard chính."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from PyQt5.QtCore import Qt


MODULE_NAME = "_vcc_sherpa_vi_experiment"


def create_sherpa_vi_dashboard(root: Path, parent: Any = None) -> Any:
    """Load experiment bằng đường dẫn tuyệt đối, không cần cài như package."""
    module = sys.modules.get(MODULE_NAME)
    if module is None:
        experiment_dir = root / "experiments" / "sherpa_vi"
        source = experiment_dir / "dashboard.py"
        if not source.is_file():
            raise RuntimeError(f"Sherpa VI dashboard not found: {source}")
        sys.path.insert(0, str(experiment_dir))
        spec = importlib.util.spec_from_file_location(MODULE_NAME, source)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load {source}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[MODULE_NAME] = module
        spec.loader.exec_module(module)

    window = module.SherpaViDashboard()
    window.setParent(parent)
    window.setWindowFlags(Qt.Widget)
    return window
