"""
Export full casefile (brochure + target intel + pitch + citations) as PDF.
"""
from __future__ import annotations

import io
import re
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _val(field: Any) -> str:
    if isinstance(field, dict):
        return str(field.get("value", "") or "")
    return str(field or "")


def _esc(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


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


def run(
    brochure: dict,
    target: dict,
    pitch: Optional[dict] = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CaseTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=colors.HexColor("#1B2430"),
        spaceAfter=6,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#2C5B57"),
        spaceBefore=14,
        spaceAfter=8,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#241F1A"),
    )
    muted = ParagraphStyle(
        "Muted",
        parent=body,
        fontSize=9,
        textColor=colors.HexColor("#6E6555"),
    )
    cite = ParagraphStyle(
        "Cite",
        parent=body,
        fontSize=8,
        textColor=colors.HexColor("#2C5B57"),
        leftIndent=12,
    )

    story = []
    meta = target.get("_meta") or {}
    target_name = meta.get("company_name") or (target.get("company_profile") or {}).get("name", "Target")
    pitcher_name = brochure.get("company_name", "Your Company")

    story.append(Paragraph("Casefile — Client Intelligence &amp; Outreach", muted))
    story.append(Paragraph(f"{pitcher_name} → {target_name}", title_style))
    story.append(Paragraph(f"Generated {meta.get('generated_at', '')}", muted))
    story.append(Spacer(1, 0.2 * inch))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#D9D2BE")))
    story.append(Spacer(1, 0.15 * inch))

    # Exhibit A
    story.append(Paragraph("Exhibit A — Pitching Company Profile", h2))
    story.append(Paragraph(_esc(brochure.get("summary", "")), body))
    story.append(Spacer(1, 0.1 * inch))
    services = brochure.get("services") or []
    if services:
        story.append(Paragraph("<b>Services:</b> " + _esc(", ".join(services)), body))
    industries = brochure.get("industries") or []
    if industries:
        story.append(Paragraph("<b>Industries:</b> " + _esc(", ".join(industries)), body))
    if brochure.get("case_studies"):
        story.append(Spacer(1, 0.08 * inch))
        story.append(Paragraph("<b>Case Studies</b>", body))
        story.append(Paragraph(_esc(brochure.get("case_studies", "")), body))

    # Exhibit B
    story.append(Paragraph("Exhibit B — Target Company Intelligence", h2))
    co = target.get("company_profile") or {}
    story.append(Paragraph(
        f"<b>{_esc(co.get('name') or target_name)}</b> — "
        f"{_esc(_val(co.get('industry')))} · {_esc(_val(co.get('headquarters')))}",
        body,
    ))
    story.append(Paragraph(_esc(_val(co.get("description"))), body))

    sc = target.get("intelligence_score") or {}
    if sc.get("overall") or sc.get("data_completeness"):
        story.append(Spacer(1, 0.08 * inch))
        story.append(Paragraph(
            f"<b>Intelligence Score:</b> {_esc(str(sc.get('overall', '')))}/100 &nbsp;|&nbsp; "
            f"<b>Completeness:</b> {_esc(str(sc.get('data_completeness', '')))}/100 &nbsp;|&nbsp; "
            f"<b>Reliability:</b> {_esc(str(sc.get('source_reliability', '')))}/100",
            muted,
        ))

    # Leadership
    leaders = target.get("leadership_team") or []
    if leaders:
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph("<b>Leadership (MCA / Public Registry)</b>", body))
        for l in leaders[:6]:
            story.append(Paragraph(
                f"• <b>{_esc(l.get('name', ''))}</b> — {_esc(l.get('role') or l.get('designation') or 'Director')} "
                f"<font color='#6E6555'>({_esc(l.get('source', ''))})</font>",
                body,
            ))

    # Products
    prod = target.get("products_services") or {}
    offerings = prod.get("primary_offerings") or []
    if offerings:
        story.append(Spacer(1, 0.08 * inch))
        story.append(Paragraph("<b>Products &amp; Services</b>", body))
        for o in offerings[:8]:
            item = o.get("item") if isinstance(o, dict) else str(o)
            if item:
                story.append(Paragraph(f"• {_esc(item)}", body))

    hiring = target.get("hiring_signals") or []
    if hiring:
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph("<b>Current Hiring Signals</b>", body))
        rows = [["Role", "Openings", "Source", "Platform"]]
        for h in hiring[:12]:
            rows.append([
                _esc(h.get("role", "")),
                str(h.get("count", 1)),
                _esc(h.get("source_title", h.get("source", ""))[:40]),
                _esc(h.get("platform", "")),
            ])
        t = Table(rows, colWidths=[2.2 * inch, 0.7 * inch, 2.0 * inch, 1.0 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE7E4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#2C5B57")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9D2BE")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBF9F3")]),
        ]))
        story.append(t)

    ai_conclusion = target.get("ai_conclusion") or (pitch or {}).get("ai_conclusion", "")
    if ai_conclusion:
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph("<b>AI Conclusion</b>", body))
        story.append(Paragraph(_esc(ai_conclusion), body))

    # SWOT
    swot = target.get("swot_analysis") or {}
    if any(swot.get(k) for k in ("strengths", "weaknesses", "opportunities", "threats")):
        story.append(Paragraph("SWOT Analysis", h2))
        for label, key in [("Strengths", "strengths"), ("Weaknesses", "weaknesses"),
                           ("Opportunities", "opportunities"), ("Threats", "threats")]:
            items = swot.get(key) or []
            if items:
                pts = []
                for i in items[:5]:
                    p = i.get("point") if isinstance(i, dict) else str(i)
                    if p:
                        pts.append(f"• {_esc(p)}")
                if pts:
                    story.append(Paragraph(f"<b>{label}</b>", body))
                    story.append(Paragraph("<br/>".join(pts), body))
                    story.append(Spacer(1, 0.06 * inch))

    # Risk assessment
    risk = target.get("risk_assessment") or {}
    if risk:
        story.append(Paragraph("Risk Assessment", h2))
        rl = _risk_text(risk.get("overall_risk_level"))
        if rl:
            story.append(Paragraph(f"<b>Overall:</b> {_esc(rl)}", body))
        for label, key in [("Regulatory", "regulatory_risks"), ("Competitive", "competitive_risks"),
                           ("Operational", "operational_risks"), ("Reputational", "reputational_risks")]:
            txt = _risk_text(risk.get(key))
            if txt:
                story.append(Paragraph(f"<b>{label}:</b> {_esc(txt)}", body))

    # Competitors
    comps = target.get("competitors") or []
    if comps:
        story.append(Paragraph("Competitors", h2))
        for c in comps[:6]:
            story.append(Paragraph(
                f"<b>{_esc(c.get('name', ''))}</b> — {_esc(c.get('description', ''))}",
                body,
            ))

    # Contacts
    ci = target.get("contact_intelligence") or {}
    emails = ci.get("emails") or []
    phones = ci.get("phones") or []
    if emails or phones or ci.get("registered_address"):
        story.append(Paragraph("Contacts", h2))
        if ci.get("registered_address"):
            story.append(Paragraph(f"<b>Address:</b> {_esc(ci['registered_address'])}", body))
        for p in phones[:5]:
            story.append(Paragraph(
                f"<b>{_esc(p.get('person_name') or p.get('name') or 'Phone')}:</b> {_esc(p.get('number', ''))}",
                body,
            ))
        for e in emails[:5]:
            story.append(Paragraph(
                f"<b>{_esc(e.get('person_name') or e.get('name') or 'Email')}:</b> {_esc(e.get('email', ''))}",
                body,
            ))

    # Content strategy
    cs = target.get("content_strategy") or {}
    if cs:
        story.append(Paragraph("Content Strategy", h2))
        if _val(cs.get("brand_voice")):
            story.append(Paragraph(_esc(_val(cs.get("brand_voice"))), body))
        pillars = cs.get("content_pillars") or cs.get("pillars") or []
        if pillars:
            story.append(Paragraph(
                "<b>Pillars:</b> " + _esc(", ".join(
                    p.get("point") if isinstance(p, dict) else str(p) for p in pillars[:6]
                )),
                body,
            ))

    # Exhibit C
    if pitch:
        story.append(Paragraph("Exhibit C — Compare &amp; Pitch", h2))
        story.append(Paragraph(f"<b>Match Score: {pitch.get('match_score', 0)}%</b>", body))
        if pitch.get("ai_conclusion"):
            story.append(Paragraph(_esc(pitch["ai_conclusion"]), body))
        matches = pitch.get("matches") or []
        if matches:
            story.append(Spacer(1, 0.08 * inch))
            mrows = [["You Offer", "They Need", "Fit"]]
            for m in matches:
                mrows.append([
                    _esc(m.get("pitcher_offers", "")),
                    _esc(m.get("target_needs", "")),
                    _esc(m.get("fit", "")),
                ])
            mt = Table(mrows, colWidths=[2.0 * inch, 2.5 * inch, 1.3 * inch])
            mt.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFDFC4")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9D2BE")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(mt)

        email = pitch.get("email_draft") or {}
        if email.get("body_html") or email.get("body"):
            story.append(Spacer(1, 0.12 * inch))
            story.append(Paragraph("<b>Outreach Email Draft</b>", body))
            story.append(Paragraph(
                f"<b>To:</b> {_esc(email.get('to_name', ''))} "
                f"&lt;{_esc(email.get('to_email', ''))}&gt;",
                muted,
            ))
            story.append(Paragraph(f"<b>Subject:</b> {_esc(email.get('subject', ''))}", muted))
            body_text = email.get("body_html") or email.get("body", "")
            body_text = re.sub(r"<[^>]+>", " ", body_text) if "<" in body_text else body_text
            story.append(Paragraph(_esc(body_text), body))

    # Citations
    citations = meta.get("citations") or []
    hiring_cites = [h for h in hiring if h.get("source_url")]
    all_cites = citations + [
        {"title": h.get("role", "Job posting"), "url": h.get("source_url", ""),
         "domain": h.get("platform", ""), "category": "Hiring"}
        for h in hiring_cites
    ]
    if all_cites:
        story.append(Paragraph("Sources &amp; Citations", h2))
        seen = set()
        for c in all_cites[:25]:
            url = c.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            story.append(Paragraph(
                f"• [{_esc(c.get('category', c.get('domain', 'Web')))}] "
                f"{_esc(c.get('title', url))}<br/>"
                f"<font color='#2C5B57'>{_esc(url)}</font>",
                cite,
            ))

    doc.build(story)
    return buf.getvalue()
