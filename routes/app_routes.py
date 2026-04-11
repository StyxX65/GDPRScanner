"""
App-level routes: about, language, version
"""
from __future__ import annotations
import sys
from flask import Blueprint, Response, jsonify, request
from pathlib import Path
from routes import state
from app_config import _set_lang_override, _load_lang_forced

bp = Blueprint("app_routes", __name__)

_APP_VERSION = (Path(__file__).parent.parent / "VERSION").read_text().strip()
_LANG_DIR    = (Path(sys._MEIPASS) if getattr(sys, "frozen", False)
                else Path(__file__).parent.parent) / "lang"


@bp.route("/api/about")
def about_info():
    import platform
    info = {"python": platform.python_version(), "app": _APP_VERSION}
    try:
        import msal as _msal
        info["msal"] = getattr(_msal, "__version__", "installed")
    except ImportError:
        info["msal"] = "not installed"
    try:
        import requests as _req
        info["requests"] = getattr(_req, "__version__", "installed")
    except ImportError:
        info["requests"] = "not installed"
    try:
        import openpyxl as _xl
        info["openpyxl"] = getattr(_xl, "__version__", "installed")
    except ImportError:
        info["openpyxl"] = "not installed"
    return jsonify(info)


@bp.route("/api/langs")
def get_langs():
    display_names = {
        "da": "Dansk", "en": "English", "de": "Deutsch",
        "fr": "Français", "nl": "Nederlands", "sv": "Svenska",
        "no": "Norsk", "fi": "Suomi", "es": "Español",
        "it": "Italiano", "pl": "Polski", "pt": "Português",
    }
    langs = []
    if _LANG_DIR.exists():
        seen = set()
        for f in sorted(list(_LANG_DIR.glob("*.json")) + list(_LANG_DIR.glob("*.lang"))):
            code = f.stem
            if code not in seen:
                seen.add(code)
                langs.append({"code": code, "name": display_names.get(code, code.upper())})
        langs.sort(key=lambda x: x["code"])
    return jsonify({"langs": langs, "current": state.LANG.get("_lang_code", "en")})


@bp.route("/api/set_lang", methods=["POST"])
def set_lang():
    data = request.get_json(force=True) or {}
    code = str(data.get("lang", "en")).strip().lower()[:10]
    _set_lang_override(code)
    state.LANG = _load_lang_forced(code)
    return jsonify({"status": "ok", "lang": code, "translations": state.LANG})


@bp.route("/api/lang")
def get_lang_json():
    """Return the current language translations as JSON."""
    return jsonify(state.LANG)


