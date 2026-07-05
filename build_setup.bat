@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "APP_NAME=MarkdownStudio"
set "ENTRYPOINT=src\app.py"
set "VENV_DIR=.venv"
set "PY=%VENV_DIR%\Scripts\python.exe"
set "ISCC="

echo.
echo === Markdown Studio - build setup ===
echo.

if not exist "%PY%" (
    echo Creo ambiente virtuale...
    py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Errore: impossibile creare la venv. Verifica che Python sia installato.
        exit /b 1
    )
)

echo Aggiorno pip e installo dipendenze...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

"%PY%" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

echo.
echo Pulisco build precedenti...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "installer" rmdir /s /q "installer"

echo.
echo Creo eseguibile con PyInstaller...
"%PY%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --onedir ^
    --name "%APP_NAME%" ^
    --icon "assets\app_icon.ico" ^
    --paths "src" ^
    --add-data "assets\app_icon.ico;assets" ^
    --hidden-import "markdown.extensions.extra" ^
    --hidden-import "markdown.extensions.toc" ^
    --hidden-import "markdown.extensions.sane_lists" ^
    --hidden-import "markdown.extensions.codehilite" ^
    --collect-all "PyQt6" ^
    "%ENTRYPOINT%"
if errorlevel 1 exit /b 1

echo.
echo Cerco Inno Setup Compiler...
where ISCC.exe >nul 2>nul
if not errorlevel 1 set "ISCC=ISCC.exe"

if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo.
    echo Errore: Inno Setup 6 non trovato.
    echo Installa Inno Setup da https://jrsoftware.org/isinfo.php oppure aggiungi ISCC.exe al PATH.
    exit /b 1
)

echo Uso Inno Setup: %ISCC%
echo.
echo Creo installer...
"%ISCC%" "installer.iss"
if errorlevel 1 exit /b 1

echo.
echo Build completata.
echo Installer generato in: installer\MarkdownStudioSetup_setup.exe
echo.
exit /b 0
