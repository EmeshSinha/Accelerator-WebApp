# Power BI Playbook Accelerator (Xebia)

Upload a BRD and get a Power BI Playbook, shown section by section in the browser and downloadable as a
Xebia-branded PDF.

- **AI:** Google Gemini (free tier) by default. Claude can be switched on with one line in `.env`.
- **Any BRD:** the Xebia BRD template gives the best results, but any Excel, Word, PDF, CSV or text BRD works.
  The AI uses everything the BRD contains and fills the gaps from Power BI and industry knowledge,
  marking those parts as *assumed*.
- Frontend: HTML, CSS, JavaScript (`frontend/`). Backend: Python + Flask (`backend/`).

---

## 1. Prerequisites

- **VS Code** with the **Python** extension (by Microsoft) installed.
- **Python 3.10 or newer**: https://www.python.org/downloads/
  On Windows, tick **"Add python.exe to PATH"** during installation.
- A **free Gemini API key**: sign in with a Google account at **https://aistudio.google.com/apikey** and click
  **Create API key**.
- Internet access.

## 2. Run it in VS Code

**Step 1: Open the project**
1. Right-click `playbook-accelerator.zip` → **Extract All**.
2. In VS Code: **File → Open Folder…** and select the extracted `playbook-accelerator` folder
   (the one that contains `backend`, `frontend` and `requirements.txt`).
3. Open a terminal: **Terminal → New Terminal**. It opens in the project folder.

**Step 2: Create a virtual environment and install packages** (one time only)

Windows (PowerShell, the default VS Code terminal):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
If PowerShell says *"running scripts is disabled on this system"*, run this once and then activate again:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.venv\Scripts\Activate.ps1
```
macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
When the environment is active, the terminal prompt starts with `(.venv)`.
If VS Code asks *"We noticed a new environment… select it for the workspace?"*, click **Yes**.

**Step 3: Add your API key** (one time only)
1. Make a copy of `.env.example` named `.env`:
   - Windows: `copy .env.example .env`
   - macOS / Linux: `cp .env.example .env`
2. Open `.env` in VS Code and replace `your-gemini-key-here` with your key, then save (**Ctrl+S**):
   ```
   GEMINI_API_KEY=AIza...your key...
   ```
   No spaces or quotes around the key.

**Step 4: Start the app**
```
python backend/app.py
```
When the terminal shows *"Power BI Playbook Accelerator is running"*, your browser opens the app.
If it doesn't, **Ctrl+click** the address shown in the terminal (normally http://localhost:5000).
Leave the terminal running while you use the app. To stop it, click in the terminal and press **Ctrl+C**.

While a playbook is generating, the terminal and the progress page show each step and each AI call
(model, retries, how long it took), so you can always see what is happening.

**Check Gemini first (recommended):** before generating, run
```
python backend/check_gemini.py
```
It tests your key and connection, lists the models your key can use and times a small request on each.
If it reports a working model different from `GEMINI_MODEL`, put that model in `.env`.

You can also start it with **F5**: choose **Run and Debug → "Run Playbook Accelerator"** (configuration
included in `.vscode/launch.json`).

**Next time:** open the folder in VS Code, open a terminal, activate the environment
(`.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` on macOS/Linux), then run
`python backend/app.py`. Steps 2 and 3 don't need repeating.

## 3. Use it

1. Prepare the BRD. **BRD template** (top right) downloads the Xebia template; using it gives the most accurate
   playbook. Any other BRD file also works.
   Samples: `samples/FreshMart_Sample_BRD.xlsx` (retail) and `samples/HeroMotors_Sample_BRD.xlsx` (manufacturing).
2. Drop the BRD on the upload box and click **Generate playbook**.
3. Generation runs in three AI steps (about 1–3 minutes). The playbook appears with a contents sidebar on the
   left; click any section or sub-section to jump to it.
4. Click **Download PDF** at the top of the playbook. PDFs are also saved in the `output/` folder.

## 4. How BRDs are read

- **Template BRD:** the sheets are read field by field, and the full content is also passed to the AI.
- **Any other BRD:** the full readable content (every sheet, paragraph, table or page) is passed to the AI.
- Nothing is rejected for missing fields. The AI proposes what is missing (tables, columns, KPIs, pages,
  personas, security) based on the rest of the BRD and marks it as *assumed* for the team to confirm.
- Only an unreadable or empty file, or an unsupported file type, is refused.
- Supported: `.xlsx`, `.xlsm`, `.docx`, `.pdf` (text-based, not scanned), `.csv`, `.txt`, `.md`.

## 5. Configuration (`.env`)

| Setting | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` (free) or `claude` (needs Claude API credits) |
| `GEMINI_API_KEY` | — | Free key from aistudio.google.com/apikey |
| `GEMINI_MODEL` | `gemini-3.8-flash` | First Gemini model to try |
| `GEMINI_TIMEOUT` / `GEMINI_TOTAL_TIMEOUT` | `180` / `420` | Seconds to wait for one answer / for one whole step including retries |
| `GEMINI_FALLBACK_MODELS` | `gemini-flash-latest,gemini-3.6-flash,gemini-3.5-flash-lite` | Tried in order if the first model isn't available on your key or its free quota is used up |
| `ANTHROPIC_API_KEY` / `CLAUDE_MODEL` | — / `claude-sonnet-5-5` | Only used when `LLM_PROVIDER=claude` |
| `MAX_OUTPUT_TOKENS` | `32000` | Output limit per step; raise for very large BRDs |
| `DEMO_MODE` | `false` | `true` = no AI calls, shows a bundled sample playbook |
| `PORT` | `5000` | Local port |

