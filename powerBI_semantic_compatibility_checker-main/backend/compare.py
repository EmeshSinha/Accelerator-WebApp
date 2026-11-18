"""Check every field a report uses against a target semantic model."""
from __future__ import annotations

import difflib
from collections import defaultdict
from typing import Any

from .pbi import AUTO_DATE

BREAKING = {"Missing table", "Missing column", "Missing measure", "Missing hierarchy",
            "Type mismatch", "Moved to another table"}


def _ci(d: dict[str, Any]) -> dict[str, str]:
    return {k.lower(): k for k in d}


def _suggest(name: str, options: list[str]) -> str:
    hit = difflib.get_close_matches(name, options, n=3, cutoff=0.6)
    return ", ".join(hit)


def check_field(table: str, field: str, kind: str, model: dict, ext_measures: set[tuple[str, str]]) -> tuple[str, str]:
    """Return (status, note)."""
    tables = model["tables"]
    tl = _ci(tables)

    if kind == "Table":
        if AUTO_DATE.match(table):
            return "Auto date table", "Auto-generated date table; its name differs per model. Check the date column it belongs to."
        if table.lower() in tl:
            return ("OK", "") if table in tables else ("OK (case differs)", f"Model uses '{tl[table.lower()]}'")
        return "Missing table", f"Did you mean: {_suggest(table, list(tables))}" if _suggest(table, list(tables)) else ""

    if (table, field) in ext_measures:
        return "Report-level measure", "Defined inside the report, so it travels with it."
    if AUTO_DATE.match(table):
        return "Auto date table", "Auto date/time hierarchy; verify the underlying date column exists."

    if table.lower() not in tl:
        where = [t for t, v in tables.items() if field in v["columns"] or field in v["measures"]]
        note = f"Table not in model. '{field}' exists in: {', '.join(where)}" if where else \
            (f"Did you mean table: {_suggest(table, list(tables))}" if _suggest(table, list(tables)) else "")
        return "Missing table", note

    real_t = tl[table.lower()]
    t = tables[real_t]
    case_note = "" if real_t == table else f"Table is '{real_t}' in the model. "
    cols, meas, hier = _ci({c: 1 for c in t["columns"]}), _ci({m: 1 for m in t["measures"]}), _ci({h: 1 for h in t["hierarchies"]})
    key = field.lower()

    pool = {"Column": (cols, "Missing column"), "Measure": (meas, "Missing measure"), "Hierarchy": (hier, "Missing hierarchy")}
    own, missing_status = pool[kind]
    if key in own:
        exact = own[key] == field and real_t == table
        return ("OK", "") if exact else ("OK (case differs)", case_note + f"Model uses '{own[key]}'")

    # right name, wrong kind
    for other_kind, (other, _) in pool.items():
        if other_kind != kind and key in other:
            return "Type mismatch", f"Report expects a {kind.lower()} but the model has a {other_kind.lower()} named '{other[key]}'."
    # right name, other table
    elsewhere = [n for n, v in tables.items() if n != real_t and
                 (field in v["columns"] or field in v["measures"] or field in v["hierarchies"])]
    if elsewhere:
        return "Moved to another table", f"'{field}' exists in: {', '.join(elsewhere)}"
    options = list(own.values())
    s = _suggest(field, options)
    return missing_status, (f"Did you mean: {s}" if s else "")


def connected_groups(model: dict) -> dict[str, int]:
    parent: dict[str, str] = {t: t for t in model["tables"]}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, _ in model["relationships"]:
        parent[find(a)] = find(b)
    return {t: hash(find(t)) for t in list(parent)}


def run_check(usage: list[dict], ext_measures: set[tuple[str, str]], model: dict) -> dict[str, Any]:
    rows = []
    for u in usage:
        status, note = check_field(u["Table"], u["Field"], u["Kind"], model, ext_measures)
        rows.append({**u, "Status": status, "Note": note})

    groups = connected_groups(model)
    by_visual: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if r["Visual"]:
            by_visual[(r["Page"], r["Visual"])].append(r)

    visual_rows = []
    for (page, visual), items in by_visual.items():
        bad = [i for i in items if i["Status"] in BREAKING]
        warn = [i for i in items if i["Status"] not in BREAKING and i["Status"] not in ("OK", "Report-level measure")]
        fields = [i for i in items if i["Kind"] in ("Column", "Hierarchy") and i["Status"] == "OK"
                  and i["Where used"] == "Visual fields"]
        used_tables = {i["Table"] for i in fields}
        rel_note = ""
        if len(used_tables) > 1 and len({groups.get(t) for t in used_tables}) > 1:
            rel_note = "Tables used together are not connected by relationships in the target model."
        visual_rows.append({
            "Page": page, "Visual": visual, "Visual type": items[0]["Visual type"],
            "Fields checked": len(items), "Breaking issues": len(bad), "Warnings": len(warn) + (1 if rel_note else 0),
            "Result": "Will break" if bad else ("Check manually" if (warn or rel_note) else "OK"),
            "Problem fields": "; ".join((f"{i['Table']}[{i['Field']}]" if i["Field"] else i["Table"]) + f" ({i['Status']})" for i in bad),
            "Relationship note": rel_note,
        })

    field_rows = [r for r in rows if r["Kind"] != "Table"]
    table_rows = [r for r in rows if r["Kind"] == "Table"]
    # unique field-level view (a field used in 10 visuals is one problem, not ten)
    uniq: dict[tuple, dict] = {}
    for r in field_rows:
        k = (r["Table"], r["Field"], r["Kind"])
        u = uniq.setdefault(k, {"Table": r["Table"], "Field": r["Field"], "Kind": r["Kind"], "Status": r["Status"],
                                "Note": r["Note"], "Used in visuals": set(), "Also used in": set()})
        if r["Visual"]:
            u["Used in visuals"].add(f"{r['Page']} / {r['Visual']}")
        if r["Where used"] not in ("Visual fields", "Formatting / other", "Visual filter"):
            u["Also used in"].add(r["Where used"])
    unique_rows = [{**u, "Used in visuals": len(u["Used in visuals"]), "Also used in": ", ".join(sorted(u["Also used in"]))}
                   for u in uniq.values()]
    problems = [u for u in unique_rows if u["Status"] in BREAKING]
    warnings = [u for u in unique_rows if u["Status"] not in BREAKING and u["Status"] not in ("OK", "Report-level measure")]
    missing_tables = [t for t in table_rows if t["Status"] == "Missing table"]

    breaking_visuals = sum(1 for v in visual_rows if v["Result"] == "Will break")
    if problems or missing_tables:
        verdict = "Not compatible"
    elif warnings or any(v["Result"] != "OK" for v in visual_rows):
        verdict = "Compatible with warnings"
    else:
        verdict = "Compatible"

    return {
        "verdict": verdict,
        "all_rows": rows, "unique_rows": unique_rows, "visual_rows": visual_rows,
        "problems": problems, "warnings": warnings,
        "summary": {
            "Unique fields checked": len(unique_rows),
            "Fields OK": sum(1 for u in unique_rows if u["Status"] in ("OK", "Report-level measure")),
            "Breaking problems": len(problems),
            "Warnings": len(warnings),
            "Visuals checked": len(visual_rows),
            "Visuals that will break": breaking_visuals,
            "Visuals to check manually": sum(1 for v in visual_rows if v["Result"] == "Check manually"),
        },
    }
