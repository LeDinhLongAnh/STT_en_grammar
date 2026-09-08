"""HTTP and server-sent-events client for vcc_engine.

Everything here runs OFF the GUI thread. A 2-second model load or a blocking
socket read on the Qt event loop is a frozen window, and a frozen window during
exactly the operation you are trying to observe makes the tool useless.

Two mechanisms:

* ``EngineClient`` -- plain blocking calls, safe to use from a worker.
* ``ApiWorker`` / ``EventStream`` -- QThread wrappers that emit results as
  signals, which is how the widgets talk to the engine.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional

from PyQt5.QtCore import QThread, pyqtSignal


class EngineError(RuntimeError):
    """An engine call failed. Carries a message fit to show a human."""


class EngineClient:
    """Blocking HTTP client. One instance is shared; it holds no state."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # -- low level ---------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[bytes] = None,
        content_type: str = "application/json",
        timeout: Optional[float] = None,
    ) -> bytes:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, data=body, method=method)
        if body is not None:
            req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            # The engine reports failures as {"error": "..."}; surfacing that
            # text beats surfacing "HTTP 400".
            detail = ""
            try:
                payload = json.loads(exc.read().decode("utf-8", "replace"))
                detail = payload.get("error", "")
            except Exception:
                pass
            raise EngineError(detail or f"HTTP {exc.code} on {path}") from exc
        except urllib.error.URLError as exc:
            raise EngineError(f"cannot reach the engine: {exc.reason}") from exc
        except OSError as exc:
            raise EngineError(f"cannot reach the engine: {exc}") from exc

    def get_json(self, path: str, timeout: Optional[float] = None) -> Any:
        raw = self._request("GET", path, timeout=timeout)
        return json.loads(raw.decode("utf-8", "replace")) if raw else None

    def get_text(self, path: str) -> str:
        return self._request("GET", path).decode("utf-8", "replace")

    def post_json(self, path: str, payload: Dict[str, Any],
                  timeout: Optional[float] = None) -> Any:
        raw = self._request("POST", path, json.dumps(payload).encode("utf-8"),
                            timeout=timeout)
        return json.loads(raw.decode("utf-8", "replace")) if raw else None

    def post_text(self, path: str, text: str) -> Any:
        raw = self._request("POST", path, text.encode("utf-8"), "text/plain")
        return json.loads(raw.decode("utf-8", "replace")) if raw else None

    def post_bytes(self, path: str, data: bytes, content_type: str,
                   timeout: Optional[float] = None) -> Any:
        raw = self._request("POST", path, data, content_type, timeout=timeout)
        return json.loads(raw.decode("utf-8", "replace")) if raw else None

    # -- endpoints ---------------------------------------------------------

    def state(self) -> Dict[str, Any]:
        return self.get_json("/api/state")

    def history(self) -> list:
        return self.get_json("/api/history") or []

    def hotwords(self) -> str:
        return self.get_text("/api/hotwords")

    def hotwords_wire(self) -> str:
        return self.get_text("/api/hotwords/wire")

    def rewrites(self) -> str:
        return self.get_text("/api/rewrites")

    def set_hotwords(self, text: str, save: bool = False) -> Dict[str, Any]:
        # Re-decoding the whole history happens engine-side, so give it room.
        return self.post_bytes(
            f"/api/hotwords?save={'1' if save else '0'}",
            text.encode("utf-8"), "text/plain", timeout=180.0)

    def set_rewrites(self, text: str, save: bool = False) -> Dict[str, Any]:
        return self.post_bytes(
            f"/api/rewrites?save={'1' if save else '0'}",
            text.encode("utf-8"), "text/plain", timeout=60.0)

    def set_filter(self, **kwargs: Any) -> Dict[str, Any]:
        return self.post_json("/api/filter", kwargs, timeout=180.0)

    def load_model(self, **kwargs: Any) -> Dict[str, Any]:
        return self.post_json("/api/model", kwargs, timeout=300.0)

    def reload_files(self) -> Dict[str, Any]:
        return self.post_json("/api/reload", {}, timeout=180.0)

    def clear_history(self) -> Dict[str, Any]:
        return self.post_json("/api/history/clear", {})

    def record_start(self, index: int) -> Dict[str, Any]:
        return self.post_json("/api/record/start", {"mic": index}, timeout=60.0)

    def record_stop(self) -> Dict[str, Any]:
        # Stopping also decodes the take, twice (unbiased and biased), so this
        # is the one call that legitimately takes a while.
        return self.post_json("/api/record/stop", {}, timeout=300.0)

    def record_cancel(self) -> Dict[str, Any]:
        return self.post_json("/api/record/cancel", {}, timeout=60.0)

    def recognize_wav(self, data: bytes, name: str, normalize: bool,
                      reference: str = "") -> list:
        from urllib.parse import quote
        query = (f"?normalize={'1' if normalize else '0'}"
                 f"&name={quote(name)}")
        if reference:
            query += f"&reference={quote(reference)}"
        return self.post_bytes(f"/api/recognize{query}", data, "audio/wav",
                               timeout=300.0) or []


class ApiWorker(QThread):
    """Runs one callable against the engine, off the GUI thread.

    Deliberately single-shot: a worker per action keeps cancellation and error
    reporting trivial, and these actions are rare enough that thread churn does
    not matter.
    """

    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable[[], Any], parent=None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:  # noqa: D102 - QThread override
        try:
            self.done.emit(self._fn())
        except EngineError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # a bug here must not take the window down
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class EventStream(QThread):
    """Reads the engine's SSE stream and re-emits each event as a signal.

    Server-sent events are a long-lived streaming read, so this cannot live on
    the GUI thread. Reconnects on its own: the engine restarts when a model is
    reloaded under some conditions, and a dashboard that goes permanently deaf
    after one hiccup is worse than one that blinks.
    """

    level = pyqtSignal(dict)
    recording = pyqtSignal(dict)
    utterance = pyqtSignal(dict)
    connected = pyqtSignal(bool)

    def __init__(self, base_url: str, parent=None) -> None:
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:  # noqa: D102 - QThread override
        while not self._stop:
            try:
                self._read_once()
            except Exception:
                self.connected.emit(False)
            if self._stop:
                break
            # Back off a little so a dead engine does not spin the CPU.
            self.msleep(700)

    def _read_once(self) -> None:
        req = urllib.request.Request(f"{self.base_url}/api/events")
        with urllib.request.urlopen(req, timeout=60.0) as resp:
            self.connected.emit(True)
            event = ""
            data_lines: list[str] = []
            while not self._stop:
                raw = resp.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
                elif line == "":
                    # Blank line terminates one event.
                    if event and data_lines:
                        self._dispatch(event, "\n".join(data_lines))
                    event, data_lines = "", []
        self.connected.emit(False)

    def _dispatch(self, event: str, data: str) -> None:
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return
        if event == "level":
            self.level.emit(payload)
        elif event == "recording":
            self.recording.emit(payload)
        elif event == "utterance":
            self.utterance.emit(payload)
