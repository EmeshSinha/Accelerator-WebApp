# Power BI Metadata Extractor

A separate web application for uploading Power BI `.pbix` or `.pbit` files and exporting available report and semantic-model metadata to Excel.

## Recommended environment
- Windows + VS Code
- Python 3.12 (recommended for compatibility with the PBIX parsing library)
- No Node.js required
- No AI API required

## Run locally
1. Extract the ZIP and open the `powerbi_metadata_extractor` folder in VS Code.
2. Open Terminal > New Terminal.
3. Create a virtual environment:
   ```powershell
   py -3.12 -m venv .venv
   ```
   If `py -3.12` is unavailable, install Python 3.12 first. You can check installed versions with `py -0p`.
4. Activate it:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks activation:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\.venv\Scripts\Activate.ps1
   ```
5. Install dependencies:
   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
6. Start the app:
   ```powershell
   python -m uvicorn backend.main:app --reload
   ```
7. Open http://127.0.0.1:8000.

## Metadata sheets
The Excel export may include report pages, visuals, visual fields, filters, tables, columns, measures and DAX expressions, calculated columns/tables, relationships, Power Query (M), M parameters, connections, RLS/OLS, hierarchies, package contents and warnings.

## Important limitations
- `.pbix` and `.pbit` are accepted. Actual metadata available depends on the file format, model type and Power BI version.
- Thin reports/live connections may not contain an embedded semantic model. The report pages and connection manifest may still be available, but remote model metadata cannot be retrieved from the file alone.
- The application does not connect to Power BI Service or extract workspace permissions, refresh history, gateway configuration, or tenant-level settings.
- This application extracts DAX and M source text; it does not evaluate DAX or execute Power Query.
- The report is parsed locally by the Python backend. Keep sensitive reports on a trusted machine and do not expose the local server to a public network.

When deployed as the public Render demo, uploaded reports are sent to the hosted service and anyone with its URL can use it. Use only non-confidential files that you are authorized to upload.
