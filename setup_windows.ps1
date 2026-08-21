<#
================================================================================
  AutoCut - Einrichtung fuer Windows
================================================================================
  Dieses Skript richtet AutoCut vollstaendig ein:

    1. prueft Python und ffmpeg und installiert Fehlendes per winget
    2. installiert die benoetigten Python-Pakete
    3. macht einen kompletten Funktionstest (Analyse + Rendern)
    4. startet einmal die Oberflaeche zur Kontrolle
    5. legt die Desktop-Verknuepfung "AutoCut" an

  Start:  Doppelklick auf Setup.bat
  Oder:   powershell -ExecutionPolicy Bypass -File setup_windows.ps1

  Es wird nichts an Windows veraendert ausser den Installationen oben.
  Keine Anmeldung, keine Schluessel, keine kostenpflichtigen Dienste.
================================================================================
#>

[CmdletBinding()]
param(
    # Oberflaeche am Ende nicht testweise starten
    [switch]$NoGuiTest,
    # Keine Desktop-Verknuepfung anlegen
    [switch]$NoShortcut,
    # Funktionstest ueberspringen (schneller, aber ungeprueft)
    [switch]$SkipSelfTest
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'   # macht Downloads spuerbar schneller

$Root = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$Schritt = 0
$Probleme = New-Object System.Collections.ArrayList
$Erledigt = New-Object System.Collections.ArrayList

# ------------------------------------------------------------------ Ausgabe --

function Write-Kopf {
    param([string]$Text)
    Write-Host ''
    Write-Host ('=' * 74) -ForegroundColor DarkCyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ('=' * 74) -ForegroundColor DarkCyan
}

function Write-Schritt {
    param([string]$Text)
    $script:Schritt++
    Write-Host ''
    Write-Host "[$script:Schritt] $Text" -ForegroundColor White
    Write-Host ('-' * 74) -ForegroundColor DarkGray
}

function Write-Gut    { param([string]$T) Write-Host "    [OK]      $T" -ForegroundColor Green }
function Write-Info   { param([string]$T) Write-Host "    [Info]    $T" -ForegroundColor Gray }
function Write-Warnung{ param([string]$T) Write-Host "    [Hinweis] $T" -ForegroundColor Yellow }
function Write-Fehler {
    param([string]$T)
    Write-Host "    [FEHLER]  $T" -ForegroundColor Red
    [void]$script:Probleme.Add($T)
}

# ------------------------------------------------------------------ Helfer ---

function Update-PfadVariable {
    <# Nach einer Installation kennt das laufende Fenster den neuen PATH noch
       nicht. Hier wird er frisch aus der Registrierung gelesen. #>
    $maschine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $benutzer = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($maschine, $benutzer) | Where-Object { $_ }) -join ';'
}

function Test-Befehl {
    param([string]$Name)
    $gefunden = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $gefunden) { return $null }
    return $gefunden
}

function Get-BefehlsAusgabe {
    <# Fuehrt ein Programm aus und liefert die erste Zeile der Ausgabe.
       Fehler fuehren zu $null statt zu einem Abbruch. #>
    param([string]$Datei, [string[]]$Argumente)
    try {
        $ausgabe = & $Datei @Argumente 2>&1 | Select-Object -First 1
        if ($LASTEXITCODE -ne 0 -and -not $ausgabe) { return $null }
        return ([string]$ausgabe).Trim()
    } catch {
        return $null
    }
}

function Test-StoreStub {
    <# Der "python.exe" aus dem Microsoft Store ist nur ein Platzhalter mit
       0 Bytes, der den Store oeffnet - der taugt nicht zum Arbeiten. #>
    param([string]$Pfad)
    try {
        if (-not $Pfad -or -not (Test-Path -LiteralPath $Pfad)) { return $false }
        if ($Pfad -like '*\WindowsApps\*' -and (Get-Item -LiteralPath $Pfad).Length -eq 0) {
            return $true
        }
    } catch { }
    return $false
}

