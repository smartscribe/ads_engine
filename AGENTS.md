# AGENTS.md

## Cursor Cloud specific instructions

### Architecture
Single Python (FastAPI) application serving both API and static frontend (no Node.js/npm needed). Data is stored as flat JSON files in `data/`. See `CLAUDE.md` for full product context.

### Running the dev server
```
python3 -m uvicorn dashboard.api.app:app --host 0.0.0.0 --port 8000 --reload
```
The root URL redirects to `/dashboard/pages/review.html`.

### Key gotchas
- **No `.env` file is required** to start the server — all settings in `config/settings.py` default to empty strings. API features (Anthropic, Meta, OpenAI) will fail gracefully without keys.
- **Playwright Chromium must be installed** (`python3 -m playwright install chromium`) for template→PNG rendering. This is handled by the update script but may need `python3 -m playwright install-deps chromium` on a fresh VM.
- **No linter, formatter, or test suite** is configured. `pytest` is in `requirements.txt` but no test files exist (exit code 5 = "no tests collected").
- **Startup asset healing** runs automatically — the server scans all variant JSONs and fixes stale `asset_path` references on boot. This can log `[startup] Healed N stale asset paths` and is expected.
- The CLI is available via `python -m engine.orchestrator <command>` (supports `daily`, `idea`, `concept`, `export`, `analyze`, `generate`, `full-cycle`).
