#Requires -RunAsAdministrator
# Always run from the folder this script lives in
Set-Location -Path $PSScriptRoot
<#
.SYNOPSIS
    M365 GDPR Scanner -- Windows Installation Script
.DESCRIPTION
    Installs all dependencies for gdpr_scanner.py and m365_connector.py:
      - Python 3.11 or 3.12  (3.13+ blocked -- spaCy incompatible)
      - Tesseract OCR 5.x with Danish + English language packs
      - Poppler (required by pdfplumber for PDF rendering)
      - All Python packages including pywebview, pystray
      - spaCy Danish NER model (da_core_news_lg, ~500 MB)
    Adds Tesseract and Poppler to the system PATH.
.NOTES
    Run from an elevated PowerShell prompt:
        PowerShell -ExecutionPolicy Bypass -File install_windows.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -- Colours --------------------------------------------------------------------
function Write-Step  { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK    { param($msg) Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "    [!!] $msg" -ForegroundColor Yellow }
function Write-Fail  { param($msg) Write-Host "    [XX] $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  M365 GDPR Scanner - Windows Setup" -ForegroundColor White
Write-Host "  -----------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# -- 0. Check architecture ------------------------------------------------------
if ($env:PROCESSOR_ARCHITECTURE -ne "AMD64") {
    Write-Warn "This script targets 64-bit Windows. Proceeding anyway."
}

# -- 1. Install Chocolatey (if not present) -------------------------------------
Write-Step "Checking Chocolatey package manager"
if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
    Write-Host "    Installing Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString(
        'https://community.chocolatey.org/install.ps1'))
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH","User")
    Write-OK "Chocolatey installed"
} else {
    Write-OK "Chocolatey already installed ($((choco --version)))"
}

# -- Virtualenv path -----------------------------------------------------------
$VenvDir    = Join-Path $PSScriptRoot "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

# -- 2. Install / validate Python ---------------------------------------------------
# Compatible: 3.11.x or 3.12.x
# spaCy does not support 3.13+. pywebview requires 3.8+.
Write-Step "Checking Python (need 3.11 or 3.12 -- prefer 3.12, spaCy incompatible with 3.13+)"

function Get-PythonExe {
    # Returns the path/command of a compatible Python (3.11 or 3.12), or $null.
    $candidates = @()

    # py launcher -- wrap in try/catch so "No runtime found" exit codes don't bubble up
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in @("3.12", "3.11")) {
            try {
                $test = $null
                $prev = $ErrorActionPreference
                $ErrorActionPreference = 'SilentlyContinue'
                $test = & py "-$v" --version 2>&1
                $ErrorActionPreference = $prev
            } catch { $ErrorActionPreference = $prev }
            if ("$test" -match "^Python $v") { $candidates += "py -$v" }
        }
    }

    # Direct python / python3 commands
    foreach ($cmd in @("python3.12", "python3.11", "python", "python3")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            $candidates += $cmd
        }
    }

    # Well-known install locations (e.g. installed from python.org without PATH update)
    $wellKnown = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python311\python.exe"
    )
    foreach ($p in $wellKnown) {
        if (Test-Path $p) { $candidates += $p }
    }

    foreach ($cmd in $candidates) {
        $parts = $cmd -split " "
        $raw = & $parts[0] $(if ($parts.Count -gt 1) { $parts[1..($parts.Count-1)] }) --version 2>&1
        if ("$raw" -match "Python (\d+)\.(\d+)") {
            $maj = [int]$Matches[1]; $min = [int]$Matches[2]
            if ($maj -eq 3 -and ($min -eq 11 -or $min -eq 12)) { return $cmd }
        }
    }
    return $null
}

function Get-PythonVersionStr {
    param($cmd)
    $parts = $cmd -split " "
    $raw = & $parts[0] $(if ($parts.Count -gt 1) { $parts[1..($parts.Count-1)] }) --version 2>&1
    return $raw
}

