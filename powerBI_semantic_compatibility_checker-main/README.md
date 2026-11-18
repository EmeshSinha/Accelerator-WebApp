# Semantic Model Compatibility Checker

Answers one question: **can this report be repointed to that semantic model?**

Upload
1. a **report** (`.pbix`/`.pbit`, thin reports are fine) or a structured field list (`.xlsx`/`.docx`), and
2. the **target semantic model** (a `.pbix`/`.pbit` that contains the model).

The app lists every table, column, measure and hierarchy the report uses (visuals, conditional formatting, visual/page/report filters, report-level measures) and checks each one against the target model.

Excel and Word reports must contain a table with `Table`, `Field`, and `Kind` headers, with one required field per row. Use `Column`, `Measure`, or `Hierarchy` for `Kind`. In Word, put the field list in a Word table; prose descriptions are not parsed.

## Statuses
| Status | Meaning |
|---|---|
| OK | Found, same table and kind |
| OK (case differs) | Found, but capitalisation differs |
| Missing table / column / measure / hierarchy | Not in the target model (with "did you mean" suggestions) |
| Type mismatch | Report expects a measure but the model has a column, or vice versa |
| Moved to another table | Name exists, but in a different table |
| Auto date table | `LocalDateTable_…` names are generated per model; verify manually |
| Report-level measure | Defined in the report itself, so it travels with it |

Verdict: **Compatible**, **Compatible with warnings**, or **Not compatible**. Visuals are marked *OK*, *Check manually* or *Will break*. A visual that uses tables not connected by a relationship in the target model is flagged for a manual check.

## Run
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload
```
Open http://127.0.0.1:8000. No Node.js and no AI API needed.

## Limits
- Names are compared, not data types or values: the report file does not store column data types.
- `.pbit` target models are read straight from `DataModelSchema`. `.pbix` target models go through the `pbixray` library.
- New PBIR-format reports (no `Report/Layout`) are not supported; save as classic `.pbix`/`.pbit`.
- Models published in Power BI Service can't be read from a file. Download the `.pbix`, or export it as `.pbit`.
- The hosted demo is public and has no sign-in. Do not upload confidential reports or semantic models. Files are processed by the server and are not sent to an AI service.
- For confidential files, run the checker locally and do not expose the server to a public network.
