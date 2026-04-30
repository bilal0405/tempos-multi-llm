"""
TEMPOS multi-LLM scoring backend.

Sends one prompt to up to 5 LLM providers in parallel and returns each
response independently. Any provider missing an API key is skipped.
"""

import asyncio
import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

ROOT = Path(__file__).parent
RESULTS_CSV = ROOT / "results.csv"

DEFAULT_MODELS = {
    "openai": "gpt-5.5",
    "anthropic": "claude-opus-4-7",
    "xai": "grok-4-fast-reasoning",
    "deepseek": "deepseek-v4-pro",
    "google": "gemini-3.1-pro-preview",
}

# Display names used as the {{RATER_ID}} value baked into the prompt for each provider.
DISPLAY_NAMES = {
    "openai": "ChatGPT",
    "anthropic": "Claude",
    "xai": "Grok",
    "deepseek": "DeepSeek",
    "google": "Gemini",
}


def model_for(provider: str) -> str:
    env_key = f"{provider.upper()}_MODEL"
    return os.getenv(env_key) or DEFAULT_MODELS[provider]


def rater_id_for(provider: str) -> str:
    return f"{DISPLAY_NAMES[provider]} ({model_for(provider)})"


def build_prompt(template: str, article_id: str, rater_id: str, article_text: str) -> str:
    """Substitute placeholders and append the article text to the template."""
    filled = template.replace("{{ARTICLE_ID}}", str(article_id)).replace(
        "{{RATER_ID}}", rater_id
    )
    return f"{filled}\n\nARTICLE TEXT:\n{article_text}"


# ---------- Provider clients ----------

def _openai_content(prompt: str, images: list[dict]) -> list[dict]:
    """Build an OpenAI-format content array with optional image_url parts."""
    parts: list[dict] = [{"type": "text", "text": prompt}]
    for img in images:
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{img['mime_type']};base64,{img['base64']}"},
        })
    return parts


async def call_openai(prompt: str, model: str, timeout: float, images: list[dict] | None = None) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    content = _openai_content(prompt, images or [])
    # Flatten to plain string when no images — some models reject content arrays
    msg_content = content if images else prompt
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": msg_content}],
    }
    # Reasoning-tier models (gpt-5.x, o-series) only accept the default temperature.
    if not (model.startswith("gpt-5") or model.startswith("o3") or model.startswith("o4")):
        payload["temperature"] = 0
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def call_anthropic(prompt: str, model: str, timeout: float, images: list[dict] | None = None) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    parts: list[dict] = []
    for img in (images or []):
        parts.append({
            "type": "image",
            "source": {"type": "base64", "media_type": img["mime_type"], "data": img["base64"]},
        })
    parts.append({"type": "text", "text": prompt})
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": parts}],
            },
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"]


