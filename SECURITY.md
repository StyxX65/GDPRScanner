# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest  | ✅ Yes    |

We support only the latest release. Please update before reporting a bug.

---

## Reporting a Vulnerability

**Please do not file a public GitHub issue for security vulnerabilities.**

This tool processes sensitive personal data including Danish CPR numbers (national
identifiers). Security issues should be reported privately so a fix can be prepared
before public disclosure.

**Report to:** Open a [GitHub Security Advisory](https://github.com/your-org/gdpr-scanner/security/advisories/new)
(Settings → Security → Advisories → New draft advisory)

Please include:
- A description of the vulnerability and its potential impact
- Steps to reproduce the issue
- Any relevant logs or screenshots (redact personal data)
- Your suggested fix if you have one

We will acknowledge receipt within **3 business days** and aim to release a fix
within **14 days** for critical issues.

---

## Scope

Issues we consider in scope:

- Authentication bypass or token leakage in the M365 connector
- Unauthorised access to scan results via the web UI
- CPR numbers or other personal data exposed in logs, error messages, or API responses
- SQL injection or path traversal in the local scanner or database layer
- SSRF (Server-Side Request Forgery) via URL inputs
- Dependency vulnerabilities with a known exploit path

Out of scope:

- Issues requiring physical access to the machine running the scanner
- Vulnerabilities in Microsoft Graph API itself (report to Microsoft MSRC)
- Social engineering attacks

---

## Data Handling Notes for Security Researchers

- CPR numbers are stored in the SQLite database as **SHA-256 hashes only** — never in plaintext
- SMTP passwords are stored in `~/.gdpr_scanner_smtp.json` with chmod 600
- Microsoft OAuth tokens are stored in the MSAL token cache in `~/.gdpr_scanner_config.json`
- Scan results are stored locally in `~/.gdpr_scanner.db` — never transmitted externally
- The web UI binds to `127.0.0.1` by default — it is not designed to be exposed to the internet

---

## Dependency Security

This project uses Python dependencies listed in `requirements.txt`. We recommend
running `pip audit` or `safety check` periodically to identify known CVEs in
dependencies.

```bash
pip install pip-audit
pip-audit -r requirements.txt
```
