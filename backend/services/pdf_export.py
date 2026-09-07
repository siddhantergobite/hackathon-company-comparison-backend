"""
Casefile PDF — branded intelligence report matching the UI.

Exhibits: A brochure · B target · C pitch · D outreach · F AEO/GEO (if run)
"""
from __future__ import annotations

import html as html_lib
import io
import re
from datetime import datetime, timezone
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# Casefile UI tokens
INK = colors.HexColor("#1B2430")
PAPER = colors.HexColor("#F5F1E7")
TEAL = colors.HexColor("#2C5B57")
TEAL_SOFT = colors.HexColor("#DCE7E4")
AMBER = colors.HexColor("#B9752E")
AMBER_SOFT = colors.HexColor("#EFDFC4")
RED = colors.HexColor("#A2402B")
RULE = colors.HexColor("#D9D2BE")
TEXT = colors.HexColor("#241F1A")
MUTED = colors.HexColor("#6E6555")
CREAM = colors.HexColor("#EFEAE0")
WHITE = colors.white
SOFT_RED = colors.HexColor("#F4E4DC")
ROW_ALT = colors.HexColor("#FBF9F3")

PAGE_W, PAGE_H = A4
LEFT = 0.68 * inch
RIGHT = 0.68 * inch
CONTENT_W = PAGE_W - LEFT - RIGHT

_JUNK_INDUSTRY = re.compile(
    r"(?i)\b(edible fruit|fruit tree|malus|pome fruit|pomaceous|apple tree)\b"
)
_JUNK_COMPETITOR = re.compile(r"(?i)^competitor\s*\d")


def _val(field: Any) -> str:
    if isinstance(field, dict):
        return str(field.get("value", "") or "")
    if field is None:
        return ""
    return str(field).strip()


def _latin(text: Any) -> str:
    """Map common unicode to WinAnsi-safe characters for Helvetica/Times."""
    s = str(text or "")
    return (
        s.replace("→", "->")
        .replace("←", "<-")
        .replace("…", "...")
        .replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("–", "-")
        .replace("—", "-")
        .replace("•", "-")
    )


