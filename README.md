# Analytics Accelerator Hub

Start the local analytics tools from one dashboard. The hosted accelerators are also available on Render.

## Start

In PowerShell, open this folder and run:

```powershell
.\setup.ps1
.\start.ps1
```

The setup installs each project's Python dependencies. After running `.\start.ps1`, copy the hub link shown in PowerShell (`http://127.0.0.1:8500`) and open it manually when you are ready. The browser does not open automatically. The tools run on ports 8501, 8001, 8002, and 8003. Keep the PowerShell window open and press Ctrl+C to stop. Logs are in `logs/`.

For the Playbook Generator's AI features, copy `Power-BI-Playbook-Generator--main/.env.example` to `.env` in that project and set `GEMINI_API_KEY`. For AI-assisted complex conversions, copy the Tableau converter's `.env.example` to `.env` and set `GEMINI_API_KEY`.

## Deploy to Render

The root `render.yaml` defines the five Python web services and the static dashboard. To deploy:

1. Push the repository to GitHub.
2. In Render, choose **New → Blueprint**, connect this repository, and deploy the Blueprint from the repository root.
3. Set the prompted `GEMINI_API_KEY` values for the Playbook Generator and Tableau converter. Do not commit API keys.
4. Open the dashboard URL for `analytics-accelerator-hub` and test each accelerator link.

The dashboard links use the service names in `render.yaml` to form their default `onrender.com` URLs. If Render assigns a different URL, update the corresponding link in `index.html` and push the change. The free web services may sleep when idle; PBIX/PBIP processing can also need more memory than a free instance provides.

The Metadata Extractor is a public demo endpoint without sign-in. Uploaded reports are sent to the Render service for processing. Use only non-confidential files that you are authorized to upload; do not use client or production reports. Its upload limit is 200 MB, which may exceed the memory available on a free instance.

The Semantic Model Compatibility Checker is also a public demo without sign-in. Uploaded reports and semantic models are processed by the Render service. Use only non-confidential files; run it locally for confidential reports.