async def call_xai(prompt: str, model: str, timeout: float, images: list[dict] | None = None) -> str:
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("XAI_API_KEY not set")
    content = _openai_content(prompt, images or [])
    msg_content = content if images else prompt
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": msg_content}],
                "temperature": 0,
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def call_deepseek(prompt: str, model: str, timeout: float, images: list[dict] | None = None) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
    # DeepSeek doesn't support vision — send text only
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def call_google(prompt: str, model: str, timeout: float, images: list[dict] | None = None) -> str:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:streamGenerateContent?alt=sse&key={api_key}"
    )
    generation_config: dict = {}
    # Gemini 3.x thinking models: "low" reduces latency without disabling thinking.
    # Do NOT set temperature alongside thinkingConfig — the API rejects it.
    if "gemini-3" in model:
        generation_config["thinkingConfig"] = {"thinkingLevel": "low"}
    else:
        generation_config["temperature"] = 0
    parts: list[dict] = []
    for img in (images or []):
        parts.append({"inline_data": {"mime_type": img["mime_type"], "data": img["base64"]}})
    parts.append({"text": prompt})
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": generation_config,
    }
    # Use separate connect vs. read timeouts. The read timeout applies per-chunk,
    # so a long inter-chunk pause on a thinking model won't kill the stream.
    # A unified timeout(=timeout) would apply per-chunk and fire mid-stream.
    httpx_timeout = httpx.Timeout(connect=15.0, read=timeout, write=30.0, pool=5.0)
    backoff = 4.0
    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=httpx_timeout) as client:
                async with client.stream("POST", url, json=payload) as r:
                    if r.status_code in (429, 503):
                        body = await r.aread()
                        last_err = RuntimeError(
                            f"HTTP {r.status_code}: {body.decode()[:200]}"
                        )
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    r.raise_for_status()
                    chunks: list[str] = []
                    async for line in r.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        # Surface API-level errors embedded in the stream
                        if "error" in obj:
                            raise RuntimeError(
                                f"Gemini stream error: {json.dumps(obj['error'])}"
                            )
                        try:
                            chunks.append(
                                obj["candidates"][0]["content"]["parts"][0]["text"]
                            )
                        except (KeyError, IndexError):
                            continue
                    return "".join(chunks)
        except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            # Don't retry on timeout — it won't help and burns the budget
            raise RuntimeError(f"Gemini timed out after {timeout}s: {e}") from e
        except RuntimeError:
            raise
        except Exception as e:
            last_err = e
            if attempt < 2:
                await asyncio.sleep(backoff)
                backoff *= 2
    raise last_err or RuntimeError("Google request failed after retries")


PROVIDERS = {
    "openai": call_openai,
    "anthropic": call_anthropic,
    "xai": call_xai,
    "deepseek": call_deepseek,
    "google": call_google,
}


# ---------- Parsing the response ----------

EXCEL_COLUMNS = [
    "Article ID",
    "Rater ID",
    "Rater Type (Person/AI)",
    "TEMPOS 1 Rating",
    "TEMPOS 2 Rating",
    "TEMPOS 3 Rating",
    "TEMPOS 4 Rating",
    "TEMPOS 5 Rating",
    "TEMPOS 6 Rating",
    "TEMPOS 7 Rating",
    "TEMPOS 8 Rating",
    "TEMPOS 9 Rating",
    "TEMPOS 10 Rating",
    "TEMPOS total score",
]


def extract_json(text: str) -> Optional[dict]:
    """Find the first JSON object in the response."""
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def extract_excel_row(text: str) -> Optional[list[str]]:
    """Pull the last tab-delimited row of 14 fields out of the response."""
    for line in reversed(text.strip().splitlines()):
        clean = line.strip().strip("`").strip()
        if "\t" in clean:
            fields = clean.split("\t")
            if len(fields) == len(EXCEL_COLUMNS):
                return fields
    return None


# ---------- API ----------

class ImageAttachment(BaseModel):
    mime_type: str
    base64: str


class ScoreRequest(BaseModel):
    system_prompt: str
    article_text: str
    article_id: str
    providers: Optional[list[str]] = None
    timeout_seconds: float = 300.0
    images: list[ImageAttachment] = []


class ProviderResult(BaseModel):
    provider: str
    rater_id: str
    model: str
    ok: bool
    raw_text: Optional[str] = None
    parsed_json: Optional[dict] = None
    excel_row: Optional[list[str]] = None
    error: Optional[str] = None
    latency_ms: Optional[int] = None


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/providers")
def list_providers():
    """Report which providers are configured (have API keys set)."""
    out = []
    for p in PROVIDERS:
        env_key = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "xai": "XAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "google": "GOOGLE_API_KEY",
        }[p]
        out.append(
            {
                "provider": p,
                "display_name": DISPLAY_NAMES[p],
                "model": model_for(p),
                "configured": bool(os.getenv(env_key)),
            }
        )
    return {"providers": out}


