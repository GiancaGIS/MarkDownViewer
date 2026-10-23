from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

try:
    from .config import GITHUB_REPOSITORY, VERSION
except ImportError:
    from config import GITHUB_REPOSITORY, VERSION


RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
CHECK_TIMEOUT_MS = 10_000
MAX_RESPONSE_BYTES = 1024 * 1024
STABLE_VERSION = re.compile(r"[vV]?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?", re.ASCII)


def version_tuple(value: str) -> tuple[int, int, int] | None:
    """Accept stable numeric tags, with optional v prefix and build metadata."""
    if not isinstance(value, str) or len(value) > 128:
        return None
    match = STABLE_VERSION.fullmatch(value.strip())
    return tuple(int(part or 0) for part in match.groups()) if match else None


@dataclass(frozen=True)
class Release:
    version: str
    url: str


@dataclass(frozen=True)
class UpdateResult:
    status: str  # available, current, no_release, error
    release: Release | None = None


def parse_release(data: object, current_version: str) -> UpdateResult:
    if not isinstance(data, dict):
        return UpdateResult("error")
    if data.get("draft") is True or data.get("prerelease") is True:
        return UpdateResult("no_release")
    tag = data.get("tag_name")
    latest = version_tuple(tag)
    current = version_tuple(current_version)
    if latest is None or current is None:
        return UpdateResult("error")
    if latest <= current:
        return UpdateResult("current")
    url = data.get("html_url")
    if not isinstance(url, str):
        return UpdateResult("error")
    try:
        parsed = urlsplit(url)
    except ValueError:
        return UpdateResult("error")
    prefix = f"/{GITHUB_REPOSITORY}/releases/tag/".lower()
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or not parsed.path.lower().startswith(prefix) or len(parsed.path) <= len(prefix):
        return UpdateResult("error")
    return UpdateResult("available", Release(".".join(str(part) for part in latest), url))


class UpdateChecker(QObject):
    """One asynchronous GitHub request at a time, with a bounded lifetime."""

    finished = pyqtSignal(object)
    busy_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None, *, current_version: str = VERSION) -> None:
        super().__init__(parent)
        self.current_version = current_version
        self.has_checked = False
        self.network = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._data = bytearray()
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.setInterval(CHECK_TIMEOUT_MS)
        self._timeout.timeout.connect(self._abort)

    @property
    def busy(self) -> bool:
        return self._reply is not None

    def check(self) -> bool:
        if self.busy:
            return False
        request = QNetworkRequest(QUrl(RELEASE_API_URL))
        request.setRawHeader(b"User-Agent", f"MarkdownStudio/{self.current_version}".encode("ascii"))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"X-GitHub-Api-Version", b"2022-11-28")
        request.setTransferTimeout(CHECK_TIMEOUT_MS)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute, QNetworkRequest.RedirectPolicy.SameOriginRedirectPolicy)
        self._data = bytearray()
        self.has_checked = True
        reply = self.network.get(request)
        self._reply = reply
        reply.setReadBufferSize(MAX_RESPONSE_BYTES + 1)
        reply.readyRead.connect(lambda: self._read(reply))
        reply.finished.connect(lambda: self._finish(reply))
        self._timeout.start()
        self.busy_changed.emit(True)
        return True

    def _read(self, reply: QNetworkReply) -> None:
        if reply is not self._reply:
            return
        self._data.extend(bytes(reply.readAll()))
        if len(self._data) > MAX_RESPONSE_BYTES:
            reply.abort()

    def _abort(self) -> None:
        if self._reply is not None:
            self._reply.abort()

    def _finish(self, reply: QNetworkReply) -> None:
        if reply is not self._reply:
            return
        self._timeout.stop()
        self._data.extend(bytes(reply.readAll()))
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status == 404:
            result = UpdateResult("no_release")
        elif reply.error() != QNetworkReply.NetworkError.NoError or status != 200 or len(self._data) > MAX_RESPONSE_BYTES:
            result = UpdateResult("error")
        else:
            try:
                result = parse_release(json.loads(self._data), self.current_version)
            except (ValueError, UnicodeError, RecursionError):
                result = UpdateResult("error")
        self._reply = None
        self._data.clear()
        reply.deleteLater()
        self.busy_changed.emit(False)
        self.finished.emit(result)

    def cancel(self) -> None:
        self._timeout.stop()
        reply, self._reply = self._reply, None
        self._data.clear()
        if reply is not None:
            reply.abort()
            reply.deleteLater()
            self.busy_changed.emit(False)