def _esc(text: Any) -> str:
    return (
        _latin(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _has(text: Any) -> bool:
    t = _val(text) if not isinstance(text, str) else text.strip()
    return bool(t) and t not in ("—", "-", "None", "n/a", "N/A")


def _point(obj: Any) -> str:
    if isinstance(obj, dict):
        return str(
            obj.get("point")
            or obj.get("value")
            or obj.get("item")
            or obj.get("name")
            or obj.get("role")
            or ""
        ).strip()
    return str(obj or "").strip()


def _risk_text(field: Any) -> str:
    if isinstance(field, str):
        return field
    if isinstance(field, dict):
        return str(field.get("risk") or field.get("value") or field.get("point") or "")
    if isinstance(field, list):
        parts = []
        for item in field:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                t = item.get("risk") or item.get("value") or item.get("point")
                if t:
                    parts.append(str(t))
        return "; ".join(parts)
    return str(field or "")


def _industry(co: dict) -> str:
    raw = _val(co.get("industry"))
    if not raw or _JUNK_INDUSTRY.search(raw):
        return ""
    return raw


def _valid_phone(num: str) -> bool:
    s = str(num or "").strip()
    if not s:
        return False
    digits = re.sub(r"\D", "", s)
    if len(digits) < 10:
        return False
    if re.match(r"^\d{5}\s*\(\d{3}\)", s):
        return False
    return True


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", (name or "report").strip()).strip("-").lower()
    return (s or "report")[:42]


def filename_for(brochure: dict, target: dict) -> str:
    meta = target.get("_meta") or {}
    target_name = meta.get("company_name") or (target.get("company_profile") or {}).get("name") or "target"
    return f"casefile-{_slug(str(target_name))}.pdf"


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "kicker": ParagraphStyle(
            "Kicker",
            fontName="Courier",
            fontSize=8,
            leading=11,
            textColor=AMBER,
            spaceAfter=4,
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle",
            fontName="Times-Bold",
            fontSize=26,
            leading=30,
            textColor=INK,
            spaceAfter=4,
        ),
        "cover_sub": ParagraphStyle(
            "CoverSub",
            fontName="Times-Roman",
            fontSize=13,
            leading=17,
            textColor=MUTED,
            spaceAfter=10,
        ),
        "h_exhibit": ParagraphStyle(
            "HExhibit",
            fontName="Times-Bold",
            fontSize=14,
            leading=18,
            textColor=INK,
        ),
        "h3": ParagraphStyle(
            "H3",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=TEAL,
            spaceBefore=10,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "Body",
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=TEXT,
            alignment=TA_LEFT,
        ),
        "body_sm": ParagraphStyle(
            "BodySm",
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=TEXT,
        ),
        "muted": ParagraphStyle(
            "Muted",
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=MUTED,
        ),
        "cite": ParagraphStyle(
            "Cite",
            fontName="Helvetica",
            fontSize=7.5,
            leading=10.5,
            textColor=TEAL,
            leftIndent=4,
        ),
        "chip_lbl": ParagraphStyle(
            "ChipLbl",
            fontName="Courier",
            fontSize=7,
            leading=9,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "chip_val": ParagraphStyle(
            "ChipVal",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=INK,
            alignment=TA_CENTER,
        ),
        "cell": ParagraphStyle(
            "Cell",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=TEXT,
        ),
        "cell_b": ParagraphStyle(
            "CellB",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=INK,
        ),
        "th": ParagraphStyle(
            "TH",
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=TEAL,
        ),
        "letter": ParagraphStyle(
            "Letter",
            fontName="Times-Roman",
            fontSize=10,
            leading=14.5,
            textColor=TEXT,
            spaceAfter=7,
        ),
        "center_muted": ParagraphStyle(
            "CenterMuted",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "right_muted": ParagraphStyle(
            "RightMuted",
            fontName="Courier",
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
            alignment=TA_RIGHT,
        ),
        "swot_h": ParagraphStyle(
            "SwotH",
            fontName="Courier-Bold",
            fontSize=8,
            leading=11,
            textColor=INK,
            spaceAfter=4,
        ),
        "swot_b": ParagraphStyle(
            "SwotB",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=TEXT,
        ),
        "fit_strong": ParagraphStyle(
            "FitStrong",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=TEAL,
        ),
        "fit_partial": ParagraphStyle(
            "FitPartial",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=AMBER,
        ),
        "fit_other": ParagraphStyle(
            "FitOther",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=MUTED,
        ),
    }


def _P(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text or "&nbsp;", style)


def _exhibit_banner(letter: str, title: str, S: dict) -> Table:
    left = _P(f'<font color="#B9752E"><b>EXHIBIT {letter}</b></font>', S["kicker"])
    right = _P(title, S["h_exhibit"])
    t = Table([[left, right]], colWidths=[1.28 * inch, CONTENT_W - 1.28 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("LINEBEFORE", (0, 0), (0, 0), 3.2, AMBER),
        ("LINEBELOW", (0, 0), (-1, -1), 1.4, TEAL),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 10),
        ("LEFTPADDING", (1, 0), (1, 0), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _kpi_row(pairs: list[tuple[str, str]], S: dict) -> Optional[Table]:
    items = [(l, v) for l, v in pairs if _has(v)]
    if not items:
        return None
    n = len(items)
    w = CONTENT_W / n
    cells = [[
        [_P(_esc(lbl).upper(), S["chip_lbl"]), _P(_esc(val), S["chip_val"])]
        for lbl, val in items
    ]]
    t = Table(cells, colWidths=[w] * n)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _styled_table(
    header: list[str],
    rows: list[list[Any]],
    col_widths: list[float],
    S: dict,
) -> Optional[Table]:
    if not rows:
        return None
    data = [[_P(f'<font color="#EFEAE0"><b>{_esc(h).upper()}</b></font>', S["th"]) for h in header]]
    for row in rows:
        data.append(row)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("BACKGROUND", (0, 1), (-1, -1), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, ROW_ALT]),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _bullets(items: list[str], S: dict, limit: int = 8) -> list:
    out = []
    for raw in items[:limit]:
        t = _point(raw) if not isinstance(raw, str) else raw.strip()
        if t:
            out.append(_P(f"• {_esc(t)}", S["body"]))
    return out


def _link(url: str, label: str, S: dict) -> Paragraph:
    href = _esc(url)
    return _P(f'<link href="{href}" color="#2C5B57">{_esc(label or url)}</link>', S["cite"])


def _html_to_paras(raw: str, S: dict) -> list:
    text = raw or ""
    text = re.sub(r"</p>\s*<p[^>]*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</div>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        one = " ".join(text.split())
        if one:
            paras = [one]
    return [_P(_esc(p), S["letter"]) for p in paras]


def _dedupe_hiring(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for h in rows or []:
        if not h or not (h.get("role") or "").strip():
            continue
        url = (h.get("source_url") or "").rstrip("/").lower()
        role = (h.get("role") or "").strip().lower()
        plat = (h.get("platform") or "").strip().lower()
        key = url or f"{role}|{plat}"
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def _fit_style(fit: str, S: dict) -> ParagraphStyle:
    f = (fit or "").lower()
    if "strong" in f:
        return S["fit_strong"]
    if "partial" in f:
        return S["fit_partial"]
    return S["fit_other"]


def _swot_cell(title: str, items: list, bg, S: dict) -> list:
    bits = [_P(title.upper(), S["swot_h"])]
    pts = []
    for i in (items or [])[:5]:
        p = _point(i)
        if p:
            pts.append(f"• {_esc(p)}")
    bits.append(_P("<br/>".join(pts) if pts else "—", S["swot_b"]))
    inner = Table([[bits]], colWidths=[CONTENT_W / 2 - 8])
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return [inner]


def _draw_cover_chrome(c, ctx: dict) -> None:
    c.setFillColor(PAPER)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    banner_h = 1.62 * inch
    c.setFillColor(INK)
    c.rect(0, PAGE_H - banner_h, PAGE_W, banner_h, fill=1, stroke=0)
    c.setStrokeColor(AMBER)
    c.setLineWidth(2)
    c.line(0, PAGE_H - banner_h, PAGE_W, PAGE_H - banner_h)

    cx, cy = 0.78 * inch, PAGE_H - 0.78 * inch
    c.setStrokeColor(AMBER)
    c.setLineWidth(1.4)
    c.circle(cx, cy, 13, stroke=1, fill=0)
    c.setFillColor(AMBER)
    c.setFont("Courier-Bold", 8)
    c.drawCentredString(cx, cy - 3, "CF")

    c.setFillColor(CREAM)
    c.setFont("Times-Bold", 18)
    c.drawString(1.12 * inch, PAGE_H - 0.72 * inch, "Casefile")
    c.setFillColor(colors.HexColor("#B8B0A0"))
    c.setFont("Courier", 8)
    c.drawString(1.12 * inch, PAGE_H - 0.94 * inch, "CLIENT INTELLIGENCE  ·  OUTREACH")

    c.setFillColor(AMBER)
    c.setFont("Courier-Bold", 8)
    c.drawRightString(PAGE_W - 0.7 * inch, PAGE_H - 0.68 * inch, "CONFIDENTIAL")
    c.setFillColor(colors.HexColor("#B8B0A0"))
    c.setFont("Courier", 7.5)
    c.drawRightString(PAGE_W - 0.7 * inch, PAGE_H - 0.88 * inch, ctx.get("generated", ""))

    c.setFillColor(PAPER)
    c.rect(0, 0, PAGE_W, 0.42 * inch, fill=1, stroke=0)
    c.setFillColor(MUTED)
    c.setFont("Courier", 7)
    c.drawString(LEFT, 0.18 * inch, "Casefile  ·  not for public distribution")
    c.drawRightString(PAGE_W - RIGHT, 0.18 * inch, "Exhibit pack A–F")


def _draw_body_chrome(c, doc, ctx: dict) -> None:
    c.setFillColor(PAPER)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    header_h = 0.48 * inch
    c.setFillColor(INK)
    c.rect(0, PAGE_H - header_h, PAGE_W, header_h, fill=1, stroke=0)
    c.setStrokeColor(AMBER)
    c.setLineWidth(1.5)
    c.line(0, PAGE_H - header_h, PAGE_W, PAGE_H - header_h)

    c.setFillColor(AMBER)
    c.setFont("Courier-Bold", 8)
    c.drawString(LEFT, PAGE_H - 0.30 * inch, "CF")
    c.setFillColor(CREAM)
    c.setFont("Times-Bold", 10)
    c.drawString(LEFT + 0.28 * inch, PAGE_H - 0.31 * inch, "Casefile")
    pair = f"{_latin(ctx.get('pitcher', ''))}  |  {_latin(ctx.get('target', ''))}"
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#C9C2B4"))
    c.drawRightString(PAGE_W - RIGHT, PAGE_H - 0.31 * inch, pair[:78])

    c.setFillColor(PAPER)
    c.rect(0, 0, PAGE_W, 0.46 * inch, fill=1, stroke=0)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.line(LEFT, 0.46 * inch, PAGE_W - RIGHT, 0.46 * inch)
    c.setFillColor(MUTED)
    c.setFont("Courier", 7)
    c.drawString(LEFT, 0.20 * inch, "Confidential  ·  Casefile intelligence report")
    c.drawRightString(PAGE_W - RIGHT, 0.20 * inch, f"Page  {doc.page}")


def _cover_story(brochure, target, pitch, aeo, S, ctx) -> list:
    pitcher = ctx["pitcher"]
    target_name = ctx["target"]
    meta = target.get("_meta") or {}
    co = target.get("company_profile") or {}
    sc = target.get("intelligence_score") or {}
    ind = _industry(co)
    hq = _val(co.get("headquarters"))

    story = []
    story.append(_P("INTELLIGENCE CASEFILE", S["kicker"]))
    story.append(_P(_esc(target_name), S["cover_title"]))
    story.append(_P(
        f"{_esc(pitcher)}  pitching  ·  generated { _esc(ctx['generated']) }",
        S["cover_sub"],
    ))

    chips = _kpi_row([
        ("Founded", _val(co.get("founded"))),
        ("Employees", _val(co.get("employee_count") or co.get("employees")
                           or (target.get("employee_insights") or {}).get("total_employees"))),
        ("Revenue", _val(co.get("annual_revenue"))),
        ("HQ", hq.split(",")[0].strip() if hq else ""),
        ("Score", f"{sc.get('overall')}/100" if sc.get("overall") not in (None, "") else ""),
    ], S)
    if chips:
        story.append(chips)
        story.append(Spacer(1, 0.16 * inch))

    subline = " · ".join(x for x in [ind, hq, _val(co.get("founded"))] if _has(x))
    if subline:
        story.append(_P(_esc(subline), S["muted"]))
        story.append(Spacer(1, 0.08 * inch))

    desc = _val(co.get("description"))
    if desc:
        story.append(_P(_esc(desc[:420] + ("..." if len(desc) > 420 else "")), S["body"]))
        story.append(Spacer(1, 0.16 * inch))

    status_rows = [
        ["A", "Pitching company profile", "Included" if brochure else "Missing"],
        ["B", "Target company intelligence", "Included" if target else "Missing"],
        ["C", "Compare &amp; pitch", "Included" if pitch else "Not generated"],
        ["D", "Outreach email draft", "Included" if (pitch or {}).get("email_draft") else "Not generated"],
        ["F", "AEO / GEO visibility audit", "Included" if aeo else "Not run — omitted"],
    ]
    pack = [[
        _P('<font color="#EFEAE0"><b>EX.</b></font>', S["th"]),
        _P('<font color="#EFEAE0"><b>SECTION</b></font>', S["th"]),
        _P('<font color="#EFEAE0"><b>THIS REPORT</b></font>', S["th"]),
    ]]
    for letter, title, st in status_rows:
        pack.append([
            _P(f"<b>{letter}</b>", S["cell_b"]),
            _P(title, S["cell"]),
            _P(_esc(st), S["cell"]),
        ])
    pt = Table(pack, colWidths=[0.55 * inch, 3.4 * inch, CONTENT_W - 3.95 * inch])
    pt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("BACKGROUND", (0, 1), (-1, -1), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PAPER]),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(_P("WHAT IS IN THIS FILE", S["h3"]))
    story.append(pt)
    story.append(Spacer(1, 0.18 * inch))

    domain = meta.get("domain") or ""
    story.append(_P(
        "Prepared for internal use. Facts are drawn from public web sources. "
        "Completeness is not accuracy — treat unverified fields as leads, not ground truth."
        + (f" Target site: {_esc(domain)}." if domain else ""),
        S["muted"],
    ))
    return story


def _exhibit_a(brochure: dict, S: dict) -> list:
    story = [_exhibit_banner("A", "Pitching company profile", S), Spacer(1, 0.12 * inch)]
    name = brochure.get("company_name") or "Pitching company"
    story.append(_P(f"<b>{_esc(name)}</b>", S["body"]))
    if brochure.get("website"):
        story.append(_link(str(brochure["website"]), str(brochure["website"]), S))
    story.append(Spacer(1, 0.06 * inch))
    if brochure.get("summary"):
        story.append(_P(_esc(brochure["summary"]), S["body"]))

    services = [s for s in (brochure.get("services") or []) if s]
    if services:
        story.append(_P("Services", S["h3"]))
        tags = "  ·  ".join(_esc(s) for s in services)
        story.append(_P(tags, S["body_sm"]))

    industries = [s for s in (brochure.get("industries") or []) if s]
    if industries:
        story.append(_P("Industries", S["h3"]))
        story.append(_P(_esc(", ".join(industries)), S["body"]))

    if brochure.get("case_studies"):
        story.append(_P("Case studies / proof", S["h3"]))
        story.append(_P(_esc(brochure.get("case_studies", "")), S["body"]))

    contacts = brochure.get("contacts") or []
    if contacts:
        story.append(_P("Primary contact", S["h3"]))
        rows = []
        for c in contacts[:4]:
            if not isinstance(c, dict):
                continue
            bits = " · ".join(
                x for x in [c.get("title"), c.get("email"), c.get("phone")] if x
            )
            src = c.get("source") or ""
            rows.append([
                _P(_esc(c.get("name") or "Contact"), S["cell_b"]),
                _P(_esc(bits), S["cell"]),
                _P(_esc(src), S["muted"]),
            ])
        t = _styled_table(["Name", "Details", "Source"], rows, [1.7 * inch, 3.4 * inch, CONTENT_W - 5.1 * inch], S)
        if t:
            story.append(t)
    return story


def _exhibit_b(target: dict, S: dict) -> list:
    story = [_exhibit_banner("B", "Target company intelligence", S), Spacer(1, 0.12 * inch)]
    co = target.get("company_profile") or {}
    meta = target.get("_meta") or {}
    sc = target.get("intelligence_score") or {}
    name = meta.get("company_name") or co.get("name") or "Target"
    hq = _val(co.get("headquarters"))
    ind = _industry(co)

    story.append(_P(_esc(name) + (f"  ·  {_esc(hq.split(',')[0])}" if hq else ""), S["cover_title"]))
    sub = " · ".join(x for x in [ind, _val(co.get("founded")), meta.get("domain")] if _has(x))
    if sub:
        story.append(_P(_esc(sub), S["cover_sub"]))

    desc = _val(co.get("description"))
    if desc:
        story.append(_P(_esc(desc), S["body"]))
        story.append(Spacer(1, 0.10 * inch))

    chips = _kpi_row([
        ("Founded", _val(co.get("founded"))),
        ("Employees", _val(co.get("employee_count") or co.get("employees")
                           or (target.get("employee_insights") or {}).get("total_employees"))),
        ("Revenue", _val(co.get("annual_revenue") or (target.get("financial_data") or {}).get("revenue_estimate"))),
        ("HQ", hq),
        ("Score", f"{sc.get('overall')}/100" if sc.get("overall") not in (None, "") else ""),
    ], S)
    if chips:
        story.append(chips)
        story.append(Spacer(1, 0.12 * inch))

    conf_bits = []
    for lbl, key in (
        ("Authenticity", "authenticity"),
        ("Completeness", "data_completeness"),
        ("Reliability", "source_reliability"),
        ("Overall", "overall"),
    ):
        v = sc.get(key)
        if v not in (None, ""):
            conf_bits.append(f"<b>{lbl}</b> {_esc(str(v))}/100")
    if conf_bits:
        bar = Table([[_P("  ".join(conf_bits) +
                         "<br/><font size='7' color='#6E6555'>Completeness is not accuracy — overall is capped by authenticity and source reliability.</font>",
                         S["body_sm"])]], colWidths=[CONTENT_W])
        bar.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), ROW_ALT),
            ("BOX", (0, 0), (-1, -1), 0.5, RULE),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(bar)

    conclusion = target.get("ai_conclusion") or sc.get("summary") or ""
    if conclusion:
        story.append(_P("Analyst conclusion", S["h3"]))
        story.append(_P(_esc(conclusion), S["body"]))

    # Overview
    prod = target.get("products_services") or {}
    mkt = target.get("market_analysis") or {}
    offerings = []
    for o in prod.get("primary_offerings") or prod.get("value") or []:
        n = _point(o) if not isinstance(o, str) else o
        if n:
            offerings.append(n)
    if offerings:
        story.append(_P("Products &amp; services", S["h3"]))
        story.append(_P("  ·  ".join(_esc(x) for x in offerings[:12]), S["body_sm"]))
    if _has(_val(prod.get("target_customers"))):
        story.append(_P(f"<b>Target customers.</b> {_esc(_val(prod.get('target_customers')))}", S["body"]))
    if _has(_val(prod.get("pricing_model"))):
        story.append(_P(f"<b>Pricing.</b> {_esc(_val(prod.get('pricing_model')))}", S["body"]))
    mp = mkt.get("market_position")
    mp_val = _val(mp) if not isinstance(mp, str) else mp
    if _has(mp_val):
        story.append(_P("Market position", S["h3"]))
        story.append(_P(_esc(mp_val), S["body"]))
    if _has(_val(mkt.get("geographic_reach"))):
        story.append(_P(f"<b>Geographic reach.</b> {_esc(_val(mkt.get('geographic_reach')))}", S["body"]))

    # Leadership
    leaders = [l for l in (target.get("leadership_team") or []) if l and l.get("name")]
    if leaders:
        block = [
            _P("Current leadership", S["h3"]),
            _P("Public company profiles, leadership pages, and filings - not MCA.", S["muted"]),
        ]
        rows = []
        for l in leaders[:12]:
            role = l.get("role") or l.get("designation") or ""
            src = l.get("source") or "Public source"
            if src.lower().startswith("http"):
                src = "Leadership page"
            conf = l.get("confidence") or ""
            rows.append([
                _P(_esc(l.get("name", "")), S["cell_b"]),
                _P(_esc(role), S["cell"]),
                _P(_esc(f"{src}" + (f" · {conf}" if conf else "")), S["muted"]),
            ])
        t = _styled_table(["Name", "Role", "Source"], rows,
                          [2.1 * inch, 2.4 * inch, CONTENT_W - 4.5 * inch], S)
        if t:
            block.append(t)
        story.append(KeepTogether(block))

    # Hiring
    hiring = _dedupe_hiring(target.get("hiring_signals") or [])
    if hiring:
        block = [
            _P("Current hiring", S["h3"]),
            _P(
                "Official careers, LinkedIn, Naukri, Indeed, and company ATS pages.",
                S["muted"],
            ),
        ]
        rows = []
        for h in hiring[:14]:
            url = h.get("source_url") or ""
            label = h.get("source_title") or h.get("source") or url
            if len(label) > 64:
                label = label[:61] + "..."
            src_cell = _link(url, label, S) if url else _P(_esc(label), S["cite"])
            rows.append([
                _P(_esc(h.get("role", "")), S["cell_b"]),
                _P(_esc(h.get("platform") or "Official"), S["cell"]),
                src_cell,
            ])
        t = _styled_table(["Role / board", "Platform", "Source"], rows,
                          [2.15 * inch, 1.25 * inch, CONTENT_W - 3.4 * inch], S)
        if t:
            block.append(t)
        story.append(KeepTogether(block))

    # POC
    poc = target.get("point_of_contact") or {}
    if any(poc.get(k) for k in ("name", "email", "phone", "title")):
        story.append(_P("Point of contact", S["h3"]))
        poc_bits = [
            f"<b>{_esc(poc.get('name') or '—')}</b>",
            _esc(poc.get("title") or ""),
            _esc(poc.get("email") or ""),
            _esc(poc.get("phone") or "") if _valid_phone(poc.get("phone") or "") else "",
        ]
        story.append(_P("  ·  ".join(x for x in poc_bits if x), S["body"]))
        if poc.get("reason"):
            story.append(_P(_esc(poc["reason"]), S["muted"]))

    # People / culture
    emp = target.get("employee_insights") or {}
    if any(_has(_val(emp.get(k))) for k in ("total_employees", "hiring_trend", "remote_policy", "glassdoor_rating", "culture_summary")):
        story.append(_P("People &amp; culture", S["h3"]))
        for lbl, key in (
            ("Employees", "total_employees"),
            ("Hiring trend", "hiring_trend"),
            ("Remote policy", "remote_policy"),
            ("Glassdoor", "glassdoor_rating"),
        ):
            if _has(_val(emp.get(key))):
                story.append(_P(f"<b>{lbl}.</b> {_esc(_val(emp.get(key)))}", S["body"]))
        if _has(_val(emp.get("culture_summary"))):
            story.append(_P(_esc(_val(emp.get("culture_summary"))), S["muted"]))

    # News
    news = [n for n in (target.get("recent_news") or []) if n and (n.get("title") or n.get("summary"))]
    if news:
        block = [_P("Recent news", S["h3"])]
        for n in news[:6]:
            sent = f"  ·  {_esc(n.get('sentiment'))}" if n.get("sentiment") else ""
            date = f"  ·  {_esc(n.get('date'))}" if n.get("date") else ""
            block.append(_P(f"<b>{_esc(n.get('title') or 'Update')}</b>{date}{sent}", S["body"]))
            if n.get("summary"):
                block.append(_P(_esc(n["summary"]), S["muted"]))
        story.append(KeepTogether(block))

    # SWOT
    swot = target.get("swot_analysis") or {}
    if any(swot.get(k) for k in ("strengths", "weaknesses", "opportunities", "threats")):
        story.append(_P("SWOT", S["h3"]))
        grid = Table(
            [
                [
                    _swot_cell("Strengths", swot.get("strengths"), TEAL_SOFT, S)[0],
                    _swot_cell("Weaknesses", swot.get("weaknesses"), SOFT_RED, S)[0],
                ],
                [
                    _swot_cell("Opportunities", swot.get("opportunities"), AMBER_SOFT, S)[0],
                    _swot_cell("Threats", swot.get("threats"), PAPER, S)[0],
                ],
            ],
            colWidths=[CONTENT_W / 2, CONTENT_W / 2],
        )
        grid.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(grid)

    # Risk + finance
    risk = target.get("risk_assessment") or {}
    fin = target.get("financial_data") or {}
    if risk or _has(_val(fin.get("revenue_estimate"))) or _has(_val(fin.get("funding_status"))):
        story.append(_P("Risk &amp; financials", S["h3"]))
        if _has(_val(fin.get("revenue_estimate"))):
            story.append(_P(f"<b>Revenue estimate.</b> {_esc(_val(fin.get('revenue_estimate')))}", S["body"]))
        if _has(_val(fin.get("funding_status") or fin.get("total_funding"))):
            story.append(_P(f"<b>Funding.</b> {_esc(_val(fin.get('funding_status') or fin.get('total_funding')))}", S["body"]))
        rl = _risk_text(risk.get("overall_risk_level"))
        if rl:
            story.append(_P(f"<b>Overall risk.</b> {_esc(rl)}", S["body"]))
        for label, key in (
            ("Regulatory", "regulatory_risks"),
            ("Competitive", "competitive_risks"),
            ("Operational", "operational_risks"),
            ("Reputational", "reputational_risks"),
        ):
            txt = _risk_text(risk.get(key))
            if txt:
                story.append(_P(f"<b>{label}.</b> {_esc(txt)}", S["body"]))

    comps = [
        c for c in (target.get("competitors") or [])
        if isinstance(c, dict) and c.get("name") and not _JUNK_COMPETITOR.match(c.get("name") or "")
    ]
    if comps:
        story.append(_P("Competitors", S["h3"]))
        rows = []
        for c in comps[:8]:
            threat = c.get("threat_level") or ""
            rows.append([
                _P(_esc(c.get("name", "")), S["cell_b"]),
                _P(_esc(c.get("description") or ""), S["cell"]),
                _P(_esc(threat), S["cell"]),
            ])
        t = _styled_table(["Company", "Why they matter", "Threat"], rows,
                          [1.6 * inch, CONTENT_W - 2.45 * inch, 0.85 * inch], S)
        if t:
            story.append(t)

    ci = target.get("contact_intelligence") or {}
    emails = ci.get("emails") or []
    phones = [p for p in (ci.get("phones") or []) if _valid_phone(p.get("number") or "")]
    addr = ci.get("registered_address") or _val(co.get("registered_address"))
    if emails or phones or addr:
        story.append(_P("Contacts", S["h3"]))
        if addr:
            story.append(_P(f"<b>Address.</b> {_esc(addr)}", S["body"]))
        for p in phones[:6]:
            who = p.get("person_name") or p.get("name") or "Phone"
            story.append(_P(f"<b>{_esc(who)}.</b> {_esc(p.get('number', ''))}", S["body"]))
        for e in emails[:6]:
            who = e.get("person_name") or e.get("name") or e.get("label") or "Email"
            title = f" ({_esc(e.get('title'))})" if e.get("title") else ""
            story.append(_P(f"<b>{_esc(who)}</b>{title}: {_esc(e.get('email', ''))}", S["body"]))

    cs = target.get("content_strategy") or {}
    if cs:
        bits = []
        if _has(_val(cs.get("brand_voice"))):
            bits.append(_esc(_val(cs.get("brand_voice"))))
        pillars = cs.get("content_pillars") or cs.get("pillars") or []
        pillar_txt = ", ".join(_point(p) for p in pillars[:8] if _point(p))
        if pillar_txt:
            bits.append(f"<b>Pillars.</b> {_esc(pillar_txt)}")
        gap = _val(cs.get("competitor_content_gap") or cs.get("content_gap_opportunity"))
        if _has(gap):
            bits.append(f"<b>Content gap.</b> {_esc(gap)}")
        if bits:
            story.append(KeepTogether([
                _P("Content strategy", S["h3"]),
                _P("<br/>".join(bits), S["body"]),
            ]))

    return story


def _exhibit_c(pitch: dict, S: dict) -> list:
    story = [_exhibit_banner("C", "Compare &amp; pitch", S), Spacer(1, 0.12 * inch)]
    score = pitch.get("match_score")
    if score not in (None, ""):
        badge = Table([[_P(
            f"<font color='#2C5B57'><b>MATCH  { _esc(str(score)) }%</b></font>",
            S["chip_val"],
        )]], colWidths=[1.6 * inch])
        badge.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), TEAL_SOFT),
            ("BOX", (0, 0), (-1, -1), 0.6, TEAL),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        story.append(badge)
        story.append(Spacer(1, 0.10 * inch))
    if pitch.get("ai_conclusion"):
        story.append(_P(_esc(pitch["ai_conclusion"]), S["body"]))
        story.append(Spacer(1, 0.08 * inch))

    matches = pitch.get("matches") or []
    if matches:
        rows = []
        for m in matches[:10]:
            fit = m.get("fit") or ""
            rows.append([
                _P(_esc(m.get("pitcher_offers") or ""), S["cell"]),
                _P(_esc(m.get("target_needs") or ""), S["cell"]),
                _P(_esc(fit), _fit_style(fit, S)),
            ])
        t = _styled_table(["You offer", "They need", "Fit"], rows,
                          [2.25 * inch, 3.15 * inch, CONTENT_W - 5.4 * inch], S)
        if t:
            story.append(t)

    tips = [t for t in (pitch.get("talking_points") or []) if t]
    if tips:
        story.append(_P("Talking points", S["h3"]))
        story.extend(_bullets(tips, S, 8))
    return story


def _exhibit_d(pitch: dict, S: dict) -> list:
    email = (pitch or {}).get("email_draft") or {}
    if not (email.get("body_html") or email.get("body") or email.get("subject")):
        return []
    story = [_exhibit_banner("D", "Outreach email draft", S), Spacer(1, 0.12 * inch)]

    to_line = " ".join(x for x in [
        email.get("to_name") or "",
        f"&lt;{_esc(email.get('to_email'))}&gt;" if email.get("to_email") else "",
    ] if x)
    from_line = " ".join(x for x in [
        email.get("from_name") or "",
        f"&lt;{_esc(email.get('from_email'))}&gt;" if email.get("from_email") else "",
    ] if x)
    meta_rows = []
    if to_line.strip():
        meta_rows.append([_P("<b>To</b>", S["muted"]), _P(to_line + (f"  ·  {_esc(email.get('to_title'))}" if email.get("to_title") else ""), S["body_sm"])])
    if from_line.strip():
        meta_rows.append([_P("<b>From</b>", S["muted"]), _P(from_line, S["body_sm"])])
    if email.get("subject"):
        meta_rows.append([_P("<b>Subject</b>", S["muted"]), _P(_esc(email.get("subject")), S["cell_b"])])
    if meta_rows:
        mt = Table(meta_rows, colWidths=[0.85 * inch, CONTENT_W - 0.85 * inch])
        mt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), ROW_ALT),
            ("BOX", (0, 0), (-1, -1), 0.5, RULE),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(mt)
        story.append(Spacer(1, 0.12 * inch))

    body_raw = email.get("body_html") or email.get("body") or ""
    letter = _html_to_paras(body_raw, S)
    wrap = Table([[letter]], colWidths=[CONTENT_W])
    wrap.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("LINEBEFORE", (0, 0), (0, 0), 3, AMBER),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(wrap)
    return story


