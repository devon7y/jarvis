# Repository Guidelines

## Project Structure & Module Organization
The Python backend lives at the repo root. `server.py` is the FastAPI and WebSocket entrypoint; adjacent modules such as `actions.py`, `browser.py`, `memory.py`, `planner.py`, and the Apple integration files (`calendar_access.py`, `mail_access.py`, `notes_access.py`) hold the core logic. Frontend code is isolated in `frontend/`, with sources in `frontend/src/` and production output in `frontend/dist/`. Tests live in `tests/`. Keep reusable prompt scaffolds in `templates/prompts/`, helper scripts in `helpers/`, and treat `data/` as local runtime state (`jarvis.db`, usage logs), not hand-edited source.

## Build, Test, and Development Commands
Install backend dependencies with `pip install -r requirements.txt`. Install the UI with `cd frontend && npm install`. Start the backend with `python server.py --reload`; add `--ssl` or generate `key.pem` and `cert.pem` if you need the secure browser flow from the README. Run the frontend with `cd frontend && npm run dev`. Create a production bundle with `cd frontend && npm run build`, and preview it with `cd frontend && npm run preview`. Run the main automated suite with `pytest -q`. Use `python3 tests/test_classifier.py` only when `ANTHROPIC_API_KEY` is set; browser tests may require `python -m playwright install`.

## Coding Style & Naming Conventions
Follow the surrounding style because no formatter config is checked in. Python uses 4-space indentation, module docstrings, `snake_case` functions, and descriptive filenames such as `work_mode.py`. TypeScript in `frontend/src/` uses 2-space indentation, double quotes, semicolons, and small focused modules like `voice.ts` or `orb.ts`. Keep new environment variables documented in `.env.example`, and prefer narrow, single-purpose helpers over large utility dumps.

## Testing Guidelines
Add tests under `tests/` using `test_*.py` names and `test_*` functions. Prefer deterministic `pytest` coverage with fixtures and mocks; reserve live network and API-dependent checks for explicitly scoped integration tests. If a change touches browser automation, note whether Playwright and network access were available when you ran the suite.

## Commit & Pull Request Guidelines
Recent history uses short, imperative subjects such as `Add Marvel/Disney disclaimer to README`. Keep commit titles concise, sentence case, and focused on one change. PRs should explain user-facing impact, list commands run, link the issue when applicable, and include screenshots or short recordings for frontend or voice UX changes.

## Security & Configuration Tips
Never commit real secrets from `.env`. API keys, local certs, and macOS-specific credentials should stay local. Changes that affect Calendar, Mail, Notes, or AppleScript behavior should call out the macOS-only assumption in the PR.
