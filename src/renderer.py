from __future__ import annotations

import html
import re

import markdown
from pygments.formatters import HtmlFormatter

try:
    from .config import APP_NAME, THEMES
    from .preferences import Typography
    from .source_map import SourceMap
except ImportError:
    from config import APP_NAME, THEMES
    from preferences import Typography
    from source_map import SourceMap

class MarkdownRenderer:
    """Converts Markdown text to a complete themed HTML document."""

    MERMAID_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*mermaid\s*$", re.IGNORECASE)

    def __init__(self, theme: str = "light") -> None:
        self.theme = theme if theme in THEMES else "light"
        self.typography = Typography()
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
        typography = self.typography
        # Escape font names as CSS strings, including HTML-significant characters.
        font = "".join(f"\\{ord(char):x} " if char in '\\"<>\n\r' else char for char in typography.preview_font)
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
  font-family: "{font}", -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  font-size: {typography.preview_size}px;
  line-height: {typography.preview_spacing};
}}

.page {{
  max-width: {typography.preview_width}px;
  margin: 0 auto;
  padding: 28px 32px 56px;
  background: {t['preview_page']};
  min-height: 100vh;
  box-sizing: border-box;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.05);
}}

h1, h2, h3, h4, h5, h6 {{
  line-height: 1.25;
  margin-top: 1.7em;
  margin-bottom: 0.55em;
}}

.page > :first-child {{
  margin-top: 0;
}}

h1 {{
  border-bottom: 1px solid {t['preview_border']};
  padding-bottom: 0.25em;
}}

