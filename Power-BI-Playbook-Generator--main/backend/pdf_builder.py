"""Renders a playbook dict to a Xebia-branded PDF (A4)."""
import os
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily, stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate,
                                Paragraph, Preformatted, Spacer, Table, TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
LOGO = os.path.join(HERE, "assets", "xebia_logo.png")

pdfmetrics.registerFont(TTFont("Sans", os.path.join(FONTS, "LiberationSans-Regular.ttf")))
pdfmetrics.registerFont(TTFont("Sans-B", os.path.join(FONTS, "LiberationSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("Sans-I", os.path.join(FONTS, "LiberationSans-Italic.ttf")))
pdfmetrics.registerFont(TTFont("Mono", os.path.join(FONTS, "LiberationMono-Regular.ttf")))
registerFontFamily("Sans", normal="Sans", bold="Sans-B", italic="Sans-I", boldItalic="Sans-B")

PURPLE = colors.HexColor("#6A2060"); PURPLE_L = colors.HexColor("#F3E8F1")
GREY = colors.HexColor("#5F5F5F"); LINE = colors.HexColor("#D9CCD6"); INK = colors.HexColor("#222222")
ZEBRA = colors.HexColor("#FAF6F9")

W, H = A4
LM = RM = 20 * mm; TM = 24 * mm; BM = 20 * mm
CW = W - LM - RM

S = {}
S["body"] = ParagraphStyle("body", fontName="Sans", fontSize=10, leading=14, textColor=INK, spaceAfter=5)
S["cell"] = ParagraphStyle("cell", parent=S["body"], fontSize=8.8, leading=11.4, spaceAfter=0)
S["hcell"] = ParagraphStyle("hcell", parent=S["cell"], fontName="Sans-B", textColor=colors.white)
S["part"] = ParagraphStyle("part", fontName="Sans", fontSize=9, textColor=PURPLE, leading=12, spaceAfter=2)
S["h1"] = ParagraphStyle("h1", fontName="Sans-B", fontSize=17, leading=21, textColor=PURPLE, spaceBefore=2, spaceAfter=10)
S["h2"] = ParagraphStyle("h2", fontName="Sans-B", fontSize=12, leading=15, textColor=INK, spaceBefore=10, spaceAfter=5)
S["h3"] = ParagraphStyle("h3", fontName="Sans-B", fontSize=10, leading=13, textColor=PURPLE, spaceBefore=8, spaceAfter=3)
S["bullet"] = ParagraphStyle("bullet", parent=S["body"], leftIndent=12, bulletIndent=2, spaceAfter=2.5)
S["code"] = ParagraphStyle("code", fontName="Mono", fontSize=8.2, leading=10.6, textColor=INK)
S["note"] = ParagraphStyle("note", parent=S["body"], fontSize=9.4, leading=13, spaceAfter=0)
S["notelabel"] = ParagraphStyle("notelabel", parent=S["note"], fontName="Sans-B", textColor=PURPLE, spaceAfter=2)


def x(t):
    """Escape model text for reportlab paragraphs; ₹ is not in the font so it becomes INR."""
    return escape(str(t if t is not None else "")).replace("₹", "INR ").replace("\n", "<br/>")


def P(t, s="body"):
    return Paragraph(x(t), S[s])


def bullets(items):
    return [Paragraph(x(i), S["bullet"], bulletText="•") for i in items if i]


def tbl(header, rows, widths, pad=4):
    data = [[Paragraph(x(h), S["hcell"]) for h in header]] + [[Paragraph(x(c), S["cell"]) for c in r] for r in rows]
    t = Table(data, colWidths=[w * CW for w in widths], repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), PURPLE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), pad),
          ("BOTTOMPADDING", (0, 0), (-1, -1), pad), ("LEFTPADDING", (0, 0), (-1, -1), 5),
          ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
    st += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(2, len(data), 2)]
    t.setStyle(TableStyle(st))
    return t


def kv(rows, w=(0.26, 0.74)):
    data = [[Paragraph(x(k), S["cell"]), Paragraph(x(v), S["cell"])] for k, v in rows]
    t = Table(data, colWidths=[w[0] * CW, w[1] * CW])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), PURPLE_L), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
    return t


