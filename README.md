# Markdown Studio

Markdown Studio is a desktop Markdown editor built with Python and PyQt6. It is designed as a compact writing workspace: edit Markdown on the left, preview rendered HTML on the right, and manage notes from a workspace sidebar.

![Markdown Studio main window](images/main_windows.png)

## Highlights

- Multi-tab Markdown editor for working on several documents at once
- Line numbers and lightweight Markdown syntax highlighting
- Live HTML preview powered by `QWebEngineView`
- Bidirectional synchronized scrolling between editor and preview
- Light and dark themes
- Italian and English interface language
- Workspace sidebar with file tree, recent documents, global search, and document outline
- Case-sensitive workspace search across `.md`, `.markdown`, `.mdown`, `.mkd`, and `.txt` files
- Quick Markdown tools for bold, italic, inline code, code blocks, links, images, tables, lists, headings, and quotes
- Mermaid diagram preview for fenced `mermaid` blocks
- Drag and drop images into the editor, with automatic copy into a local `assets/` folder
- Autosave for documents that have already been opened or saved
- HTML export
- PDF export through Qt WebEngine
- External links opened in the system browser
- Windows installer build with optional Markdown file association

## Requirements

- Python 3.10+
- PyQt6
- PyQt6-WebEngine
- Markdown
- Pygments

Installable Python dependencies are listed in [requirements.txt](requirements.txt).

## Quick Start

### Windows

Run:

```bat
run_windows.bat
```

The script creates a local virtual environment if needed, installs dependencies, and launches the app.

### Linux/macOS

Run:

```bash
./run_linux_mac.sh
```

## Manual Installation

```bash
python -m venv .venv
```

### Windows PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src/app.py
```

### Linux/macOS

```bash
source .venv/bin/activate
pip install -r requirements.txt
python src/app.py
```

## Workspace Workflow

1. Press **Folder...** or use **Workspace -> Open workspace folder**.
2. Select a folder containing Markdown files.
3. Double-click a file in the **Files** tab to open it.
4. Use the search field in the sidebar to search the workspace.
5. Double-click a result to open the file at the matching line.
6. Use the **Outline** tab to jump to headings in the current document.

The workspace panel also provides recent documents, quick note creation, file rename, and file delete actions.

## Tabs

Markdown Studio supports multiple open documents through tabs. Opening a file creates a new tab, unless that file is already open. Each tab keeps its own file path and modified state, while the preview follows the active tab.

Closing a modified tab prompts you to save, discard, or cancel.

## Images

You can drag images directly into the editor:

- `.png`
- `.jpg`
- `.jpeg`
- `.gif`
- `.webp`
- `.svg`

If the document has not been saved yet, the app asks where to save it first. Then it copies dropped images into an `assets/` folder next to the Markdown file and inserts references like:

```md
![alt](assets/file.png)
```

## Mermaid Diagrams

Markdown Studio renders Mermaid diagrams in the live preview, HTML export, and PDF export.

Use a fenced code block with the `mermaid` language:

````md
```mermaid
flowchart LR
  A[Write Markdown] --> B[Preview]
  B --> C[Export]
```
````

Mermaid is loaded in the rendered HTML through the jsDelivr CDN, so diagram rendering requires network access when previewing or opening exported HTML files.

## Export

Markdown Studio can export the current document as:

- HTML
- PDF

PDF export depends on Qt WebEngine support on the target platform.

## Useful Shortcuts

| Action | Shortcut |
| --- | --- |
| New file | Ctrl+N |
| New workspace note | Ctrl+Shift+N |
| Open file | Ctrl+O |
| Open workspace folder | Ctrl+Shift+O |
| Rename workspace file | F2 |
| Delete workspace file | Delete |
| Save | Ctrl+S |
| Save as | Ctrl+Shift+S |
| Search workspace | Ctrl+Shift+F |
| Show/hide sidebar | Ctrl+Alt+S |
| Sync preview scroll | Ctrl+Alt+P |
| Light/dark theme | Ctrl+T |
| Export HTML | Ctrl+Shift+H |
| Export PDF | Ctrl+Shift+P |
| Bold | Ctrl+B |
| Italic | Ctrl+I |
| Inline code | Ctrl+K |
| Code block | Ctrl+Shift+K |
| Link | Ctrl+Shift+L |
| Image | Ctrl+Shift+I |
| Table | Ctrl+Shift+T |

## Windows Installer Build

Prerequisites:

- Python installed and available through `py -3`
- Inno Setup 6 installed, with `ISCC.exe` in `PATH` or in the standard `Program Files` folder

To create the executable and installer:

```bat
build_setup.bat
```

The script:

1. creates or reuses `.venv`;
2. installs dependencies, PyInstaller, and required packages;
3. generates `dist\MarkdownStudio\MarkdownStudio.exe`;
4. compiles [installer.iss](installer.iss) with Inno Setup;
5. produces `installer\MarkdownStudioSetup-<version>.exe`.

The installer displays the [MIT License](LICENSE) during setup and copies the `LICENSE` file into the application installation directory.

At setup startup, the installer lets you choose the installation scope:

- all users: installs under `C:\Program Files`;
- current user only: installs under the current user's profile.

During installation, there is an option to associate Markdown files with Markdown Studio:

- `.md`
- `.markdown`
- `.mdown`
- `.mkd`

The association follows the selected installation scope and opens the selected file directly in the app.

The application icon is located at `assets\app_icon.ico`; it is embedded in the PyInstaller executable, used by the Inno Setup installer, and also applied to the Qt window when the app is launched from source.

## Project Structure

`src/app.py` and `src/markdown_studio.py` are lightweight entrypoints. The application code is split into focused modules:

| Path | Responsibility |
| --- | --- |
| `src/app.py` | Qt bootstrap and command-line file opening |
| `src/config.py` | Constants, themes, and stylesheet |
| `src/editor.py` | Markdown editor, line numbers, syntax highlighting, and image drop handling |
| `src/i18n.py` | Italian/English UI translations |
| `src/main_window.py` | Main window, actions, tabs, preview coordination, export, and settings |
| `src/renderer.py` | Markdown to HTML conversion |
| `src/utils.py` | Settings helpers, file helpers, and the `SearchHit` model |
| `src/web_page.py` | WebEngine preview behavior and external link handling |
| `src/workspace.py` | Sidebar, file tree, recent files, search results, and outline |
| `tools/generate_icon.py` | Reproducible application icon generation |

## Assets

- `assets/app_icon.ico`: application and installer icon
- `assets/app_icon.png`: PNG preview of the application icon
- `images/main_windows.png`: main window screenshot used in this README

## Known Limitations

- Global search is simple text search and is not indexed.
- Very large folders may benefit from a SQLite FTS5 index.
- PDF export depends on `PyQt6-WebEngine` and platform support.

## Roadmap Ideas

- Indexed search with SQLite FTS5
- Backlinks between notes with `[[Note]]` syntax

## License

This project is distributed under the terms of the [MIT License](LICENSE).

## Disclaimer

The software is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