def _exhibit_f(aeo: dict, S: dict) -> list:
    if not aeo:
        return []
    analysis = aeo.get("analysis") or {}
    on_page = aeo.get("on_page") or {}
    signals = on_page.get("signals") or {}
    geo = aeo.get("geo_snapshot") or {}
    meta = aeo.get("_meta") or {}

    story = [_exhibit_banner("F", "AEO / GEO visibility audit", S), Spacer(1, 0.12 * inch)]
    story.append(_P(_esc(aeo.get("company_name") or aeo.get("domain") or "Audit"), S["h_exhibit"]))
    story.append(_P(
        _esc(" · ".join(x for x in [
            aeo.get("domain") or "",
            meta.get("search_engine") or "",
            f"{meta.get('elapsed_seconds')}s" if meta.get("elapsed_seconds") else "",
        ] if x)),
        S["muted"],
    ))
    if analysis.get("visibility_summary"):
        story.append(Spacer(1, 0.06 * inch))
        story.append(_P(_esc(analysis["visibility_summary"]), S["body"]))

    chips = _kpi_row([
        ("AEO", str(analysis.get("aeo_score") if analysis.get("aeo_score") is not None else "")),
        ("GEO", str(analysis.get("geo_score_blended") if analysis.get("geo_score_blended") is not None else analysis.get("geo_score") or "")),
        ("Topics", str(len(aeo.get("topics") or []))),
        ("Mentions", str(geo.get("mention_count") if geo.get("mention_count") is not None else "")),
        ("Fixes", str(len(analysis.get("recommendations") or []))),
    ], S)
    if chips:
        story.append(Spacer(1, 0.10 * inch))
        story.append(chips)

    story.append(_P("On-page signals", S["h3"]))
    sig_line = "   ·   ".join([
        f"H1: {'Yes' if signals.get('has_h1') else 'No'}",
        f"Meta: {'Yes' if signals.get('has_meta_description') else 'No'}",
        f"About: {'Yes' if signals.get('has_about_page') else 'No'}",
        f"FAQs: {signals.get('faq_count') or 0}",
        f"FAQ schema: {'Yes' if signals.get('has_faq_schema') else 'No'}",
        f"Org schema: {'Yes' if signals.get('has_organization_schema') else 'No'}",
    ])
    story.append(_P(_esc(sig_line), S["body_sm"]))

    topics = aeo.get("topic_research") or []
    if topics:
        story.append(_P("Who ranks for your topics", S["h3"]))
        for tr in topics[:6]:
            winners = ", ".join(tr.get("winner_domains") or [])
            story.append(_P(f"<b>{_esc(tr.get('topic') or '')}</b>  —  {_esc(winners or 'no clear winners')}", S["body"]))
            for r in (tr.get("top_results") or [])[:3]:
                url = r.get("url") or ""
                title = r.get("title") or url
                if url:
                    story.append(_link(url, title, S))

    gaps = analysis.get("gaps") or []
    if gaps:
        story.append(_P("Gaps", S["h3"]))
        for g in gaps[:8]:
            if isinstance(g, dict):
                sev = g.get("severity") or ""
                area = g.get("area") or ""
                finding = g.get("finding") or _point(g)
                why = g.get("why_it_matters") or ""
                head = " · ".join(x for x in [sev, area] if x)
                if head:
                    story.append(_P(f"<b>{_esc(head)}</b>", S["body"]))
                if finding:
                    story.append(_P(_esc(finding), S["body"]))
                if why:
                    story.append(_P(_esc(why), S["muted"]))
            elif g:
                story.append(_P(f"• {_esc(g)}", S["body"]))

    recs = analysis.get("recommendations") or []
    if recs:
        story.append(_P("Recommended fixes", S["h3"]))
        for rec in recs[:8]:
            if not isinstance(rec, dict):
                story.append(_P(f"• {_esc(rec)}", S["body"]))
                continue
            bits = " · ".join(x for x in [rec.get("priority"), rec.get("type"), rec.get("page")] if x)
            title = rec.get("title") or "Fix"
            story.append(_P(f"<b>{_esc(title)}</b>" + (f"  —  {_esc(bits)}" if bits else ""), S["body"]))
            if rec.get("why"):
                story.append(_P(_esc(rec["why"]), S["muted"]))
            if rec.get("before") or rec.get("after"):
                ba = []
                if rec.get("before"):
                    ba.append(f"<b>Before.</b> {_esc(rec['before'])}")
                if rec.get("after"):
                    ba.append(f"<b>After.</b> {_esc(rec['after'])}")
                story.append(_P("<br/>".join(ba), S["body_sm"]))
                story.append(Spacer(1, 0.06 * inch))

    faqs = analysis.get("suggested_faqs") or []
    if faqs:
        story.append(_P("Suggested FAQs", S["h3"]))
        for f in faqs[:6]:
            if isinstance(f, dict):
                q = f.get("question") or f.get("q") or ""
                a = f.get("answer") or f.get("a") or ""
                if q:
                    story.append(_P(f"<b>Q.</b> {_esc(q)}", S["body"]))
                if a:
                    story.append(_P(f"<b>A.</b> {_esc(a)}", S["muted"]))
            elif f:
                story.append(_P(f"• {_esc(f)}", S["body"]))

    mentions = geo.get("external_mentions") or geo.get("mentions") or []
    if mentions:
        story.append(_P("GEO mentions", S["h3"]))
        if geo.get("note"):
            story.append(_P(_esc(geo["note"]), S["muted"]))
        for m in mentions[:8]:
            if not isinstance(m, dict):
                continue
            kind = m.get("kind") or "other"
            url = m.get("url") or ""
            title = m.get("title") or url
            story.append(_P(f"<b>{_esc(kind)}</b>  {_esc(title)}", S["body_sm"]))
            if url:
                story.append(_link(url, url, S))

    checklist = analysis.get("distribution_checklist") or []
    if checklist:
        story.append(_P("Distribution checklist", S["h3"]))
        for c in checklist[:8]:
            if isinstance(c, dict):
                story.append(_P(
                    f"<b>{_esc(c.get('action') or '')}</b>  —  {_esc(c.get('helps') or '')}. {_esc(c.get('done_hint') or '')}",
                    S["body_sm"],
                ))
    return story


