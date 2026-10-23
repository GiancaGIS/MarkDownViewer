from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings

try:
    from .pdf_options import PdfOptions
    from .renderer import MarkdownRenderer
    from .utils import write_bytes_atomic
except ImportError:
    from pdf_options import PdfOptions
    from renderer import MarkdownRenderer
    from utils import write_bytes_atomic


@dataclass(frozen=True)
class PdfResult:
    path: Path
    success: bool
    error: str = ""
    detail: str = ""


class PdfExporter(QObject):
    """Render a document snapshot on a separate page, then atomically save it."""

    finished = pyqtSignal(object)
    busy_changed = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._page: QWebEnginePage | None = None
        self._path: Path | None = None
        self._options: PdfOptions | None = None
        self._printing = False
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.setInterval(30_000)
        self._timeout.timeout.connect(lambda: self._finish(False, "pdf_timeout"))

    @property
    def busy(self) -> bool:
        return self._page is not None

    def start(self, text: str, title: str, base_url: QUrl, path: Path, options: PdfOptions) -> bool:
        if self.busy:
            return False
        self._path, self._options = Path(path), options
        self._printing = False
        page = QWebEnginePage(self)
        self._page = page
        page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        page.settings().setAttribute(QWebEngineSettings.WebAttribute.PrintElementBackgrounds, True)
        for name, value in (("PrintHeaderAndFooter", False), ("PreferCSSMarginsForPrinting", True)):
            attribute = getattr(QWebEngineSettings.WebAttribute, name, None)
            if attribute is not None:
                page.settings().setAttribute(attribute, value)
        page.loadFinished.connect(lambda ok: self._loaded(page, ok))
        page.renderProcessTerminated.connect(lambda *_: self._finish(False, "pdf_load_failed") if self._page is page else None)
        self.busy_changed.emit(True)
        self._timeout.start()
        page.setHtml(MarkdownRenderer().to_pdf_document(text, title, options), base_url)
        return True

    def _loaded(self, page, ok: bool) -> None:
        if page is not self._page:
            return
        if not ok:
            self._finish(False, "pdf_load_failed")
            return
        self._check_resources(page)

    def _check_resources(self, page) -> None:
        if page is not self._page or self._printing:
            return
        script = """
(() => {
  const images = Array.from(document.images);
  const hasDiagrams = Boolean(document.querySelector('pre.mermaid'));
  const diagramsReady = !hasDiagrams || Boolean(window.markdownStudioMermaidReady);
  return {
    ready: (!document.fonts || document.fonts.status === 'loaded') && images.every(img => img.complete) && diagramsReady,
    broken: images.some(img => img.complete && img.naturalWidth === 0),
    diagramError: hasDiagrams && diagramsReady && !window.markdownStudioMermaidSuccess
  };
})();
"""
        page.runJavaScript(script, lambda state: self._resources_ready(page, state))

    def _resources_ready(self, page, state) -> None:
        if page is not self._page or self._printing:
            return
        if not isinstance(state, dict):
            self._finish(False, "pdf_load_failed")
        elif state.get("broken") or state.get("diagramError"):
            self._finish(False, "pdf_resources_failed")
        elif not state.get("ready"):
            QTimer.singleShot(100, lambda: self._check_resources(page))
        else:
            self._printing = True
            page.printToPdf(lambda data: self._printed(page, data), self._options.page_layout())

    def _printed(self, page, data) -> None:
        if page is not self._page:
            return
        payload = bytes(data)
        if not payload.startswith(b"%PDF-"):
            self._finish(False, "pdf_load_failed")
            return
        try:
            write_bytes_atomic(self._path, payload)
        except OSError as exc:
            self._finish(False, "pdf_write_failed", str(exc))
            return
        self._finish(True)

    def _finish(self, success: bool, error: str = "", detail: str = "") -> None:
        if not self.busy:
            return
        result = PdfResult(self._path, success, error, detail)
        self.cancel()
        self.finished.emit(result)

    def cancel(self) -> None:
        self._timeout.stop()
        page, self._page = self._page, None
        if page is not None:
            page.triggerAction(QWebEnginePage.WebAction.Stop)
            page.deleteLater()
            self.busy_changed.emit(False)
