"""
JSON schemas Claude must fill. Each generation step is a forced tool call, so the
output always has exactly these fields — the layout and section order come from code.
"""


def s(desc=""):
    return {"type": "string", "description": desc} if desc else {"type": "string"}


def arr(items, desc=""):
    d = {"type": "array", "items": items}
    if desc:
        d["description"] = desc
    return d


def obj(props, desc=""):
    d = {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    if desc:
        d["description"] = desc
    return d


STRINGS = arr(s())

# ---------------- Step 1: data foundation
DATA_FOUNDATION = obj({
    "overview": obj({
        "client": s("Client / company name from the BRD"),
        "project": s("Project or report name; propose a short name if the BRD has none"),
        "domain": s("Business domain, e.g. Retail, BFSI, Manufacturing"),
        "business_owner": s("Business owner from the BRD, or 'To be confirmed'"),
        "objective": s("Business objective in 1-3 sentences"),
        "scope": s("What the report covers, in 1-2 sentences"),
    }, "Project details. Take them from the BRD; where missing, infer sensibly from the content."),
    "source_systems": obj({
        "items": arr(obj({
            "source": s("Source name exactly as in the BRD"),
            "type": s("System type as in the BRD"),
            "owner": s("Data owner from BRD, or '—'"),
            "history": s("History required from BRD, or '—'"),
            "refresh": s("Refresh frequency from BRD"),
            "connector": s("Recommended Power BI connector"),
            "gateway": s("Whether an on-premises data gateway is needed, e.g. 'Yes (on-premises)' or 'No'"),
        })),
        "notes": arr(s(), "Notes for this section. The Import vs DirectQuery (or Dual) recommendation with its "
                          "rationale MUST be given here and nowhere else. 1-3 short paragraphs."),
    }),
    "tables": obj({
        "items": arr(obj({
            "source_table": s("Table name exactly as in the BRD, or '(derived from <table>)' for a table you add"),
            "model_name": s("Business-friendly name of the table in the Power BI model"),
            "role": s("Fact, Dimension, Bridge or Security"),
            "rows": s("Approx. row count from BRD, or '—'"),
            "transformations": s("Power Query transformations needed, one or two sentences"),
        })),
        "columns": arr(obj({
            "model_table": s("Model name of the table"),
            "column": s("Column name as in the BRD"),
            "pbi_type": s("Power BI data type: Text, Whole number, Decimal number, Fixed decimal, Date, Date/time, True/false"),
            "key": s("'PK', 'FK → <model table>' or '—'"),
            "notes": s("Short note on meaning or use"),
        }), "Every column listed in the BRD, in BRD order"),
    }),
    "data_model": obj({
        "relationships": arr(obj({
            "from": s("Many side as ModelTable[Column]"),
            "to": s("One side as ModelTable[Column]"),
            "cardinality": s("Many-to-one, One-to-one or Many-to-many"),
            "cross_filter": s("Single or Both"),
            "basis": s("'Stated in BRD' if from Key Type/References, otherwise 'Inferred — <short reason>'"),
        })),
        "notes": arr(s(), "Short notes on relationships to confirm with the client. Can be empty."),
    }),
})

# ---------------- Step 2: measures and pages
MEASURES_AND_PAGES = obj({
    "kpis": obj({
        "intro": s("One or two sentences on where measures are stored and how base measures are reused"),
        "base_measures": s("DAX for the reusable base measures, one per line, aligned. Plain text, no markdown fences."),
        "items": arr(obj({
            "name": s("KPI name exactly as in the BRD"),
            "priority": s("Priority exactly as in the BRD"),
            "definition": s("Business definition, refined from the BRD description"),
            "uses": s("Columns and measures used, e.g. Sales[LineAmount], [Net Sales]"),
            "dax": s("Complete DAX for the KPI and any status/helper measure it needs. Plain text, no markdown fences. "
                     "Use -- comments for assumptions."),
        }), "One entry per BRD KPI, in BRD order"),
    }),
    "report_pages": obj({
        "intro": s("One sentence introducing the page designs; mention any report-level filter"),
        "pages": arr(obj({
            "name": s("Page name exactly as in the BRD"),
            "purpose": s("Purpose from the BRD"),
            "priority": s("Priority exactly as in the BRD"),
            "personas": s("Personas who use this page (names), or 'All users' if the BRD has no audience"),
            "kpis_shown": s("Comma-separated KPI names shown on this page"),
            "slicers": s("Comma-separated slicer names, e.g. 'Month, Region'. Keep each name short."),
            "page_filters": s("Page-level filters, or 'None'"),
            "drill": s("Drill-down and drill-through design, or 'None'"),
            "interactions": s("How visuals interact on the page"),
            "visuals": arr(obj({
                "visual": s("Short visual title"),
                "type": s("Power BI visual type, e.g. Card, Line chart, Clustered bar, Matrix, Map, Treemap"),
                "fields": s("Fields placed in the visual wells, e.g. Axis: ...; Values: ..."),
            }), "3 to 7 visuals. List all KPI cards first."),
        }), "One entry per BRD page, in BRD order"),
    }),
})

# ---------------- Step 3: access, operations and delivery
ACCESS_AND_DELIVERY = obj({
    "key_decisions": arr(s(), "3-5 key design decisions for the executive summary, one sentence each. "
                              "Do not mention Import/DirectQuery or star schema."),
    "audience": obj({
        "source_note": s("One sentence: whether personas come from the BRD or are assumed because the Audience sheet was empty"),
        "personas": arr(obj({
            "persona": s(), "users": s("Number of users or '—'"), "key_decisions": s(), "data_access": s(),
            "primary_pages": s("Page names this persona uses most"), "device": s("Desktop, Mobile or Desktop & mobile"),
        })),
        "recommendations": STRINGS,
    }),
    "security": obj({
        "source_note": s("One sentence: whether RLS comes from BRD requirements or is Xebia's recommendation because none were given"),
        "security_table_description": s("How the user-to-data mapping table is maintained and loaded. Empty string if no RLS is needed."),
        "security_table_columns": arr(obj({"column": s(), "example": s(), "notes": s()})),
        "roles": arr(obj({"role": s(), "members": s(), "filter_table": s(), "requirement": s("BRD requirement it covers, or 'Recommended'")})),
        "rls_dax": s("DAX filter expression for each role, with a '-- Role: <name>  (table: <table>)' comment above each. Plain text."),
        "recommendations": STRINGS,
    }),
    "refresh": obj({
        "schedule": arr(obj({"source": s(), "required": s(), "schedule": s(), "method": s()})),
        "incremental": arr(obj({"label": s("e.g. Table, Archive, Refresh window, Partition column, Licence note"), "value": s()}),
                           "Incremental refresh settings for the largest fact table. Empty array if not needed."),
        "incremental_title": s("Sub-heading, e.g. 'Incremental refresh — Sales'. Empty string if not needed."),
        "practices": STRINGS,
    }),
    "deployment": obj({
        "workspaces": arr(obj({"stage": s(), "workspace": s(), "purpose": s(), "access": s()})),
        "pipeline": s("One or two sentences on how content is promoted between stages"),
        "governance": arr(s(), "Each item as 'Topic: detail', e.g. 'Version control: ...'"),
    }),
    "delivery": obj({
        "intro": s("One or two sentences: sprints are ordered by priority and no durations are given because they depend on team size"),
        "sprints": arr(obj({"sprint": s("e.g. Sprint 0"), "goal": s(), "scope": s("Named items in scope, no IDs"),
                            "exit_criteria": s()})),
        "dependencies": STRINGS,
    }),
})
