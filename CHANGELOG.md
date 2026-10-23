# Changelog

## 1.1.0

- Redesigned the window around one compact command/tab header, scalable stroke icons, and a narrow tool navigation rail.
- Replaced the four-tab sidebar and permanent search controls with one tool panel at a time; added an explicit empty workspace state.
- Added automatic sidebar collapse, vertical splitting on narrow windows, and independent horizontal/vertical split proportions.
- Centered the writing column on wide windows and reduced formatting/status chrome.
- Increased menu item spacing and kept labels and keyboard shortcuts readable in the Insert menu.
- Rebuilt bidirectional Split scrolling around Markdown source ranges and wrapped editor lines, with live preview scroll events, layout refresh, and guards against feedback loops and stale tab events.
- Added Writing, Split, and Reading layouts with persistent panel proportions and document tabs available in every mode.
- Added on-demand document search and centralized typography/behavior preferences.
- Added dedicated PDF print styling with configurable A4/Letter paper, orientation, margins, typography, and optional title/page numbering footers on supported WebEngine versions.
- Improved PDF pagination for headings, multipage tables, code blocks, and images; added explicit page breaks through the `page-break` class.
- Isolated PDF rendering from the active preview, waited for fonts/images/diagrams, and made PDF writes atomic with bounded timeout and resource error reporting.
- Added atomic document saves and independent autosave timers for background tabs.
- Prevented Save As from overwriting another open document.
- Added asynchronous GitHub release checks on startup, a manual check in the Help menu, and an optional startup-check preference.
- Added an actionable update toast with a release link, dismissal, and automatic expiration.
- Added Help → About with the application version, author, and copyright in Italian and English.
- Aligned application and Windows installer versions to 1.1.0.
- Hardened the Windows build launcher with compiler/version preflight, a persistent live log, readable failures, offline dependency reuse, and packaging from the tracked spec without deleting all previous build outputs.

## 1.0.3

- Previous published release.
