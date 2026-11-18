"""Readers for Power BI packages: report layout (fields used) and semantic model (fields available)."""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

AUTO_DATE = re.compile(r"^(LocalDateTable|DateTableTemplate)_", re.I)
# 'Table Name'[Column]  or  TableName[Column]
DAX_REF = re.compile(r"(?:'([^']+)'|\b([A-Za-z_]\w*))\[([^\]]+)\]")


# ---------------------------------------------------------------- helpers
def decode_part(raw: bytes) -> str:
    """PBIX parts are often UTF-16-LE without a BOM; PBIT/others may be UTF-8."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    if len(raw) > 3 and raw[1:2] == b"\x00":
        return raw.decode("utf-16-le")
    return raw.decode("utf-8")


def load_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        return json.loads(value)
    except ValueError:
        return {}


def read_part(zf: zipfile.ZipFile, name: str) -> Any:
    real = next((n for n in zf.namelist() if n.lower() == name.lower()), None)
    if not real:
        return None
    return json.loads(decode_part(zf.read(real)))


# ---------------------------------------------------------------- report side
def _field_from(node: dict, kind: str, scope: dict[str, str]) -> tuple[str, str, str] | None:
    """Return (table, field, kind) for a Column / Measure / Hierarchy node."""
    expr = node.get("Expression")
    if not isinstance(expr, dict):
        return None
    ref = expr.get("SourceRef")
    if not isinstance(ref, dict):
        return None
    table = ref.get("Entity") or scope.get(ref.get("Source", ""), ref.get("Source", ""))
    field = node.get("Hierarchy") if kind == "Hierarchy" else node.get("Property")
    if not table or not isinstance(field, str):
        return None
    return str(table), field, kind


def collect_fields(obj: Any, scope: dict[str, str] | None = None) -> set[tuple[str, str, str]]:
    """Walk any layout JSON, resolving query aliases (From: Name -> Entity) per scope."""
    scope = dict(scope or {})
    found: set[tuple[str, str, str]] = set()
    if isinstance(obj, dict):
        frm = obj.get("From")
        if isinstance(frm, list):
            for item in frm:
                if isinstance(item, dict) and item.get("Name") and item.get("Entity"):
                    scope[item["Name"]] = item["Entity"]
                    found.add((item["Entity"], "", "Table"))
        for kind in ("Column", "Measure", "Hierarchy"):
            node = obj.get(kind)
            if isinstance(node, dict):
                hit = _field_from(node, kind, scope)
                if hit:
                    found.add(hit)
        for v in obj.values():
            found |= collect_fields(v, scope)
    elif isinstance(obj, list):
        for v in obj:
            found |= collect_fields(v, scope)
    return found


def report_extensions(layout: dict) -> tuple[set[tuple[str, str]], list[tuple[str, str, str]]]:
    """Report-level measures (live-connection 'modelExtensions'); they travel with the report."""
    cfg = load_json(layout.get("config"))
    measures: set[tuple[str, str]] = set()
    refs: list[tuple[str, str, str]] = []
    for ext in cfg.get("modelExtensions", []) if isinstance(cfg, dict) else []:
        for ent in ext.get("entities", []):
            for m in ent.get("measures", []):
                measures.add((ent.get("name", ""), m.get("name", "")))
                expr = m.get("expression", "")
                if isinstance(expr, dict):
                    expr = expr.get("expression", "")
                for q, bare, col in DAX_REF.findall(str(expr)):
                    refs.append((q or bare, col, f"{ent.get('name','')}[{m.get('name','')}]"))
    return measures, refs


def extract_report(zf: zipfile.ZipFile) -> dict[str, Any]:
    layout = read_part(zf, "Report/Layout")
    if not isinstance(layout, dict):
        names = zf.namelist()
        hint = ""
        if any(n.lower().startswith("report/definition") for n in names):
            hint = " This looks like the new PBIR format; save the report as a classic .pbix/.pbit."
        raise ValueError("No readable Report/Layout found in the report file." + hint)

    usage: list[dict[str, Any]] = []

    def add(page: str, visual: str, vtype: str, where: str, fields: set[tuple[str, str, str]]):
        for table, field, kind in sorted(fields):
            usage.append({"Page": page, "Visual": visual, "Visual type": vtype,
                          "Where used": where, "Table": table, "Field": field, "Kind": kind})

    add("(report)", "", "", "Report filter", collect_fields(load_json(layout.get("filters"))))
    visual_count = 0
    for page in layout.get("sections", []):
        pname = page.get("displayName") or page.get("name") or ""
        add(pname, "", "", "Page filter", collect_fields(load_json(page.get("filters"))))
        for i, vc in enumerate(page.get("visualContainers", []), 1):
            visual_count += 1
            cfg = load_json(vc.get("config"))
            single = cfg.get("singleVisual", {}) if isinstance(cfg, dict) else {}
            vtype = single.get("visualType", "")
            vname = cfg.get("name") or vc.get("id") or f"Visual {i}"
            title = ""
            try:
                title = single["vcObjects"]["title"][0]["properties"]["text"]["expr"]["Literal"]["Value"].strip("'")
            except (KeyError, IndexError, TypeError, AttributeError):
                pass
            label = f"{title} [{vname}]" if title else str(vname)
            add(pname, label, vtype, "Visual fields", collect_fields(single.get("prototypeQuery")))
            # formatting rules, tooltips etc. also reference fields
            rest = {k: v for k, v in single.items() if k != "prototypeQuery"}
            add(pname, label, vtype, "Formatting / other", collect_fields(rest))
            add(pname, label, vtype, "Visual filter", collect_fields(load_json(vc.get("filters"))))
            # fall back to the container query if prototypeQuery was absent
            if not single.get("prototypeQuery"):
                add(pname, label, vtype, "Visual fields", collect_fields(load_json(vc.get("query"))))

    ext_measures, ext_refs = report_extensions(layout)
    for table, field, owner in ext_refs:
        usage.append({"Page": "(report)", "Visual": "", "Visual type": "", "Where used": f"Report-level measure {owner}",
                      "Table": table, "Field": field, "Kind": "Column"})

    # de-duplicate
    seen, unique = set(), []
    for row in usage:
        key = tuple(row.values())
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return {"usage": unique, "ext_measures": ext_measures, "pages": len(layout.get("sections", [])), "visuals": visual_count}


def report_connection(zf: zipfile.ZipFile) -> str:
    names = {n.lower() for n in zf.namelist()}
    if "datamodel" in names or "datamodelschema" in names:
        return "Report with embedded model"
    if "connections" in names:
        return "Thin report (live connection)"
    return "Unknown"


# ---------------------------------------------------------------- model side
def model_from_schema(schema: dict) -> dict[str, Any]:
    tables: dict[str, dict] = {}
    model = schema.get("model", schema)
    for t in model.get("tables", []):
        name = t.get("name", "")
        tables[name] = {
            "columns": {c["name"] for c in t.get("columns", []) if c.get("type") != "rowNumber"},
            "measures": {m["name"] for m in t.get("measures", [])},
            "hierarchies": {h["name"] for h in t.get("hierarchies", [])},
            "hidden": bool(t.get("isHidden")),
        }
    rels = [(r.get("fromTable", ""), r.get("toTable", ""), r.get("isActive", True)) for r in model.get("relationships", [])]
    return {"tables": tables, "relationships": rels}


def model_from_pbixray(path: Path) -> dict[str, Any]:
    from pbixray import PBIXRay  # imported lazily

    m = PBIXRay(str(path))
    tables: dict[str, dict] = {}

    def slot(t: str) -> dict:
        return tables.setdefault(t, {"columns": set(), "measures": set(), "hierarchies": set(), "hidden": False})

    def rows(attr: str):
        try:
            df = getattr(m, attr)
            return [] if df is None else df.to_dict(orient="records")
        except Exception:
            return []

    for r in rows("schema"):
        slot(str(r.get("TableName")))["columns"].add(str(r.get("ColumnName")))
    for r in rows("dax_columns"):
        slot(str(r.get("TableName")))["columns"].add(str(r.get("ColumnName")))
    for r in rows("dax_tables"):
        slot(str(r.get("TableName")))
    for r in rows("dax_measures"):
        slot(str(r.get("TableName")))["measures"].add(str(r.get("Name")))
    try:
        for t in list(getattr(m, "tables", []) or []):
            slot(str(t))
    except Exception:
        pass
    for r in rows("tmschema_hierarchies"):  # column names vary by version, so be tolerant
        tname = next((v for k, v in r.items() if "table" in k.lower() and isinstance(v, str)), None)
        hname = r.get("Name")
        if tname and hname:
            slot(tname)["hierarchies"].add(str(hname))
    rels = []
    for r in rows("relationships"):
        f = next((v for k, v in r.items() if "fromtable" in k.lower()), None)
        t = next((v for k, v in r.items() if "totable" in k.lower()), None)
        if f and t:
            rels.append((str(f), str(t), bool(r.get("IsActive", True))))
    return {"tables": tables, "relationships": rels}


def extract_model(zf: zipfile.ZipFile, path: Path) -> tuple[dict[str, Any], str]:
    schema = read_part(zf, "DataModelSchema")  # present in .pbit
    if isinstance(schema, dict):
        return model_from_schema(schema), "DataModelSchema (.pbit)"
    names = {n.lower() for n in zf.namelist()}
    if "datamodel" not in names:
        raise ValueError("This file has no embedded semantic model (it looks like a thin report). "
                         "Upload the .pbix/.pbit that actually contains the model.")
    try:
        return model_from_pbixray(path), "DataModel (.pbix via PBIXRay)"
    except Exception as exc:
        raise ValueError(f"The semantic model could not be read: {type(exc).__name__}: {exc}") from exc