def note(paragraphs, label="Note"):
    paragraphs = [p for p in paragraphs if p]
    if not paragraphs:
        return Spacer(1, 0)
    body = Paragraph("<br/><br/>".join(x(p) for p in paragraphs), S["note"])
    t = Table([[[Paragraph(label, S["notelabel"]), body]]], colWidths=[CW])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PURPLE_L), ("LINEBEFORE", (0, 0), (0, -1), 2.5, PURPLE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return KeepTogether([Spacer(1, 6), t])


def code(text):
    t = Table([[Preformatted(str(text).strip("\n").replace("₹", "INR "), S["code"], maxLineLength=105)]], colWidths=[CW])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F6F6F6")),
                           ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
                           ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def section(part, title):
    return [Paragraph(x(part.upper()), S["part"]), Paragraph(x(title), S["h1"])]


# ---------------- wireframe (auto layout from the page's visuals and slicers)
def wireframe_blocks(page):
    """Returns blocks (x, y, w, h, label, kind) as fractions of the canvas. Shared logic with the web view."""
    blocks = [(0, 0, 1, .12, page.get("name", ""), "title")]
    slicers = [s.strip() for s in str(page.get("slicers", "")).split(",") if s.strip() and s.strip().lower() != "none"][:4]
    visuals = page.get("visuals", [])
    cards = [v for v in visuals if "card" in v.get("type", "").lower()][:5]
    others = [v for v in visuals if v not in cards][:6]
    y = .12
    if slicers:
        w = 1 / len(slicers)
        for i, s in enumerate(slicers):
            blocks.append((i * w, y, w, .11, "Slicer: " + s.split("(")[0].strip(), "slicer"))
        y += .11
    if cards:
        w = 1 / len(cards)
        for i, c in enumerate(cards):
            blocks.append((i * w, y, w, .17, c.get("visual", ""), "card"))
        y += .17
    if others:
        rest = 1 - y
        cols = 1 if len(others) == 1 else 2
        rows = (len(others) + cols - 1) // cols
        rh = rest / rows
        for i, v in enumerate(others):
            r, c = divmod(i, cols)
            full = cols == 1 or (i == len(others) - 1 and len(others) % 2 == 1)
            bx, bw = (0, 1) if full else (c / cols, 1 / cols)
            blocks.append((bx, y + r * rh, bw, rh, f"{v.get('visual', '')}\n({v.get('type', '')})", "visual"))
    return blocks


def _fit(text, font, size, width):
    while text and stringWidth(text, font, size) > width:
        text = text[:-2] + "…" if len(text) > 2 else ""
        text = text.replace("……", "…")
    return text


def wireframe(page, h=62 * mm):
    d = Drawing(CW, h)
    d.add(Rect(0, 0, CW, h, fillColor=colors.white, strokeColor=GREY, strokeWidth=0.8))
    for bx, by, bw, bh, lab, kind in wireframe_blocks(page):
        px, pw, ph = bx * CW, bw * CW, bh * h
        py = h - by * h - ph
        fill = {"slicer": colors.HexColor("#EDE3EB"), "card": PURPLE_L, "visual": colors.HexColor("#F7F7F7"),
                "title": PURPLE}[kind]
        d.add(Rect(px + 2, py + 2, pw - 4, ph - 4, fillColor=fill, strokeColor=LINE, strokeWidth=0.6, rx=2, ry=2))
        font = "Sans-B" if kind == "title" else "Sans"
        lines = [_fit(ln, font, 7.5, pw - 10) for ln in lab.split("\n")]
        for i, ln in enumerate(lines):
            d.add(String(px + pw / 2, py + ph / 2 + (len(lines) / 2 - i - 0.75) * 9, ln, fontName=font, fontSize=7.5,
                         fillColor=colors.white if kind == "title" else INK, textAnchor="middle"))
    return d


# ---------------- build
def build_pdf(pb, out_path):
    dc = pb["doc_control"]
    header_text = f"Power BI Playbook  ·  {dc['client']} — {dc['project']}"

    def cover_page(c, doc):
        c.saveState()
        img = ImageReader(LOGO); iw, ih = img.getSize()
        lw = 62 * mm; lh = lw * ih / iw
        top = H - 60 * mm
        c.drawImage(img, LM, top - lh, width=lw, height=lh, mask="auto")
        y = top - lh - 26 * mm
        c.setFillColor(PURPLE); c.rect(LM, y + 16 * mm, 18 * mm, 1.6 * mm, stroke=0, fill=1)
        c.setFont("Sans-B", 30); c.setFillColor(INK); c.drawString(LM, y, "Power BI Playbook")
        c.setFont("Sans", 15); c.setFillColor(PURPLE); c.drawString(LM, y - 11 * mm, _fit(dc["project"], "Sans", 15, CW))
        c.setFont("Sans", 12); c.setFillColor(GREY); c.drawString(LM, y - 18.5 * mm, _fit(dc["client"], "Sans", 12, CW))
        c.restoreState()

    def normal_page(c, doc):
        c.saveState()
        img = ImageReader(LOGO); iw, ih = img.getSize()
        lw = 17 * mm; lh = lw * ih / iw
        c.drawImage(img, W - RM - lw, H - 13 * mm - lh / 2, width=lw, height=lh, mask="auto")
        c.setFont("Sans", 8); c.setFillColor(GREY)
        c.drawString(LM, H - 13 * mm - 2.5, _fit(header_text, "Sans", 8, CW - 25 * mm))
        c.setStrokeColor(LINE); c.setLineWidth(0.5)
        c.line(LM, H - 17.5 * mm, W - RM, H - 17.5 * mm); c.line(LM, 13 * mm, W - RM, 13 * mm)
        c.drawString(LM, 9 * mm, _fit(f"Xebia  ·  Confidential — prepared for {dc['client']}", "Sans", 8, CW - 25 * mm))
        c.drawRightString(W - RM, 9 * mm, f"Page {doc.page}")
        c.restoreState()

    doc = BaseDocTemplate(out_path, pagesize=A4, leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM,
                          title=f"Power BI Playbook — {dc['client']} {dc['project']}", author="Xebia")
    fr = Frame(LM, BM, CW, H - TM - BM, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate("cover", frames=[fr], onPage=cover_page),
                          PageTemplate("normal", frames=[fr], onPage=normal_page)])

    st = [NextPageTemplate("normal"), PageBreak()]

    # 1 + 2
    st += section("Part A · Overview", "1. Document Control")
    st.append(kv([("Client", dc["client"]), ("Project", dc["project"]), ("Business Domain", dc["domain"]),
                  ("Business Owner", dc["business_owner"]), ("Generated On", dc["generated_on"]),
                  ("Prepared By", dc["prepared_by"])]))
    st.append(Spacer(1, 14))
    es = pb["executive_summary"]
    st.append(Paragraph("2. Executive Summary", S["h1"]))
    st += [Paragraph("Objective", S["h3"]), P(es["objective"]), Paragraph("Scope", S["h3"]), P(es["scope"]),
           Paragraph("At a glance", S["h2"])]
    g = es["at_a_glance"]
    gt = Table([[str(g["source_systems"]), str(g["tables"]), str(g["columns"]), str(g["kpis"]), str(g["report_pages"])],
                ["Source systems", "Tables", "Columns", "KPIs", "Report pages"]], colWidths=[CW / 5] * 5)
    gt.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Sans", 20), ("TEXTCOLOR", (0, 0), (-1, 0), PURPLE),
                            ("FONT", (0, 1), (-1, 1), "Sans", 8.5), ("TEXTCOLOR", (0, 1), (-1, 1), GREY),
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("BACKGROUND", (0, 0), (-1, -1), PURPLE_L),
                            ("LINEAFTER", (0, 0), (-2, -1), 1, colors.white), ("TOPPADDING", (0, 0), (-1, 0), 8),
                            ("BOTTOMPADDING", (0, 1), (-1, 1), 8)]))
    st.append(gt)
    st.append(Paragraph("Key design decisions", S["h2"]))
    st += bullets(es["key_decisions"])
    st.append(PageBreak())

    # 3
    ss = pb["source_systems"]
    st += section("Part B · Data Foundation", "3. Source System Inventory")
    st.append(P("Each source system from the BRD, with the recommended connection approach."))
    st.append(tbl(["Source", "Type", "Owner", "History", "Refresh", "Connector", "Gateway"],
                  [[i["source"], i["type"], i["owner"], i["history"], i["refresh"], i["connector"], i["gateway"]]
                   for i in ss["items"]], [0.16, 0.13, 0.14, 0.11, 0.09, 0.20, 0.17]))
    st.append(note(ss["notes"]))
    st.append(PageBreak())

    # 4
    t = pb["tables"]
    st += section("Part B · Data Foundation", "4. Table & Column Catalogue")
    st.append(Paragraph("Tables", S["h2"]))
    st.append(tbl(["Table (source name)", "Model name", "Role", "Rows", "Power Query transformations"],
                  [[i["source_table"], i["model_name"], i["role"], i["rows"], i["transformations"]] for i in t["items"]],
                  [0.24, 0.13, 0.11, 0.13, 0.39]))
    st.append(Paragraph("Columns", S["h2"]))
    st.append(tbl(["Model table", "Column", "Power BI type", "Key", "Notes"],
                  [[c["model_table"], c["column"], c["pbi_type"], c["key"], c["notes"]] for c in t["columns"]],
                  [0.15, 0.19, 0.15, 0.15, 0.36], pad=2.6))
    st.append(PageBreak())

    # 5
    dm = pb["data_model"]
    st += section("Part B · Data Foundation", "5. Data Model Design")
    st.append(Paragraph("Relationships", S["h2"]))
    st.append(tbl(["From (many)", "To (one)", "Cardinality", "Cross-filter", "Basis"],
                  [[r["from"], r["to"], r["cardinality"], r["cross_filter"], r["basis"]] for r in dm["relationships"]],
                  [0.25, 0.22, 0.15, 0.13, 0.25]))
    st.append(note(dm["notes"]))
    st.append(PageBreak())

    # 6
    k = pb["kpis"]
    st += section("Part C · Measures & Report Design", "6. KPI & DAX Catalogue")
    st.append(P(k["intro"]))
    if k.get("base_measures"):
        st += [Paragraph("Base measures", S["h2"]), code(k["base_measures"])]
    st.append(Paragraph("KPIs", S["h2"]))
    for item in k["items"]:
        head = Table([[Paragraph(x(item["name"]), ParagraphStyle("k", parent=S["cell"], fontName="Sans-B", fontSize=10,
                                                                 textColor=colors.white)),
                       Paragraph(x(f"Priority: {item['priority']}"),
                                 ParagraphStyle("k2", parent=S["cell"], textColor=colors.white, alignment=2))]],
                     colWidths=[0.75 * CW, 0.25 * CW])
        head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PURPLE), ("TOPPADDING", (0, 0), (-1, -1), 5),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
        st.append(KeepTogether([Spacer(1, 8), head,
                                kv([("Business definition", item["definition"]), ("Uses", item["uses"])], (0.22, 0.78)),
                                Spacer(1, 3), code(item["dax"])]))
    st.append(PageBreak())

    # 7
    rp = pb["report_pages"]
    st += section("Part C · Measures & Report Design", "7. Report Page Design")
    st.append(P(rp["intro"]))
    for i, pg in enumerate(rp["pages"]):
        if i:
            st.append(PageBreak())
        st += [Paragraph(x(pg["name"]), S["h2"]),
               kv([("Purpose", pg["purpose"]), ("Priority", pg["priority"]), ("For personas", pg["personas"]),
                   ("KPIs shown", pg["kpis_shown"]), ("Slicers", pg["slicers"]), ("Page filters", pg["page_filters"]),
                   ("Drill-down / drill-through", pg["drill"]), ("Interactions", pg["interactions"])], (0.24, 0.76)),
               Paragraph("Visuals", S["h3"]),
               tbl(["#", "Visual", "Type", "Fields"],
                   [[str(n + 1), v["visual"], v["type"], v["fields"]] for n, v in enumerate(pg["visuals"])],
                   [0.05, 0.24, 0.20, 0.51]),
               KeepTogether([Paragraph("Layout wireframe", S["h3"]), wireframe(pg)])]
    st.append(PageBreak())

    # 8
    a = pb["audience"]
    st += section("Part C · Measures & Report Design", "8. Audience & Access")
    st.append(P(a["source_note"]))
    if a["personas"]:
        st.append(tbl(["Persona", "Users", "Key decisions", "Data access", "Primary pages", "Device"],
                      [[p["persona"], p["users"], p["key_decisions"], p["data_access"], p["primary_pages"], p["device"]]
                       for p in a["personas"]], [0.16, 0.08, 0.29, 0.13, 0.20, 0.14]))
    if a["recommendations"]:
        st.append(Paragraph("Recommendations", S["h2"]))
        st += bullets(a["recommendations"])
    st.append(PageBreak())

    # 9
    sec = pb["security"]
    st += section("Part C · Measures & Report Design", "9. Security & RLS")
    st.append(P(sec["source_note"]))
    if sec["security_table_description"] or sec["security_table_columns"]:
        st.append(Paragraph("Security table", S["h2"]))
        if sec["security_table_description"]:
            st.append(P(sec["security_table_description"]))
        if sec["security_table_columns"]:
            st.append(tbl(["Column", "Example", "Notes"], [[c["column"], c["example"], c["notes"]]
                                                          for c in sec["security_table_columns"]], [0.25, 0.35, 0.40]))
    if sec["roles"]:
        st.append(Paragraph("Roles", S["h2"]))
        st.append(tbl(["Role", "Members", "Filter table", "BRD requirement"],
                      [[r["role"], r["members"], r["filter_table"], r["requirement"]] for r in sec["roles"]],
                      [0.16, 0.26, 0.16, 0.42]))
    if sec["rls_dax"]:
        st.append(KeepTogether([Paragraph("Role filter expressions", S["h3"]), code(sec["rls_dax"])]))
    if sec["recommendations"]:
        st.append(Paragraph("Additional recommendations", S["h2"]))
        st += bullets(sec["recommendations"])
    st.append(PageBreak())

    # 10
    rf = pb["refresh"]
    st += section("Part D · Build, Deploy & Deliver", "10. Refresh & Performance")
    st.append(Paragraph("Refresh schedule", S["h2"]))
    st.append(tbl(["Source", "Required", "Schedule", "Method"],
                  [[r["source"], r["required"], r["schedule"], r["method"]] for r in rf["schedule"]],
                  [0.22, 0.27, 0.25, 0.26]))
    if rf["incremental"]:
        st.append(Paragraph(x(rf["incremental_title"] or "Incremental refresh"), S["h2"]))
        st.append(kv([(i["label"], i["value"]) for i in rf["incremental"]]))
    if rf["practices"]:
        st.append(Paragraph("Performance practices", S["h2"]))
        st += bullets(rf["practices"])
    st.append(PageBreak())

    # 11
    dp = pb["deployment"]
    st += section("Part D · Build, Deploy & Deliver", "11. Deployment & Governance")
    st.append(Paragraph("Workspaces & pipeline", S["h2"]))
    st.append(tbl(["Stage", "Workspace", "Purpose", "Who has access"],
                  [[w["stage"], w["workspace"], w["purpose"], w["access"]] for w in dp["workspaces"]],
                  [0.17, 0.20, 0.35, 0.28]))
    st += [Spacer(1, 6), P(dp["pipeline"]), Paragraph("Governance", S["h2"])]
    st += bullets(dp["governance"])
    st.append(PageBreak())

    # 12
    dl = pb["delivery"]
    st += section("Part D · Build, Deploy & Deliver", "12. Delivery Plan")
    st.append(P(dl["intro"]))
    st.append(tbl(["Sprint", "Goal", "Scope", "Exit criteria"],
                  [[s["sprint"], s["goal"], s["scope"], s["exit_criteria"]] for s in dl["sprints"]],
                  [0.11, 0.16, 0.44, 0.29]))
    if dl["dependencies"]:
        st.append(Paragraph("Dependencies", S["h2"]))
        st += bullets(dl["dependencies"])

    doc.build(st)
    return out_path