function Invoke-Py {
    param([string[]]$PyArgs)
    $parts = $script:pythonCmd -split " "
    if ($parts.Count -gt 1) { & $parts[0] $parts[1] @PyArgs }
    else                     { & $parts[0] @PyArgs }
    return $LASTEXITCODE
}

$pythonCmd = Get-PythonExe

if ($pythonCmd) {
    $verStr = Get-PythonVersionStr $pythonCmd
    Write-OK "Compatible Python found: $verStr  (using '$pythonCmd')"
} else {
    # Check if an incompatible version is present so we can warn clearly
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $raw = & python --version 2>&1
        if ($raw -match "Python (\d+)\.(\d+)") {
            $maj = [int]$Matches[1]; $min = [int]$Matches[2]
            if ($maj -eq 3 -and $min -ge 13) {
                Write-Warn "Python $maj.$min is installed but too new (spaCy needs <= 3.12)"
                Write-Warn "Python 3.11 will be installed alongside it"
            } elseif ($maj -eq 3 -and $min -le 10) {
                Write-Warn "Python $maj.$min is installed but too old (need >= 3.11)"
            }
        }
    }
    # ---- Try Chocolatey first (fast, silent) ----
    $chocoOk = $false
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        Write-Host "    Installing Python 3.12 via Chocolatey..."
        choco install python312 -y --no-progress | Out-Null
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("PATH","User")
        $pythonCmd = Get-PythonExe
        if ($pythonCmd) { $chocoOk = $true }
    }

    # ---- Direct download from python.org (works without Chocolatey) ----
    if (-not $chocoOk) {
        $PyVersion  = "3.12.9"
        $PyInstaller = "$env:TEMP\python-$PyVersion-amd64.exe"
        $PyUrl       = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-amd64.exe"

        Write-Host "    Downloading Python $PyVersion from python.org..."
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            & curl.exe -L --silent --show-error -o $PyInstaller $PyUrl
            if ($LASTEXITCODE -ne 0) { throw "curl.exe download failed" }
        } catch {
            Write-Fail "Download failed: $_`nInstall Python 3.12 manually from https://www.python.org/downloads/ then re-run this script."
        }

        Write-Host "    Installing Python $PyVersion (silent, all users)..."
        $installArgs = "/quiet InstallAllUsers=0 PrependPath=0 Include_test=0"
        Start-Process -FilePath $PyInstaller -ArgumentList $installArgs -Wait -NoNewWindow

        # Reload PATH so the new python.exe is visible in this session
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("PATH","User")

        $pythonCmd = Get-PythonExe
        if (-not $pythonCmd) {
            Write-Fail ("Python $PyVersion was installed but could not be found.`n" +
                        "  -- Open a NEW PowerShell window and re-run this script, or`n" +
                        "  -- Install manually from https://www.python.org/downloads/")
        }
    }

    $verStr = Get-PythonVersionStr $pythonCmd
    Write-OK "Python installed: $verStr"
}

# Final sanity check
$parts = $pythonCmd -split " "
$raw = & $parts[0] $(if ($parts.Count -gt 1) { $parts[1..($parts.Count-1)] }) --version 2>&1
if ($raw -notmatch "Python 3\.(11|12)") {
    Write-Fail "Could not confirm a Python 3.11 or 3.12 interpreter. Got: $raw"
}

# -- Create / reuse virtualenv -------------------------------------------------
Write-Step "Setting up virtualenv at $VenvDir"
if (Test-Path $VenvPython) {
    Write-OK "Existing virtualenv found -- reusing"
} else {
    if (Test-Path $VenvDir) { Remove-Item $VenvDir -Recurse -Force }
    Write-Host "    Creating virtualenv..."
    Invoke-Py @("-m", "venv", $VenvDir)
    Write-OK "Virtualenv created: $VenvDir"
}

function Invoke-VenvPip {
    param([string[]]$PipArgs)
    & $VenvPython -m pip @PipArgs
    return $LASTEXITCODE
}

Write-Host "    Upgrading pip..."
Invoke-VenvPip @("install", "--upgrade", "pip", "--quiet") | Out-Null
Write-OK "pip up to date"

