"""Build the Windows package and installer with live output and a persistent log."""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


class BuildError(RuntimeError):
    pass


def workspace_path(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT.resolve()) or path == ROOT.resolve():
        raise BuildError(f"Percorso di build esterno al progetto: {path}")
    return path


def find_compiler() -> Path:
    override = os.environ.get("ISCC")
    if override:
        path = Path(override.strip('"'))
        located = shutil.which(str(path))
        if located:
            return Path(located)
        raise BuildError(f"Il compilatore indicato da ISCC non esiste: {override}")
    located = shutil.which("ISCC.exe")
    if located:
        return Path(located)
    for variable, suffix in (
        ("ProgramFiles(x86)", "Inno Setup 6/ISCC.exe"),
        ("ProgramFiles", "Inno Setup 6/ISCC.exe"),
        ("LOCALAPPDATA", "Programs/Inno Setup 6/ISCC.exe"),
    ):
        directory = os.environ.get(variable)
        if directory and (path := Path(directory) / suffix).is_file():
            return path
    raise BuildError(
        "Inno Setup 6 non trovato. Installalo da https://jrsoftware.org/isinfo.php "
        "oppure imposta ISCC con il percorso completo di ISCC.exe."
    )


def source_version() -> str:
    tree = ast.parse((ROOT / "src/config.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets):
            version = ast.literal_eval(node.value)
            if isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version):
                return version
    raise BuildError("VERSION non valida in src/config.py.")


class BuildLog:
    def __init__(self, stream):
        self.stream = stream

    def write(self, message):
        self.stream.write(message + "\n")
        self.stream.flush()
        try:
            print(message, flush=True)
        except UnicodeEncodeError:
            sys.stdout.buffer.write((message + "\n").encode(sys.stdout.encoding, errors="replace"))
            sys.stdout.buffer.flush()

    def run(self, command, env):
        self.write("\n> " + subprocess.list2cmdline([str(arg) for arg in command]))
        with subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        ) as process:
            for line in process.stdout:
                self.write(line.rstrip("\r\n"))
            code = process.wait()
        if code:
            raise BuildError(f"Comando non riuscito (codice {code}). Vedi il dettaglio qui sopra.")


def build(log, *, skip_install=False):
    compiler = find_compiler()
    for relative in ("MarkdownStudio.spec", "installer.iss", "requirements.txt", "src/app.py", "assets/app_icon.ico", "LICENSE"):
        if not (ROOT / relative).is_file():
            raise BuildError(f"File necessario non trovato: {relative}")
    version = source_version()
    installer_source = (ROOT / "installer.iss").read_text(encoding="utf-8")
    if not re.search(rf'^#define MyAppVersion "{re.escape(version)}"$', installer_source, re.MULTILINE):
        raise BuildError("La versione in installer.iss non corrisponde a src/config.py.")
    dist = workspace_path("dist")
    workspace_path("dist/MarkdownStudio")  # PyInstaller replaces only this package.
    work = workspace_path("build/pyinstaller")
    cache = workspace_path("build/pyinstaller-cache")
    output = workspace_path("installer")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
               PYINSTALLER_CONFIG_DIR=str(cache), PIP_DISABLE_PIP_VERSION_CHECK="1",
               PIP_CACHE_DIR=str(workspace_path("build/pip-cache")))
    log.write(f"Python: {sys.executable}\nVersione: {version}\nInno Setup: {compiler}")
    if skip_install:
        log.write("\n[1/3] Uso le dipendenze gia installate (--skip-install).")
    else:
        log.write("\n[1/3] Installazione dipendenze...")
        log.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "pyinstaller"], env)
    log.write("\n[2/3] Creazione eseguibile con MarkdownStudio.spec...")
    log.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "--distpath", str(dist), "--workpath", str(work), str(ROOT / "MarkdownStudio.spec")], env)
    executable = dist / "MarkdownStudio/MarkdownStudio.exe"
    if not executable.is_file():
        raise BuildError(f"Eseguibile non generato: {executable}")
    log.write("\n[3/3] Creazione installer...")
    log.run([str(compiler), f"/O{output}", str(ROOT / "installer.iss")], env)
    installer = output / f"MarkdownStudioSetup-{version}.exe"
    if not installer.is_file():
        raise BuildError(f"Installer non generato: {installer}")
    log.write(f"\nBuild completata.\nEseguibile: {executable}\nInstaller: {installer}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-install", action="store_true", help="Usa le dipendenze gia installate, senza pip/rete.")
    parser.add_argument("--no-pause", action="store_true", help="Disabilita la pausa finale del launcher batch.")
    args = parser.parse_args()
    log_path = workspace_path("build/setup.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", buffering=1) as stream:
        log = BuildLog(stream)
        try:
            log.write("=== Markdown Studio - build setup ===")
            build(log, skip_install=args.skip_install)
        except (BuildError, OSError) as exc:
            log.write(f"\nERRORE: {exc}")
            log.write("Se l'app compilata e aperta, chiudila prima di riprovare.")
            log.write(f"Log completo: {log_path}")
            return 1
        log.write(f"Log completo: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
