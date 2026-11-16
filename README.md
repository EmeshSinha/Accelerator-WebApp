# Analytics Accelerator Hub

Start all three local analytics tools from one dashboard. The source projects are included in this folder.

## Start

In PowerShell, open this folder and run:

```powershell
.\setup.ps1
.\start.ps1
```

The setup installs each project's Python dependencies. After running `.\start.ps1`, copy the hub link shown in PowerShell (`http://127.0.0.1:8500`) and open it manually when you are ready. The browser does not open automatically. The tools run on ports 8501, 8001, and 8002. Keep the PowerShell window open and press Ctrl+C to stop. Logs are in `logs/`.

For the Playbook Generator's AI features, copy `Power-BI-Playbook-Generator--main/.env.example` to `.env` in that project and set `GEMINI_API_KEY`. For AI-assisted complex conversions, copy the Tableau converter's `.env.example` to `.env` and set `GEMINI_API_KEY`.
