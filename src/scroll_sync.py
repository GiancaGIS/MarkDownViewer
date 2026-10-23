from __future__ import annotations

import json
import math

from PyQt6.QtCore import QFile, QIODevice, QObject, QTimer, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineScript


class EditorScrollMap:
    """Translate logical source positions to Qt's wrapped visual scroll lines."""

    def __init__(self):
        self._key = None
        self._starts = []

    def _layout(self, editor):
        key = (editor.document(), editor.document().revision(), editor.viewport().width(), editor.font().toString(), editor.lineWrapMode())
        if key != self._key:
            starts = [0]
            block = editor.document().begin()
            while block.isValid():
                editor.document().documentLayout().blockBoundingRect(block)
                starts.append(starts[-1] + max(1, block.layout().lineCount()))
                block = block.next()
            self._key, self._starts = key, starts
        return self._starts

    def position(self, editor):
        starts = self._layout(editor)
        block = editor.firstVisibleBlock()
        top = editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top()
        height = max(1, editor.blockBoundingRect(block).height())
        fraction = max(0.0, min(1.0, -top / height))
        scrollbar = editor.verticalScrollBar()
        return {
            "line": block.blockNumber() + 1 + fraction,
            "totalLines": len(starts) - 1,
            "atTop": scrollbar.value() == 0,
            "atBottom": scrollbar.maximum() > 0 and scrollbar.value() == scrollbar.maximum(),
        }

    def apply(self, editor, payload):
        starts = self._layout(editor)
        scrollbar = editor.verticalScrollBar()
        if payload.get("atTop"):
            target = 0
        elif payload.get("atBottom"):
            target = scrollbar.maximum()
        else:
            line = max(0.0, min(len(starts) - 1.000001, float(payload["line"]) - 1))
            index = math.floor(line)
            target = round(starts[index] + (starts[index + 1] - starts[index]) * (line - index))
        scrollbar.setValue(max(0, min(scrollbar.maximum(), target)))


class ScrollSynchronizer(QObject):
    def __init__(self, preview, editor, enabled, parent=None):
        super().__init__(parent)
        self.preview = preview
        self.editor = editor
        self.enabled = enabled
        self._document_editor = None
        self._revision = 0
        self._document_revision = -1
        self._epoch = 0
        self._ready = False
        self._applying = False
        self._leader = "editor"
        self._position = None
        self.mapping = EditorScrollMap()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.align)
        self.channel = QWebChannel(self)
        self.channel.registerObject("scrollSync", self)
        self.preview.page().setWebChannel(self.channel, QWebEngineScript.ScriptWorldId.ApplicationWorld.value)
        script = QWebEngineScript()
        script.setName("markdownStudioScrollSync")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld.value)
        script.setRunsOnSubFrames(False)
        resource = QFile(":/qtwebchannel/qwebchannel.js")
        if not resource.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError("Qt WebChannel JavaScript resource is unavailable")
        script.setSourceCode(bytes(resource.readAll()).decode("utf-8") + "\n" + PREVIEW_SCRIPT)
        resource.close()
        self.preview.page().scripts().insert(script)

    def prepare(self, editor):
        self.timer.stop()
        self._document_editor = editor
        self._document_revision = editor.document().revision()
        self._revision += 1
        self._epoch = 0
        self._ready = False
        self._leader = "editor"
        self._position = None
        return self._revision

    def _current(self):
        return (self._document_editor is self.editor()
                and self._document_revision == self.editor().document().revision())

    def editor_scrolled(self, editor=None):
        if self._applying or not self.enabled() or (editor is not None and editor is not self.editor()):
            return
        self._leader = "editor"
        self.timer.start()

    def schedule(self):
        if not self._applying:
            self.timer.start()

    def _javascript(self, code):
        self.preview.page().runJavaScript(code, QWebEngineScript.ScriptWorldId.ApplicationWorld.value)

    def align(self):
        if not self._ready or not self._current():
            return
        active = self.enabled()
        self._javascript(f"window.markdownStudioScrollSync?.enable({json.dumps(active)})")
        if not active:
            return
        if self._leader == "preview" and self._position is not None:
            self._apply_editor(self._position)
            return
        self._applying = True
        try:
            payload = self.mapping.position(self.editor())
        finally:
            self._applying = False
        payload.update(revision=self._revision, epoch=self._epoch)
        self._javascript(f"window.markdownStudioScrollSync?.fromEditor({json.dumps(payload)})")

    def _apply_editor(self, payload):
        self._applying = True
        try:
            self.mapping.apply(self.editor(), payload)
        finally:
            self._applying = False

    @pyqtSlot(str)
    def report(self, encoded):
        try:
            payload = json.loads(encoded)
            if not isinstance(payload, dict) or payload.get("revision") != self._revision or not self._current():
                return
            if payload.get("kind") == "ready":
                self._ready = True
                self.align()
                return
            if not self.enabled():
                return
            epoch = payload.get("epoch")
            if not isinstance(epoch, int) or epoch < self._epoch:
                return
            self._epoch = epoch
            if payload.get("kind") == "intent":
                self.timer.stop()
                self._leader = "preview"
                if isinstance(payload.get("line"), (int, float)) and math.isfinite(payload["line"]):
                    self._position = payload
                return
            line = payload.get("line")
            if not isinstance(line, (int, float)) or not math.isfinite(line):
                return
            if payload.get("kind") == "layout":
                self.timer.start()
                return
            self.timer.stop()
            self._leader = "preview"
            self._position = payload
            self._apply_editor(payload)
        except (TypeError, ValueError, RuntimeError):
            return


