"""Fill a Starters Labo–style ONTVANGSTEN paper page from a Shopify sync plan.

Draws a blank grid matching the official dagontvangstenboek layout (A4 landscape),
then overlays month values. Output is a copy-aid for the numbered physical book —
not a substitute for the paper register.
"""

from __future__ import annotations

import json
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from reportlab.lib.colors import Color, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ASSETS = Path(__file__).resolve().parent.parent / "assets"
DEFAULT_LAYOUT = ASSETS / "paper_layout.json"
DEFAULT_TEMPLATE = ASSETS / "dagontvangstenboek-template.pdf"

DUTCH_MONTHS = (
    "",
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)


def load_layout(path: Path | None = None) -> dict:
    p = path or DEFAULT_LAYOUT
    return json.loads(p.read_text(encoding="utf-8"))


def fmt_eur(value: Decimal | str | float) -> str:
    d = Decimal(str(value or "0")).quantize(Decimal("0.01"))
    return f"{d}".replace(".", ",")


def _color(rgb: list[float]) -> Color:
    return Color(rgb[0], rgb[1], rgb[2])


def _register_fonts() -> tuple[str, str]:
    """Prefer Helvetica; try a narrow system font for long omschrijvingen."""
    regular, bold = "Helvetica", "Helvetica-Bold"
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Narrow.ttf",
        "/Library/Fonts/Arial Narrow.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            try:
                pdfmetrics.registerFont(TTFont("ArialNarrow", path))
                return "ArialNarrow", bold
            except Exception:
                pass
    return regular, bold


def table_bottom(layout: dict) -> float:
    t = layout["table"]
    return t["top"] - t["header_height"] - t["row_count"] * t["row_height"]


