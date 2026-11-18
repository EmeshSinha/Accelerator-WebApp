from __future__ import annotations

import zipfile
from io import BytesIO
from typing import Any

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException


KINDS = {
    "column": "Column",
    "measure": "Measure",
    "hierarchy": "Hierarchy",
}


def _header_map(values: tuple[Any, ...] | list[Any]) -> dict[str, int] | None:
    headers = {str(value or "").strip().casefold(): i for i, value in enumerate(values)}
    table_col = next((headers[k] for k in ("table", "table name") if k in headers), None)
    field_col = next((headers[k] for k in ("field", "field name") if k in headers), None)
    kind_col = next((headers[k] for k in ("kind", "type", "field type") if k in headers), None)
    if table_col is None or field_col is None or kind_col is None:
        return None
    return {"Table": table_col, "Field": field_col, "Kind": kind_col}


def _rows_from_table(rows: list[tuple[Any, ...]]) -> list[dict[str, str]]:
    header_index = next((i for i, row in enumerate(rows[:10]) if _header_map(row)), None)
    if header_index is None:
        return []
    columns = _header_map(rows[header_index])
    assert columns is not None
    result = []
    for row in rows[header_index + 1:]:
        values = {key: str(row[index] or "").strip() if index < len(row) else ""
                  for key, index in columns.items()}
        table, field, kind = values["Table"], values["Field"], values["Kind"].casefold()
        if not table and not field and not kind:
            continue
        if kind not in KINDS:
            raise ValueError(f"Unknown kind '{values['Kind']}'. Use Column, Measure, or Hierarchy.")
        if not table or not field:
            raise ValueError("Each row needs a table name, a field name, and a kind.")
        result.append({
            "Page": "(input)", "Visual": "", "Visual type": "", "Where used": "Structured report",
            "Table": table, "Field": field, "Kind": KINDS[kind],
        })
    return result


def extract_structured_report(data: bytes, suffix: str) -> list[dict[str, str]]:
    if suffix == ".xlsx":
        try:
            workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
        except (InvalidFileException, zipfile.BadZipFile) as exc:
            raise ValueError("The Excel report is not a valid .xlsx file.") from exc
        try:
            rows = [item for sheet in workbook.worksheets
                    for item in _rows_from_table(list(sheet.iter_rows(values_only=True)))]
        finally:
            workbook.close()
    elif suffix == ".docx":
        try:
            document = Document(BytesIO(data))
        except (PackageNotFoundError, zipfile.BadZipFile) as exc:
            raise ValueError("The Word report is not a valid .docx file.") from exc
        rows = []
        for table in document.tables:
            table_rows = [tuple(cell.text for cell in row.cells) for row in table.rows]
            rows.extend(_rows_from_table(table_rows))
    else:
        raise ValueError("Use a .pbix, .pbit, .xlsx, or .docx report file.")

    if not rows:
        raise ValueError(
            "No supported field list found. Add a table with headers Table, Field, and Kind "
            "(Kind: Column, Measure, or Hierarchy)."
        )
    return rows