## 6. Important: free tier and client data

On Google's **free** Gemini tier, the content you send may be used by Google to improve its products.
Use the free tier for **sample, demo or anonymised BRDs**. For real client BRDs, use a paid tier
(Gemini with billing enabled, or `LLM_PROVIDER=claude` with API credits).

Free-tier limits (requests per minute and per day) change from time to time. One playbook uses three
requests. If you hit a limit, the app waits and retries, then tries the fallback models.

## 7. How it works

```
BRD file ──► brd_parser.py  (template fields if present + full text of the file)
                 │
                 ▼
         generator.py  ──► llm.py  (Gemini or Claude, 3 structured calls with fixed JSON schemas)
           1. Project details, source systems, tables & columns, relationships
           2. KPI DAX catalogue, report page design
           3. Audience, security & RLS, refresh, deployment, delivery plan, key decisions
                 │
                 ▼
  playbook JSON ──► web view (frontend/app.js)  +  PDF (pdf_builder.py)
```

- Every call uses a fixed JSON schema (`backend/schemas.py`), so every playbook has the same sections in the
  same order whichever AI is used. Missing fields are filled with blanks so the page and PDF never break.
- Project details typed in the BRD always win; the AI fills only the ones that are missing.
- Rules given to the AI (in `generator.py`): no IDs, use BRD names exactly, mark assumptions, Import/DirectQuery
  advice only in the Source System note, relationships only (no star schema / date table / diagram),
  no durations in the delivery plan.

## 8. Project structure

```
playbook-accelerator/
├─ .vscode/launch.json       F5 run configuration
├─ requirements.txt
├─ .env.example              copy to .env and add your key
├─ backend/
│  ├─ app.py                 Flask server and API
│  ├─ brd_parser.py          reads any BRD (template-aware, no rejection)
│  ├─ generator.py           prompts and the 3 generation steps
│  ├─ llm.py                 Gemini / Claude provider switch
│  ├─ schemas.py             JSON schemas for each step
│  ├─ pdf_builder.py         Xebia-branded PDF
│  ├─ sample_playbook.json   used by demo mode
│  ├─ assets/xebia_logo.png
│  └─ fonts/                 Liberation Sans/Mono (SIL Open Font Licence)
├─ frontend/
│  ├─ index.html, styles.css, app.js
│  └─ assets/                logo + blank BRD template
├─ samples/                  FreshMart and Hero Motors sample BRDs
└─ output/                   generated PDFs (created on first run)
```

## 9. Troubleshooting

First look at the VS Code terminal: every step and AI call is logged there with the reason for any wait or failure.
Then run `python backend/check_gemini.py`.

| Message | Fix |
|---|---|
| `GEMINI_API_KEY is not set` | Make sure the file is named exactly `.env` (not `.env.txt`), the key is set, and restart the app |
| `Gemini rejected the API key` | Copy the key again from aistudio.google.com/apikey |
| `Model … is not available` / `not included in your free-tier quota` | The app tries the fallback models automatically. If all fail, set `GEMINI_MODEL` to a model listed for your key in AI Studio |
| `daily free-tier quota … is used up` | Wait until the quota resets (next day), or use another model |
| `Gemini is busy or rate-limited` | Wait a minute and click **Try again** |
| `Could not connect to the Gemini API` | Your network/VPN/firewall blocks Google's API. Try another network (e.g. mobile hotspot) or ask IT to allow `generativelanguage.googleapis.com` |
| `did not answer within 180s` | The model is overloaded; the app moves to the next model automatically. You can also set a lighter `GEMINI_MODEL` (e.g. a flash-lite model) |
| `response was cut off` | Increase `MAX_OUTPUT_TOKENS` in `.env` |
| `No readable content was found` | The file is empty or a scanned image; upload the original document |
| `python is not recognized` / `Python was not found` | Install Python from python.org with "Add python.exe to PATH" ticked, then restart VS Code |
| `ModuleNotFoundError: No module named 'flask'` (or another package) | The virtual environment isn't active. Activate it (step 2) and run `pip install -r requirements.txt` |
| Browser shows "can't reach this page" | Wait until the terminal says the app is running, then refresh. Use the address shown in the terminal |

Jobs are kept in memory, so restarting the server clears past playbooks from the browser (PDFs stay in
`output/`). The app listens on `localhost` only.
