# Contributing to GDPR Scanner

Thank you for considering a contribution. This project helps organisations find
and manage personal data in Microsoft 365 tenants. Contributions that improve
compliance coverage, reliability, and usability are very welcome.

---

## Before You Start

- Check the [open issues](../../issues) and [SUGGESTIONS.md](SUGGESTIONS.md) to
  see if your idea is already tracked
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

# Run the Document Scanner
python server.py

# Run the GDPRScanner
python gdpr_scanner.py
```

You will need a Microsoft Azure app registration with the permissions described
in the README to test GDPRScanner against a real tenant. A developer tenant
is available for free via the [Microsoft 365 Developer Program](https://developer.microsoft.com/microsoft-365/dev-program).

---

## What We Welcome

- Bug fixes
- Improved CPR false-positive reduction
- New language files (see `lang/en.lang` for the key list)
- Items from [SUGGESTIONS.md](SUGGESTIONS.md) — check the status column first
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

**JavaScript (embedded in the Flask templates)**
- `const` / `let` — no `var`
- `async/await` over `.then()` chains
- All user-visible strings must have a `data-i18n` key so translations work

**SQL**
- Use parameterised queries — never string-format SQL
- New columns on existing tables must have a corresponding migration in `_MIGRATIONS` in `gdpr_db.py`

---

## Adding a Language

1. Copy `lang/en.lang` to `lang/xx.lang` (ISO 639-1 code)
2. Translate all values — keys must stay identical
3. Test by setting `~/.m365_scanner_lang` to `xx` and restarting

---

## Pull Request Process

1. Fork the repository and create a branch: `git checkout -b feature/my-feature`
2. Make your changes and test them
3. Run a syntax check: `python -m py_compile gdpr_scanner.py m365_connector.py gdpr_db.py`
4. Update `README.md` if your change adds or changes user-visible behaviour
5. Open a pull request with a clear description of what it does and why
6. Link to the relevant issue or SUGGESTIONS.md item if applicable

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
