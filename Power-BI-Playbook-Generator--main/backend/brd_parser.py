"""
Reads a BRD without rejecting it.

- If the file follows Power_BI_BRD_Template v1.0, the known fields are picked out (best effort).
- Whatever the layout, the full readable content of the file is also extracted as text,
  so the AI can use everything that was provided and fill gaps from its own knowledge.

Supported: .xlsx / .xlsm, .csv, .txt / .md, .docx, .pdf
Nothing here raises for missing or wrong fields. Only an unreadable or empty file is an error.
"""
import csv
import io
import os

MAX_TEXT_CHARS = 120_000  # keeps very large files inside the model's context window

TEMPLATE_SHEETS = {
    "Source Systems": ("source_systems", ["name", "system_type", "owner", "history", "refresh"],
                       ["Source Name", "System Type", "Data Owner", "History Required", "Refresh Frequency"]),
    "Tables": ("tables", ["source_system", "name", "description", "row_count"],
               ["Source System", "Table Name", "Description", "Approx. Row Count"]),
    "Columns": ("columns", ["table", "name", "description", "key_type", "references"],
                ["Table Name", "Column Name", "Description", "Key Type", "References (Table.Column)"]),
    "KPIs": ("kpis", ["name", "description", "target", "priority"],
             ["KPI Name", "Description", "Target / Threshold", "Priority"]),
    "Report Pages": ("report_pages", ["name", "purpose", "expected_visuals", "priority"],
                     ["Page Name", "Purpose", "Expected Visuals", "Priority"]),
    "Audience": ("audience", ["role", "users", "key_decisions", "data_access"],
                 ["Persona / Role", "No. of Users", "Key Decisions They Make", "Data Access Level"]),
    "Security & NFR": ("security_nfr", ["category", "requirement", "details", "priority"],
                       ["Category", "Requirement", "Details / Rule Logic", "Priority"]),
}
OVERVIEW_FIELDS = [("client", "Client Name"), ("project", "Project Name"), ("domain", "Business Domain"),
                   ("business_owner", "Business Owner"), ("objective", "Business Objective"), ("in_scope", "In Scope")]
GUIDANCE_HINTS = ("what to fill", "pick from dropdown", "pick the", "exact name as in", "name of the system",
                  "what one row", "short title of", "job role of", "must / should / could")


class BRDReadError(Exception):
    pass


def _val(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return " ".join(str(v).split())


def _norm(v):
    return _val(v).replace("*", "").strip().lower()


def _is_guidance(values):
    joined = " ".join(values).lower()
    return any(h in joined for h in GUIDANCE_HINTS)


# ---------------------------------------------------------------- Excel
def _read_excel(path):
    from openpyxl import load_workbook
    try:
        wb = load_workbook(path, data_only=True, read_only=False)
    except Exception:
        raise BRDReadError("The Excel file could not be opened. Save it as .xlsx and try again.")

    text_parts, template = [], {"overview": {}}
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        rows = []
        for row in ws.iter_rows(values_only=True):
            vals = [_val(v) for v in row]
            while vals and not vals[-1]:
                vals.pop()
            if any(vals):
                rows.append(vals)
        if rows:
            text_parts.append(f"### Sheet: {ws.title}\n" + "\n".join(" | ".join(r) for r in rows))

        # ---- best-effort template extraction
        title = ws.title.strip()
        if title.lower() == "project overview":
            for r in range(1, ws.max_row + 1):
                label = _norm(ws.cell(r, 1).value)
                for key, lab in OVERVIEW_FIELDS:
                    if label == lab.lower():
                        template["overview"][key] = _val(ws.cell(r, 2).value)
            continue
        match = next((k for k in TEMPLATE_SHEETS if k.lower() == title.lower()), None)
        if not match:
            continue
        key, fields, headers = TEMPLATE_SHEETS[match]
        # find the header row anywhere in the first 10 rows
        header_row, colmap = None, {}
        for r in range(1, min(ws.max_row, 10) + 1):
            found = {_norm(c.value): c.column for c in ws[r] if c.value}
            hits = {f: found.get(h.lower()) for f, h in zip(fields, headers)}
            if sum(1 for v in hits.values() if v) >= 2:
                header_row, colmap = r, hits
                break
        if not header_row:
            continue
        items = []
        for r in range(header_row + 1, ws.max_row + 1):
            rec = {f: (_val(ws.cell(r, c).value) if c else "") for f, c in colmap.items()}
            if not any(rec.values()) or _is_guidance(list(rec.values())):
                continue
            items.append(rec)
        template[key] = items
    return "\n\n".join(text_parts), template


# ---------------------------------------------------------------- other formats
def _read_csv(path):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        rows = [" | ".join(_val(c) for c in row) for row in csv.reader(f) if any(c.strip() for c in row)]
    return "\n".join(rows)


def _read_txt(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _read_docx(path):
    try:
        import docx
    except ImportError:
        raise BRDReadError("Word support needs the python-docx package. Run: pip install -r requirements.txt")
    try:
        d = docx.Document(path)
    except Exception:
        raise BRDReadError("The Word file could not be opened. Save it as .docx and try again.")
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for row in t.rows:
            cells = [_val(c.text) for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _read_pdf(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise BRDReadError("PDF support needs the pypdf package. Run: pip install -r requirements.txt")
    try:
        reader = PdfReader(path)
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        raise BRDReadError("The PDF could not be read. If it is a scanned image, upload the original document instead.")


SUPPORTED = {".xlsx": "excel", ".xlsm": "excel", ".csv": "csv", ".txt": "txt", ".md": "txt",
             ".docx": "docx", ".pdf": "pdf"}


def read_brd(path, filename):
    """Returns {"text": full readable content, "template": fields found (may be partial or empty),
    "follows_template": bool}. Raises BRDReadError only for unreadable/empty/unsupported files."""
    ext = os.path.splitext(filename.lower())[1]
    kind = SUPPORTED.get(ext)
    if not kind:
        raise BRDReadError(f"'{ext or filename}' files are not supported. Use Excel (.xlsx), Word (.docx), PDF, CSV or text.")

    template = {"overview": {}}
    if kind == "excel":
        text, template = _read_excel(path)
    elif kind == "csv":
        text = _read_csv(path)
    elif kind == "txt":
        text = _read_txt(path)
    elif kind == "docx":
        text = _read_docx(path)
    else:
        text = _read_pdf(path)

    text = (text or "").strip()
    if not text:
        raise BRDReadError("No readable content was found in the file.")
    truncated = len(text) > MAX_TEXT_CHARS
    if truncated:
        text = text[:MAX_TEXT_CHARS] + "\n\n[... content truncated ...]"

    filled_lists = [k for k in ("source_systems", "tables", "columns", "kpis", "report_pages") if template.get(k)]
    follows = len(filled_lists) >= 2
    overview = {k: v for k, v in template.get("overview", {}).items() if v}
    return {"text": text, "template": template if follows or overview else {},
            "overview": overview, "follows_template": follows, "truncated": truncated}
