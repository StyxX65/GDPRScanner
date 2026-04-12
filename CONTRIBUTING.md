# Contributing to GDPR Scanner

Thank you for considering a contribution. This project helps organisations find
and manage personal data across Microsoft 365 (Exchange, OneDrive, SharePoint,
Teams), Google Workspace (Gmail, Google Drive), and local/SMB file systems.
Contributions that improve compliance coverage, reliability, and usability are
very welcome.

---

## Before You Start

- Check the [open issues](../../issues) to see if your idea is already tracked
- For large features, open an issue first to discuss the approach — this avoids
  wasted effort if the direction doesn't fit
- Security vulnerabilities: see [SECURITY.md](SECURITY.md) — do not file public issues

---

## Development Setup

```bash
# Clone and set up a virtual environment
git clone https://github.com/your-org/gdpr-scanner.git
cd gdpr-scanner
python3 -m venv venv
source venv/bin/activate          # macOS / Linux
venv\Scripts\activate             # Windows

pip install -r requirements.txt

# Danish NER model (optional — needed for name/address detection)
python -m spacy download da_core_news_lg

# Start the scanner (serves on http://0.0.0.0:5100)
python gdpr_scanner.py

# Run the test suite
python -m pytest tests/ -q
```

To test against a real M365 tenant you will need a Microsoft Azure app
registration with the permissions described in the README. A free developer
tenant is available via the [Microsoft 365 Developer Program](https://developer.microsoft.com/microsoft-365/dev-program).

---

## What We Welcome

- Bug fixes
- Improved CPR false-positive reduction
- New language files (see `lang/en.json` for the key list)
- Performance improvements for large tenants
- Docker / deployment improvements
- Documentation fixes

---

## Code Style

**Python**
- Follow PEP 8 with a line length of 100
- Use type hints for function signatures
- No external formatters are enforced — just keep it consistent with the surrounding code
- All personal data (CPR numbers) must be SHA-256 hashed before storage — never store or log raw CPR values
- Wrap Graph API calls in try/except and handle `M365PermissionError` gracefully

**JavaScript (`static/js/*.js` — ES modules)**
- `const` / `let` — no `var`
- `async/await` over `.then()` chains
- All user-visible strings must have a `data-i18n` key so translations work

**SQL**
- Use parameterised queries — never string-format SQL
- New columns on existing tables must have a corresponding migration in `_MIGRATIONS` in `gdpr_db.py`

---

## Adding a Language

1. Copy `lang/en.json` to `lang/xx.json` (ISO 639-1 code)
2. Translate all values — keys must stay identical
3. Test by writing `xx` to `~/.gdprscanner/lang` and restarting

---

## Pull Request Process

1. Fork the repository and create a branch: `git checkout -b feature/my-feature`
2. Make your changes and test them
3. Run the test suite: `python -m pytest tests/ -q`
4. Run a syntax check on the modules you touched, e.g.:
   `python -m py_compile gdpr_scanner.py scan_engine.py app_config.py gdpr_db.py`
5. Update `README.md` if your change adds or changes user-visible behaviour
6. Open a pull request with a clear description of what it does and why
7. Link to the relevant issue if applicable

We aim to review pull requests within one week.

---

## Personal Data in Tests and Examples

**Do not include real CPR numbers, email addresses, or names in test data,
example output, or documentation.** Use clearly fictional values:

```python
# Good
test_cpr = "010101-1234"   # fictional — fails Modulus 11 check

# Bad
test_cpr = "150385-1234"   # could be a real person
```

If you are testing with a real Microsoft 365 tenant, ensure you have appropriate
authorisation to access that data.

---

## Contributor License Agreement

By submitting a pull request you confirm that:

- You wrote the contribution yourself or have the right to submit it
- You license your contribution under the same AGPL-3.0 terms as this project
- You understand the disclaimer in LICENSE — this is a compliance tool, not legal advice

---

## Code of Conduct

Be respectful. Harassment of any kind will not be tolerated.