PREVIEW_SCRIPT = r"""
(() => {
  const revision = Number(document.documentElement.dataset.previewRevision);
  if (!revision) return;
  new QWebChannel(qt.webChannelTransport, channel => {
    const bridge = channel.objects.scrollSync;
    let enabled = false, epoch = 0, userScroll = false, points = null;
    let lastPosition = null, expectedScroll = null, frame = 0, layoutTimer = 0;
    const maxScroll = () => Math.max(0, document.documentElement.scrollHeight - innerHeight);
    const send = data => bridge.report(JSON.stringify({...data, revision, epoch}));

    function anchors() {
      if (points) return points;
      const values = [{line: 1, y: 0}];
      for (const element of document.querySelectorAll('[data-source-line]')) {
        if (!element.getClientRects().length) continue;
        const nested = element.querySelector('[data-source-line]');
        if (nested && ['BLOCKQUOTE', 'TABLE', 'DIV'].includes(element.tagName)) continue;
        if (element.tagName === 'LI' && element.firstElementChild?.tagName === 'P') continue;
        const rect = element.getBoundingClientRect();
        let top = rect.top + scrollY, bottom = rect.bottom + scrollY;
        if (element.tagName === 'PRE' && !element.classList.contains('mermaid')) {
          const style = getComputedStyle(element);
          top += parseFloat(style.paddingTop) || 0;
          bottom -= parseFloat(style.paddingBottom) || 0;
        }
        const line = Number(element.dataset.sourceLine), end = Number(element.dataset.sourceEnd);
        if (Number.isFinite(line)) values.push({line, y: top});
        if (!nested && end > line) values.push({line: end, y: bottom});
      }
      values.sort((a, b) => a.line - b.line || a.y - b.y);
      points = [];
      for (const value of values) {
        const previous = points[points.length - 1];
        if (!previous || (value.line > previous.line && value.y >= previous.y)) points.push(value);
      }
      return points;
    }

    function interpolate(value, from, to) {
      const map = anchors();
      if (!map.length) return 0;
      let previous = map[0];
      for (const next of map.slice(1)) {
        if (value <= next[from]) {
          const progress = Math.max(0, Math.min(1, (value - previous[from]) / Math.max(0.0001, next[from] - previous[from])));
          return previous[to] + (next[to] - previous[to]) * progress;
        }
        previous = next;
      }
      return previous[to];
    }

    function position() {
      const maximum = maxScroll();
      return {line: interpolate(scrollY, 'y', 'line'), atTop: scrollY <= 1,
              atBottom: maximum > 0 && scrollY >= maximum - 1};
    }

    function apply(payload) {
      userScroll = false;
      const maximum = maxScroll();
      const target = payload.atTop ? 0 : payload.atBottom ? maximum : interpolate(payload.line, 'line', 'y');
      const bounded = Math.max(0, Math.min(maximum, target));
      expectedScroll = Math.abs(scrollY - bounded) > 1 ? bounded : null;
      scrollTo({top: bounded, behavior: 'instant'});
      lastPosition = payload;
    }

    function intent() {
      if (!enabled) return;
      userScroll = true;
      expectedScroll = null;
      ++epoch;
      send({...position(), kind: 'intent'});
    }
    addEventListener('wheel', intent, {passive: true});
    addEventListener('pointerdown', intent, {passive: true});
    addEventListener('keydown', event => {
      if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) intent();
    });
    addEventListener('scroll', () => {
      if (!enabled || frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        if (layoutTimer) return;
        if (expectedScroll !== null && Math.abs(scrollY - expectedScroll) <= 1) {
          expectedScroll = null;
          return;
        }
        // Chromium's scrollbar can scroll without dispatching pointer events to
        // the document. Any scroll other than our own command is user input.
        if (!userScroll) intent();
        lastPosition = position();
        send({...lastPosition, kind: 'scroll'});
      });
    }, {passive: true});

    function layoutChanged() {
      points = null;
      clearTimeout(layoutTimer);
      layoutTimer = setTimeout(() => {
        layoutTimer = 0;
        if (!enabled || !lastPosition) return;
        apply(lastPosition);
        send({...lastPosition, kind: 'layout'});
      }, 50);
    }
    new ResizeObserver(layoutChanged).observe(document.querySelector('main') || document.body);
    new MutationObserver(layoutChanged).observe(document.body, {childList: true, subtree: true});
    document.addEventListener('load', layoutChanged, true);
    document.fonts?.ready.then(layoutChanged);
    addEventListener('resize', layoutChanged);
    window.markdownStudioScrollSync = {
      enable(value) { enabled = value; if (!value) userScroll = false; },
      fromEditor(payload) {
        if (!enabled || payload.revision !== revision || payload.epoch !== epoch) return;
        apply(payload);
      },
      position
    };
    send({kind: 'ready'});
  });
})();
"""
