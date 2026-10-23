"""Attach source ranges while Markdown's block processors build the HTML tree."""
from __future__ import annotations

from bisect import bisect_left
from difflib import SequenceMatcher
import re

from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
from markdown.treeprocessors import Treeprocessor


BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "blockquote", "table", "tr", "hr"}
PLACEHOLDER = re.compile(r"\x02wzxhzdk:(\d+)\x03")


def _key(line: str) -> str:
    line = re.sub(r"^(?:\s*>\s?)+", "", line).strip()
    return re.sub(r"^(?:[-+*]|\d+[.)])\s+", "", line).strip()


class SourceMap(Extension):
    def __init__(self, source: str):
        super().__init__()
        self.source = source.expandtabs(4).split("\n")
        self.lines = []
        self.ranges = []
        self.positions = {}
        self.frames = []
        self.cursor = 0

    def extendMarkdown(self, md):
        md.preprocessors.register(_Capture(md, self), "source_map", 0)
        # Preserve indented-code ranges when codehilite replaces pre with a stash.
        md.treeprocessors.register(_CodeRanges(md), "source_code_ranges", 31)
        for processor in md.parser.blockprocessors:
            run = processor.run

            def mapped_run(parent, blocks, original=run):
                return self.process(original, parent, blocks)

            processor.run = mapped_run

    def capture(self, md, lines):
        self.lines = lines
        self.ranges = [(1, 2)] * len(lines)
        for kind, a, b, c, d in SequenceMatcher(None, self.source, lines).get_opcodes():
            if kind == "equal":
                for offset in range(d - c):
                    self.ranges[c + offset] = (a + offset + 1, a + offset + 2)
            elif c < d:
                start, end = a, b
                while start < end and not self.source[start].strip():
                    start += 1
                while end > start and not self.source[end - 1].strip():
                    end -= 1
                for index in range(c, d):
                    self.ranges[index] = (start + 1, max(start + 2, end + 1))
        for index, line in enumerate(lines):
            key = _key(line)
            if key:
                self.positions.setdefault(key, []).append(index)
            for match in PLACEHOLDER.finditer(line):
                stash = int(match.group(1))
                raw = md.htmlStash.rawHtmlBlocks[stash]
                if not isinstance(raw, str):
                    continue
                start, end = self.ranges[index]
                # Fenced code's visible content excludes the opening/closing fences.
                if "<pre" in raw and 'class="mermaid"' not in raw:
                    start += 1
                    end = max(start + 1, end - 1)
                attrs = f' data-source-line="{start}" data-source-end="{end}"'
                pattern = r"<(pre)(\s[^>]*|)>" if "<pre" in raw else r"<(table|blockquote|h[1-6]|div)(\s[^>]*|)>"
                raw = re.sub(pattern,
                             lambda m: m.group(0)[:-1] + f' data-source-end="{end}">' if "data-source-line" in m.group(0) else f'<{m[1]}{m[2]}{attrs}>', raw, count=1)
                md.htmlStash.rawHtmlBlocks[stash] = raw

    def locate(self, text, cursor=0):
        lines = text.split("\n")
        first = next((i for i, line in enumerate(lines) if line.strip()), 0)
        candidates = self.positions.get(_key(lines[first]), [])
        index = bisect_left(candidates, cursor)
        if index < len(candidates):
            start = candidates[index]
        else:
            start = min(cursor, max(0, len(self.lines) - 1))
        return start, min(len(self.lines), start + max(1, len(lines) - first))

    def annotate(self, node, start, end):
        if node.tag not in BLOCK_TAGS or not self.ranges:
            return
        # A raw-HTML placeholder paragraph must remain attribute-free for Markdown
        # to unwrap it correctly in the postprocessor.
        if node.tag == "p" and PLACEHOLDER.fullmatch((node.text or "").strip()):
            return
        first = self.ranges[min(start, len(self.ranges) - 1)][0]
        last = self.ranges[min(max(start, end - 1), len(self.ranges) - 1)][1]
        if "data-source-line" not in node.attrib:
            node.set("data-source-line", str(first))
        try:
            previous_end = int(node.get("data-source-end", "0"))
        except ValueError:
            previous_end = 0
        node.set("data-source-end", str(max(previous_end, last)))

    def process(self, run, parent, blocks):
        if not blocks or not self.lines or not blocks[0].strip() or blocks[0].startswith("\n"):
            return run(parent, blocks)
        cursor = self.frames[-1][0] if self.frames else self.cursor
        start, end = self.locate(blocks[0], cursor)
        frame = [start]
        self.frames.append(frame)
        before = set(parent)
        self.annotate(parent, start, end)
        original_block = blocks[0]
        result = run(parent, blocks)
        self.frames.pop()
        if result is False:
            return result
        for node in parent:
            if node in before:
                continue
            node_start, node_end = start, end
            if re.fullmatch("h[1-6]", node.tag):
                heading = re.search(r"(?m)^\s{0,3}#{1,6}\s+", original_block)
                if heading:
                    node_start = start + original_block[:heading.start()].count("\n")
                    node_end = node_start + 1
            if "data-source-line" not in node.attrib:
                self.annotate(node, node_start, node_end)
            if node.tag == "table":
                rows = list(node.iter("tr"))
                for offset, row in enumerate(rows):
                    line = start if offset == 0 else start + offset + 1
                    self.annotate(row, line, line + 1)
        consumed = max(end, frame[0])
        # Some processors put the unconsumed suffix back at the front (e.g. a
        # heading without surrounding blank lines). Keep that suffix available.
        if blocks and blocks[0] and original_block.endswith(blocks[0]) and blocks[0] != original_block:
            consumed = start + original_block[:len(original_block) - len(blocks[0])].count("\n")
        if self.frames:
            self.frames[-1][0] = max(self.frames[-1][0], consumed)
        else:
            self.cursor = consumed
        return result


class _Capture(Preprocessor):
    def __init__(self, md, mapping):
        super().__init__(md)
        self.mapping = mapping

    def run(self, lines):
        self.mapping.capture(self.md, lines)
        return lines


class _CodeRanges(Treeprocessor):
    def run(self, root):
        blocks = [node for node in root.iter("pre") if node.get("data-source-line")]
        if not blocks:
            return
        original_store = self.md.htmlStash.store
        ranges = iter((node.get("data-source-line"), node.get("data-source-end")) for node in blocks)

        def store(raw):
            if isinstance(raw, str) and "<pre" in raw:
                source_range = next(ranges, None)
                if source_range:
                    start, end = source_range
                    raw = raw.replace("<pre", f'<pre data-source-line="{start}" data-source-end="{end}"', 1)
            return original_store(raw)

        self.md.htmlStash.store = store
