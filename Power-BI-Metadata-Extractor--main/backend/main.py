from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Power BI Metadata Extractor", version="1.0.0")
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
MAX_FILE_SIZE = 200 * 1024 * 1024
SENSITIVE = re.compile(r"(password|passwd|token|secret|credential|access.?key|client.?secret)", re.I)


def json_load(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return {}
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return {}


def records_from(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, pd.DataFrame):
        return value.where(pd.notna(value), None).to_dict(orient="records")
    if isinstance(value, dict):
        return [value]
    try:
        return [x if isinstance(x, dict) else {"Value": str(x)} for x in list(value)]
    except Exception:
        return []


def df_records(model: Any, attr: str) -> list[dict[str, Any]]:
    try:
        return records_from(getattr(model, attr))
    except Exception:
        return []


def safe_json_text(value: str) -> str:
    # Avoid returning values for keys that look like credentials.
    try:
        obj = json.loads(value)
        return json.dumps(redact(obj), ensure_ascii=False)
    except Exception:
        return value


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if SENSITIVE.search(str(k)) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def get_key(obj: Any, *keys: str) -> Any:
    if not isinstance(obj, dict):
        return ""
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return ""


def walk_objects(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_objects(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk_objects(value)


def extract_report_layout(zf: zipfile.ZipFile, names: list[str], filename: str, file_size: int) -> dict[str, list[dict[str, Any]]]:
    sheets: dict[str, list[dict[str, Any]]] = {
        "Report_Summary": [], "Report_Pages": [], "Visuals": [], "Visual_Fields": [],
        "Report_Filters": [], "Package_Contents": [], "Warnings": []
    }
    layout_name = next((n for n in names if n.lower() == "report/layout"), None)
    if not layout_name:
        sheets["Warnings"].append({"Area": "Report layout", "Finding": "No Report/Layout part was found in the package.", "Details": "The file may use an unsupported format or may not be a valid PBIX/PBIT archive."})
        return sheets

    try:
        layout = json.loads(zf.read(layout_name).decode("utf-8-sig"))
    except Exception as exc:
        sheets["Warnings"].append({"Area": "Report layout", "Finding": "Report/Layout could not be parsed as JSON.", "Details": str(exc)})
        return sheets

    sections = layout.get("sections", []) if isinstance(layout, dict) else []
    page_rows, visual_rows, visual_field_rows, filter_rows = [], [], [], []
    for page_index, page in enumerate(sections, start=1):
        page_name = get_key(page, "name", "displayName")
        page_display = get_key(page, "displayName", "name")
        page_visuals = page.get("visualContainers", []) if isinstance(page, dict) else []
        page_filters = page.get("filters", [])
        page_rows.append({
            "Page order": page_index, "Page internal name": page_name, "Page display name": page_display,
            "Page type": get_key(page, "visibility", "type"), "Visual count": len(page_visuals),
            "Filter count": len(page_filters), "Width": get_key(page, "width"),
            "Height": get_key(page, "height"), "Page JSON properties": json.dumps(redact({k:v for k,v in page.items() if k not in {"visualContainers", "filters"}}), ensure_ascii=False)[:12000]
        })
        for f_index, filt in enumerate(page_filters, start=1):
            filter_rows.append({
                "Scope": "Page", "Page": page_display or page_name, "Visual": "",
                "Filter order": f_index, "Filter definition": json.dumps(redact(filt), ensure_ascii=False)[:12000]
            })
        for v_index, visual in enumerate(page_visuals, start=1):
            config_raw = visual.get("config", "{}") if isinstance(visual, dict) else "{}"
            config = json_load(config_raw)
            data_raw = visual.get("dataTransforms", "{}") if isinstance(visual, dict) else "{}"
            data_transforms = json_load(data_raw)
            query_raw = visual.get("query", "{}") if isinstance(visual, dict) else "{}"
            query = json_load(query_raw)
            objects = list(walk_objects(config))
            visual_type = next((get_key(o, "visualType") for o in objects if get_key(o, "visualType")), "")
            visual_name = get_key(visual, "name", "id") or f"Visual {v_index}"
            position = visual.get("position", {}) if isinstance(visual, dict) else {}
            visual_rows.append({
                "Page": page_display or page_name, "Visual order": v_index, "Visual name / ID": visual_name,
                "Visual type": visual_type, "X": get_key(position, "x"), "Y": get_key(position, "y"),
                "Width": get_key(position, "width"), "Height": get_key(position, "height"),
                "Title / config": json.dumps(redact(config), ensure_ascii=False)[:12000],
                "Query definition": json.dumps(redact(query), ensure_ascii=False)[:12000],
                "Data transform definition": json.dumps(redact(data_transforms), ensure_ascii=False)[:12000],
            })
            # Best-effort field projections from query and data transforms.
            found = set()
            for obj in walk_objects(query):
                for key in ("Column", "Measure", "Hierarchy", "Aggregation", "Entity"):
                    val = obj.get(key)
                    if isinstance(val, dict):
                        entity = val.get("Expression", val)
                        if isinstance(entity, dict):
                            source = entity.get("SourceRef", {})
                            source_name = get_key(source, "Source")
                            prop = get_key(entity, "Property", "Name")
                            if prop or source_name:
                                tup = (str(source_name), str(prop), key)
                                if tup not in found:
                                    found.add(tup)
                                    visual_field_rows.append({"Page": page_display or page_name, "Visual": visual_name, "Source reference": source_name, "Field / measure": prop, "Projection type": key})
                for key, val in obj.items():
                    if key.lower() in {"queryref", "displayname", "nativequeryref"} and isinstance(val, str):
                        tup = ("", val, key)
                        if tup not in found:
                            found.add(tup)
                            visual_field_rows.append({"Page": page_display or page_name, "Visual": visual_name, "Source reference": "", "Field / measure": val, "Projection type": key})
            for f_index, filt in enumerate(visual.get("filters", []) if isinstance(visual, dict) else [], start=1):
                filter_rows.append({
                    "Scope": "Visual", "Page": page_display or page_name, "Visual": visual_name,
                    "Filter order": f_index, "Filter definition": json.dumps(redact(filt), ensure_ascii=False)[:12000]
                })

    sheets["Report_Pages"] = page_rows
    sheets["Visuals"] = visual_rows
    sheets["Visual_Fields"] = visual_field_rows
    sheets["Report_Filters"] = filter_rows
    sheets["Report_Summary"].append({
        "Uploaded file": filename, "File type": Path(filename).suffix.lower(),
        "File size (MB)": round(file_size / (1024 * 1024), 2),
        "Page count": len(page_rows), "Visual count": len(visual_rows),
        "Report-level filter count": len(layout.get("filters", [])) if isinstance(layout, dict) else 0,
        "Package part count": len(names),
    })
    for name in names:
        sheets["Package_Contents"].append({
            "Package path": name,
            "Extension": Path(name).suffix.lower(),
            "Likely purpose": package_purpose(name),
            "Size (bytes)": ""
        })
    return sheets


def package_purpose(name: str) -> str:
    lower = name.lower()
    if lower == "report/layout": return "Report pages, visuals and layout JSON"
    if "datamodelschema" in lower: return "Semantic model schema metadata"
    if "metadata.sqlitedb" in lower: return "Embedded semantic model metadata database"
    if "datamashup" in lower: return "Power Query mashup container"
    if lower == "connections": return "Data connection manifest"
    if "diagramstate" in lower: return "Model diagram layout"
    if lower.endswith(".json"): return "JSON metadata"
    return "Packaged report/model resource"


def extract_connections(zf: zipfile.ZipFile, names: list[str]) -> list[dict[str, Any]]:
    name = next((n for n in names if n.lower() == "connections"), None)
    if not name:
        return []
    try:
        data = json.loads(zf.read(name).decode("utf-8-sig"))
        result = []
        for item in walk_objects(data):
            if any(k in item for k in ("connectionString", "connectionType", "server", "database")):
                cleaned = redact(item)
                result.append({"Connection metadata": json.dumps(cleaned, ensure_ascii=False)[:12000]})
        return result
    except Exception:
        return [{"Connection metadata": "Connections part was present but could not be parsed."}]


def extract_with_pbixray(path: Path, sheets: dict[str, list[dict[str, Any]]]) -> None:
    try:
        from pbixray import PBIXRay
    except Exception as exc:
        sheets["Warnings"].append({"Area": "Semantic model", "Finding": "PBIXRay is not available.", "Details": f"Install the project requirements in the recommended Python 3.12 environment. {exc}"})
        return

    try:
        model = PBIXRay(str(path))
    except Exception as exc:
        sheets["Warnings"].append({
            "Area": "Semantic model",
            "Finding": "Embedded semantic model could not be read.",
            "Details": f"{type(exc).__name__}: {exc}. Thin/live-connected reports may not contain a local model."
        })
        return

    mapping = [
        ("Tables_Columns", "schema"),
        ("Measures", "dax_measures"),
        ("Calculated_Columns", "dax_columns"),
        ("Calculated_Tables", "dax_tables"),
        ("Relationships", "relationships"),
        ("Power_Query", "power_query"),
        ("M_Parameters", "m_parameters"),
        ("Security_RLS", "rls"),
        ("Security_OLS", "ols"),
        ("Hierarchies", "tmschema_hierarchies"),
        ("Partitions", "tmschema_partitions"),
        ("Model_Metadata", "metadata"),
        ("Perspectives", "perspectives"),
        ("Aggregations", "aggregations"),
        ("Column_Statistics", "statistics"),
    ]
    for sheet_name, attr in mapping:
        sheets[sheet_name] = df_records(model, attr)

    # Additional connection manifest from PBIXRay, redacted and normalized.
    try:
        conns = getattr(model, "connections", [])
        sheets["Connections"].extend({"Connection metadata": json.dumps(redact(item), ensure_ascii=False)[:12000]} for item in conns)
    except Exception:
        pass

    try:
        sheets["Report_Summary"][0]["Semantic model table count"] = len(getattr(model, "tables", []) or [])
        sheets["Report_Summary"][0]["Model size (bytes)"] = getattr(model, "size", "")
    except Exception:
        pass


def workbook_to_excel(sheets: dict[str, list[dict[str, Any]]]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, records in sheets.items():
            frame = pd.DataFrame(records)
            if frame.empty:
                frame = pd.DataFrame([{"Status": "No matching metadata found or this metadata is not available in the uploaded file."}])
            safe_name = sheet_name[:31]
            frame.to_excel(writer, sheet_name=safe_name, index=False)
            ws = writer.sheets[safe_name]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for cells in ws.columns:
                max_len = max((len(str(c.value or "")) for c in list(cells)[:150]), default=12)
                ws.column_dimensions[cells[0].column_letter].width = min(max(max_len + 2, 12), 58)
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True, color="FFFFFF")
                cell.fill = __import__("openpyxl").styles.PatternFill("solid", fgColor="245EEA")
    output.seek(0)
    return output.read()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Power BI Metadata Extractor"}


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    filename = file.filename or "powerbi_report"
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pbix", ".pbit"}:
        raise HTTPException(status_code=400, detail="Please upload a Power BI .pbix or .pbit file.")
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File is larger than the 200 MB upload limit.")

    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            sheets = extract_report_layout(zf, names, filename, len(contents))
            sheets["Connections"] = extract_connections(zf, names)
            if not sheets["Report_Summary"]:
                sheets["Report_Summary"] = [{"Uploaded file": filename, "File type": suffix, "File size (MB)": round(len(contents)/(1024*1024), 2)}]
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="The file is not a valid Power BI package. Please upload a .pbix or .pbit file.")

    # PBIXRay needs a path; use a temporary file and remove it immediately afterwards.
    import tempfile
    import os
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
            temp.write(contents)
            temp_path = Path(temp.name)
        extract_with_pbixray(temp_path, sheets)
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass

    sheets["Warnings"].append({
        "Area": "Coverage",
        "Finding": "Metadata coverage depends on the report format, model type and Power BI version.",
        "Details": "Thin/live reports may not embed a model. This tool reads metadata only; it does not connect to Power BI Service, resolve external permissions, or evaluate DAX/M expressions."
    })
    excel = workbook_to_excel(sheets)
    out_name = f"{Path(filename).stem}_metadata.xlsx"
    return StreamingResponse(
        io.BytesIO(excel),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'}
    )


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