function Find-Python {
    <# Sucht ein brauchbares Python (3.9 oder neuer) und liefert dessen Pfad. #>
    $kandidaten = New-Object System.Collections.ArrayList

    # 1. Der offizielle Python-Starter "py" kennt alle Installationen.
    if (Test-Befehl 'py') {
        $pfad = Get-BefehlsAusgabe 'py' @('-3', '-c', 'import sys; print(sys.executable)')
        if ($pfad) { [void]$kandidaten.Add($pfad) }
    }
    # 2. python aus dem PATH
    foreach ($treffer in (Get-Command python -All -ErrorAction SilentlyContinue)) {
        [void]$kandidaten.Add($treffer.Source)
    }
    # 3. Uebliche Installationsorte
    foreach ($muster in @(
            "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
            "$env:ProgramFiles\Python3*\python.exe",
            "C:\Python3*\python.exe")) {
        foreach ($treffer in (Get-ChildItem -Path $muster -ErrorAction SilentlyContinue)) {
            [void]$kandidaten.Add($treffer.FullName)
        }
    }

    foreach ($pfad in ($kandidaten | Select-Object -Unique)) {
        if (-not $pfad -or -not (Test-Path -LiteralPath $pfad)) { continue }
        if (Test-StoreStub $pfad) { continue }
        $version = Get-BefehlsAusgabe $pfad @('-c', 'import sys; print("%d.%d.%d" % sys.version_info[:3])')
        if (-not $version) { continue }
        $teile = $version.Split('.')
        if ([int]$teile[0] -gt 3 -or ([int]$teile[0] -eq 3 -and [int]$teile[1] -ge 9)) {
            return [pscustomobject]@{ Pfad = $pfad; Version = $version }
        }
    }
    return $null
}