@bp.route("/manual")
def manual():
    """Serve the user manual as a styled, printable HTML page.
    Respects ?lang=da|en; falls back to the current UI language."""
    import sys as _sys

    lang = request.args.get("lang", "").strip().lower() or \
           state.LANG.get("_lang_code", "da")
    lang = lang if lang in ("da", "en") else "da"

    _here = Path(_sys._MEIPASS) if getattr(_sys, "frozen", False) \
            else Path(__file__).parent.parent
    fname = "MANUAL-DA.md" if lang == "da" else "MANUAL-EN.md"
    md_path = _here / "docs" / "manuals" / fname
    if not md_path.exists():
        return f"Manual file not found: {fname}", 404

    md_text = md_path.read_text(encoding="utf-8")
    body_html = _md_to_html(md_text)

    title = "GDPR Scanner — Brugermanual" if lang == "da" \
            else "GDPR Scanner — User Manual"
    print_label = "Udskriv" if lang == "da" else "Print"
    other_lang = "en" if lang == "da" else "da"
    other_label = "English" if lang == "da" else "Dansk"

    page = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --text:    #1a1a1a;
    --muted:   #555;
    --border:  #ddd;
    --accent:  #0060b0;
    --bg:      #fff;
    --surface: #f6f8fa;
    --code-bg: #f0f0f0;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 15px;
    line-height: 1.7;
    color: var(--text);
    background: var(--bg);
    max-width: 860px;
    margin: 0 auto;
    padding: 32px 24px 64px;
  }}
  h1 {{ font-size: 1.9em; margin: 0 0 4px; color: var(--text); }}
  h2 {{ font-size: 1.35em; margin: 2.2em 0 .6em; padding-bottom: .3em;
        border-bottom: 2px solid var(--border); color: var(--text); }}
  h3 {{ font-size: 1.1em; margin: 1.6em 0 .4em; color: var(--text); }}
  h4 {{ font-size: 1em; margin: 1.2em 0 .3em; color: var(--muted); }}
  p  {{ margin: .6em 0; }}
  a  {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  strong {{ font-weight: 600; }}
  em {{ font-style: italic; }}
  hr {{ border: none; border-top: 1px solid var(--border); margin: 1.8em 0; }}
  blockquote {{
    border-left: 3px solid var(--accent);
    margin: .8em 0;
    padding: .4em 1em;
    background: var(--surface);
    border-radius: 0 4px 4px 0;
    color: var(--muted);
  }}
  code {{
    font-family: "SF Mono", Consolas, "Liberation Mono", monospace;
    font-size: .88em;
    background: var(--code-bg);
    padding: 1px 5px;
    border-radius: 3px;
  }}
  pre {{
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 14px 16px;
    overflow-x: auto;
    margin: .8em 0;
    font-size: .85em;
    line-height: 1.5;
  }}
  pre code {{ background: none; padding: 0; font-size: inherit; }}
  ul, ol {{ margin: .5em 0 .5em 1.6em; }}
  li {{ margin: .25em 0; }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: .8em 0;
    font-size: .93em;
  }}
  th, td {{
    border: 1px solid var(--border);
    padding: 7px 12px;
    text-align: left;
    vertical-align: top;
  }}
  th {{
    background: var(--surface);
    font-weight: 600;
  }}
  tr:nth-child(even) td {{ background: #fafafa; }}

  /* ── Top toolbar ── */
  .manual-toolbar {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 28px;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
  }}
  .manual-toolbar .spacer {{ flex: 1; }}
  .toolbar-btn {{
    font-size: 13px;
    padding: 5px 14px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
    text-decoration: none;
    display: inline-block;
  }}
  .toolbar-btn:hover {{ background: var(--border); }}
  .toolbar-btn.primary {{
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }}
  .toolbar-btn.primary:hover {{ opacity: .88; }}

  /* ── Table of contents ── */
  .toc {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    margin: 1.2em 0 2em;
    font-size: .93em;
  }}
  .toc ol {{ margin: .3em 0 0 1.2em; }}
  .toc li {{ margin: .3em 0; }}

  /* ── Print ── */
  @media print {{
    .manual-toolbar {{ display: none !important; }}
    body {{ max-width: 100%; padding: 0; font-size: 12pt; }}
    h2 {{ page-break-before: always; }}
    h2:first-of-type {{ page-break-before: avoid; }}
    pre, blockquote, table {{ page-break-inside: avoid; }}
    a {{ color: var(--text); text-decoration: none; }}
    a[href^="http"]::after {{ content: " (" attr(href) ")"; font-size: .8em; color: var(--muted); }}
    tr:nth-child(even) td {{ background: #f5f5f5; }}
  }}
</style>
</head>
<body>
<div class="manual-toolbar">
  <strong style="font-size:14px">{title}</strong>
  <span class="spacer"></span>
  <a class="toolbar-btn" href="/manual?lang={other_lang}">{other_label}</a>
  <button class="toolbar-btn primary" onclick="window.print()">🖨 {print_label}</button>
</div>
{body_html}
</body>
</html>"""
    return Response(page, mimetype="text/html")


def _md_to_html(md: str) -> str:
    """Lightweight Markdown → HTML converter (no external dependencies).
    Handles headings, tables, lists, blockquotes, code blocks, bold/italic,
    inline code, links, and horizontal rules."""
    import re, html as _html

    def inline(text: str) -> str:
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*',     r'<em>\1</em>',         text)
        text = re.sub(r'`(.+?)`',       lambda m: '<code>' + _html.escape(m.group(1)) + '</code>', text)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
        return text

    def make_anchor(text: str) -> str:
        return re.sub(r'[^\w\s-]', '', text.lower()).strip().replace(' ', '-')

    result   = []
    lines    = md.splitlines()
    i        = 0

    in_code   = False
    code_buf  = []
    in_list   = False
    list_type = None
    list_buf  = []
    in_table  = False
    tbl_buf   = []

    def flush_list():
        nonlocal in_list, list_type, list_buf
        if not in_list:
            return
        tag = list_type
        result.append(f'<{tag}>')
        for item in list_buf:
            result.append(f'  <li>{inline(item)}</li>')
        result.append(f'</{tag}>')
        in_list = False; list_buf = []; list_type = None

    def flush_table():
        nonlocal in_table, tbl_buf
        if not in_table or len(tbl_buf) < 2:
            in_table = False; tbl_buf = []; return
        heads = [c.strip() for c in tbl_buf[0].strip('|').split('|')]
        result.append('<table>')
        result.append('<thead><tr>' + ''.join(f'<th>{inline(h)}</th>' for h in heads) + '</tr></thead>')
        result.append('<tbody>')
        for row in tbl_buf[2:]:
            cols = [c.strip() for c in row.strip('|').split('|')]
            result.append('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in cols) + '</tr>')
        result.append('</tbody></table>')
        in_table = False; tbl_buf = []

    while i < len(lines):
        line = lines[i]
        i += 1

        # ── fenced code block ──────────────────────────────────────────
        if line.startswith('```'):
            if not in_code:
                flush_list(); flush_table()
                in_code = True; code_buf = []
            else:
                in_code = False
                escaped = _html.escape('\n'.join(code_buf))
                result.append(f'<pre><code>{escaped}</code></pre>')
            continue
        if in_code:
            code_buf.append(line)
            continue

        # ── table row ─────────────────────────────────────────────────
        if line.strip().startswith('|') and '|' in line[1:]:
            flush_list()
            in_table = True
            tbl_buf.append(line)
            continue
        elif in_table:
            flush_table()

        # ── blank line ────────────────────────────────────────────────
        if not line.strip():
            flush_list()
            result.append('')
            continue

        # ── heading ───────────────────────────────────────────────────
        m = re.match(r'^(#{1,6})\s+(.+)$', line)
        if m:
            flush_list()
            lvl  = len(m.group(1))
            text = m.group(2)
            anc  = make_anchor(text)
            result.append(f'<h{lvl} id="{anc}">{inline(text)}</h{lvl}>')
            continue

        # ── horizontal rule ───────────────────────────────────────────
        if re.match(r'^-{3,}$', line.strip()):
            flush_list()
            result.append('<hr>')
            continue

        # ── blockquote ────────────────────────────────────────────────
        if line.startswith('> '):
            flush_list()
            result.append(f'<blockquote>{inline(line[2:])}</blockquote>')
            continue

        # ── unordered list ────────────────────────────────────────────
        m = re.match(r'^- (.+)$', line)
        if m:
            if not in_list or list_type != 'ul':
                flush_list()
                in_list = True; list_type = 'ul'; list_buf = []
            list_buf.append(m.group(1))
            continue

        # ── ordered list ─────────────────────────────────────────────
        m = re.match(r'^\d+\. (.+)$', line)
        if m:
            if not in_list or list_type != 'ol':
                flush_list()
                in_list = True; list_type = 'ol'; list_buf = []
            list_buf.append(m.group(1))
            continue

        # ── paragraph ────────────────────────────────────────────────
        flush_list()
        result.append(f'<p>{inline(line)}</p>')

    flush_list()
    flush_table()
    return '\n'.join(result)


