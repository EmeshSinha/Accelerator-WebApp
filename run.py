from __future__ import annotations
import subprocess, sys, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPS = [
    ("validator", ROOT / "powerBI_report_validation-main", [sys.executable, "-m", "streamlit", "run", "app_powerbi.py", "--server.address", "127.0.0.1", "--server.port", "8501", "--server.headless", "true"]),
    ("playbook", ROOT / "Power-BI-Playbook-Generator--main" / "backend", [sys.executable, "-c", "from waitress import serve; from app import app; serve(app, host='127.0.0.1', port=8001)"]),
    ("converter", ROOT / "Tableau_to_DAX_Convertor-main", [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8002"]),
]
logs = ROOT / "logs"
logs.mkdir(exist_ok=True)
children = []
server = None
try:
    for name, cwd, command in APPS:
        log = open(logs / f"{name}.log", "a", encoding="utf-8")
        proc = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        children.append((name, proc, log))
        print(f"Started {name} (PID {proc.pid})")
    time.sleep(2)
    for name, proc, _ in children:
        if proc.poll() is not None:
            print(f"{name} stopped during startup; check logs/{name}.log")
    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(*args, directory=str(ROOT), **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", 8500), handler)
    print("Copy this link to open the hub: http://127.0.0.1:8500", flush=True)
    print("Open the link manually when you are ready. Press Ctrl+C to stop all services.")
    server.serve_forever()
except KeyboardInterrupt:
    print("\nStopping services...")
finally:
    if server is not None: server.server_close()
    for _, proc, log in children:
        if proc.poll() is None: proc.terminate()
        log.close()
    for _, proc, _ in children:
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill()
