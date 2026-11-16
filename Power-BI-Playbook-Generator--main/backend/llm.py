"""
One function for both AI providers:
    structured_call(system, name, description, schema, prompt) -> dict

LLM_PROVIDER=gemini  (default, free tier)  -> Google Gemini, JSON-schema output
LLM_PROVIDER=claude                         -> Anthropic Claude, forced tool call

Every attempt is logged in the terminal and reported to the web page, and every request has a
time limit, so a slow or blocked connection ends with a clear message instead of waiting forever.
"""
import copy
import json
import os
import re
import threading
import time


class GenerationError(Exception):
    pass


# ---------------------------------------------------------------- status reporting
_local = threading.local()


def set_status_hook(fn):
    """app.py registers a callback per job thread; messages show on the progress page."""
    _local.hook = fn


def status(msg):
    print(f"  [{time.strftime('%H:%M:%S')}] {msg}", flush=True)
    hook = getattr(_local, "hook", None)
    if hook:
        try:
            hook(msg)
        except Exception:
            pass


# ---------------------------------------------------------------- settings
def provider():
    return os.getenv("LLM_PROVIDER", "gemini").strip().lower()


def model_label():
    if provider() == "claude":
        return f"Claude ({os.getenv('CLAUDE_MODEL', 'claude-sonnet-5-5')})"
    return f"Gemini ({os.getenv('GEMINI_MODEL', 'gemini-3.8-flash')})"


