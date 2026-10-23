from __future__ import annotations

from html.parser import HTMLParser
import json
import re
import unittest
from unittest.mock import MagicMock

import markdown

from tests.qt_support import APP
from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QPlainTextEdit
from src.editor import MarkdownEditor
from src.renderer import MarkdownRenderer
from src.scroll_sync import EditorScrollMap, ScrollSynchronizer


class Blocks(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.nodes = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'data-source-line' in attrs:
            self.nodes.append((tag, int(attrs['data-source-line']), int(attrs.get('data-source-end', 0))))


class SourceMapTests(unittest.TestCase):
    def render(self, text):
        return Blocks(MarkdownRenderer().to_html_document(text)).nodes

    def test_quote_list_and_table_do_not_shift_later_anchors(self):
        text = '# H\n\n> Quote\n>\n> Next\n\n- First\n- Second\n\nAfter\n\n| A | B |\n| --- | --- |\n| C | D |\n\n```python\nx=1\ny=2\n```\n\nEnd'
        nodes = self.render(text)
        for node in [('h1', 1, 2), ('p', 3, 4), ('p', 5, 6), ('li', 7, 8), ('li', 8, 9), ('p', 10, 11), ('tr', 12, 13), ('tr', 14, 15), ('pre', 17, 19), ('p', 21, 22)]:
            self.assertIn(node, nodes, nodes)

    def test_repeated_paragraphs_fences_and_heading_without_blank_lines(self):
        text = 'Repeated\n\nRepeated\n\n````text\na\n```\nb\n````\n\nBefore\n## Heading\nAfter\n\nFinal'
        nodes = self.render(text)
        for node in [('p', 1, 2), ('p', 3, 4), ('pre', 6, 9), ('p', 11, 12), ('h2', 12, 13), ('p', 13, 14), ('p', 15, 16)]:
            self.assertIn(node, nodes, nodes)

    def test_nested_and_loose_list_and_indented_code(self):
        text = '- First\n\n    Paragraph\n\n    - Nested\n\n- Second\n\n    print(1)\n    print(2)\n\n# End'
        nodes = self.render(text)
        self.assertIn(('p', 3, 4), nodes)
        self.assertIn(('li', 5, 6), nodes)
        self.assertIn(('h1', 12, 13), nodes)
        code = self.render('Start\n\n    print(1)\n    print(2)\n\nEnd')
        self.assertIn(('pre', 3, 5), code)
        self.assertIn(('p', 6, 7), code)

    def test_mermaid_keeps_original_line_numbers(self):
        nodes = self.render('Intro\n\n```mermaid\ngraph LR\n A-->B\n```\n\nAfter')
        self.assertIn(('pre', 3, 7), nodes)
        self.assertIn(('p', 8, 9), nodes)

    def test_source_annotations_preserve_markdown_rendering(self):
        renderer = MarkdownRenderer()
        samples = [
            '# Heading\n\n> Quote **bold**\n>\n> Second paragraph\n\n- First\n\n    Paragraph\n\n    - Nested\n\n- Second',
            'Setext\n======\n\nText with [link][ref].\n\n[ref]: https://example.com\n\n---\n\n| A | B |\n| --- | --- |\n| 1 | 2 |',
            '```python\nprint(1)\n```\n\n    print(2)\n\n<div>Raw HTML</div>\n\nFootnote[^x].\n\n[^x]: A footnote.',
            'Definition\n: Description\n\n## Styled {#custom}\n\n[TOC]',
        ]
        for text in samples:
            document = renderer.to_html_document(text)
            actual = document.split('<main class="page">\n', 1)[1].split('\n  </main>', 1)[0]
            actual = re.sub(r' data-source-(?:line|end)="\d+"', '', actual)
            expected = markdown.markdown(text, extensions=renderer.extensions, extension_configs=renderer.extension_configs, output_format='html5')
            self.assertEqual(actual, expected)

    def test_long_repetitive_document_retains_exact_source_ranges(self):
        text = '\n'.join(f'## Section {i}\n\nRepeated paragraph.\n\n> Repeated quote.\n\n- First\n- Second\n\n```python\nprint(1)\nprint(2)\n```\n\nEnd paragraph.\n' for i in range(100))
        nodes = self.render(text)
        headings = [index for index, line in enumerate(text.splitlines(), 1) if line.startswith('## ')]
        code = [index + 1 for index, line in enumerate(text.splitlines(), 1) if line == '```python']
        self.assertEqual([start for tag, start, end in nodes if tag == 'h2'], headings)
        self.assertEqual([start for tag, start, end in nodes if tag == 'pre'], code)


class EditorScrollTests(unittest.TestCase):
    def setUp(self):
        self.editor = MarkdownEditor()
        self.editor.resize(430, 300)
        self.editor.setPlainText('\n'.join(f'{i}: ' + ('wrapped text ' * (15 if i % 3 == 0 else 2)) for i in range(100)))
        self.editor.show()
        APP.processEvents()
        self.mapping = EditorScrollMap()

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_wrapped_logical_line_and_fraction_round_trip_without_moving_cursor(self):
        cursor = self.editor.textCursor()
        cursor.setPosition(6)
        cursor.setPosition(25, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        for line in (10.25, 25.5, 40.75, 61.25):
            self.mapping.apply(self.editor, {'line': line})
            actual = self.mapping.position(self.editor)['line']
            self.assertAlmostEqual(actual, line, delta=.25)
        self.assertEqual(self.editor.textCursor().selectionStart(), 6)
        self.assertEqual(self.editor.textCursor().selectionEnd(), 25)

    def test_mapping_refreshes_after_resize_edit_and_wrap_change(self):
        for width in (700, 310):
            self.editor.resize(width, 300)
            APP.processEvents()
            self.mapping.apply(self.editor, {'line': 40.5})
            self.assertAlmostEqual(self.mapping.position(self.editor)['line'], 40.5, delta=.25)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.mapping.apply(self.editor, {'line': 40})
        self.assertEqual(self.editor.firstVisibleBlock().blockNumber(), 39)
        self.editor.setPlainText('\n'.join(f'New {i}' for i in range(100)))
        self.mapping.apply(self.editor, {'line': 65})
        self.assertEqual(self.editor.firstVisibleBlock().blockNumber(), 64)

    def test_document_edges_clamp_to_matching_edges(self):
        self.mapping.apply(self.editor, {'line': 1000, 'atBottom': True})
        self.assertTrue(self.mapping.position(self.editor)['atBottom'])
        self.mapping.apply(self.editor, {'line': 1, 'atTop': True})
        self.assertTrue(self.mapping.position(self.editor)['atTop'])


class SynchronizerTests(unittest.TestCase):
    def setUp(self):
        self.documents = [MarkdownEditor(), MarkdownEditor()]
        for doc in self.documents:
            doc.resize(500, 250)
            doc.setPlainText('\n'.join(f'Line {i}' for i in range(200)))
            doc.show()
        APP.processEvents()
        self.current = self.documents[0]
        self.active = True
        self.sync = ScrollSynchronizer(MagicMock(), lambda: self.current, lambda: self.active)
        self.sync._javascript = MagicMock()
        for doc in self.documents:
            doc.verticalScrollBar().valueChanged.connect(lambda value, editor=doc: self.sync.editor_scrolled(editor))
        self.revision = self.sync.prepare(self.current)
        self.send(kind='ready')

    def tearDown(self):
        self.sync.timer.stop()
        self.sync.deleteLater()
        for doc in self.documents:
            doc.close()
            doc.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def send(self, **kwargs):
        self.sync.report(json.dumps({'revision': self.revision, 'epoch': 1, **kwargs}))

    def test_reverse_scroll_does_not_echo_or_move_background_document(self):
        self.send(kind='scroll', line=50)
        self.assertEqual(self.current.firstVisibleBlock().blockNumber(), 49)
        self.assertEqual(self.sync._leader, 'preview')
        self.assertFalse(self.sync.timer.isActive())
        self.documents[1].verticalScrollBar().setValue(100)
        self.assertFalse(self.sync.timer.isActive())
        self.assertEqual(self.current.firstVisibleBlock().blockNumber(), 49)

    def test_stale_events_after_tab_change_or_edit_are_ignored(self):
        self.current = self.documents[1]
        current_revision = self.sync.prepare(self.current)
        self.send(kind='scroll', line=90)
        self.assertEqual(self.current.verticalScrollBar().value(), 0)
        self.send(revision=current_revision, kind='scroll', line=50)
        self.assertEqual(self.current.firstVisibleBlock().blockNumber(), 49)
        self.current.appendPlainText('New edit')
        before = self.current.verticalScrollBar().value()
        self.send(revision=current_revision, kind='scroll', line=90)
        self.assertEqual(self.current.verticalScrollBar().value(), before)

    def test_disabled_sync_invalid_messages_and_old_input_are_ignored(self):
        self.send(kind='intent', epoch=5, line=1)
        self.send(kind='scroll', epoch=4, line=70)
        self.assertEqual(self.current.verticalScrollBar().value(), 0)
        self.active = False
        self.send(kind='scroll', epoch=6, line=90)
        self.assertEqual(self.current.verticalScrollBar().value(), 0)
        self.active = True
        for encoded in ('invalid JSON', '[]', '{"revision": 1, "line": "bad"}'):
            self.sync.report(encoded)
        self.send(kind='scroll', epoch=6, line=float('nan'))
        self.assertEqual(self.current.verticalScrollBar().value(), 0)