async def score_one(
    provider: str, prompt_template: str, article_id: str, article_text: str,
    timeout: float, images: list[dict] | None = None,
) -> ProviderResult:
    rater_id = rater_id_for(provider)
    model = model_for(provider)
    prompt = build_prompt(prompt_template, article_id, rater_id, article_text)
    start = datetime.now()
    try:
        text = await PROVIDERS[provider](prompt, model, timeout, images)
        latency = int((datetime.now() - start).total_seconds() * 1000)
        return ProviderResult(
            provider=provider,
            rater_id=rater_id,
            model=model,
            ok=True,
            raw_text=text,
            parsed_json=extract_json(text),
            excel_row=extract_excel_row(text),
            latency_ms=latency,
        )
    except httpx.HTTPStatusError as e:
        return ProviderResult(
            provider=provider,
            rater_id=rater_id,
            model=model,
            ok=False,
            error=f"HTTP {e.response.status_code}: {e.response.text[:300]}",
            latency_ms=int((datetime.now() - start).total_seconds() * 1000),
        )
    except Exception as e:
        return ProviderResult(
            provider=provider,
            rater_id=rater_id,
            model=model,
            ok=False,
            error=f"{type(e).__name__}: {e}",
            latency_ms=int((datetime.now() - start).total_seconds() * 1000),
        )


def append_to_csv(results: list[ProviderResult]) -> int:
    """Append valid Excel rows to results.csv. Returns number of rows added."""
    new_file = not RESULTS_CSV.exists()
    rows_added = 0
    with RESULTS_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["timestamp_utc"] + EXCEL_COLUMNS)
        for r in results:
            if r.ok and r.excel_row:
                writer.writerow([datetime.utcnow().isoformat()] + r.excel_row)
                rows_added += 1
    return rows_added


@app.post("/api/score")
async def score(req: ScoreRequest):
    selected = req.providers or [
        p for p in PROVIDERS if os.getenv({
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "xai": "XAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "google": "GOOGLE_API_KEY",
        }[p])
    ]
    if not selected:
        return {"results": [], "csv_rows_added": 0, "warning": "No API keys configured. Edit .env and restart."}

    imgs = [i.model_dump() for i in req.images]
    tasks = [
        score_one(p, req.system_prompt, req.article_id, req.article_text, req.timeout_seconds, imgs or None)
        for p in selected
    ]
    results = await asyncio.gather(*tasks)
    rows_added = append_to_csv(results)
    return {
        "results": [r.model_dump() for r in results],
        "csv_rows_added": rows_added,
        "csv_path": str(RESULTS_CSV),
    }


@app.post("/api/score_stream")
async def score_stream(req: ScoreRequest):
    """Stream provider results as Server-Sent Events as each provider completes."""
    selected = req.providers or [
        p for p in PROVIDERS if os.getenv({
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "xai": "XAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "google": "GOOGLE_API_KEY",
        }[p])
    ]

    async def event_stream():
        if not selected:
            yield f"event: warning\ndata: {json.dumps({'warning': 'No API keys configured. Edit .env and restart.'})}\n\n"
            yield "event: done\ndata: {}\n\n"
            return

        yield f"event: start\ndata: {json.dumps({'providers': selected})}\n\n"

        imgs = [i.model_dump() for i in req.images]
        tasks = {
            asyncio.create_task(
                score_one(p, req.system_prompt, req.article_id, req.article_text, req.timeout_seconds, imgs or None)
            ): p
            for p in selected
        }
        completed_results: list[ProviderResult] = []
        for coro in asyncio.as_completed(tasks):
            result = await coro
            completed_results.append(result)
            yield f"event: result\ndata: {json.dumps(result.model_dump())}\n\n"

        rows_added = append_to_csv(completed_results)
        yield f"event: done\ndata: {json.dumps({'csv_rows_added': rows_added, 'csv_path': str(RESULTS_CSV)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/results/clear")
def clear_results():
    if RESULTS_CSV.exists():
        RESULTS_CSV.unlink()
    return {"ok": True}


@app.get("/api/download-xlsx")
def download_xlsx():
    import io
    import openpyxl
    from fastapi.responses import Response

    if not RESULTS_CSV.exists():
        return {"error": "No results yet."}

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "TEMPOS Results"

    with RESULTS_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=results.xlsx"},
    )


# Serve the static frontend at /
app.mount("/", StaticFiles(directory=str(ROOT / "static"), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
