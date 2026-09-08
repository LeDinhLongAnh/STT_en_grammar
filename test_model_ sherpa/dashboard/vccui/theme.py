"""Colours, derived from the Qt palette rather than hardcoded.

The dashboard has to stay readable under a dark system theme, and hardcoding
"#f5f5f5" is how a tool becomes unusable for half its users. So the accent
colours here are chosen for contrast against the *current* palette's window
colour, and everything else comes from the palette itself.
"""

from __future__ import annotations

from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication


def _is_dark() -> bool:
    palette = QApplication.palette()
    return palette.color(QPalette.Window).lightness() < 128


class Theme:
    """Semantic colours. Instantiate after QApplication exists."""

    def __init__(self) -> None:
        dark = _is_dark()
        self.dark = dark

        # Diff and status colours. Two variants each, because a green that reads
        # on white is invisible on charcoal and vice versa.
        self.equal = QColor("#9aa3b2") if dark else QColor("#6b7280")
        self.added = QColor("#62c98d") if dark else QColor("#1f7a4d")
        self.removed = QColor("#e88b8b") if dark else QColor("#a52a2a")
        self.changed = QColor("#e0b060") if dark else QColor("#9a6209")

        self.ok = self.added
        self.warn = self.changed
        self.bad = self.removed
        self.muted = self.equal

        self.raw_text = QApplication.palette().color(QPalette.Text)
        self.filtered_text = QColor("#8fc4f0") if dark else QColor("#1d4e89")

        # Level meter: green up to about -12 dBFS, amber, then red at clipping.
        self.meter_ok = self.added
        self.meter_hot = self.changed
        self.meter_clip = self.removed

        self.panel_border = QColor("#2b3038") if dark else QColor("#dfe3ea")

    # -- helpers -----------------------------------------------------------

    def hex(self, colour: QColor) -> str:
        return colour.name()

    def diff_colour(self, op: str) -> QColor:
        return {
            "equal": self.equal,
            "insert": self.added,
            "delete": self.removed,
            "substitute": self.changed,
        }.get(op, self.equal)

    def meter_colour(self, peak_dbfs: float, clipped: bool) -> QColor:
        if clipped or peak_dbfs > -1.0:
            return self.meter_clip
        if peak_dbfs > -12.0:
            return self.meter_hot
        return self.meter_ok

    def level_advice(self, peak_dbfs: float, clipped: bool) -> str:
        """One short sentence, or empty when the level is fine.

        This exists so the user can tell "the model is wrong" from "the
        microphone did not hear me", which is the single most common confusion
        when testing speech recognition.
        """
        if clipped:
            return "clipping - lower the input gain"
        if peak_dbfs < -45.0:
            return "almost silent - is the right device selected?"
        if peak_dbfs < -35.0:
            return "very quiet - move closer to the mic"
        return ""
