"""
Generate binary fixture files for the local-file GDPR scan test suite.

Run from repo root:
    source venv/bin/activate
    python tests/fixtures/local_files/generate_fixtures.py
"""
from pathlib import Path
import sys

HERE = Path(__file__).parent

def _require(pkg):
    try:
        return __import__(pkg)
    except ImportError:
        print(f"Missing: {pkg}  →  pip install {pkg}", file=sys.stderr)
        sys.exit(1)

openpyxl = _require("openpyxl")
docx = _require("docx")

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH


# ── 09_cpr_in_docx.docx ───────────────────────────────────────────────────────
def make_docx():
    doc = Document()

    doc.add_heading("Elevjournal — Gudenaaskolen", level=1)

    p = doc.add_paragraph()
    p.add_run("Dette dokument indeholder personoplysninger og er fortroligt.")
    p.runs[0].italic = True

    doc.add_heading("Elevoplysninger", level=2)
    # Use labelled paragraphs so CPR values are always preceded by ": " —
    # avoids the _CPR_PREFIX_NOISE guard that fires when table-cell runs are
    # concatenated without a separator.
    fields = [
        ("Navn",       "Magnus Lund Eriksen"),
        ("CPR-nummer", "010172-1019"),
        ("Klasse",     "8B"),
        ("Adresse",    "Egevej 3, 8680 Ry"),
        ("Telefon",    "+45 40 12 34 56"),
        ("E-mail",     "magnus.eriksen@elev.gudenaaskolen.dk"),
    ]
    for label, value in fields:
        p = doc.add_paragraph()
        run_label = p.add_run(f"{label}: ")
        run_label.bold = True
        p.add_run(value + " ")

    doc.add_heading("Forældrekontakt", level=2)
    doc.add_paragraph(
        "Forældrene er orienteret om elevens situation den 15. marts 2026. "
        "Begge forældre deltog i mødet. Næste opfølgning er planlagt til "
        "maj 2026."
    )

    doc.add_heading("Anden elev — tabel", level=2)
    doc.add_paragraph(
        "Nedenstående tabel viser en anden elev, der deler klasse med Magnus."
    )
    for label, value in [
        ("Navn",         "Nora Bjerrum Nielsen"),
        ("Personnummer", "280490-0120"),
        ("Klasse",       "8B"),
    ]:
        p = doc.add_paragraph()
        p.add_run(f"{label}: ").bold = True
        p.add_run(value + " ")

    doc.add_heading("Sagsbehandlernote", level=2)
    doc.add_paragraph(
        "Sagsbehandler: M. Andersen\n"
        "Dato: 20. april 2026\n"
        "Der er ikke fundet grundlag for yderligere foranstaltninger."
    )

    out = HERE / "09_cpr_in_docx.docx"
    doc.save(str(out))
    print(f"Written: {out.name}")


# ── 13_cpr_in_xlsx.xlsx ───────────────────────────────────────────────────────
def make_xlsx():
    wb = Workbook()

    # Sheet 1: Elevliste
    ws1 = wb.active
    ws1.title = "Elevliste"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2B5F9E")

    headers = ["Klasse", "Navn", "CPR-nummer", "Adresse", "Forælder tlf", "Bemærkninger"]
    for col, h in enumerate(headers, 1):
        cell = ws1.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    students = [
        ("7A", "Magnus Lund Eriksen",   "010172-1019", "Egevej 3, 8680 Ry",        "+45 40 12 34 56", ""),
        ("7A", "Nora Bjerrum Nielsen",  "280490-0120", "Møllevej 11, 8680 Ry",     "+45 50 23 45 67", "Brillebærer"),
        ("7A", "Oliver Skov Madsen",    "250372-0100", "Kirkegade 2, 8660 Skanderborg", "+45 60 34 56 78", ""),
        ("7B", "Rasmus Dal Kristensen", "150365-1102", "Rosenvej 5, 8680 Ry",       "+45 21 56 78 90", ""),
        ("7B", "Sofie Holm Thomsen",    "111111-1010", "Birkevej 22, 8660 Skanderborg", "+45 31 67 89 01", "Allergi: nødder"),
        ("7B", "Emil Sand Jensen",      "010107-4102", "Hybenvej 7, 8680 Ry",       "+45 41 78 90 12", ""),
    ]
    for row_i, row_data in enumerate(students, 2):
        for col_i, val in enumerate(row_data, 1):
            ws1.cell(row=row_i, column=col_i, value=val)

    for col in ws1.columns:
        max_len = max(len(str(c.value or "")) for c in col)
        ws1.column_dimensions[col[0].column_letter].width = max_len + 4

    # Sheet 2: Medarbejdere
    ws2 = wb.create_sheet("Medarbejdere")
    emp_headers = ["ID", "Navn", "Personnummer", "Afdeling", "E-mail"]
    for col, h in enumerate(emp_headers, 1):
        cell = ws2.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    employees = [
        ("EMP-001", "Christian Bøgh Hansen",  "150365-1102", "Ledelse",        "c.hansen@gudenaaskolen.dk"),
        ("EMP-002", "Mette Dahl Andersen",     "280490-0120", "Administration", "m.andersen@gudenaaskolen.dk"),
        ("EMP-003", "Søren Lykke Jakobsen",    "010172-1019", "Pædagogik",      "s.jakobsen@gudenaaskolen.dk"),
    ]
    for row_i, row_data in enumerate(employees, 2):
        for col_i, val in enumerate(row_data, 1):
            ws2.cell(row=row_i, column=col_i, value=val)

    for col in ws2.columns:
        max_len = max(len(str(c.value or "")) for c in col)
        ws2.column_dimensions[col[0].column_letter].width = max_len + 4

    out = HERE / "13_cpr_in_xlsx.xlsx"
    wb.save(str(out))
    print(f"Written: {out.name}")


if __name__ == "__main__":
    make_docx()
    make_xlsx()
    print("Done.")
