@echo off
REM ===================================================================
REM  AutoCut - Einrichtung starten
REM
REM  Doppelklick auf diese Datei richtet AutoCut komplett ein:
REM  Python und ffmpeg pruefen, Pakete installieren, Funktionstest,
REM  Desktop-Verknuepfung anlegen.
REM ===================================================================
title AutoCut - Einrichtung
cd /d "%~dp0"

echo.
echo   AutoCut wird eingerichtet. Bitte dieses Fenster offen lassen.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1" %*
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
    echo.
    echo   Die Einrichtung ist noch nicht vollstaendig - siehe Meldungen oben.
)

echo.
echo   Dieses Fenster kann jetzt geschlossen werden.
pause
exit /b %EXITCODE%