function Install-MitWinget {
    param(
        [string]$Id,
        [string]$Anzeige,
        # Bei -Optional ist ein Fehlschlag kein Beinbruch (es gibt einen Ersatzweg).
        [switch]$Optional
    )
    if (-not (Test-Befehl 'winget')) {
        $meldung = "$Anzeige fehlt und winget ist auf diesem Windows nicht verfuegbar."
        if ($Optional) { Write-Warnung $meldung } else { Write-Fehler $meldung }
        Write-Info "Bitte von Hand installieren - die Adressen stehen am Ende dieser Ausgabe."
        return $false
    }
    Write-Info "Installiere $Anzeige ueber winget (das dauert ein paar Minuten) ..."
    Write-Info "Falls Windows nach Erlaubnis fragt: bitte mit Ja bestaetigen."

    & winget install --id $Id --source winget --exact `
        --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Host
    $code = $LASTEXITCODE
    Update-PfadVariable

    # winget meldet auch "ist schon installiert" mit einem Code ungleich 0.
    if ($code -ne 0) {
        Write-Info "winget meldete Code $code - es wird gleich geprueft, ob es trotzdem geklappt hat."
    }
    return $true
}

# =========================================================== Los geht es =====

Write-Kopf 'AutoCut - Einrichtung fuer Windows'
Write-Info "Projektordner: $Root"
Write-Info "Windows: $([Environment]::OSVersion.Version)  PowerShell: $($PSVersionTable.PSVersion)"

# --------------------------------------------------------- 1. Grundlagen ----

Write-Schritt 'Python pruefen'

$python = Find-Python
if (-not $python) {
    Write-Warnung 'Kein passendes Python gefunden - es wird jetzt installiert.'
    if (Install-MitWinget 'Python.Python.3.12' 'Python 3.12') {
        Start-Sleep -Seconds 3
        $python = Find-Python
    }
}
if ($python) {
    Write-Gut "Python $($python.Version)"
    Write-Info "  $($python.Pfad)"
    [void]$Erledigt.Add("Python $($python.Version)")
} else {
    Write-Fehler 'Python konnte nicht eingerichtet werden.'
    Write-Info   'Bitte von https://www.python.org/downloads/ installieren und dabei'
    Write-Info   'den Haken bei "Add python.exe to PATH" setzen. Danach Setup.bat erneut starten.'
}

$pythonw = $null
if ($python) {
    $pythonw = Join-Path (Split-Path -Parent $python.Pfad) 'pythonw.exe'
    if (Test-Path -LiteralPath $pythonw) {
        Write-Gut 'pythonw.exe (startet die App ohne Konsolenfenster)'
    } else {
        Write-Warnung 'pythonw.exe nicht gefunden - die App startet dann mit Konsolenfenster.'
        $pythonw = $python.Pfad
    }

    # Tkinter gehoert zu Python, fehlt aber bei manchen Installationen.
    $tk = Get-BefehlsAusgabe $python.Pfad @('-c', 'import tkinter; print("ja")')
    if ($tk -eq 'ja') {
        Write-Gut 'Tkinter (Programmoberflaeche)'
    } else {
        Write-Fehler 'Tkinter fehlt in dieser Python-Installation.'
        Write-Info   'Python neu installieren und dabei "tcl/tk and IDLE" aktiviert lassen.'
    }
}

Write-Schritt 'ffmpeg pruefen'

$ffmpegVersion = if (Test-Befehl 'ffmpeg') { Get-BefehlsAusgabe 'ffmpeg' @('-version') } else { $null }
if (-not $ffmpegVersion) {
    Write-Warnung 'ffmpeg nicht gefunden - es wird jetzt installiert.'
    if (Install-MitWinget 'Gyan.FFmpeg' 'ffmpeg' -Optional) {
        Start-Sleep -Seconds 3
        $ffmpegVersion = if (Test-Befehl 'ffmpeg') { Get-BefehlsAusgabe 'ffmpeg' @('-version') } else { $null }
    }
}
if ($ffmpegVersion) {
    Write-Gut $ffmpegVersion
    [void]$Erledigt.Add('ffmpeg')
} else {
    Write-Warnung 'ffmpeg ist noch nicht im Suchpfad.'
    Write-Info    'Das ist meist kein Problem: AutoCut installiert sich gleich das Paket'
    Write-Info    '"imageio-ffmpeg", das ein eigenes ffmpeg mitbringt.'
    Write-Info    'Sonst hilft: Fenster schliessen, neu oeffnen, Setup.bat noch einmal starten.'
}

$ffprobeVersion = if (Test-Befehl 'ffprobe') { Get-BefehlsAusgabe 'ffprobe' @('-version') } else { $null }
if ($ffprobeVersion) {
    Write-Gut $ffprobeVersion
} else {
    Write-Warnung 'ffprobe nicht gefunden - AutoCut liest die Videodaten dann mit OpenCV.'
    Write-Info    'Das funktioniert genauso, nur die Erkennung des Aufnahmedatums ist schwaecher.'
}

# ------------------------------------------------------------ 2. Pakete -----

Write-Schritt 'Python-Pakete installieren'

if ($python) {
    $anforderungen = Join-Path $Root 'requirements.txt'
    if (-not (Test-Path -LiteralPath $anforderungen)) {
        Write-Fehler "requirements.txt wurde nicht gefunden (erwartet in $Root)."
    } else {
        Write-Info 'pip wird auf den neuesten Stand gebracht ...'
        & $python.Pfad -m pip install --upgrade pip --quiet 2>&1 | Out-Null

        Write-Info 'Pakete werden installiert (beim ersten Mal dauert das einige Minuten) ...'
        & $python.Pfad -m pip install -r $anforderungen | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Warnung 'Erster Versuch fehlgeschlagen - neuer Versuch fuer das Benutzerkonto ...'
            & $python.Pfad -m pip install --user -r $anforderungen | Out-Host
        }

        # Drag & Drop ist freiwillig: Fehler hier sind kein Beinbruch.
        & $python.Pfad -m pip install tkinterdnd2 --quiet 2>&1 | Out-Null

        # Jetzt wird geprueft, ob sich wirklich jedes Paket laden laesst.
        $pruefer = @'
import importlib, sys
pakete = [("numpy","numpy"),("yaml","pyyaml"),("librosa","librosa"),
          ("soundfile","soundfile"),("cv2","opencv-python")]
fehlt = []
for modul, name in pakete:
    try:
        m = importlib.import_module(modul)
        print("  OK    %-16s %s" % (name, getattr(m, "__version__", "")))
    except Exception as fehler:
        fehlt.append(name)
        print("  FEHLT %-16s %s" % (name, fehler))
for modul, name in [("imageio_ffmpeg","imageio-ffmpeg"),("tkinterdnd2","tkinterdnd2")]:
    try:
        importlib.import_module(modul)
        print("  OK    %-16s (optional)" % name)
    except Exception:
        print("  ---   %-16s (optional, nicht vorhanden)" % name)
sys.exit(1 if fehlt else 0)
'@
        Write-Host ''
        Write-Info 'Ladeprobe der Pakete:'
        & $python.Pfad -c $pruefer | Out-Host
        if ($LASTEXITCODE -eq 0) {
            Write-Gut 'Alle benoetigten Pakete lassen sich fehlerfrei laden.'
            [void]$Erledigt.Add('Python-Pakete (numpy, pyyaml, librosa, soundfile, opencv-python)')

            # Jetzt kann AutoCut selbst sagen, welches ffmpeg es benutzt -
            # das schliesst das ueber pip mitgelieferte imageio-ffmpeg ein.
            $ffmpegPruefer = @'
import sys
sys.path.insert(0, sys.argv[1])
from autocut.ffmpeg_tools import ffmpeg_path, have_ffmpeg
print(ffmpeg_path() if have_ffmpeg() else "")
'@
            $gefunden = (& $python.Pfad -c $ffmpegPruefer $Root 2>$null | Select-Object -First 1)
            if ($gefunden) {
                Write-Gut "AutoCut benutzt dieses ffmpeg: $gefunden"
                if (-not $ffmpegVersion) {
                    [void]$Erledigt.Add('ffmpeg (ueber das Paket imageio-ffmpeg)')
                }
            } else {
                Write-Fehler 'AutoCut findet kein ffmpeg - ohne ffmpeg kann kein Video entstehen.'
                Write-Info   'Bitte im Terminal ausfuehren:  winget install ffmpeg'
            }
        } else {
            Write-Fehler 'Mindestens ein Paket laesst sich nicht laden (siehe Liste oben).'
        }
    }
} else {
    Write-Warnung 'Uebersprungen, weil kein Python vorhanden ist.'
}

# ---------------------------------------------------- 3. Funktionstest ------

Write-Schritt 'Funktionstest (Analyse und Rendern mit Testdaten)'

if ($python -and -not $SkipSelfTest -and $Probleme.Count -eq 0) {
    Write-Info 'AutoCut erzeugt jetzt einen kurzen Test-Song und drei Testclips'
    Write-Info 'und rendert daraus ein Video. Das dauert etwa eine halbe Minute.'
    Write-Host ''
    & $python.Pfad (Join-Path $Root 'autocut.py') --selftest | Out-Host
    if ($LASTEXITCODE -eq 0) {
        Write-Gut 'Funktionstest bestanden - Analyse und Rendern laufen auf diesem Rechner.'
        [void]$Erledigt.Add('Funktionstest bestanden')
    } else {
        Write-Fehler 'Der Funktionstest ist fehlgeschlagen (Einzelheiten stehen oben).'
    }
} elseif ($SkipSelfTest) {
    Write-Warnung 'Uebersprungen (--SkipSelfTest).'
} else {
    Write-Warnung 'Uebersprungen, weil weiter oben etwas fehlt.'
}

# ------------------------------------------------------ 4. Oberflaeche ------

Write-Schritt 'Oberflaeche testweise starten'

$pyw = Join-Path $Root 'AutoCut.pyw'
if ($python -and -not $NoGuiTest -and $Probleme.Count -eq 0 -and (Test-Path -LiteralPath $pyw)) {
    try {
        $prozess = Start-Process -FilePath $pythonw -ArgumentList "`"$pyw`"" `
                                 -WorkingDirectory $Root -PassThru
        Write-Info 'Das Fenster wird geoeffnet, kurz geprueft und wieder geschlossen ...'
        $titel = ''
        for ($i = 0; $i -lt 20; $i++) {
            Start-Sleep -Milliseconds 500
            if ($prozess.HasExited) { break }
            $prozess.Refresh()
            if ($prozess.MainWindowTitle) { $titel = $prozess.MainWindowTitle; break }
        }

        if ($prozess.HasExited) {
            Write-Fehler "Die Oberflaeche hat sich sofort wieder beendet (Code $($prozess.ExitCode))."
            Write-Info   'Starte zur Fehlersuche AutoCut.bat - dort wird die Ursache angezeigt.'
        } else {
            if ($titel) {
                Write-Gut "Fenster geoeffnet: `"$titel`""
            } else {
                Write-Gut 'Die Oberflaeche laeuft (Fenstertitel nicht auslesbar, das ist normal).'
            }
            Write-Gut 'Kein Konsolenfenster - gestartet ueber pythonw.exe.'
            [void]$Erledigt.Add('Oberflaeche startet fehlerfrei')

            [void]$prozess.CloseMainWindow()
            Start-Sleep -Seconds 2
            if (-not $prozess.HasExited) { $prozess | Stop-Process -Force -ErrorAction SilentlyContinue }
        }
    } catch {
        Write-Fehler "Die Oberflaeche liess sich nicht starten: $($_.Exception.Message)"
    }
} elseif ($NoGuiTest) {
    Write-Warnung 'Uebersprungen (--NoGuiTest).'
} else {
    Write-Warnung 'Uebersprungen, weil weiter oben etwas fehlt.'
}

# --------------------------------------------------- 5. Verknuepfung --------

Write-Schritt 'Desktop-Verknuepfung anlegen'

if (-not $NoShortcut -and $python) {
    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        if (-not $desktop -or -not (Test-Path -LiteralPath $desktop)) {
            $desktop = Join-Path $env:USERPROFILE 'Desktop'
        }
        $ziel = Join-Path $desktop 'AutoCut.lnk'

        $shell = New-Object -ComObject WScript.Shell
        $verknuepfung = $shell.CreateShortcut($ziel)
        $verknuepfung.TargetPath = $pythonw
        $verknuepfung.Arguments = "`"$pyw`""
        $verknuepfung.WorkingDirectory = $Root
        $verknuepfung.Description = 'AutoCut - automatischer Videoschnitt auf Musik'
        $symbol = Join-Path $Root 'AutoCut.ico'
        if (Test-Path -LiteralPath $symbol) { $verknuepfung.IconLocation = "$symbol,0" }
        $verknuepfung.Save()

        if (Test-Path -LiteralPath $ziel) {
            Write-Gut "Verknuepfung angelegt: $ziel"
            [void]$Erledigt.Add("Desktop-Verknuepfung `"AutoCut`"")
        } else {
            Write-Fehler 'Die Verknuepfung wurde nicht geschrieben.'
        }
    } catch {
        Write-Fehler "Verknuepfung fehlgeschlagen: $($_.Exception.Message)"
        Write-Info   'Von Hand: Rechtsklick auf AutoCut.pyw -> (Windows 11: "Weitere Optionen anzeigen")'
        Write-Info   '-> "Senden an" -> "Desktop (Verknuepfung erstellen)", dann mit F2 in AutoCut umbenennen.'
    }
} else {
    Write-Warnung 'Uebersprungen.'
}

# ------------------------------------------------------ Zusammenfassung -----

Write-Kopf 'Zusammenfassung'

if ($Erledigt.Count -gt 0) {
    Write-Host '  Eingerichtet:' -ForegroundColor White
    foreach ($eintrag in $Erledigt) { Write-Host "    - $eintrag" -ForegroundColor Green }
}

if ($Probleme.Count -eq 0) {
    Write-Host ''
    Write-Host '  Alles bereit. AutoCut kann benutzt werden.' -ForegroundColor Green
    Write-Host ''
    Write-Host '  So geht es weiter:' -ForegroundColor White
    Write-Host '    1. Doppelklick auf das Symbol "AutoCut" auf dem Desktop'
    Write-Host '    2. Clip-Ordner waehlen (alle Videos in einem Ordner sammeln)'
    Write-Host '    3. Musikdatei waehlen (MP3 oder WAV)'
    Write-Host '    4. Vorlage waehlen und auf "Video erstellen" klicken'
} else {
    Write-Host ''
    Write-Host '  Es fehlt noch etwas:' -ForegroundColor Red
    foreach ($problem in $Probleme) { Write-Host "    - $problem" -ForegroundColor Red }
    Write-Host ''
    Write-Host '  Hilfreiche Adressen:' -ForegroundColor White
    Write-Host '    Python : https://www.python.org/downloads/  (Haken bei "Add python.exe to PATH")'
    Write-Host '    ffmpeg : https://www.gyan.dev/ffmpeg/builds/ (Datei ffmpeg-release-essentials.zip)'
    Write-Host ''
    Write-Host '  Nach dem Beheben dieses Fenster schliessen und Setup.bat erneut starten.'
}

Write-Host ''
Write-Host ('=' * 74) -ForegroundColor DarkCyan
if ($Probleme.Count -gt 0) { exit 1 } else { exit 0 }
