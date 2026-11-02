"""Markdown -> PDF for Bot outputs (shift summaries, incident reports)."""
from __future__ import annotations

import markdown
from fpdf import FPDF

# fpdf2's core fonts are Latin-1; map the typographic characters Bots commonly emit.
_ASCII = str.maketrans({
    "—": "-", "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "→": "->", "←": "<-",
    "↑": "^", "↓": "v", "✓": "[x]", "✗": "[ ]", "×": "x", "•": "-", "≈": "~", "°": " deg", "·": "-",
})


def _latin1(text: str) -> str:
    return text.translate(_ASCII).encode("latin-1", "replace").decode("latin-1")


def to_pdf(title: str, body_md: str, footer: str) -> bytes:
    html = markdown.markdown(_latin1(body_md), extensions=["tables", "sane_lists"])
    # fpdf's HTML renderer has no checkbox glyphs or code styling.
    html = html.replace("[ ]", "[  ]").replace("<code>", "<font face='courier'>").replace("</code>", "</font>")
    pdf = FPDF(format="Letter")
    pdf.set_title(_latin1(title))
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_font("helvetica", size=8)
    pdf.set_text_color(180, 90, 0)
    pdf.cell(0, 5, "ADVISORY PROTOTYPE - NOT FOR OPERATIONAL USE", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", size=10)
    pdf.write_html(html, table_line_separators=True)
    pdf.ln(4)
    pdf.set_font("helvetica", size=7)
    pdf.set_text_color(110, 110, 110)
    pdf.multi_cell(0, 4, _latin1(footer))
    return bytes(pdf.output())