def _int_env(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


def _max_tokens():
    return _int_env("MAX_OUTPUT_TOKENS", os.getenv("CLAUDE_MAX_TOKENS", "32000"))


# ---------------------------------------------------------------- defaults filler
def fill_defaults(value, schema):
    """Makes sure every field the schema requires exists, so the web view and PDF never break
    on a missing key, whatever the model returned."""
    t = schema.get("type")
    if t == "object":
        value = value if isinstance(value, dict) else {}
        return {k: fill_defaults(value.get(k), sub) for k, sub in schema.get("properties", {}).items()}
    if t == "array":
        if not isinstance(value, list):
            return []
        return [fill_defaults(v, schema["items"]) for v in value if v is not None]
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


# ---------------------------------------------------------------- Gemini
def _strip_additional(schema):
    s = copy.deepcopy(schema)

    def walk(n):
        if isinstance(n, dict):
            n.pop("additionalProperties", None)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(s)
    return s


_WORKING_GEMINI_MODEL = None  # remembered after the first success, so later steps skip unavailable models


def _gemini_models():
    first = (_WORKING_GEMINI_MODEL or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")).strip()
    fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", "gemini-flash-latest,gemini-3.6-flash,gemini-3.5-flash-lite")
    out = []
    for m in [first, os.getenv("GEMINI_MODEL", "")] + fallbacks.split(","):
        m = m.strip()
        if m and m not in out:
            out.append(m)
    return out


def _retry_delay(err_text, default):
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", err_text)
    return min(float(m.group(1)) + 1, 45) if m else default


def _gemini_call(system, name, description, schema, prompt):
    global _WORKING_GEMINI_MODEL
    try:
        import httpx
        from google import genai
        from google.genai import errors, types
    except ImportError:
        raise GenerationError("The Gemini SDK is not installed. Run: pip install -r requirements.txt")

    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip().strip('"').strip("'")
    if not key or key.startswith("your-"):
        raise GenerationError("GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey, "
                              "add it to the .env file and restart the app.")

    req_timeout = _int_env("GEMINI_TIMEOUT", "180")            # seconds per request
    deadline = time.time() + _int_env("GEMINI_TOTAL_TIMEOUT", "420")  # seconds for this whole step
    client = genai.Client(api_key=key, http_options=types.HttpOptions(
        timeout=req_timeout * 1000, retry_options=types.HttpRetryOptions(attempts=1)))
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=_strip_additional(schema),
        max_output_tokens=_max_tokens(),
        temperature=0.3,
    )
    contents = f"Task: {description}\n\n{prompt}\n\nReturn only the JSON object for '{name}'."

    last_error = None
    for model in _gemini_models():
        for attempt in (1, 2, 3):
            if time.time() > deadline:
                raise GenerationError(f"Gemini did not complete this step in time. Last issue: {last_error or 'no response'}. "
                                      "Wait a minute and click Try again.")
            status(f"Asking {model} (attempt {attempt})…")
            t0 = time.time()
            try:
                resp = client.models.generate_content(model=model, contents=contents, config=config)
            except errors.APIError as e:
                code = getattr(e, "code", None)
                full = str(e)
                low = full.lower()
                status(f"{model}: error {code} after {time.time() - t0:.0f}s: {getattr(e, 'message', '')}")
                if code in (401, 403) or "api key not valid" in low or "api_key_invalid" in low:
                    raise GenerationError("Gemini rejected the API key. Check GEMINI_API_KEY in your .env file.")
                if code == 400 and "location is not supported" in low:
                    raise GenerationError("The Gemini API free tier is not available from your current location/network.")
                if code == 404 or "is not found" in low or "not supported for generatecontent" in low:
                    last_error = f"model '{model}' is not available to this key"
                    break
                if code == 429 and "limit: 0" in low:
                    last_error = f"model '{model}' is not included in your free-tier quota"
                    break
                if code == 429 and ("perday" in low or "per day" in low):
                    last_error = f"the daily free-tier quota for '{model}' is used up"
                    break
                if code in (429, 500, 502, 503, 504) and attempt < 3:
                    wait = _retry_delay(full, 10 * attempt)
                    last_error = f"Gemini is busy or rate-limited ({code})"
                    status(f"{model} is busy or rate-limited — retrying in {wait:.0f}s")
                    time.sleep(wait)
                    continue
                if code in (429, 500, 502, 503, 504):
                    last_error = f"Gemini is busy or rate-limited ({code})"
                    break
                raise GenerationError(f"Gemini API error ({code}): {getattr(e, 'message', full)}")
            except httpx.TimeoutException:
                last_error = f"'{model}' did not answer within {req_timeout}s"
                status(f"{model}: no answer within {req_timeout}s — trying the next model")
                break
            except (httpx.ConnectError, httpx.ProxyError, httpx.NetworkError) as e:
                raise GenerationError(
                    "Could not connect to the Gemini API (generativelanguage.googleapis.com). "
                    "A company network, VPN or firewall may be blocking it — try another network (e.g. a mobile "
                    f"hotspot), or ask IT to allow that address. Details: {e}")

            cand = (resp.candidates or [None])[0]
            finish = str(getattr(cand, "finish_reason", "") or "")
            text = resp.text or ""
            status(f"{model} answered in {time.time() - t0:.0f}s")
            if "MAX_TOKENS" in finish:
                raise GenerationError("The response was cut off because it hit the token limit. "
                                      "Increase MAX_OUTPUT_TOKENS in .env, or shorten the BRD.")
            if "SAFETY" in finish or "PROHIBITED" in finish:
                raise GenerationError("Gemini blocked the response. Please check the BRD content and try again.")
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                last_error = "Gemini returned output that was not valid JSON"
                status(f"{model}: output was not valid JSON — retrying")
                continue
            _WORKING_GEMINI_MODEL = model
            return result
    raise GenerationError(f"Gemini could not complete this step: {last_error or 'no response'}. "
                          "Run  python backend/check_gemini.py  in the terminal to see which models your key can use.")


# ---------------------------------------------------------------- Claude
def _claude_call(system, name, description, schema, prompt):
    try:
        import anthropic
    except ImportError:
        raise GenerationError("The Anthropic SDK is not installed. Run: pip install -r requirements.txt")
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key or key.startswith("your-"):
        raise GenerationError("ANTHROPIC_API_KEY is not set. Add your key to the .env file and restart the app.")
    model = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
    client = anthropic.Anthropic(api_key=key, timeout=_int_env("CLAUDE_TIMEOUT", "300"), max_retries=2)
    status(f"Asking {model}…")
    t0 = time.time()
    try:
        resp = client.messages.create(
            model=model, max_tokens=_max_tokens(), system=system,
            tools=[{"name": name, "description": description, "input_schema": schema}],
            tool_choice={"type": "tool", "name": name},
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise GenerationError("The Claude API rejected the API key. Check ANTHROPIC_API_KEY in your .env file.")
    except anthropic.NotFoundError:
        raise GenerationError(f"Model '{model}' was not found. Check CLAUDE_MODEL in your .env file.")
    except anthropic.RateLimitError:
        raise GenerationError("The Claude API rate limit was reached. Wait a minute and try again.")
    except anthropic.APITimeoutError:
        raise GenerationError("Claude did not answer in time. Please try again.")
    except anthropic.APIConnectionError:
        raise GenerationError("Could not reach the Claude API. Check your internet connection or proxy.")
    except anthropic.APIStatusError as e:
        if "credit balance" in str(e.message).lower():
            raise GenerationError("Your Claude API account has no credits. Add credits in the Claude Console "
                                  "(Settings > Billing), or switch to LLM_PROVIDER=gemini in .env.")
        raise GenerationError(f"Claude API error ({e.status_code}): {e.message}")
    status(f"{model} answered in {time.time() - t0:.0f}s")
    if resp.stop_reason == "max_tokens":
        raise GenerationError("The response was cut off because it hit the token limit. Increase MAX_OUTPUT_TOKENS in .env.")
    for block in resp.content:
        if block.type == "tool_use" and block.name == name:
            return block.input
    raise GenerationError("Claude did not return the expected structured output. Please try again.")


# ---------------------------------------------------------------- entry point
def structured_call(system, name, description, schema, prompt):
    p = provider()
    if p == "claude":
        raw = _claude_call(system, name, description, schema, prompt)
    elif p == "gemini":
        raw = _gemini_call(system, name, description, schema, prompt)
    else:
        raise GenerationError(f"Unknown LLM_PROVIDER '{p}'. Use 'gemini' or 'claude' in .env.")
    return fill_defaults(raw, schema)
