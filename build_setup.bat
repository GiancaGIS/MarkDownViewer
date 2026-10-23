@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
set "BUILD_EXIT=1"
set "NO_PAUSE="
for %%A in (%*) do if /i "%%~A"=="--no-pause" set "NO_PAUSE=1"

if exist "%PY%" goto build
echo Creo ambiente virtuale...
py -3 -m venv ".venv"
if errorlevel 1 (
    echo Errore: impossibile creare la venv. Verifica che Python sia installato.
    goto finish
)

:build
"%PY%" "tools\build_setup.py" %*
set "BUILD_EXIT=%ERRORLEVEL%"

:finish
echo.
if not defined NO_PAUSE pause
exit /b %BUILD_EXIT%
