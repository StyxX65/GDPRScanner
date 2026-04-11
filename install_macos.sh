#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Document Scanner — macOS Installation Script
# ══════════════════════════════════════════════════════════════════════════════
# Installs all dependencies for document_scanner.py, server.py, build.py,
# gdpr_scanner.py and m365_connector.py:
#   - Homebrew (if not present)
#   - Python 3.11 or 3.12  (3.13+ blocked — spaCy incompatible)
#   - Tesseract OCR with Danish + English language packs
#   - Poppler (required by pdf2image for PDF rendering)
#   - A virtualenv at ./venv with all Python packages
#   - spaCy Danish NER model (~500 MB)
#
# All Python packages are installed into a virtualenv (./venv) to avoid the
# "externally-managed-environment" error from Homebrew Python 3.12+.
#
# Usage:
#   chmod +x install_macos.sh && ./install_macos.sh
# ══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

step()  { echo -e "\n${CYAN}==> $1${RESET}"; }
ok()    { echo -e "    ${GREEN}[OK]${RESET} $1"; }
warn()  { echo -e "    ${YELLOW}[!!]${RESET} $1"; }
fail()  { echo -e "    ${RED}[XX]${RESET} $1"; exit 1; }

# Where the virtualenv will live — next to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

echo ""
echo -e "${BOLD}  Document Scanner — macOS Setup${RESET}"
echo "  -----------------------------------------"
echo ""

# ── 0. Detect architecture ────────────────────────────────────────────────────
ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
    BREW_PREFIX="/opt/homebrew"
    ok "Apple Silicon (M-series) — Homebrew prefix: $BREW_PREFIX"
else
    BREW_PREFIX="/usr/local"
    ok "Intel Mac — Homebrew prefix: $BREW_PREFIX"
fi

# ── 1. Install Homebrew ───────────────────────────────────────────────────────
step "Checking Homebrew"
if command -v brew &>/dev/null; then
    ok "Homebrew already installed: $(brew --version | head -1)"
else
    echo "    Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$($BREW_PREFIX/bin/brew shellenv)"
    ok "Homebrew installed"
fi
eval "$($BREW_PREFIX/bin/brew shellenv)" 2>/dev/null || true

# ── 2. Find or install Python 3.11 / 3.12 ────────────────────────────────────
# Homebrew Python 3.12+ is "externally managed" — pip installs must go into
# a virtualenv. We find a compatible base interpreter here; all packages will
# be installed into ./venv below, not into the system interpreter.
step "Checking Python (need 3.11 or 3.12 — spaCy incompatible with 3.13+)"

