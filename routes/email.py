"""
SMTP configuration, test, and report sending
"""
from __future__ import annotations
from flask import Blueprint, jsonify, request
from routes import state
from app_config import _load_smtp_config, _save_smtp_config
from routes.export import _build_excel_bytes

bp = Blueprint("email", __name__)


def _send_report_email(xl_bytes: bytes, fname: str,
                       smtp_cfg: dict, recipients: list[str]) -> None:
    """Send the scan report Excel as an email attachment via SMTP."""
    import smtplib as _smtp
    import email.mime.text as _mime_text
    import email.mime.multipart as _mime_mp
    import email.mime.base as _mime_base
    import email.encoders as _encoders
    import datetime as _dt

    host      = smtp_cfg.get("host", "").strip()
    port      = int(smtp_cfg.get("port", 587))
    username  = smtp_cfg.get("username", "").strip()
    password  = smtp_cfg.get("password", "")
    from_addr = smtp_cfg.get("from_addr", "").strip() or username
    use_ssl   = bool(smtp_cfg.get("use_ssl", False))
    use_tls   = bool(smtp_cfg.get("use_tls", True)) and not use_ssl

    if not host:
        raise ValueError("No SMTP host configured")

    subject = f"GDPR Scanner \u2014 scan report {_dt.datetime.now().strftime('%Y-%m-%d')}"
    body_html = (
        "<html><body style='font-family:Arial,sans-serif;color:#333;padding:24px'>"
        "<h2 style='color:#1F3864'>\u2601\ufe0f GDPR Scanner \u2014 scan report</h2>"
        f"<p>Please find the latest scan report attached ({fname}).</p>"
        f"<p style='color:#888;font-size:12px'>Generated: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
        "</body></html>"
    )

    msg = _mime_mp.MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = ", ".join(recipients)
    msg.attach(_mime_text.MIMEText(body_html, "html"))

    part = _mime_base.MIMEBase(
        "application",
        "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    part.set_payload(xl_bytes)
    _encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
    msg.attach(part)

    if use_ssl:
        server = _smtp.SMTP_SSL(host, port, timeout=30)
    else:
        server = _smtp.SMTP(host, port, timeout=30)
    with server:
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        if username and password:
            server.login(username, password)
        server.sendmail(from_addr, recipients, msg.as_string())


def _send_email_graph(subject: str, html_body: str,
                      recipients: list[str],
                      attachment_bytes: bytes = None,
                      attachment_name: str = None) -> None:
    """Send an email via Microsoft Graph API using the current connector token.
    Requires Mail.Send permission (delegated or application).
    Raises on failure."""
    if not state.connector or not state.connector.is_authenticated():
        raise RuntimeError("Not connected to Microsoft 365")

    to_list = [{"emailAddress": {"address": r}} for r in recipients]
    message: dict = {
        "subject": subject,
        "body":    {"contentType": "HTML", "content": html_body},
        "toRecipients": to_list,
    }
    if attachment_bytes and attachment_name:
        import base64 as _b64
        message["attachments"] = [{
            "@odata.type":  "#microsoft.graph.fileAttachment",
            "name":         attachment_name,
            "contentType":  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "contentBytes": _b64.b64encode(attachment_bytes).decode(),
        }]

    if state.connector.is_app_mode:
        smtp_cfg = _load_smtp_config()
        sender = smtp_cfg.get("from_addr") or smtp_cfg.get("username") or recipients[0]
        state.connector._post(f"/users/{sender}/sendMail", {"message": message, "saveToSentItems": False})
    else:
        state.connector._post("/me/sendMail", {"message": message, "saveToSentItems": False})


@bp.route("/api/smtp/config", methods=["GET"])
def smtp_config_get():
    """Return saved SMTP config (password redacted — never sent to client)."""
    cfg = _load_smtp_config()
    safe = {k: v for k, v in cfg.items() if k != "password"}
    safe["has_password"] = bool(cfg.get("password"))
    return jsonify(safe)


@bp.route("/api/smtp/config", methods=["POST"])
def smtp_config_save():
    """Save SMTP config. Omitting 'password' preserves any previously saved password."""
    data = request.get_json() or {}
    existing = _load_smtp_config()
    if not data.get("password") and existing.get("password"):
        data["password"] = existing["password"]
    _save_smtp_config(data)
    return jsonify({"status": "saved"})


@bp.route("/api/smtp/test", methods=["POST"])
def smtp_test():
    """Send a test email. Tries Microsoft Graph API first (no SMTP config needed),
    falls back to SMTP if Graph is unavailable."""
    import datetime as _dt
    saved      = _load_smtp_config()
    recipients = saved.get("recipients", [])
    if isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.replace(";", ",").split(",") if r.strip()]
    if not recipients:
        return jsonify({"error": "No recipients configured — add at least one recipient and save first"}), 400

    subject  = f"GDPR Scanner — test email ({_dt.datetime.now().strftime('%Y-%m-%d %H:%M')})"
    body_html = (
        "<html><body style='font-family:Arial,sans-serif;color:#333;padding:24px'>"
        "<h2 style='color:#1F3864'>☁️ GDPR Scanner — test email</h2>"
        "<p>This is a test email confirming that your email configuration is working correctly.</p>"
        f"<p style='color:#888;font-size:12px'>Sent: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
        "</body></html>"
    )

    # Try Graph API first
    if state.connector and state.connector.is_authenticated():
        try:
            _send_email_graph(subject, body_html, recipients)
            return jsonify({"ok": True, "method": "graph", "recipients": recipients})
        except Exception as graph_err:
            graph_error_str = str(graph_err)
    else:
        graph_error_str = None

    # Fall back to SMTP
    host      = saved.get("host", "").strip()
    port      = int(saved.get("port", 587))
    username  = saved.get("username", "").strip()
    password  = saved.get("password", "")
    from_addr = saved.get("from_addr", "").strip() or username
    use_ssl   = bool(saved.get("use_ssl", False))
    use_tls   = bool(saved.get("use_tls", True)) and not use_ssl

    if not host:
        if graph_error_str:
            return jsonify({"error": (
                f"Microsoft Graph email failed: {graph_error_str}\n\n"
                "Make sure Mail.Send is added to your Azure app registration and admin consent has been granted:\n"
                "Azure AD → App registrations → [your app] → API permissions → Add → Microsoft Graph → Mail.Send → Grant admin consent."
            )}), 400
        return jsonify({"error": "No SMTP host configured. To send via Microsoft 365 Graph (no SMTP needed), add Mail.Send to your Azure app registration."}), 400

    try:
        import smtplib as _smtp
        import email.mime.text as _mime_text
        import email.mime.multipart as _mime_mp
        msg = _mime_mp.MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_addr
        msg["To"]      = ", ".join(recipients)
        msg.attach(_mime_text.MIMEText(body_html, "html"))
        if use_ssl:
            server = _smtp.SMTP_SSL(host, port, timeout=15)
        else:
            server = _smtp.SMTP(host, port, timeout=15)
        with server:
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
            if username and password:
                server.login(username, password)
            server.sendmail(from_addr, recipients, msg.as_string())
        return jsonify({"ok": True, "method": "smtp", "recipients": recipients,
                        "graph_also_failed": bool(graph_error_str)})
    except Exception as smtp_err:
        err_str = str(smtp_err)
        _h = host.lower()
        _corp_m365   = "office365" in _h or "microsoft" in _h
        _personal_ms = not _corp_m365 and any(s in _h for s in ("outlook", "live", "hotmail"))
        _gmail_host  = "gmail" in _h or "smtp.google" in _h
        _auth_err    = "5.7.57" in err_str or "530" in err_str or "535" in err_str or \
                       "534" in err_str or "not authenticated" in err_str.lower() or \
                       "Username and Password" in err_str
        _conn_err    = "nodename nor servname" in err_str or "Name or service not known" in err_str or \
                       "getaddrinfo" in err_str or "Connection refused" in err_str or \
                       "Errno 8" in err_str or "Errno 111" in err_str or "Errno 61" in err_str or \
                       "timed out" in err_str.lower()
        if _conn_err:
            err_str = (f"Could not connect to SMTP server \"{host}\" on port {port}. "
                       f"Check that the hostname and port are correct.")
        elif _corp_m365 and _auth_err:
            err_str = ("M365 blocked SMTP AUTH. Fix: enable Authenticated SMTP in the M365 admin centre "
                       "(Users → Active users → [user] → Mail → Manage email apps → Authenticated SMTP), "
                       "or add Mail.Send to your Azure app to use Graph instead.")
        elif (_personal_ms or _gmail_host) and _auth_err:
            if _gmail_host:
                _gws_account = "@gmail.com" not in username.lower() and "@googlemail.com" not in username.lower()
                if _gws_account:
                    err_str = ("Google Workspace SMTP authentication failed.\n\n"
                               "Your account uses a custom domain via Google Workspace. "
                               "SMTP access is controlled by your organisation's Google Workspace admin, not your personal account settings.\n\n"
                               "Ask your Google Workspace admin to:\n"
                               "  • Enable 2-Step Verification for your account (required for App Passwords)\n"
                               "  • Allow users to manage their own App Passwords (Admin console → Security → 2-Step Verification)\n"
                               "  • Or configure SMTP relay: Admin console → Apps → Google Workspace → Gmail → Routing → SMTP relay service\n\n"
                               "If App Passwords are available for your account, generate one at "
                               "myaccount.google.com → Security → 2-Step Verification → App passwords "
                               "and use it instead of your normal password.")
                else:
                    err_str = ("Gmail SMTP authentication failed.\n\n"
                               "Google requires an App Password for SMTP — your normal password will not work.\n\n"
                               "If you are already using an App Password, check:\n"
                               "  • No spaces — the 16-character code must be entered without spaces\n"
                               "  • The App Password has not been revoked — generate a new one at "
                               "myaccount.google.com → Security → 2-Step Verification → App passwords\n"
                               "  • The correct username (your full Gmail address, e.g. you@gmail.com)\n"
                               "  • Port 587 with STARTTLS, or port 465 with SSL")
            else:
                url = "account.microsoft.com/security"
                err_str = (f"Authentication failed — Microsoft blocks regular passwords for SMTP when MFA is enabled.\n\n"
                           f"Fix: create an App Password at {url} → App passwords "
                           f"and use that instead of your normal password.")
        elif graph_error_str:
            err_str = f"SMTP: {err_str} | Graph also unavailable (Mail.Send not granted)"
        return jsonify({"error": err_str}), 200