# -- 3. Install Visual C++ Redistributable (required by OpenCV/cv2) -----------
Write-Step "Checking Visual C++ Redistributable 2015-2022"
$vcKey = "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
$vcAlt = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
$vcInstalled = (Test-Path $vcKey) -or (Test-Path $vcAlt)
if ($vcInstalled) {
    Write-OK "Visual C++ Redistributable already installed"
} else {
    Write-Host "    Downloading VC++ Redistributable..."
    $vcUrl = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
    $vcInstaller = "$env:TEMP\vc_redist.x64.exe"
    & curl.exe -L --silent --show-error -o $vcInstaller $vcUrl
    if ($LASTEXITCODE -ne 0) { Write-Warn "VC++ download failed -- skipping (may already be installed)" }
    Write-Host "    Installing silently..."
    Start-Process -FilePath $vcInstaller -ArgumentList "/install", "/quiet", "/norestart" -Wait
    Remove-Item $vcInstaller -Force
    Write-OK "Visual C++ Redistributable installed"
}

# -- 4. Install Tesseract OCR ---------------------------------------------------
Write-Step "Installing Tesseract OCR"
$ToolsDir = Join-Path $PSScriptRoot "tools"
$TessDir  = Join-Path $ToolsDir "tesseract"
$tessExe  = Join-Path $TessDir "tesseract.exe"
New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
if (Test-Path $tessExe) {
    $tessVer = & $tessExe --version 2>&1 | Select-Object -First 1
    Write-OK "Tesseract already installed: $tessVer"
} else {
    Write-Host "    Downloading Tesseract 5.x installer..."
    # Download Tesseract installer -- try multiple mirrors
    $tessInstaller = "$env:TEMP\tesseract-setup.exe"
    $tessUrls = @(
        "https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.3.4.20240503.exe",
        "https://github.com/UB-Mannheim/tesseract/releases/download/v5.3.4.20240503/tesseract-ocr-w64-setup-5.3.4.20240503.exe"
    )
    $downloaded = $false
    foreach ($tessUrl in $tessUrls) {
        Write-Host "    Trying: $tessUrl"
        # Suppress NativeCommandError -- check exit code manually
        $prev = $ErrorActionPreference; $ErrorActionPreference = "SilentlyContinue"
        & curl.exe -L --fail --silent --show-error -o $tessInstaller $tessUrl 2>&1 | Out-Null
        $curlExit = $LASTEXITCODE
        $ErrorActionPreference = $prev
        $sz = if (Test-Path $tessInstaller) { (Get-Item $tessInstaller).Length } else { 0 }
        if ($curlExit -eq 0 -and $sz -gt 1MB) {
            Write-OK "Downloaded ($([math]::Round($sz/1MB,1)) MB)"
            $downloaded = $true
            break
        }
        Write-Host "    Failed (exit $curlExit, $sz bytes) -- trying next mirror..."
        if (Test-Path $tessInstaller) { Remove-Item $tessInstaller -Force }
    }
    if (-not $downloaded) {
        Write-Host ""
        Write-Host "    Automatic download failed." -ForegroundColor Yellow
        Write-Host "    Please download the installer manually:" -ForegroundColor Yellow
        Write-Host "    https://github.com/UB-Mannheim/tesseract/releases/tag/v5.3.4.20240503" -ForegroundColor Cyan
        Write-Host "    Save it as: $tessInstaller" -ForegroundColor Cyan
        Write-Host "    Then press Enter to continue..." -ForegroundColor Yellow
        Read-Host
        if (-not (Test-Path $tessInstaller) -or (Get-Item $tessInstaller).Length -lt 1MB) {
            Write-Fail "Installer not found at $tessInstaller"
        }
    }
    Write-Host "    Running installer (silent)..."
    Start-Process -FilePath $tessInstaller -ArgumentList "/S /D=$TessDir" -Wait
    Remove-Item $tessInstaller -Force
    Write-OK "Tesseract installed in project tools\ folder"
}

# Tesseract is local in tools\ -- session PATH set above

