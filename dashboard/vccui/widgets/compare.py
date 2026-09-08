"""The comparison view: what the STT said, and what the filter made of it.

This is the centre of the tool. Everything else exists to change one variable
and come back here.

Layout of one card:

    #3  mic  2.1s  rtf 0.04                          [ CHANGED ]
    raw       TURN ON GAS NETWORK
    filtered  TURN ON GUEST NETWORK
    diff      turn on [gas -> guest] network
    rules     gas => guest

The raw line is the honest baseline -- the same model, the same decoding method,
the same audio, with the hotword list withheld. That is what makes the
comparison mean something rather than being a before/after of two configurations
that differ in several ways at once.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ..theme import Theme

_MONO = "Cascadia Mono, Consolas, DejaVu Sans Mono, monospace"


def _mono(size: int = 11, bold: bool = False) -> QFont:
    font = QFont()
    font.setFamilies([f.strip() for f in _MONO.split(",")])
    font.setStyleHint(QFont.Monospace)
    font.setPointSize(size)
    font.setBold(bold)
    return font


def diff_html(spans: List[Dict[str, Any]], theme: Theme) -> str:
    """Render a diff span list as inline HTML.

    Substitutions show both sides, because "which word moved" is the question
    being asked and a one-sided diff cannot answer it.
    """
    parts: List[str] = []
    for span in spans:
        op = span.get("op", "equal")
        a = span.get("a", "")
        b = span.get("b", "")
        colour = theme.hex(theme.diff_colour(op))
        if op == "equal":
            parts.append(f'<span style="color:{theme.hex(theme.equal)}">{a}</span>')
        elif op == "substitute":
            parts.append(
                f'<span style="color:{colour}"><s>{a}</s>&nbsp;{b}</span>')
        elif op == "delete":
            parts.append(f'<span style="color:{colour}"><s>{a}</s></span>')
        elif op == "insert":
            parts.append(f'<span style="color:{colour}"><b>{b}</b></span>')
    return " ".join(parts)


class ComparisonCard(QFrame):
    """One utterance, decoded both ways."""

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.theme = theme
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        header = QHBoxLayout()
        self.title = QLabel()
        self.title.setFont(_mono(10))
        self.badge = QLabel()
        self.badge.setFont(_mono(9, bold=True))
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.badge)
        layout.addLayout(header)

        self.raw = self._text_row(layout, "raw")
        self.filtered = self._text_row(layout, "filtered", emphasise=True)
        self.diff = self._text_row(layout, "diff")
        self.rules = self._text_row(layout, "rules")
        self.note = QLabel()
        self.note.setFont(_mono(9))
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

    def _text_row(self, layout: QVBoxLayout, label: str,
                  emphasise: bool = False) -> QLabel:
        row = QHBoxLayout()
        row.setSpacing(8)
        tag = QLabel(label)
        tag.setFont(_mono(9))
        tag.setFixedWidth(58)
        tag.setAlignment(Qt.AlignRight | Qt.AlignTop)
        tag.setStyleSheet(f"color: {self.theme.hex(self.theme.muted)};")
        value = QLabel()
        value.setFont(_mono(12 if emphasise else 10, bold=emphasise))
        value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        row.addWidget(tag)
        row.addWidget(value, 1)
        layout.addLayout(row)
        return value

    def set_utterance(self, item: Dict[str, Any]) -> None:
        result = item.get("result") or {}
        index = item.get("index", 0)
        source = item.get("source", "?")

        if not result.get("ok", False):
            self.title.setText(f"#{index}  {source}")
            self.badge.setText("ERROR")
            self.badge.setStyleSheet(f"color: {self.theme.hex(self.theme.bad)};")
            self.raw.setText(result.get("error", "decode failed"))
            for widget in (self.filtered, self.diff, self.rules, self.note):
                widget.clear()
            return

        raw_text = (result.get("raw") or {}).get("text", "")
        filtered = result.get("filtered", "")
        changed = bool(result.get("changed"))

        bits = [f"#{index}", source, f'{result.get("audio_s", 0):.1f}s']
        biased = result.get("biased") or {}
        if biased.get("rtf"):
            bits.append(f'rtf {biased["rtf"]:.2f}')
        if result.get("has_reference"):
            bits.append(f'WER {result.get("wer_raw", 0) * 100:.0f}%'
                        f' -> {result.get("wer_filtered", 0) * 100:.0f}%')
        self.title.setText("   ".join(bits))

        if changed:
            self.badge.setText("CHANGED")
            self.badge.setStyleSheet(f"color: {self.theme.hex(self.theme.changed)};")
        else:
            self.badge.setText("same")
            self.badge.setStyleSheet(f"color: {self.theme.hex(self.theme.muted)};")

        self.raw.setText(raw_text or "(nothing recognised)")
        self.raw.setStyleSheet(f"color: {self.theme.hex(self.theme.raw_text)};")
        self.filtered.setText(filtered or "(nothing recognised)")
        self.filtered.setStyleSheet(
            f"color: {self.theme.hex(self.theme.filtered_text)};" if changed else "")

        spans = result.get("diff") or []
        if changed and spans:
            self.diff.setText(diff_html(spans, self.theme))
            self.diff.show()
        else:
            self.diff.setText("(the filter changed nothing)")
            self.diff.setStyleSheet(f"color: {self.theme.hex(self.theme.muted)};")

        rules = result.get("rules") or []
        if rules:
            self.rules.setText(", ".join(
                f'{r.get("from")} => {r.get("to")}' for r in rules))
            self.rules.show()
        else:
            self.rules.clear()
            self.rules.hide()

        advice = self.theme.level_advice(
            float(result.get("peak_dbfs", 0.0)), bool(result.get("clipped")))
        if advice:
            self.note.setText(f"input: {advice}")
            self.note.setStyleSheet(f"color: {self.theme.hex(self.theme.warn)};")
            self.note.show()
        else:
            self.note.clear()
            self.note.hide()


class ComparisonList(QScrollArea):
    """Newest-first list of comparison cards."""

    count_changed = pyqtSignal(int, int)  # total, changed

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.theme = theme
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)

        self._body = QWidget()
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._empty = QLabel(
            "Nothing yet.\n\n"
            "Start listening and say something, or drop a .wav file on the window.")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setStyleSheet(f"color: {theme.hex(theme.muted)};")
        self._layout.addWidget(self._empty)
        self._layout.addStretch(1)
        self.setWidget(self._body)

        self._cards: Dict[int, ComparisonCard] = {}

    def set_items(self, items: List[Dict[str, Any]]) -> None:
        """Replace everything. Used after a re-decode, which rewrites history."""
        for card in self._cards.values():
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        for item in items:
            self._insert(item)
        self._refresh_empty()

    def upsert(self, item: Dict[str, Any]) -> None:
        index = int(item.get("index", 0))
        card = self._cards.get(index)
        if card is None:
            self._insert(item)
        else:
            card.set_utterance(item)
        self._refresh_empty()

    def clear_all(self) -> None:
        self.set_items([])

    def _insert(self, item: Dict[str, Any]) -> None:
        index = int(item.get("index", 0))
        card = ComparisonCard(self.theme, self._body)
        card.set_utterance(item)
        # Newest first: position 0, ahead of the placeholder and the stretch.
        self._layout.insertWidget(0, card)
        self._cards[index] = card

    def _refresh_empty(self) -> None:
        self._empty.setVisible(not self._cards)
        total = len(self._cards)
        # Recomputing from the badge text would be fragile; count the cards that
        # rendered as changed by asking them.
        changed = sum(1 for c in self._cards.values() if c.badge.text() == "CHANGED")
        self.count_changed.emit(total, changed)