find_compatible_python() {
    for cmd in \
        "$BREW_PREFIX/bin/python3.12" \
        "$BREW_PREFIX/bin/python3.11" \
        python3.12 python3.11 python3 python; do
        if command -v "$cmd" &>/dev/null 2>&1; then
            local ver maj min
            ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
            maj=$(echo "$ver" | cut -d. -f1)
            min=$(echo "$ver" | cut -d. -f2)
            if [[ "$maj" == "3" ]] && { [[ "$min" == "11" ]] || [[ "$min" == "12" ]]; }; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

BASE_PYTHON=""
if BASE_PYTHON=$(find_compatible_python); then
    ok "Compatible Python: $($BASE_PYTHON --version 2>&1)  ($BASE_PYTHON)"
else
    if command -v python3 &>/dev/null; then
        EXISTING=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        EXIST_MIN=$(echo "$EXISTING" | cut -d. -f2)
        if [[ "$EXIST_MIN" -ge 13 ]]; then
            warn "Python $EXISTING is too new (spaCy requires ≤ 3.12)"
        fi
    fi
    echo "    Installing Python 3.12 via Homebrew..."
    brew install python@3.12
    BASE_PYTHON="$BREW_PREFIX/bin/python3.12"
    if [[ ! -x "$BASE_PYTHON" ]]; then
        echo "    python3.12 not found, trying python3.11..."
        brew install python@3.11
        BASE_PYTHON="$BREW_PREFIX/bin/python3.11"
    fi
    [[ -x "$BASE_PYTHON" ]] || fail "Python install failed. Try: brew install python@3.12"
    ok "Python installed: $($BASE_PYTHON --version 2>&1)"
fi

# Confirm version
$BASE_PYTHON --version 2>&1 | grep -qE 'Python 3\.(11|12)' \
    || fail "Unexpected version: $($BASE_PYTHON --version 2>&1)"

# ── 3. Create virtualenv ──────────────────────────────────────────────────────
step "Setting up virtualenv at $VENV_DIR"

if [[ -d "$VENV_DIR" && -x "$VENV_DIR/bin/python" ]]; then
    # Validate it was built with a compatible interpreter
    VENV_VER=$("$VENV_DIR/bin/python" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
    VENV_MIN=$(echo "$VENV_VER" | cut -d. -f2)
    if [[ "$VENV_MIN" == "11" || "$VENV_MIN" == "12" ]]; then
        ok "Existing virtualenv is compatible (Python $VENV_VER) — reusing"
    else
        warn "Existing virtualenv uses Python $VENV_VER — rebuilding"
        rm -rf "$VENV_DIR"
        $BASE_PYTHON -m venv "$VENV_DIR"
        ok "Virtualenv rebuilt"
    fi
else
    $BASE_PYTHON -m venv "$VENV_DIR"
    ok "Virtualenv created"
fi

# All subsequent Python/pip commands use the venv
PYTHON="$VENV_DIR/bin/python"
PIP="$PYTHON -m pip"

# Upgrade pip inside the venv (no restrictions here)
echo "    Upgrading pip..."
$PIP install --upgrade pip --quiet
ok "pip up to date: $($PIP --version)"

# ── 4. Install Tesseract OCR ──────────────────────────────────────────────────
step "Installing Tesseract OCR + language packs"
if brew list tesseract &>/dev/null 2>&1; then
    ok "Tesseract already installed: $(tesseract --version 2>&1 | head -1)"
else
    brew install tesseract
    ok "Tesseract installed: $(tesseract --version 2>&1 | head -1)"
fi

if brew list tesseract-lang &>/dev/null 2>&1; then
    ok "Tesseract language packs already installed"
else
    echo "    Installing tesseract-lang (~300 MB)..."
    brew install tesseract-lang
    ok "Language packs installed"
fi

if tesseract --list-langs 2>&1 | grep -q "^dan$"; then
    ok "Danish (dan) OCR available"
else
    warn "Danish language pack not found — try: brew reinstall tesseract-lang"
fi

# ── 5. Install Poppler ────────────────────────────────────────────────────────
step "Installing Poppler (required for PDF rendering)"
if brew list poppler &>/dev/null 2>&1; then
    ok "Poppler already installed"
else
    brew install poppler
    ok "Poppler installed"
fi
command -v pdftoppm &>/dev/null \
    && ok "pdftoppm: $(which pdftoppm)" \
    || warn "pdftoppm not on PATH — launcher will probe Homebrew paths automatically"

# ── 6. Install Python packages into venv ─────────────────────────────────────
step "Installing Python packages into virtualenv"

packages=(
    "flask"
    "pdfplumber"
    "pdf2image"
    "pytesseract"
    "pypdf"
    "reportlab"
    "python-docx"
    "openpyxl"
    "img2pdf"
    "opencv-python-headless"
    "numpy"
    "Pillow"
    "spacy"
    "py7zr"
    "pymupdf"
    "pywebview"
    "pystray"
    "pyinstaller"
    "pyinstaller-hooks-contrib"
    # GDPRScanner
    "msal"
    "requests"
    # Optional — File system scanning (#8)
    # smbprotocol: native SMB2/3 without mounting (needed for network share scanning)
    # keyring: OS keychain credential storage for SMB passwords
    # python-dotenv: .env file fallback for headless SMB credentials
    "smbprotocol"
    "keyring"
    "python-dotenv"
    # Scheduler (#19)
    "APScheduler"
    # Google Workspace scanning (#10)
    "google-auth"
    "google-auth-httplib2"
    "google-api-python-client"
)

failed=()
for pkg in "${packages[@]}"; do
    printf "    %-36s" "$pkg..."
    if $PIP install "$pkg" --quiet --disable-pip-version-check 2>/dev/null; then
        echo -e "${GREEN}OK${RESET}"
    else
        echo -e "${RED}FAILED${RESET}"
        failed+=("$pkg")
    fi
done

if [[ ${#failed[@]} -gt 0 ]]; then
    warn "Failed: ${failed[*]}"
    warn "Retry: $PIP install ${failed[*]}"
fi

# ── 7. Install create-dmg ─────────────────────────────────────────────────────
step "Checking create-dmg (optional — for .dmg packaging)"
if command -v create-dmg &>/dev/null; then
    ok "create-dmg already installed"
else
    brew install create-dmg 2>/dev/null \
        && ok "create-dmg installed" \
        || warn "create-dmg unavailable — install manually: brew install create-dmg"
fi

# ── 8. Install spaCy Danish NER model ─────────────────────────────────────────
step "Installing spaCy Danish NER model (~500 MB)"

# spaCy's download command uses shutil.which("pip") to find a package
# installer. Inside a venv the wrapper may be named pip3 only. Ensure a
# `pip` executable exists so spaCy can find it.
if [[ ! -x "$VENV_DIR/bin/pip" ]]; then
    echo "    Creating pip wrapper in venv (needed by spaCy download)…"
    cat > "$VENV_DIR/bin/pip" << 'PIPSHIM'
#!/usr/bin/env bash
exec "$(dirname "$0")/python3" -m pip "$@"
PIPSHIM
    chmod +x "$VENV_DIR/bin/pip"
fi
# Verify pip is now visible
if "$VENV_DIR/bin/pip" --version &>/dev/null; then
    ok "pip available: $("$VENV_DIR/bin/pip" --version 2>&1)"
else
    warn "pip wrapper not working — will use direct pip install fallback"
fi

if $PYTHON -c "import da_core_news_lg" &>/dev/null 2>&1; then
    ok "spaCy Danish model already installed"
else
    installed=false
    for model in da_core_news_lg da_core_news_md da_core_news_sm; do
        echo "    Trying $model..."

        # Method 1: spacy download with venv/bin explicitly on PATH
        # (spaCy uses shutil.which("pip") which searches PATH)
        if PATH="$VENV_DIR/bin:$PATH" $PYTHON -m spacy download "$model" 2>/dev/null; then
            ok "Installed: $model (via spacy download)"
            installed=true
            break
        fi

        # Method 2: direct pip install — spaCy models are regular PyPI packages
        echo "    spacy download failed — trying pip install..."
        if $PIP install "$model" 2>&1; then
            if $PYTHON -c "import ${model//-/_}" &>/dev/null 2>&1; then
                ok "Installed: $model (via pip)"
                installed=true
                break
            else
                warn "$model pip install reported success but import failed"
            fi
        fi
    done
    if [[ "$installed" == false ]]; then
        warn "No spaCy model installed — anonymisation unavailable"
        warn "Retry manually:  $PIP install da_core_news_sm"
    fi
fi

# ── 9. Verify ─────────────────────────────────────────────────────────────────
step "Verifying installation"

ok "Python (venv): $($PYTHON --version 2>&1)"
ok "Tesseract: $(tesseract --version 2>&1 | head -1)"
ok "Poppler: $(pdftoppm -v 2>&1 | head -1 || echo 'available via Homebrew PATH')"

$PYTHON - <<'PYCHECK'
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
    ('pywebview',     'webview'),
    ('pystray',       'pystray'),
    ('PyInstaller',   'PyInstaller'),
    ('py7zr',         'py7zr'),
    # GDPRScanner
    ('msal',          'msal'),
    ('requests',      'requests'),
]
optional_checks = [
    ('smbprotocol',   'smbprotocol',  'SMB/CIFS network share scanning'),
    ('keyring',       'keyring',      'OS keychain credential storage'),
    ('python-dotenv', 'dotenv',       '.env file credential fallback'),
    ('APScheduler',   'apscheduler',  'In-process scheduled scans'),
]
missing = []
for name, imp in checks:
    try:
        __import__(imp)
        print(f'    \033[32m[OK]\033[0m {name}')
    except ImportError:
        print(f'    \033[31m[!!]\033[0m {name}  MISSING')
        missing.append(name)
print('\n    Optional (file system scanning):')
for name, imp, desc in optional_checks:
    try:
        __import__(imp)
        print(f'    \033[32m[OK]\033[0m {name}  — {desc}')
    except ImportError:
        print(f'    \033[33m[--]\033[0m {name}  — {desc} (not installed)')
if missing:
    print(f'\n    Missing: {", ".join(missing)}')
    sys.exit(1)
print('\n    All packages verified.')
PYCHECK

ALL_OK=$?

# ── 10. Shell profile ─────────────────────────────────────────────────────────
step "Shell PATH configuration"
SHELL_RC=""
if [[ "$SHELL" == *"zsh"*  ]]; then SHELL_RC="$HOME/.zshrc"; fi
if [[ "$SHELL" == *"bash"* ]]; then SHELL_RC="$HOME/.bash_profile"; fi

if [[ -n "$SHELL_RC" ]]; then
    if grep -q "brew shellenv" "$SHELL_RC" 2>/dev/null; then
        ok "Homebrew already configured in $SHELL_RC"
    else
        echo "" >> "$SHELL_RC"
        echo "# Homebrew" >> "$SHELL_RC"
        echo "eval \"\$($BREW_PREFIX/bin/brew shellenv)\"" >> "$SHELL_RC"
        ok "Homebrew added to $SHELL_RC — restart Terminal or: source $SHELL_RC"
    fi
fi

# ── 11. Create launch scripts ─────────────────────────────────────────────────
step "Creating launch scripts"

# start_gdpr.sh — launches GDPRScanner
cat > "$SCRIPT_DIR/start_gdpr.sh" << M365EOF
#!/usr/bin/env bash
# GDPRScanner — launch script (uses ./venv)
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
source "\$SCRIPT_DIR/venv/bin/activate"
exec python3 "\$SCRIPT_DIR/gdpr_scanner.py" "\${@}"
M365EOF
chmod +x "$SCRIPT_DIR/start_gdpr.sh"
ok "Created: start_gdpr.sh"

# build_gdpr.sh — builds standalone GDPRScanner .app
cat > "$SCRIPT_DIR/build_gdpr.sh" << BLD365EOF
#!/usr/bin/env bash
# GDPRScanner — build .app (uses ./venv)
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
source "\$SCRIPT_DIR/venv/bin/activate"
exec python3 "\$SCRIPT_DIR/build_gdpr.py" --clean "\$@"
BLD365EOF
chmod +x "$SCRIPT_DIR/build_gdpr.sh"
ok "Created: build_gdpr.sh"


# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "  -----------------------------------------"
[[ $ALL_OK -eq 0 ]] \
    && echo -e "  ${GREEN}${BOLD}Installation complete!${RESET}" \
    || echo -e "  ${YELLOW}${BOLD}Installation complete with warnings — see above${RESET}"
echo ""
echo -e "  ${BOLD}GDPRScanner:${RESET}"
echo -e "    ${CYAN}./start_gdpr.sh${RESET}"
echo "    Then open: http://127.0.0.1:5100"
echo ""
echo -e "  ${BOLD}File system scanning (optional):${RESET}"
echo -e "    ${CYAN}./start_gdpr.sh --scan-path ~/Documents${RESET}"
echo -e "    ${CYAN}./start_gdpr.sh --scan-path //nas/shares --smb-user 'DOMAIN\\user'${RESET}"
echo "    Or use the '📁 File sources' panel in the GDPRScanner UI"
echo ""
echo -e "  ${BOLD}Build standalone app:${RESET}"
echo -e "    ${CYAN}./build_gdpr.sh${RESET}   → dist/GDPRScanner.app"
echo ""
echo "  -----------------------------------------"
echo ""
