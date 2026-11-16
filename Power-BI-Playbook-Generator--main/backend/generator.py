"""
Turns a BRD (any layout) into a playbook dict using the configured AI provider (Gemini or Claude).

Three structured calls, each with a fixed JSON schema:
  1. Data foundation   (project details, source systems, tables & columns, relationships)
  2. Measures & pages  (KPI DAX catalogue, report page design)
  3. Access & delivery (audience, security, refresh, deployment, delivery plan, key decisions)
The section order and layout are fixed by code; the AI only fills the content.
"""
import json
from datetime import date

import schemas
from llm import GenerationError, structured_call  # noqa: F401  (re-exported for app.py)

SYSTEM_PROMPT = """You are a senior Power BI solution architect at Xebia. You turn a client's Business Requirements \
Document (BRD) into a Power BI Playbook that a development team will build from.

About the input:
- The BRD may follow Xebia's BRD template, follow a different layout, or be incomplete. Use every piece of \
information it provides. Where something needed for the playbook is missing (sources, tables, columns, keys, KPIs, \
pages, audience, security), use your Power BI expertise and knowledge of the client's industry to propose sensible, \
realistic content that fits what the BRD does say.
- Anything you propose that is not in the BRD must be marked briefly, e.g. "(assumed)" after a name or value, \
or "Assumed:" at the start of a note, so the team knows to confirm it with the client.
- Never contradict what the BRD states.

Rules for everything you write:
- Refer to every item by its name. Never create or use IDs such as SRC-01, TBL-01, KPI-01, PG-01, P-01 or SEC-01.
- Where the BRD names a source system, table, column, KPI or page, use that name exactly as written.
- Write plain text only: no markdown, no bullet characters, no headings. The application adds all formatting.
- Be concise and specific. Short sentences.
- DAX must be syntactically valid, use the model table names you were given, and use DIVIDE for division. \
Write DAX as plain text without code fences.
- Recommendations about Import, DirectQuery or Dual storage mode belong only in the Source System notes.
- Do not describe a star schema or produce a date table design or model diagram; give relationships only.
- Do not give durations, dates, effort or timelines in the delivery plan; sprint length depends on team size."""


def _brd_block(brd):
    parts = []
    if brd["follows_template"]:
        parts.append("The BRD follows the Xebia BRD template. Fields picked out of it:\n"
                     + json.dumps(brd["template"], indent=1, ensure_ascii=False))
    elif brd["overview"]:
        parts.append("Project fields found in the BRD:\n" + json.dumps(brd["overview"], indent=1, ensure_ascii=False))
    else:
        parts.append("The BRD does not follow the Xebia template. Extract what you need from the full content below.")
    parts.append("Full content of the BRD file:\n<<<BRD\n" + brd["text"] + "\nBRD>>>")
    return "\n\n".join(parts)


def generate_playbook(brd, progress=lambda step: None):
    brd_text = _brd_block(brd)

    # ---- Step 1
    progress("data_foundation")
    p1 = structured_call(
        SYSTEM_PROMPT, "write_data_foundation",
        "Write the project details, Source System Inventory, Table & Column Catalogue and Data Model relationships.",
        schemas.DATA_FOUNDATION,
        f"{brd_text}\n\n"
        "Write the data foundation sections. Include every source system, table and column the BRD mentions. "
        "If the BRD gives no or few tables and columns, design the tables and key columns needed to calculate the "
        "KPIs and build the report pages it describes, and mark them as assumed. Classify each table and give it a "
        "business-friendly model name. Derive relationships from stated keys first, then infer the rest from "
        "matching columns and mark them as inferred.")
    if not p1["tables"]["items"]:
        raise GenerationError("The AI could not identify any tables from this BRD. Add more detail and try again.")

    model_ctx = json.dumps({"tables": p1["tables"], "relationships": p1["data_model"]["relationships"]},
                           indent=1, ensure_ascii=False)

    # ---- Step 2
    progress("measures_pages")
    p2 = structured_call(
        SYSTEM_PROMPT, "write_measures_and_pages",
        "Write the KPI & DAX Catalogue and the Report Page Design.",
        schemas.MEASURES_AND_PAGES,
        f"{brd_text}\n\nThe agreed data model (model table names, columns and relationships):\n{model_ctx}\n\n"
        "Write DAX for every KPI in the BRD using these model table names. If the BRD lists few or no KPIs, propose "
        "the KPIs this kind of report needs and mark them as assumed. Where a target or RAG threshold is known, add a "
        "status measure for it. Priority must be Must, Should or Could. Then design every report page the BRD "
        "describes (propose pages if none are given): which KPIs it shows, slicers, filters, drill-down/drill-through, "
        "interactions and visuals.")

    pages_ctx = json.dumps([{"name": p["name"], "priority": p["priority"], "kpis_shown": p["kpis_shown"]}
                            for p in p2["report_pages"]["pages"]], ensure_ascii=False)

    # ---- Step 3
    progress("access_delivery")
    p3 = structured_call(
        SYSTEM_PROMPT, "write_access_and_delivery",
        "Write Audience & Access, Security & RLS, Refresh & Performance, Deployment & Governance, the Delivery Plan "
        "and the key design decisions.",
        schemas.ACCESS_AND_DELIVERY,
        f"{brd_text}\n\nModel tables and relationships:\n{model_ctx}\n\nReport pages:\n{pages_ctx}\n\n"
        "Build personas and security from the BRD where given. If the BRD has no audience, propose likely personas "
        "and say they are assumed. If it has no security requirements, give Xebia's recommended RLS approach and say "
        "it is a recommendation. For the delivery plan, start with a setup sprint (Sprint 0), then the data "
        "foundation, then Must items, then Should and Could items with go-live. Use names, not IDs.")

    # Project details: values typed in the BRD win; the AI fills any gaps
    ai_ov, brd_ov = p1["overview"], brd["overview"]
    pick = lambda brd_key, ai_key: brd_ov.get(brd_key) or ai_ov.get(ai_key) or "To be confirmed"  # noqa: E731
    counts = {"source_systems": len(p1["source_systems"]["items"]), "tables": len(p1["tables"]["items"]),
              "columns": len(p1["tables"]["columns"]), "kpis": len(p2["kpis"]["items"]),
              "report_pages": len(p2["report_pages"]["pages"])}
    return {
        "doc_control": {
            "client": pick("client", "client"), "project": pick("project", "project"),
            "domain": pick("domain", "domain"), "business_owner": pick("business_owner", "business_owner"),
            "generated_on": date.today().strftime("%d %B %Y").lstrip("0"), "prepared_by": "Xebia — Data & Analytics",
        },
        "executive_summary": {"objective": pick("objective", "objective"), "scope": pick("in_scope", "scope"),
                              "at_a_glance": counts, "key_decisions": p3["key_decisions"]},
        "source_systems": p1["source_systems"],
        "tables": p1["tables"],
        "data_model": p1["data_model"],
        "kpis": p2["kpis"],
        "report_pages": p2["report_pages"],
        "audience": p3["audience"],
        "security": p3["security"],
        "refresh": p3["refresh"],
        "deployment": p3["deployment"],
        "delivery": p3["delivery"],
    }
