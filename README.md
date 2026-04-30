# TEMPOS Multi-LLM Scoring

A simple local web app that sends one TEMPOS scoring prompt to **ChatGPT, Claude, Grok, DeepSeek, and Gemini in parallel** and collects each LLM's independent ratings into a CSV file.

---

## What this does

You paste a news article into the web app, click a button, and it automatically sends the article to up to 5 AI models at the same time. Each AI scores the article using the TEMPOS suicide reporting guidelines (10 items, 0–2 scale). The results appear on screen and are saved to an Excel file you can download.

---

## Step-by-step setup (no coding experience needed)

### Step 1 — Install Python

Python is a programming language this app is built on. You need to install it once.

1. Go to **https://www.python.org/downloads/**
2. Click the big yellow **Download Python** button
3. Open the file that downloads and follow the installer
4. **Important:** on the first screen of the installer, check the box that says **"Add Python to PATH"** before clicking Install

To confirm it worked, open **Terminal** (Mac) or **Command Prompt** (Windows) and type:
```
python3 --version
```
You should see something like `Python 3.12.0`. If you do, you're good.

---

### Step 2 — Download this app

If you're reading this on GitHub:

1. Click the green **Code** button near the top of the page
2. Click **Download ZIP**
3. Open the ZIP file — it will create a folder called `tempos-multi-llm`
4. Move that folder somewhere easy to find, like your Desktop

---

### Step 3 — Open Terminal in the app folder

**On Mac:**
1. Open the **Terminal** app (search for it with Cmd+Space)
2. Type `cd ` (with a space after), then drag the `tempos-multi-llm` folder from Finder into the Terminal window — it will fill in the path automatically
3. Press Enter

**On Windows:**
1. Open the `tempos-multi-llm` folder in File Explorer
2. Click the address bar at the top, type `cmd`, and press Enter

---

### Step 4 — Get your API keys

An API key is a password that lets the app talk to each AI. You need one per AI you want to use. You only need keys for the ones you want — the app skips any AI with no key.

| AI | Where to get the key | Cost |
|---|---|---|
| **ChatGPT (OpenAI)** | https://platform.openai.com/api-keys | Requires ~$5 minimum credit |
| **Claude (Anthropic)** | https://console.anthropic.com/settings/keys | Requires credit |
| **Grok (xAI)** | https://console.x.ai | Requires credit |
| **DeepSeek** | https://platform.deepseek.com/api_keys | Requires credit |
| **Gemini (Google)** | https://aistudio.google.com/apikey | Has a free tier |

For each one: sign in (or create a free account) → find "API Keys" → click "Create API key" → copy the key (it looks like a long string of random letters and numbers).

---

### Step 5 — Run the app for the first time

In your Terminal window (from Step 3), type:

**Mac:**
```
./start.sh
```

**Windows:**
```
python backend.py
```

The first time you run it, it will automatically install everything it needs. This may take a minute. When it's done you'll see:

```
Server starting at http://127.0.0.1:8000
```

---

### Step 6 — Add your API keys

The first run creates a file called `.env` inside the `tempos-multi-llm` folder. This is where you paste your API keys.

1. Open the `tempos-multi-llm` folder in Finder (Mac) or File Explorer (Windows)
2. You may not see the `.env` file because it starts with a dot — on Mac, press **Cmd+Shift+.** to show hidden files
3. Open `.env` with any text editor (TextEdit on Mac, Notepad on Windows)
4. Paste your API keys next to the matching provider names, like this:

```
OPENAI_API_KEY=sk-proj-abc123...
ANTHROPIC_API_KEY=sk-ant-abc123...
XAI_API_KEY=xai-abc123...
DEEPSEEK_API_KEY=sk-abc123...
GOOGLE_API_KEY=AIza...
```

5. Save the file
6. Stop the app (press **Ctrl+C** in Terminal) and run `./start.sh` again

---

### Step 7 — Use the app

1. Open your browser and go to **http://127.0.0.1:8000**
2. You'll see colored dots next to each AI — green means it's ready, grey means no API key
3. Enter an **Article ID** (any number or label you want, e.g. `1` or `article_42`)
4. Paste the full article text into the big text box
5. Click **Score with all LLMs**
6. Wait — each AI takes 20–60 seconds. Results appear as they come in.
7. Click **Download results.xlsx** to get an Excel file with all scores

---

### Every time after the first

Just open Terminal, navigate to the folder, and run:
```
./start.sh
```
Then go to http://127.0.0.1:8000 in your browser.

---

## Default AI models used

| AI | Default model |
|---|---|
| OpenAI (ChatGPT) | `gpt-5.5` |
| Anthropic (Claude) | `claude-opus-4-7` |
| xAI (Grok) | `grok-4-fast-reasoning` |
| DeepSeek | `deepseek-v4-pro` |
| Google (Gemini) | `gemini-3.1-pro-preview` |

To use a different model, add a line to your `.env` file, e.g.:
```
OPENAI_MODEL=gpt-4-turbo
```

---

## Customizing the scoring prompt

The full TEMPOS scoring instructions are preloaded into the app. You can edit them by clicking the **"System prompt"** section at the top of the page. Your edits are saved in your browser automatically.

---

## Troubleshooting

**"command not found: python3"** — Python isn't installed or wasn't added to PATH. Redo Step 1.

**"address already in use"** — The app is already running. Either use the existing window or run `kill $(lsof -ti :8000)` then start again.

**Grey dot next to an AI** — That AI's key is missing or wrong in your `.env` file.

**AI returns an error** — Usually means your API account has no credit. Check the provider's billing page.

---

## Files

- `backend.py` — the server that talks to the AIs
- `static/index.html` — the web page you use in your browser
- `results.csv` — all scores saved automatically after each run
- `.env` — your API keys (never share this file)
- `.env.example` — a blank template for the `.env` file
- `requirements.txt` — list of dependencies the app installs automatically
- `start.sh` — the script that starts everything (Mac/Linux)