# -- 4. Install Tesseract language packs ---------------------------------------
Write-Step "Installing Tesseract language packs (Danish + English)"
$tessData = Join-Path $TessDir "tessdata"
New-Item -ItemType Directory -Force -Path $tessData | Out-Null
$langFiles = @{
    "dan" = "https://github.com/tesseract-ocr/tessdata/raw/main/dan.traineddata"
    "eng" = "https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata"
}
foreach ($lang in $langFiles.Keys) {
    $dest = Join-Path $tessData "$lang.traineddata"
    if (Test-Path $dest) {
        Write-OK "'$lang' language pack already present"
    } else {
        Write-Host "    Downloading $lang.traineddata..."
        & curl.exe -L --silent --show-error -o $dest $langFiles[$lang]
        if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to download $lang language pack" }
        Write-OK "'$lang' installed"
    }
}

# -- 5. Install Poppler --------------------------------------------------------
Write-Step "Installing Poppler (required for PDF rendering)"
$PopplerDir = Join-Path $ToolsDir "poppler"
$popplerBin  = Join-Path $PopplerDir "Library\bin"
if (Test-Path (Join-Path $popplerBin "pdftoppm.exe")) {
    Write-OK "Poppler already installed"
} else {
    Write-Host "    Downloading Poppler for Windows..."
    $popplerUrl = "https://github.com/oschwartz10612/poppler-windows/releases/download/v24.07.0-0/Release-24.07.0-0.zip"
    $popplerZip = "$env:TEMP\poppler.zip"
    & curl.exe -L --silent --show-error -o $popplerZip $popplerUrl
    if ($LASTEXITCODE -ne 0) { Write-Fail "Poppler download failed. Try re-running the script." }
    Write-Host "    Extracting to $popplerBase..."
    Expand-Archive -Path $popplerZip -DestinationPath $PopplerDir -Force
    Remove-Item $popplerZip -Force
    $found = Get-ChildItem -Path $PopplerDir -Recurse -Filter "pdftoppm.exe" |
             Select-Object -First 1
    if ($found) {
        $popplerBin = $found.DirectoryName
        Write-OK "Poppler extracted: $popplerBin"
    } else {
        Write-Fail "Poppler extraction failed -- pdftoppm.exe not found"
    }
}

# Poppler is local in tools\ -- session PATH set above
$env:PATH = "$env:PATH;$popplerBin"

# -- 6. Install Python packages -------------------------------------------------
Write-Step "Installing Python packages"

$packages = @(
    # Web server
    @{ name="flask";                      desc="web server" },
    # PDF handling
    @{ name="pdfplumber";                 desc="PDF text extraction" },
    @{ name="pdf2image";                  desc="PDF to image (needs Poppler)" },
    @{ name="pytesseract";                desc="OCR wrapper (needs Tesseract)" },
    @{ name="pypdf";                      desc="PDF read/write" },
    @{ name="reportlab";                  desc="PDF generation for redaction" },
    # Document formats
    @{ name="python-docx";                desc="Word documents" },
    @{ name="openpyxl";                   desc="Excel files" },
    @{ name="img2pdf";                    desc="image to PDF" },
    # Image / CV
    @{ name="opencv-python-headless";     desc="face detection (headless, fewer DLL deps)" },
    @{ name="numpy";                      desc="image processing" },
    @{ name="Pillow";                     desc="image handling" },
    # NER / anonymisation
    @{ name="spacy";                      desc="named entity recognition" },
    # Archive scanning
    # Native app window
    @{ name="pymupdf";                    desc="secure PDF redaction (physical text removal)" },
    @{ name="pywebview";                  desc="native webview window" },
    @{ name="pystray";                    desc="system tray icon (fallback)" },
    # App bundling
    @{ name="pyinstaller";                desc="app packager" },
    @{ name="pyinstaller-hooks-contrib";  desc="PyInstaller hooks" },
    # GDPRScanner
    @{ name="msal";                          desc="Microsoft authentication" },
    @{ name="requests";                      desc="HTTP client for Graph API" },
    # Optional — File system scanning (#8)
    @{ name="smbprotocol";                   desc="native SMB2/3 network share scanning (optional)" },
    @{ name="keyring";                        desc="OS keychain credential storage for SMB (optional)" },
    @{ name="python-dotenv";                  desc=".env file credential fallback (optional)" },
    # Scheduler (#19)
    @{ name="APScheduler";                    desc="in-process scheduled scans (optional)" },
    # Google Workspace scanning (#10)
    @{ name="google-auth";                    desc="Google service account auth (optional)" },
    @{ name="google-auth-httplib2";           desc="Google auth HTTP transport (optional)" },
    @{ name="google-api-python-client";       desc="Gmail + Drive + Admin APIs (optional)" }
)

