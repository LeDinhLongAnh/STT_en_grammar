"""PyQt5 dashboard for the contextual-biasing STT engine.

The engine (``vcc_engine``) owns the model, the microphone and the filter; this
package is a client. Nothing here decodes audio, and nothing here duplicates a
decision the engine already makes -- when the two disagree, the engine wins.
"""

__all__ = ["client", "engine", "theme", "mainwindow"]