a {{
  color: {"#58a6ff" if self.theme == "dark" else "#0969da"};
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

pre.mermaid {{
  background: {t['preview_inline_code_bg']};
  color: {t['preview_fg']};
  border: 1px solid {t['preview_border']};
  text-align: center;
  white-space: pre-wrap;
}}

pre.mermaid svg {{
  max-width: 100%;
  height: auto;
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

@media (max-width: 600px) {{
  .page {{ padding: 24px 24px 48px; }}
}}

{pygments_css}
"""

    def _extract_mermaid_blocks(self, markdown_text: str) -> str:
        lines = markdown_text.splitlines()
        output: list[str] = []
        index = 0

        while index < len(lines):
            line = lines[index]
            start_match = self.MERMAID_FENCE_RE.match(line)
            if not start_match:
                output.append(line)
                index += 1
                continue

            start_line = index + 1
            fence = start_match.group(1)
            fence_char = fence[0]
            fence_length = len(fence)
            closing_re = re.compile(rf"^\s{{0,3}}{re.escape(fence_char)}{{{fence_length},}}\s*$")
            diagram_lines: list[str] = []
            index += 1

            while index < len(lines) and not closing_re.match(lines[index]):
                diagram_lines.append(lines[index])
                index += 1

            if index < len(lines):
                index += 1

            diagram = html.escape("\n".join(diagram_lines))
            output.extend(
                [
                    f'<pre class="mermaid" data-source-line="{start_line}">',
                    diagram,
                    "</pre>",
                ]
            )

        return "\n".join(output)

    def _mermaid_scripts(self) -> str:
        theme = "dark" if self.theme == "dark" else "default"
        return f"""
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <script>
  (() => {{
    const diagrams = Array.from(document.querySelectorAll("pre.mermaid"));
    window.markdownStudioMermaidReady = diagrams.length === 0;
    window.markdownStudioMermaidSuccess = diagrams.length === 0;

    const finish = (success) => {{
      window.markdownStudioMermaidReady = true;
      window.markdownStudioMermaidSuccess = Boolean(success);
    }};

    const render = async () => {{
      if (!diagrams.length) {{
        finish(true);
        return;
      }}
      if (!window.mermaid) {{
        finish(false);
        return;
      }}
      try {{
        window.mermaid.initialize({{
          startOnLoad: false,
          securityLevel: "loose",
          theme: "{theme}",
        }});
        await window.mermaid.run({{ nodes: diagrams }});
        finish(true);
      }} catch (error) {{
        document.body.dataset.mermaidError = error && error.message ? error.message : String(error);
        finish(false);
      }}
    }};

    if (document.readyState === "loading") {{
      document.addEventListener("DOMContentLoaded", render, {{ once: true }});
    }} else {{
      render();
    }}
  }})();
  </script>
"""

    def to_html_document(self, markdown_text: str, title: str = APP_NAME) -> str:
        markdown_text = self._extract_mermaid_blocks(markdown_text)
        body = markdown.markdown(
            markdown_text,
            extensions=[*self.extensions, SourceMap(markdown_text)],
            extension_configs=self.extension_configs,
            output_format="html5",
        )
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
{self._mermaid_scripts() if 'class="mermaid"' in body else ''}
</body>
</html>"""

    def to_pdf_document(self, markdown_text: str, title: str, options) -> str:
        """Produce a light, paginated document independently of screen styling."""
        renderer = MarkdownRenderer("light")
        document = renderer.to_html_document(markdown_text, title)

        def css_string(value: str) -> str:
            return "".join(f"\\{ord(char):x} " if char in '\\"<>\n\r' else char for char in value)

        footer = ""
        if options.page_numbers:
            footer = f"""
  @bottom-left {{ content: "{css_string(title[:70])}"; font: 8pt "{css_string(options.font)}", sans-serif; color: #667085; }}
  @bottom-right {{ content: counter(page) " / " counter(pages); font: 8pt "{css_string(options.font)}", sans-serif; color: #667085; }}
"""
        height = options.page_layout().paintRect().height()
        print_css = f"""
@page {{
  size: {options.paper} {"landscape" if options.landscape else "portrait"};
  margin: {options.top}mm {options.right}mm {options.bottom}mm {options.left}mm;
  {footer}
}}
:root {{ color-scheme: light; }}
html, body {{ background: white; color: #202630; }}
body {{ font-family: "{css_string(options.font)}", Arial, sans-serif; font-size: {options.font_size}pt; line-height: {options.line_height}; }}
.page {{ width: auto; max-width: none; min-height: 0; margin: 0; padding: 0; background: white; box-shadow: none; }}
h1, h2, h3, h4, h5, h6 {{ break-after: avoid; page-break-after: avoid; line-height: 1.2; color: #152536; }}
h1 {{ font-size: 24pt; margin: 0 0 14pt; padding-bottom: 9pt; border-bottom: 1pt solid #d8e0e8; }}
h2 {{ font-size: 17pt; margin: 20pt 0 8pt; }}
h3 {{ font-size: 13pt; margin: 15pt 0 6pt; }}
h4, h5, h6 {{ font-size: 11pt; margin: 12pt 0 5pt; }}
p {{ margin: 0 0 8pt; orphans: 3; widows: 3; }}
ul, ol {{ padding-left: 18pt; margin: 6pt 0 10pt; }}
li {{ margin-bottom: 3pt; orphans: 2; widows: 2; }}
a {{ color: #175ea8; overflow-wrap: anywhere; }}
table {{ width: 100%; table-layout: auto; border-collapse: collapse; margin: 12pt 0; font-size: .92em; break-inside: auto; }}
thead {{ display: table-header-group; }}
tfoot {{ display: table-footer-group; }}
tr {{ break-inside: avoid; page-break-inside: avoid; }}
th, td {{ border: .5pt solid #d6dee7; padding: 5pt 7pt; overflow-wrap: break-word; vertical-align: top; }}
td a, td code {{ overflow-wrap: anywhere; }}
th {{ color: #26384b; background: #eef3f8; font-weight: 600; }}
blockquote {{ color: #475569; background: #f5f7fa; border-left: 2pt solid #98adc5; margin: 10pt 0; padding: 7pt 11pt; orphans: 3; widows: 3; }}
blockquote p:last-child {{ margin-bottom: 0; }}
pre {{ font-family: "Consolas", "DejaVu Sans Mono", monospace; font-size: 9pt; line-height: 1.4; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; overflow: visible; padding: 9pt 11pt; border: .5pt solid #dce3ec; border-radius: 4pt; background: #f6f8fa; break-inside: auto; page-break-inside: auto; orphans: 3; widows: 3; }}
code {{ font-family: "Consolas", "Cascadia Code", "DejaVu Sans Mono", monospace; font-size: .85em; }}
pre code {{ font-size: 9pt; line-height: 1.4; }}
p code, li code, td code {{ background: #eef2f6; color: #27364a; }}
img, svg {{ max-width: 100%; max-height: {max(50, height - 12)}mm; object-fit: contain; break-inside: avoid; page-break-inside: avoid; }}
p:has(> img:only-child), pre.mermaid {{ break-inside: avoid; page-break-inside: avoid; }}
pre.mermaid {{ background: white; border: 0; padding: 6pt 0; }}
pre.mermaid svg {{ max-height: {max(50, height - 12)}mm; }}
.page-break {{ break-before: page; page-break-before: always; height: 0; }}
* {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
"""
        return document.replace("</style>", print_css + "\n</style>", 1)
