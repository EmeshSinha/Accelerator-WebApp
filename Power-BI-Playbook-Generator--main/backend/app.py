"""
Power BI Playbook Accelerator — Flask backend.

  GET  /                         -> web app (frontend folder)
  POST /api/generate             -> upload BRD, validate, start a generation job
  GET  /api/jobs/<id>            -> job status, and the playbook when finished
  GET  /api/jobs/<id>/pdf        -> download the playbook as PDF
"""
import json
import os
import re
import tempfile
import threading
import time
import traceback
import uuid
from datetime import date

import sys

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
try:  # never crash on a console that can't print some characters
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
load_dotenv(os.path.join(HERE, "..", ".env"))

from brd_parser import SUPPORTED, BRDReadError, read_brd  # noqa: E402
from generator import GenerationError, generate_playbook  # noqa: E402
import llm  # noqa: E402
from llm import model_label  # noqa: E402
from pdf_builder import build_pdf  # noqa: E402

FRONTEND = os.path.join(HERE, "..", "frontend")
OUTPUT = os.path.join(HERE, "..", "output")
os.makedirs(OUTPUT, exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

STEPS = [
    ("validate", "Reading the BRD"),
    ("data_foundation", "Designing sources, tables and relationships"),
    ("measures_pages", "Writing KPI DAX and report pages"),
    ("access_delivery", "Planning security, refresh, deployment and delivery"),
    ("pdf", "Building the PDF"),
]
JOBS = {}
LOCK = threading.Lock()


def demo_mode():
    return os.getenv("DEMO_MODE", "false").strip().lower() in ("1", "true", "yes")


def generate_demo(brd, progress):
    """Offline mode for trying the UI without an API key: uses a bundled sample playbook."""
    with open(os.path.join(HERE, "sample_playbook.json"), encoding="utf-8") as f:
        sample = json.load(f)
    for step in ("data_foundation", "measures_pages", "access_delivery"):
        progress(step)
        time.sleep(1.2)
    ov = brd["overview"]
    pb = {k: v for k, v in sample.items() if k != "key_decisions"}
    pb["doc_control"] = {"client": ov.get("client") or "FreshMart Retail Pvt. Ltd.",
                         "project": ov.get("project") or "Sales Performance Dashboard",
                         "domain": ov.get("domain") or "Retail",
                         "business_owner": ov.get("business_owner") or "Head of Sales — R. Mehta",
                         "generated_on": date.today().strftime("%d %B %Y").lstrip("0"),
                         "prepared_by": "Xebia — Data & Analytics"}
    pb["executive_summary"] = {
        "objective": ov.get("objective") or "Give sales leadership a single daily view of revenue, margin and store performance against target.",
        "scope": ov.get("in_scope") or "Sales, margin and target tracking for 120 stores across 4 regions.",
        "at_a_glance": {"source_systems": len(pb["source_systems"]["items"]), "tables": len(pb["tables"]["items"]),
                        "columns": len(pb["tables"]["columns"]), "kpis": len(pb["kpis"]["items"]),
                        "report_pages": len(pb["report_pages"]["pages"])},
        "key_decisions": sample["key_decisions"]}
    return pb


def _set(job_id, **kw):
    with LOCK:
        JOBS[job_id].update(kw)


def _run(job_id, brd):
    started = time.time()
    llm.set_status_hook(lambda msg: _set(job_id, detail=msg))
    labels = dict(STEPS)

    def progress(step):
        _set(job_id, step=step, detail="")
        print(f"\n  [{time.strftime('%H:%M:%S')}] Step: {labels.get(step, step)}", flush=True)

    print(f"\n  [{time.strftime('%H:%M:%S')}] New playbook from {JOBS[job_id]['file_name']} "
          f"({'template' if brd['follows_template'] else 'free-form'} BRD, {len(brd['text']):,} characters)", flush=True)
    try:
        pb = generate_demo(brd, progress) if demo_mode() else generate_playbook(brd, progress)
        progress("pdf")
        safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{pb['doc_control']['client']}_{pb['doc_control']['project']}").strip("_")
        pdf_path = os.path.join(OUTPUT, f"Power_BI_Playbook_{safe or 'Report'}_{job_id[:6]}.pdf")
        build_pdf(pb, pdf_path)
        _set(job_id, status="done", step="done", playbook=pb, pdf=pdf_path, detail="")
        print(f"  [{time.strftime('%H:%M:%S')}] Done in {time.time() - started:.0f}s -> {pdf_path}", flush=True)
    except GenerationError as e:
        print(f"  [{time.strftime('%H:%M:%S')}] FAILED: {e}", flush=True)
        _set(job_id, status="error", error=str(e))
    except Exception as e:  # unexpected — keep the details in the console
        traceback.print_exc()
        _set(job_id, status="error", error=f"Unexpected error: {e}")


@app.get("/")
def index():
    return send_from_directory(FRONTEND, "index.html")


@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(FRONTEND, path)


@app.get("/api/config")
def config():
    return jsonify({"steps": [{"key": k, "label": v} for k, v in STEPS], "demo_mode": demo_mode(),
                    "model": "Demo" if demo_mode() else model_label(), "accept": ",".join(SUPPORTED)})


@app.post("/api/generate")
def generate():
    f = request.files.get("brd")
    if not f or not f.filename:
        return jsonify({"error": "Please choose a BRD file to upload."}), 400
    ext = os.path.splitext(f.filename.lower())[1]
    if ext not in SUPPORTED:
        return jsonify({"error": "Please upload an Excel (.xlsx), Word (.docx), PDF, CSV or text file."}), 400

    fd, tmp = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    try:
        f.save(tmp)
        brd = read_brd(tmp, f.filename)
    except BRDReadError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    job_id = uuid.uuid4().hex
    with LOCK:
        JOBS[job_id] = {"status": "running", "step": "data_foundation", "detail": "", "started": time.time(),
                        "error": None, "playbook": None, "pdf": None,
                        "file_name": f.filename, "follows_template": brd["follows_template"]}
    threading.Thread(target=_run, args=(job_id, brd), daemon=True).start()
    return jsonify({"job_id": job_id, "follows_template": brd["follows_template"]})


@app.get("/api/jobs/<job_id>")
def job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found. It may have been lost when the server restarted."}), 404
    return jsonify({k: v for k, v in job.items() if k != "pdf"})


@app.get("/api/jobs/<job_id>/pdf")
def job_pdf(job_id):
    job = JOBS.get(job_id)
    if not job or not job.get("pdf"):
        return jsonify({"error": "PDF not available."}), 404
    return send_file(job["pdf"], as_attachment=True, download_name=os.path.basename(job["pdf"]).rsplit("_", 1)[0] + ".pdf",
                     mimetype="application/pdf")


def _free_port(start):
    """Uses PORT if it is free, otherwise the next free port, so a busy port never stops the app."""
    import socket
    for p in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


if __name__ == "__main__":
    import webbrowser

    port = _free_port(int(os.getenv("PORT", "5000")))
    url = f"http://localhost:{port}"
    mode = "DEMO MODE (no AI calls)" if demo_mode() else f"AI: {model_label()}"
    print("\n  Power BI Playbook Accelerator is running.")
    print(f"  Open {url} in your browser (it should open automatically).")
    print(f"  {mode}")
    print("  Keep this window open while you use the app. Close it to stop the app.\n")
    if os.getenv("OPEN_BROWSER", "true").strip().lower() not in ("0", "false", "no"):
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