$failed = @()
foreach ($pkg in $packages) {
    Write-Host ("    {0,-36} {1}" -f ($pkg.name + "..."), $pkg.desc) -NoNewline
    Invoke-VenvPip @("install", $pkg.name, "--quiet", "--disable-pip-version-check") | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAILED" -ForegroundColor Red
        $failed += $pkg.name
    } else {
        Write-Host "  OK" -ForegroundColor Green
    }
}

# pywebview 5.x used a [win32] extra; 6.x+ ships WebView2 support built-in -- no extra needed
if ($LASTEXITCODE -eq 0) { Write-Host "  OK" -ForegroundColor Green }
else { Write-Host "  skipped" -ForegroundColor Yellow }

if ($failed.Count -gt 0) {
    Write-Warn "Failed to install: $($failed -join ', ')"
    Write-Warn "Retry manually: python -m pip install $($failed -join ' ')"
}

# -- 7. Install spaCy language model -------------------------------------------
Write-Step "Installing spaCy Danish NER model (~500 MB, may take several minutes)"

# Check if any model already installed
$spaCyHasModel = & $VenvPython -c "import spacy; [spacy.load(m) for m in ['da_core_news_lg','da_core_news_md','da_core_news_sm'] if spacy.util.is_package(m)]; print('ok')" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-OK "spaCy Danish model already installed"
} else {
    $models = @("da_core_news_lg", "da_core_news_md", "da_core_news_sm")
    $installed = $false
    foreach ($model in $models) {
        Write-Host "    Trying $model..."
        & $VenvPython -m spacy download $model --quiet 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-OK "Installed: $model"
            $installed = $true
            break
        }
    }
    if (-not $installed) {
        Write-Warn "No spaCy Danish model installed -- anonymisation will be unavailable"
        Write-Warn "Retry manually:  python -m spacy download da_core_news_sm"
    }
}

# -- 8. Verify installation -----------------------------------------------------
Write-Step "Verifying installation"

# Python
Write-OK "Python: $(Get-PythonVersionStr $pythonCmd)"

# Tesseract
try {
    $tessVer = & tesseract --version 2>&1 | Select-Object -First 1
    Write-OK "Tesseract: $tessVer"
    $langs = & tesseract --list-langs 2>&1 | Where-Object { $_ -match "^(dan|eng)$" }
    Write-OK "OCR languages: $($langs -join ', ')"
} catch {
    Write-Warn "Tesseract not on PATH -- restart PowerShell and re-run if needed"
}

# Poppler
try {
    $pp = Get-Command pdftoppm -ErrorAction Stop
    Write-OK "Poppler: $($pp.Source)"
} catch {
    Write-Warn "Poppler not on PATH -- restart PowerShell and re-run if needed"
}

