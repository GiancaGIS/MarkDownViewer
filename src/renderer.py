from __future__ import annotations

import html
import re

import markdown
from pygments.formatters import HtmlFormatter

try:
    from .config import APP_NAME, THEMES
except ImportError:
    from config import APP_NAME, THEMES

class MarkdownRenderer:
    """Converts Markdown text to a complete themed HTML document."""

    BLOCK_TAG_RE = re.compile(r"<(h[1-6]|p|li|pre|blockquote|table)([^>]*)>", re.IGNORECASE)
    FENCE_RE = re.compile(r"^\s*(```|~~~)")
    HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
    LIST_RE = re.compile(r"^\s{0,3}([-+*]|\d+[.)])\s+")
    HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
    TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")

    def __init__(self, theme: str = "light") -> None:
        self.theme = theme if theme in THEMES else "light"
        self.extensions = [
            "extra",
            "toc",
            "sane_lists",
            "codehilite",
        ]
        self.extension_configs = {
            "codehilite": {
                "guess_lang": False,
                "noclasses": False,
            },
            "toc": {
                "permalink": False,
            },
        }

    def set_theme(self, theme: str) -> None:
        self.theme = theme if theme in THEMES else "light"

    def _css(self) -> str:
        t = THEMES[self.theme]
        try:
            pygments_css = HtmlFormatter(style=t["pygments"]).get_style_defs(".codehilite")
        except Exception:
            pygments_css = HtmlFormatter(style="default").get_style_defs(".codehilite")

        return f"""
:root {{
  color-scheme: {self.theme};
}}

body {{
  margin: 0;
  padding: 0;
  background: {t['preview_bg']};
  color: {t['preview_fg']};
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  line-height: 1.62;
}}

.page {{
  max-width: 980px;
  margin: 0 auto;
  padding: 36px 44px 72px;
  background: {t['preview_page']};
  min-height: 100vh;
  box-sizing: border-box;
  box-shadow: 0 12px 38px rgba(0, 0, 0, 0.16);
}}

h1, h2, h3, h4, h5, h6 {{
  line-height: 1.25;
  margin-top: 1.7em;
  margin-bottom: 0.55em;
}}

h1 {{
  border-bottom: 1px solid {t['preview_border']};
  padding-bottom: 0.25em;
}}

a {{
  color: #58a6ff;
  text-decoration: none;
}}

a:hover {{
  text-decoration: underline;
}}

.headerlink {{
  display: none;
}}

pre {{
  padding: 16px 18px;
  border-radius: 10px;
  overflow-x: auto;
}}

code {{
  font-family: "Cascadia Code", "Consolas", "Menlo", monospace;
  font-size: 0.94em;
}}

p code, li code, td code {{
  background: {t['preview_inline_code_bg']};
  color: {t['preview_inline_code_fg']};
  padding: 0.12em 0.32em;
  border-radius: 5px;
}}

blockquote {{
  margin: 1.2em 0;
  padding: 0.2em 1em;
  color: {t['preview_muted']};
  border-left: 4px solid {t['preview_border']};
  background: {t['preview_inline_code_bg']};
}}

table {{
  border-collapse: collapse;
  width: 100%;
  margin: 1.2em 0;
}}

th, td {{
  border: 1px solid {t['preview_border']};
  padding: 8px 10px;
}}

th {{
  background: {t['preview_inline_code_bg']};
  text-align: left;
}}

img {{
  max-width: 100%;
  height: auto;
}}

hr {{
  border: none;
  border-top: 1px solid {t['preview_border']};
  margin: 2em 0;
}}

[data-source-line] {{
  scroll-margin-top: 10px;
}}

{pygments_css}
"""

    def _source_block_lines(self, markdown_text: str) -> list[int]:
        lines = markdown_text.splitlines()
        anchors: list[int] = []
        in_fence = False
        fence_marker = ""

        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            fence_match = self.FENCE_RE.match(line)
            if fence_match:
                marker = fence_match.group(1)
                if not in_fence:
                    anchors.append(index)
                    in_fence = True
                    fence_marker = marker
                elif marker == fence_marker:
                    in_fence = False
                    fence_marker = ""
                continue

            if in_fence:
                continue

            previous_blank = index == 1 or not lines[index - 2].strip()
            next_line = lines[index].strip() if index < len(lines) else ""
            is_table_header = "|" in line and bool(self.TABLE_SEPARATOR_RE.match(next_line))
            is_table_separator = bool(self.TABLE_SEPARATOR_RE.match(line))
            is_structural = any(
                (
                    self.HEADING_RE.match(line),
                    self.LIST_RE.match(line),
                    line.lstrip().startswith(">"),
                    self.HR_RE.match(line),
                    is_table_header,
                )
            )

            if is_table_separator:
                continue
            if previous_blank or is_structural:
                anchors.append(index)

        return anchors or [1]

    def _annotate_source_lines(self, html_body: str, source_lines: list[int]) -> str:
        line_iter = iter(source_lines)

        def replace(match: re.Match[str]) -> str:
            tag = match.group(1)
            attrs = match.group(2) or ""
            if "data-source-line" in attrs:
                return match.group(0)
            try:
                line_number = next(line_iter)
            except StopIteration:
                return match.group(0)

            slash = ""
            clean_attrs = attrs.rstrip()
            if clean_attrs.endswith("/"):
                slash = " /"
                clean_attrs = clean_attrs[:-1].rstrip()
            return f'<{tag}{clean_attrs} data-source-line="{line_number}"{slash}>'

        return self.BLOCK_TAG_RE.sub(replace, html_body)

    def to_html_document(self, markdown_text: str, title: str = APP_NAME) -> str:
        body = markdown.markdown(
            markdown_text,
            extensions=self.extensions,
            extension_configs=self.extension_configs,
            output_format="html5",
        )
        body = self._annotate_source_lines(body, self._source_block_lines(markdown_text))
        safe_title = html.escape(title or APP_NAME)
        return f"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>{self._css()}</style>
</head>
<body>
  <main class="page">
{body}
  </main>
</body>
</html>"""
