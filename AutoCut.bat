@echo off
REM ---------------------------------------------------------------------
REM AutoCut starten (mit Konsolenfenster - gut zur Fehlersuche).
REM Fuer den normalen Gebrauch besser AutoCut.pyw per Doppelklick starten.
REM ---------------------------------------------------------------------
title AutoCut
cd /d "%~dp0"

REM Python suchen: erst der Starter "py", dann python aus dem PATH.
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON=python"
    ) else (
        echo.
        echo   Python wurde nicht gefunden.
        echo.
        echo   Bitte installiere Python 3.10 oder neuer von https://www.python.org/downloads/
        echo   Wichtig: beim Installieren den Haken bei "Add python.exe to PATH" setzen.
        echo.
        pause
        exit /b 1
    )
)

echo AutoCut wird gestartet ...
%PYTHON% "%~dp0AutoCut.pyw"
if errorlevel 1 (
    echo.
    echo AutoCut wurde mit einem Fehler beendet.
    pause
)