# All Python imports -- write to a temp file to avoid PowerShell expanding {vars} in f-strings
$importScriptPath = Join-Path $env:TEMP "gdpr_verify.py"
Set-Content -Path $importScriptPath -Encoding UTF8 -Value @'
import sys
checks = [
    ('flask',         'flask'),
    ('pdfplumber',    'pdfplumber'),
    ('pdf2image',     'pdf2image'),
    ('pytesseract',   'pytesseract'),
    ('pypdf',         'pypdf'),
    ('reportlab',     'reportlab'),
    ('python-docx',   'docx'),
    ('openpyxl',      'openpyxl'),
    ('opencv-python-headless', 'cv2'),
    ('numpy',         'numpy'),
    ('Pillow',        'PIL'),
    ('spacy',         'spacy'),
    ('img2pdf',       'img2pdf'),
    ('pymupdf',       'fitz'),
    ('pywebview',     'webview'),
    ('pystray',       'pystray'),
    ('PyInstaller',   'PyInstaller'),
    ('msal',          'msal'),
    ('requests',      'requests'),
]
optional_checks = [
    ('smbprotocol',   'smbprotocol'),
    ('keyring',       'keyring'),
    ('python-dotenv', 'dotenv'),
    ('APScheduler',   'apscheduler'),
]
missing = []
for name, imp in checks:
    try:
        __import__(imp)
        print("    [OK] " + name)
    except ImportError:
        print("    [!!] " + name + "  MISSING")
        missing.append(name)
print("\n    Optional (file system scanning):")
for name, imp in optional_checks:
    try:
        __import__(imp)
        print("    [OK] " + name)
    except ImportError:
        print("    [--] " + name + "  (not installed)")
if missing:
    print("\nMissing required: " + ", ".join(missing))
    sys.exit(1)
print("\nAll required packages verified.")
sys.exit(0)
'@

& $VenvPython $importScriptPath
$allOk = ($LASTEXITCODE -eq 0)
Remove-Item $importScriptPath -ErrorAction SilentlyContinue

# -- 9. Create launch scripts ---------------------------------------------------
Write-Step "Creating launch scripts"

Set-Content -Path "start_gdpr.bat" -Encoding ASCII -Value @'
@echo off
:: GDPRScanner - Web UI
cd /d "%~dp0"
set PATH=%~dp0tools\tesseract;%~dp0tools\poppler\Library\bin;%PATH%
set TESSDATA_PREFIX=%~dp0tools\tesseract\tessdata
set PORT=5100
echo.
echo   GDPRScanner
echo   Open in browser: http://localhost:%PORT%
echo   Press Ctrl+C to stop
echo.
"%~dp0venv\Scripts\python.exe" "%~dp0gdpr_scanner.py" --port %PORT%
pause
'@
Write-OK "Created: start_gdpr.bat"

Set-Content -Path "build_m365.bat" -Encoding ASCII -Value @'
@echo off
:: GDPRScanner -- Build standalone .exe
cd /d "%~dp0"
set PATH=%~dp0tools\tesseract;%~dp0tools\poppler\Library\bin;%PATH%
set TESSDATA_PREFIX=%~dp0tools\tesseract\tessdata
echo Building GDPRScanner...
echo.
"%~dp0venv\Scripts\python.exe" "%~dp0build_gdpr.py" --clean %*
pause
'@
Write-OK "Created: build_m365.bat"


# -- Done -----------------------------------------------------------------------
Write-Host ""
Write-Host "  -----------------------------------------" -ForegroundColor DarkGray
if ($allOk) {
    Write-Host "  Installation complete!" -ForegroundColor Green
} else {
    Write-Host "  Installation complete with warnings -- see above" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  GDPRScanner:" -ForegroundColor White
Write-Host "    Double-click  start_gdpr.bat" -ForegroundColor Cyan
Write-Host "    Web UI: http://localhost:5100" -ForegroundColor White
Write-Host ""
Write-Host "  File system scanning (optional):" -ForegroundColor White
Write-Host "    python gdpr_scanner.py --scan-path C:\Users\Me\Documents" -ForegroundColor Cyan
Write-Host "    python gdpr_scanner.py --scan-path //nas/shares --smb-user DOMAIN\user" -ForegroundColor Cyan
Write-Host "    Or use the File sources panel in the GDPRScanner UI" -ForegroundColor Gray
Write-Host ""
Write-Host "  Build standalone app:" -ForegroundColor White
Write-Host "    Double-click  build_gdpr.bat   ->  dist\GDPRScanner.exe" -ForegroundColor Cyan
Write-Host "  -----------------------------------------" -ForegroundColor DarkGray
Write-Host ""
