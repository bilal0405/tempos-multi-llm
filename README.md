# TEMPOS Multi-LLM Scoring

A simple local web app that sends one TEMPOS scoring prompt to **ChatGPT, Claude, Grok, DeepSeek, and Gemini in parallel** and collects each LLM's independent ratings into a CSV file.

## Quick start

```bash
cd ~/Desktop/tempos-multi-llm
./start.sh
```

The first run creates a `.env` file. Open it, paste in your API keys, then run `./start.sh` again. The web UI opens at http://127.0.0.1:8000.

## Where to get API keys

Each provider has its own dashboard. You only need keys for the LLMs you want to use — providers with no key are skipped automatically.

| Provider | Where to get the key | Notes |
|---|---|---|
| **OpenAI (ChatGPT)** | https://platform.openai.com/api-keys | Requires ~$5 minimum credit |
| **Anthropic (Claude)** | https://console.anthropic.com/settings/keys | Requires credit |
| **xAI (Grok)** | https://console.x.ai | Requires credit |
| **DeepSeek** | https://platform.deepseek.com/api_keys | Requires credit |
| **Google (Gemini)** | https://aistudio.google.com/apikey | Has a free tier |

For each, you'll: sign in → "Create API key" → copy the key (starts with `sk-…`, `xai-…`, etc.) → paste into `.env`.

## How to use

1. Enter an **Article ID** (e.g. `42`)
2. Paste the **article text** into the big text box
3. Click **Score with all LLMs**
4. Each LLM's response appears in its own card with the parsed scores. The Excel rows are appended to `results.csv` automatically.
5. Click **Download results.xlsx** to grab the accumulated results as an Excel file.

The `Rater ID` is automatically set to `<LLM Name> (<model>)` — e.g. `ChatGPT (gpt-5.5)`, `Claude (claude-opus-4-7)`.

## Customizing models

By default the app uses:
- OpenAI: `gpt-5.5`
- Anthropic: `claude-opus-4-7`
- xAI: `grok-4-fast-reasoning`
- DeepSeek: `deepseek-v4-pro`
- Google: `gemini-3.1-pro-preview`

To override, set e.g. `OPENAI_MODEL=gpt-4-turbo` in your `.env`.

## Customizing the prompt

The default prompt (the full TEMPOS scoring instructions) is preloaded into the UI. You can edit it inline by clicking the "System prompt" expander. Edits are remembered locally in your browser.

## Files

- `backend.py` — FastAPI server, parallel LLM calls, CSV writer
- `static/index.html` — the web UI
- `results.csv` — accumulates Excel rows from every successful scoring run
- `.env` — your API keys (never commit this)
- `requirements.txt` — Python dependencies
- `start.sh` — sets up venv, installs deps, runs the server