def draw_blank_form(c: canvas.Canvas, layout: dict) -> None:
    """Draw the empty ONTVANGSTEN grid (no daily values)."""
    ink = _color(layout["colors"]["ink"])
    grid = _color(layout["colors"]["grid"])
    fill_h = _color(layout["colors"]["fill_header"])
    font = layout["font"]
    hdr = layout["header"]
    table = layout["table"]
    cols = table["columns"]
    left = table["left"]
    right = table["right"]
    top = table["top"]
    hh = table["header_height"]
    rh = table["row_height"]
    n = table["row_count"]
    bottom = table_bottom(layout)

    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", font["title_size"])
    c.drawString(hdr["title_xy"][0], hdr["title_xy"][1], "ONTVANGSTEN")
    c.setFont("Helvetica", font["label_size"] + 1)
    c.drawString(hdr["page_no_xy"][0], hdr["page_no_xy"][1], "N°")
    c.line(hdr["page_no_xy"][0] + 14, hdr["page_no_xy"][1] - 1, right, hdr["page_no_xy"][1] - 1)

    c.setFont("Helvetica", font["label_size"])
    c.drawString(hdr["maand_label_xy"][0], hdr["maand_label_xy"][1], "MAAND")
    c.line(hdr["maand_value_xy"][0], hdr["maand_value_xy"][1] - 1, 300, hdr["maand_value_xy"][1] - 1)
    c.drawString(hdr["btw_label_xy"][0], hdr["btw_label_xy"][1], "B.T.W. Nr.")
    # Long enough for BTW + (dossiernr)
    c.line(hdr["btw_value_xy"][0], hdr["btw_value_xy"][1] - 1, 720, hdr["btw_value_xy"][1] - 1)
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(hdr["euro_xy"][0], hdr["euro_xy"][1], "€")

    # Header band
    c.setFillColor(fill_h)
    c.rect(left, top - hh, right - left, hh, fill=1, stroke=0)
    c.setStrokeColor(grid)
    c.setLineWidth(0.8)
    c.rect(left, bottom, right - left, top - bottom, fill=0, stroke=1)

    # Vertical column lines
    for key in ("omschrijving", "totalen", "v0", "v6", "v12", "v21"):
        x = cols[key]["x"]
        c.line(x, bottom, x, top)

    # Header separator
    c.line(left, top - hh, right, top - hh)
    # Sub-header line under BEDRAGEN INCLUSIEF B.T.W. spanning VAT cols
    vat_left = cols["v0"]["x"]
    c.line(vat_left, top - hh / 2, right, top - hh / 2)

    # Day row lines
    for i in range(1, n + 1):
        y = top - hh - i * rh
        c.line(left, y, right, y)

    # Column labels
    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", font["label_size"])
    mid_y = top - hh / 2 - 3
    c.drawCentredString(cols["datum"]["x"] + cols["datum"]["w"] / 2, mid_y, "DATUM")
    c.drawCentredString(
        cols["omschrijving"]["x"] + cols["omschrijving"]["w"] / 2, mid_y, "OMSCHRIJVING"
    )
    c.drawCentredString(cols["totalen"]["x"] + cols["totalen"]["w"] / 2, mid_y, "TOTALEN")

    c.setFont("Helvetica-Bold", font["label_size"] - 0.5)
    c.drawCentredString(
        (vat_left + right) / 2,
        top - hh / 4 - 2,
        "BEDRAGEN INCLUSIEF B.T.W.",
    )
    c.setFont("Helvetica-Bold", font["label_size"])
    for key, label in (("v0", "0%"), ("v6", "6%"), ("v12", "12%"), ("v21", "21%")):
        cx = cols[key]["x"] + cols[key]["w"] / 2
        c.drawCentredString(cx, top - 3 * hh / 4 - 2, label)

    # Pre-printed day numbers
    c.setFont("Helvetica", font["cell_size"])
    for day in range(1, n + 1):
        y = top - hh - day * rh + 3
        c.drawCentredString(cols["datum"]["x"] + cols["datum"]["w"] / 2, y, f"{day:02d}")

    # Footer labels (left of amount columns)
    foot = layout["footer"]
    c.setFont("Helvetica", font["label_size"] - 0.5)
    labels = [
        (foot["row1_y_offset"], "MAANDTOTAAL INCLUSIEF B.T.W."),
        (foot["row2_y_offset"], "MAANDTOTAAL EXCLUSIEF B.T.W."),
        (foot["row3_y_offset"], "MAANDTOTAAL B.T.W."),
    ]
    for offset, text in labels:
        y = bottom - offset
        c.drawString(foot["labels_x"], y, text)
        c.setStrokeColor(grid)
        c.line(cols["totalen"]["x"], y - 2, right, y - 2)
        c.setStrokeColor(grid)

    # Quarter recap box (left blank — fill by hand)
    box = foot["recap_box"]
    c.setStrokeColor(grid)
    c.setLineWidth(0.9)
    c.rect(box["x"], box["y"], box["w"], box["h"], fill=0, stroke=1)
    c.setFillColor(ink)
    c.setFont("Helvetica", 6.5)
    c.drawString(
        box["x"] + 4,
        box["y"] + box["h"] - 12,
        "RECAPITULATIE DER ONTVANGSTEN EXCL. B.T.W. KWARTAAL",
    )
    c.drawString(box["x"] + 4, box["y"] + 10, "TOTAAL B.T.W. KWARTAAL")

    # Starters Labo mark (bottom-right of form area)
    c.setFillColor(Color(0.1, 0.1, 0.1))
    c.rect(right - 95, 32, 55, 14, fill=1, stroke=0)
    c.setFillColor(Color(0.55, 0.85, 0.2))
    c.rect(right - 40, 32, 40, 14, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(right - 67, 36, "STARTERS")
    c.setFillColor(Color(0.1, 0.1, 0.1))
    c.drawCentredString(right - 20, 36, "LABO")


def draw_values(
    c: canvas.Canvas,
    layout: dict,
    *,
    maand: str,
    btw_nr: str,
    rows: list[dict],
    totals: dict[str, Decimal],
    fee_note: str = "",
    page_no: int | None = None,
) -> None:
    """Overlay filled fields onto the blank form (same page coordinates)."""
    ink = _color(layout["colors"]["ink"])
    font = layout["font"]
    hdr = layout["header"]
    table = layout["table"]
    cols = table["columns"]
    top = table["top"]
    hh = table["header_height"]
    rh = table["row_height"]
    bottom = table_bottom(layout)
    cell_font, _ = _register_fonts()

    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", font["label_size"] + 2)
    c.drawString(hdr["maand_value_xy"][0], hdr["maand_value_xy"][1], maand)
    if btw_nr:
        c.setFont("Helvetica-Bold", font["label_size"] + 1)
        c.drawString(hdr["btw_value_xy"][0], hdr["btw_value_xy"][1], btw_nr)
    if page_no is not None:
        c.setFont("Helvetica-Bold", font["label_size"] + 3)
        # After the printed "N°" label
        c.drawString(hdr["page_no_xy"][0] + 18, hdr["page_no_xy"][1], str(int(page_no)))

    def amount_cell(col_key: str, y: float, value: Decimal, force_zero: bool = False) -> None:
        if value == 0 and not force_zero:
            return
        text = fmt_eur(value) if value != 0 or not force_zero else "0,0"
        if value == 0 and force_zero:
            text = "0,0"
        x_right = cols[col_key]["x"] + cols[col_key]["w"] - 4
        c.setFont("Helvetica", font["amount_size"])
        c.drawRightString(x_right, y, text)

    for row in rows:
        day = int(row["day"])
        if day < 1 or day > table["row_count"]:
            continue
        y = top - hh - day * rh + 3
        desc = (row.get("description") or "").strip()
        total = Decimal(str(row.get("total_incl") or 0))
        if desc:
            c.setFont(cell_font, font["cell_size"])
            max_w = cols["omschrijving"]["w"] - 6
            # Truncate long descriptions so they stay in the cell
            while desc and c.stringWidth(desc, cell_font, font["cell_size"]) > max_w:
                desc = desc[:-1]
            if desc != (row.get("description") or "").strip():
                desc = desc[:-1] + "…" if len(desc) > 1 else desc
            c.drawString(cols["omschrijving"]["x"] + 3, y, desc)
        # Quiet days: 0,0 in TOTALEN (matches FAQ voorbeeld)
        amount_cell("totalen", y, total, force_zero=True)
        for key, col in (("v0", "v0"), ("v6", "v6"), ("v12", "v12"), ("v21", "v21")):
            amount_cell(col, y, Decimal(str(row.get(key) or 0)))

    foot = layout["footer"]
    c.setFont("Helvetica", font["amount_size"])

    def footer_amounts(y: float, totalen: Decimal, v0: Decimal, v6: Decimal, v12: Decimal, v21: Decimal) -> None:
        for col_key, val in (
            ("totalen", totalen),
            ("v0", v0),
            ("v6", v6),
            ("v12", v12),
            ("v21", v21),
        ):
            if val == 0 and col_key != "totalen":
                continue
            x_right = cols[col_key]["x"] + cols[col_key]["w"] - 4
            c.drawRightString(x_right, y, fmt_eur(val))

    # Incl. row: totals + VAT columns (incl. amounts)
    y1 = bottom - foot["row1_y_offset"]
    footer_amounts(
        y1,
        totals["incl"],
        totals.get("v0", Decimal("0")),
        totals.get("v6", Decimal("0")),
        totals.get("v12", Decimal("0")),
        totals.get("v21", Decimal("0")),
    )
    # Excl. / BTW rows: TOTALEN only (rate split of excl/tax not on form columns for footer)
    y2 = bottom - foot["row2_y_offset"]
    c.drawRightString(
        cols["totalen"]["x"] + cols["totalen"]["w"] - 4, y2, fmt_eur(totals["excl"])
    )
    y3 = bottom - foot["row3_y_offset"]
    c.drawRightString(
        cols["totalen"]["x"] + cols["totalen"]["w"] - 4, y3, fmt_eur(totals["tax"])
    )

    if fee_note:
        c.setFont("Helvetica", 6)
        c.setFillColor(Color(0.3, 0.3, 0.3))
        c.drawString(layout["table"]["left"], 18, fee_note)


def write_blank_template(dest: Path, layout_path: Path | None = None) -> Path:
    layout = load_layout(layout_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    page = layout["page"]
    c = canvas.Canvas(str(dest), pagesize=(page["width"], page["height"]))
    draw_blank_form(c, layout)
    c.showPage()
    c.save()
    return dest


def write_paper_pdf(
    plan: dict,
    dest: Path,
    *,
    rows: list[dict],
    totals: dict[str, Decimal],
    btw_nr: str = "",
    page_no: int | None = None,
    layout_path: Path | None = None,
    template_path: Path | None = None,
) -> Path:
    """Write filled paper dagontvangstenboek PDF.

    Draws a blank form (or uses an existing blank template) and overlays values.
    """
    from pypdf import PdfReader, PdfWriter

    layout = load_layout(layout_path)
    page = layout["page"]
    start = plan["period"]["start"]
    year, month, _ = start.split("-")
    maand = f"{DUTCH_MONTHS[int(month)]} {year}"

    fee_total = Decimal(str(plan.get("fee_total") or "0"))
    fee_note = ""
    if fee_total > 0:
        fee_note = (
            f"Shopify Payments fees {fmt_eur(fee_total)} EUR — niet in dit boek; "
            "aparte onkostennota."
        )

    # Overlay layer (transparent page with text only)
    overlay_buf = BytesIO()
    oc = canvas.Canvas(overlay_buf, pagesize=(page["width"], page["height"]))
    # If no blank template yet, draw form + values on one canvas
    tpl = template_path or DEFAULT_TEMPLATE
    if not tpl.is_file():
        draw_blank_form(oc, layout)
        draw_values(
            oc,
            layout,
            maand=maand,
            btw_nr=btw_nr,
            rows=rows,
            totals=totals,
            fee_note=fee_note,
            page_no=page_no,
        )
        oc.showPage()
        oc.save()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(overlay_buf.getvalue())
        return dest

    draw_values(
        oc,
        layout,
        maand=maand,
        btw_nr=btw_nr,
        rows=rows,
        totals=totals,
        fee_note=fee_note,
        page_no=page_no,
    )
    oc.showPage()
    oc.save()
    overlay_buf.seek(0)

    base = PdfReader(str(tpl))
    over = PdfReader(overlay_buf)
    writer = PdfWriter()
    page0 = base.pages[0]
    page0.merge_page(over.pages[0])
    writer.add_page(page0)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as fh:
        writer.write(fh)
    return dest


def ensure_blank_template(layout_path: Path | None = None) -> Path:
    """Create assets/dagontvangstenboek-template.pdf if missing."""
    if DEFAULT_TEMPLATE.is_file():
        return DEFAULT_TEMPLATE
    return write_blank_template(DEFAULT_TEMPLATE, layout_path)


if __name__ == "__main__":
    ensure_blank_template()
    print(f"Wrote blank template: {DEFAULT_TEMPLATE}")
