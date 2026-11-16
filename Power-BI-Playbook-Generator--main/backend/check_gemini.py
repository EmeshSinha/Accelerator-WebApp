"""
Quick Gemini check — run from the project folder:

    python backend/check_gemini.py

It tests your key and connection, lists the models your key can use, and times a tiny request
on each candidate model, so you know which GEMINI_MODEL to put in .env.
"""
import os
import sys
import time

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env"))
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


def main():
    try:
        import httpx
        from google import genai
        from google.genai import errors, types
    except ImportError:
        print("Packages are missing. Activate the virtual environment and run: pip install -r requirements.txt")
        return 1

    key = (os.getenv("GEMINI_API_KEY") or "").strip().strip('"').strip("'")
    if not key or key.startswith("your-"):
        print("GEMINI_API_KEY is not set in .env (the file must be named exactly .env, in the project folder).")
        return 1
    print(f"Key found: {key[:6]}…{key[-4:]}")

    client = genai.Client(api_key=key, http_options=types.HttpOptions(
        timeout=60_000, retry_options=types.HttpRetryOptions(attempts=1)))

    # 1. connection + list models
    print("\n1) Connecting and listing models…")
    t0 = time.time()
    try:
        names = []
        for m in client.models.list():
            actions = getattr(m, "supported_actions", None) or []
            if "gemini" in m.name and (not actions or "generateContent" in actions):
                names.append(m.name.replace("models/", ""))
    except (httpx.ConnectError, httpx.ProxyError, httpx.NetworkError, httpx.TimeoutException) as e:
        print(f"   Could not reach generativelanguage.googleapis.com ({type(e).__name__}: {e}).")
        print("   Your network, VPN or firewall is probably blocking it. Try another network (e.g. a mobile hotspot).")
        return 1
    except errors.APIError as e:
        print(f"   The API refused the request: {e.code} {getattr(e, 'message', e)}")
        return 1
    print(f"   OK in {time.time() - t0:.1f}s. {len(names)} Gemini models available to this key:")
    for n in sorted(names):
        print(f"     - {n}")

    # 2. tiny request on each candidate
    wanted = [os.getenv("GEMINI_MODEL", "gemini-3.8-flash")] + \
        os.getenv("GEMINI_FALLBACK_MODELS", "gemini-flash-latest,gemini-3.6-flash,gemini-3.5-flash-lite").split(",")
    seen, working = set(), []
    print("\n2) Testing a small request on each configured model…")
    for m in [w.strip() for w in wanted if w.strip()]:
        if m in seen:
            continue
        seen.add(m)
        t0 = time.time()
        try:
            r = client.models.generate_content(model=m, contents="Reply with the single word OK.")
            print(f"   {m:<28} OK   {time.time() - t0:5.1f}s   reply: {(r.text or '').strip()[:20]}")
            working.append(m)
        except errors.APIError as e:
            print(f"   {m:<28} FAIL {e.code}: {str(getattr(e, 'message', e))[:110]}")
        except httpx.TimeoutException:
            print(f"   {m:<28} FAIL no answer within 60s")
        except Exception as e:
            print(f"   {m:<28} FAIL {type(e).__name__}: {e}")

    print()
    if working:
        print(f"Ready. Put this in .env if it isn't already:  GEMINI_MODEL={working[0]}")
        return 0
    print("None of the configured models worked. Pick one from the list in step 1 and set GEMINI_MODEL in .env.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