def _sources(target: dict, hiring: list, S: dict) -> list:
    meta = target.get("_meta") or {}
    citations = list(meta.get("citations") or [])
    for h in hiring:
        if h.get("source_url"):
            citations.append({
                "title": h.get("role") or h.get("source_title") or "Job board",
                "url": h.get("source_url"),
                "category": h.get("platform") or "Hiring",
            })
    seen: set[str] = set()
    rows = []
    for c in citations:
        url = (c.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        cat = c.get("category") or c.get("domain") or "Web"
        title = c.get("title") or url
        rows.append([
            _P(_esc(str(cat)), S["cell_b"]),
            _P(_esc(title), S["cell"]),
            _link(url, url, S),
        ])
        if len(rows) >= 28:
            break
    if not rows:
        return []
    story = [_exhibit_banner("SRC", "Sources &amp; citations", S), Spacer(1, 0.10 * inch)]
    t = _styled_table(["Type", "Title", "URL"], rows,
                      [1.25 * inch, 2.15 * inch, CONTENT_W - 3.4 * inch], S)
    if t:
        story.append(t)
    return story


def run(
    brochure: dict,
    target: dict,
    pitch: Optional[dict] = None,
    aeo: Optional[dict] = None,
) -> bytes:
    brochure = brochure or {}
    target = target or {}
    pitch = pitch or None
    aeo = aeo or None

    S = _styles()
    meta = target.get("_meta") or {}
    pitcher = brochure.get("company_name") or "Your company"
    target_name = meta.get("company_name") or (target.get("company_profile") or {}).get("name") or "Target"
    generated = meta.get("generated_at") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ctx = {"pitcher": pitcher, "target": target_name, "generated": generated}

    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        title=f"Casefile - {pitcher} -> {target_name}",
        author="Casefile",
    )

    cover_frame = Frame(
        LEFT, 0.55 * inch, CONTENT_W, PAGE_H - 2.28 * inch,
        id="cover", showBoundary=0,
    )
    body_frame = Frame(
        LEFT, 0.58 * inch, CONTENT_W, PAGE_H - 1.18 * inch,
        id="body", showBoundary=0,
    )
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=lambda c, d: _draw_cover_chrome(c, ctx)),
        PageTemplate(id="body", frames=[body_frame], onPage=lambda c, d: _draw_body_chrome(c, d, ctx)),
    ])

    story: list = []
    story.extend(_cover_story(brochure, target, pitch, aeo, S, ctx))
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())

    story.extend(_exhibit_a(brochure, S))
    story.append(Spacer(1, 0.22 * inch))
    story.extend(_exhibit_b(target, S))

    if pitch:
        story.append(Spacer(1, 0.18 * inch))
        story.extend(_exhibit_c(pitch, S))
        d_sec = _exhibit_d(pitch, S)
        if d_sec:
            story.append(Spacer(1, 0.18 * inch))
            story.extend(d_sec)

    if aeo:
        story.append(PageBreak())
        story.extend(_exhibit_f(aeo, S))

    hiring = _dedupe_hiring(target.get("hiring_signals") or [])
    src = _sources(target, hiring, S)
    if src:
        story.append(PageBreak())
        story.extend(src)

    doc.build(story)
    return buf.getvalue()
