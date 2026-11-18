from __future__ import annotations

import base64
import io
import os
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from openpyxl.styles import Alignment, Font, PatternFill

from .compare import run_check
from .pbi import extract_model, extract_report, report_connection
from .report_input import extract_structured_report

app = FastAPI(title="Semantic Model Compatibility Checker", version="1.0.0")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
MAX_FILE_SIZE = 200 * 1024 * 1024
REPORT_ALLOWED = {".pbix", ".pbit", ".xlsx", ".docx"}
MODEL_ALLOWED = {".pbix", ".pbit"}
FILLS = {"Will break": "F8D0CC", "Check manually": "FCEBB6", "OK": "D5EBD9",
         "Not compatible": "F8D0CC", "Compatible with warnings": "FCEBB6", "Compatible": "D5EBD9"}


async def read_upload(f: UploadFile, label: str, allowed: set[str]) -> tuple[bytes, str]:
    name = f.filename or label
    if Path(name).suffix.lower() not in allowed:
        extensions = ", ".join(sorted(allowed))
        raise HTTPException(400, f"{label}: please upload one of these file types: {extensions}.")
    data = await f.read()
    if not data:
        raise HTTPException(400, f"{label}: the file is empty.")
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(413, f"{label}: file is larger than 200 MB.")
    return data, name


def style_sheet(ws, color_col: str | None = None):
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A5F")
    headers = [c.value for c in ws[1]]
    for col in ws.columns:
        width = max((len(str(c.value or "")) for c in list(col)[:120]), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 11), 60)
    if color_col in headers:
        idx = headers.index(color_col) + 1
        for row in ws.iter_rows(min_row=2):
            fill = FILLS.get(str(row[idx - 1].value))
            if not fill:
                st = str(row[idx - 1].value)
                fill = "F8D0CC" if st.startswith("Missing") or st in ("Type mismatch", "Moved to another table") \
                    else ("FCEBB6" if st not in ("OK", "Report-level measure") else None)
            if fill:
                row[idx - 1].fill = PatternFill("solid", fgColor=fill)


def build_workbook(result: dict, meta: dict, model: dict) -> bytes:
    out = io.BytesIO()
    summary = [{"Item": "Verdict", "Value": result["verdict"]}] + [{"Item": k, "Value": v} for k, v in meta.items()] \
        + [{"Item": k, "Value": v} for k, v in result["summary"].items()]
    inventory = [{"Table": t, "Columns": len(v["columns"]), "Measures": len(v["measures"]),
                  "Hierarchies": len(v["hierarchies"])} for t, v in sorted(model["tables"].items())]
    sheets = {
        "Summary": summary,
        "Problems": result["problems"],
        "Warnings": result["warnings"],
        "Visual_Impact": sorted(result["visual_rows"], key=lambda r: (r["Result"] == "OK", r["Page"])),
        "All_Fields": result["unique_rows"],
        "Usage_Detail": result["all_rows"],
        "Target_Model_Tables": inventory,
    }
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        for name, records in sheets.items():
            df = pd.DataFrame(records) if records else pd.DataFrame([{"Status": "Nothing to report."}])
            df.to_excel(w, sheet_name=name, index=False)
            style_sheet(w.sheets[name], "Status" if "Status" in df.columns else ("Result" if "Result" in df.columns else None))
        ws = w.sheets["Summary"]
        ws["B2"].fill = PatternFill("solid", fgColor=FILLS.get(result["verdict"], "FFFFFF"))
        ws["B2"].font = Font(bold=True)
        ws["B2"].alignment = Alignment(horizontal="left")
    return out.getvalue()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/check")
async def check(report: UploadFile = File(...), model: UploadFile = File(...)):
    report_bytes, report_name = await read_upload(report, "Report file", REPORT_ALLOWED)
    model_bytes, model_name = await read_upload(model, "Semantic model file", MODEL_ALLOWED)

    report_suffix = Path(report_name).suffix.lower()
    if report_suffix in {".pbix", ".pbit"}:
        try:
            with zipfile.ZipFile(io.BytesIO(report_bytes)) as zf:
                rep = extract_report(zf)
                conn = report_connection(zf)
        except zipfile.BadZipFile:
            raise HTTPException(400, "Report file is not a valid Power BI package.")
        except ValueError as exc:
            raise HTTPException(422, f"Report file: {exc}")
    else:
        try:
            usage = extract_structured_report(report_bytes, report_suffix)
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            raise HTTPException(422, f"Report file: {exc}")
        rep = {"usage": usage, "ext_measures": set(), "pages": 0, "visuals": 0}
        conn = f"Structured field list ({report_suffix[1:].upper()})"

    tmp = None
    try:
        suffix = Path(model_name).suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as t:
            t.write(model_bytes)
            tmp = Path(t.name)
        with zipfile.ZipFile(tmp) as zf:
            target, source = extract_model(zf, tmp)
    except zipfile.BadZipFile:
        raise HTTPException(400, "Semantic model file is not a valid Power BI package.")
    except ValueError as exc:
        raise HTTPException(422, f"Semantic model file: {exc}")
    finally:
        if tmp and tmp.exists():
            try:
                os.unlink(tmp)
            except OSError:
                pass

    if not target["tables"]:
        raise HTTPException(422, "Semantic model file: no tables were found in the model.")

    result = run_check(rep["usage"], rep["ext_measures"], target)
    meta = {"Report file": report_name, "Report type": conn, "Pages": rep["pages"], "Visuals": rep["visuals"],
            "Target model file": model_name, "Target model read from": source, "Target model tables": len(target["tables"])}
    excel = build_workbook(result, meta, target)

    return {
        "verdict": result["verdict"],
        "summary": result["summary"],
        "meta": meta,
        "problems": result["problems"][:300],
        "warnings": result["warnings"][:300],
        "visuals": sorted(result["visual_rows"], key=lambda r: (r["Result"] == "OK", r["Page"]))[:300],
        "filename": f"{Path(report_name).stem}_vs_{Path(model_name).stem}_compatibility.xlsx",
        "excel_base64": base64.b64encode(excel).decode(),
    }


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
