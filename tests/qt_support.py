"""A single offscreen Qt application; web previews cannot make remote requests."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineUrlRequestInterceptor
from PyQt6.QtWebEngineWidgets import QWebEngineView  # Import before constructing QApplication.


class BlockRemoteRequests(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        if info.requestUrl().scheme() in {"http", "https"}:
            info.block(True)


APP = QApplication.instance() or QApplication(["MarkdownStudioTests"])
REMOTE_BLOCKER = BlockRemoteRequests()
QWebEngineProfile.defaultProfile().setUrlRequestInterceptor(REMOTE_BLOCKER)