@bp.route("/api/send_report", methods=["POST"])
def send_report():
    """Build Excel and email it to the requested recipients.
    Tries Microsoft Graph API first, falls back to SMTP."""
    if not state.flagged_items:
        return jsonify({"error": "No results to send — run a scan first"}), 400

    data       = request.get_json() or {}
    smtp_cfg   = _load_smtp_config()
    recipients = data.get("recipients", []) or smtp_cfg.get("recipients", [])
    if isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.replace(";", ",").split(",") if r.strip()]
    if data.get("smtp"):
        smtp_cfg = {**smtp_cfg, **data["smtp"]}
    if not recipients:
        return jsonify({"error": "No recipients specified"}), 400

    try:
        xl_bytes, fname = _build_excel_bytes()
    except Exception as e:
        return jsonify({"error": f"Excel build failed: {e}"}), 500

    import datetime as _dt
    subject   = f"GDPR Scanner — scan report {_dt.datetime.now().strftime('%Y-%m-%d')}"
    body_html = (
        "<html><body style='font-family:Arial,sans-serif;color:#333;padding:24px'>"
        "<h2 style='color:#1F3864'>\u2601\ufe0f GDPR Scanner \u2014 scan report</h2>"
        f"<p>Please find the latest scan report attached ({fname}).</p>"
        f"<p style='color:#888;font-size:12px'>Generated: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>"
        f"Items flagged: {len(state.flagged_items)}</p>"
        "</body></html>"
    )

    # Try Graph API first
    if state.connector and state.connector.is_authenticated():
        try:
            _send_email_graph(subject, body_html, recipients,
                              attachment_bytes=xl_bytes, attachment_name=fname)
            return jsonify({"status": "sent", "method": "graph",
                            "recipients": recipients, "filename": fname})
        except Exception as graph_err:
            graph_err_str = str(graph_err)
            if "403" in graph_err_str or "Forbidden" in graph_err_str \
                    or "Mail.Send" in graph_err_str or "insufficient" in graph_err_str.lower():
                return jsonify({"error": (
                    "Mail.Send permission not granted on the Azure app registration. "
                    "Go to Azure AD → App registrations → [your app] → API permissions → "
                    "Add → Microsoft Graph → Mail.Send → Grant admin consent."
                )}), 500

    # Fall back to SMTP
    try:
        _send_report_email(xl_bytes, fname, smtp_cfg, recipients)
        return jsonify({"status": "sent", "method": "smtp",
                        "recipients": recipients, "filename": fname})
    except Exception as e:
        err = str(e)
        _h2 = smtp_cfg.get("host", "").lower()
        _p2 = int(smtp_cfg.get("port", 587))
        _corp_m365_2   = "office365" in _h2 or "microsoft" in _h2
        _personal_ms_2 = not _corp_m365_2 and any(s in _h2 for s in ("outlook", "live", "hotmail"))
        _gmail_2       = "gmail" in _h2 or "smtp.google" in _h2
        _auth_err_2    = "5.7.57" in err or "530" in err or "535" in err or \
                         "534" in err or "not authenticated" in err.lower()
        _conn_err_2    = "nodename nor servname" in err or "Name or service not known" in err or \
                         "getaddrinfo" in err or "Connection refused" in err or \
                         "Errno 8" in err or "Errno 111" in err or "Errno 61" in err or \
                         "timed out" in err.lower()
        if _conn_err_2:
            err = (f"Could not connect to SMTP server \"{_h2}\" on port {_p2}. "
                   f"Check that the hostname and port are correct.")
        elif _corp_m365_2 and _auth_err_2:
            err = (f"{err}\n\nTip: Enable SMTP AUTH for this mailbox in the Microsoft 365 admin centre, "
                   "or connect to M365 first so the scanner can send via Microsoft Graph instead.")
        elif (_personal_ms_2 or _gmail_2) and _auth_err_2:
            if _gmail_2:
                _uname2 = smtp_cfg.get("username", "").lower()
                _gws2   = "@gmail.com" not in _uname2 and "@googlemail.com" not in _uname2
                if _gws2:
                    err = ("Google Workspace SMTP authentication failed.\n\n"
                           "Your account uses a custom domain via Google Workspace. "
                           "SMTP access is controlled by your organisation's Google Workspace admin, not your personal account settings.\n\n"
                           "Ask your Google Workspace admin to:\n"
                           "  • Enable 2-Step Verification for your account (required for App Passwords)\n"
                           "  • Allow users to manage their own App Passwords (Admin console → Security → 2-Step Verification)\n"
                           "  • Or configure SMTP relay: Admin console → Apps → Google Workspace → Gmail → Routing → SMTP relay service\n\n"
                           "If App Passwords are available for your account, generate one at "
                           "myaccount.google.com → Security → 2-Step Verification → App passwords "
                           "and use it instead of your normal password.")
                else:
                    err = ("Gmail SMTP authentication failed.\n\n"
                           "Google requires an App Password for SMTP — your normal password will not work.\n\n"
                           "If you are already using an App Password, check:\n"
                           "  • No spaces — the 16-character code must be entered without spaces\n"
                           "  • The App Password has not been revoked — generate a new one at "
                           "myaccount.google.com → Security → 2-Step Verification → App passwords\n"
                           "  • The correct username (your full Gmail address, e.g. you@gmail.com)\n"
                           "  • Port 587 with STARTTLS, or port 465 with SSL")
            else:
                url2 = "account.microsoft.com/security"
                err = (f"Authentication failed — Microsoft blocks regular passwords for SMTP when MFA is enabled.\n\n"
                       f"Fix: create an App Password at {url2} → App passwords "
                       f"and use that instead of your normal password.")
        return jsonify({"error": err}), 500
