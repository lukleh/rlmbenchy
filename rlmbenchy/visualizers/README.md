# rlmbenchy Visualizers

Local web UI and TUI for inspecting `rlmbenchy` runtime logs.

Layout:
- `rlmbenchy/visualizers/web/` contains the browser visualizer, static assets, and frontend build files.
- `rlmbenchy/visualizers/tui/` contains the curses TUI viewer.
- Shared log normalization used by both lives in `rlmbenchy/logger/projection.py` — both viewers import `normalize_run` and `build_run_index` from there directly.

It reads:
- `~/.local/state/lukleh/rlmbenchy/logs/rlm/*.jsonl`

By default the visualizers reconstruct runs from the JSONL telemetry log only.

## Web

From repo root:

```bash
uv run python -m rlmbenchy.visualizers.web
```

Open:

```text
http://127.0.0.1:8027
```

Optional flags:

```bash
uv run python -m rlmbenchy.visualizers.web --host 127.0.0.1 --port 8030 --no-open
```

The web viewer has no authentication and serves full run logs. Keep the
default loopback host unless you intentionally place it behind appropriate
network access controls.

## TUI

```bash
uv run python -m rlmbenchy.visualizers.tui
uv run python -m rlmbenchy.visualizers.tui --refresh-ms 500
```

## Notes

- The runtime is still just the Python server plus static assets.
- `web/static/index.html` and `web/static/styles.css` are hand-authored source files served directly by the Python server.
- `web/src/app.ts` is the source of truth for frontend behavior.
- `web/static/app.js` is generated from `web/src/app.ts` by `npm run build` and should not be edited by hand.
- If you edit the frontend, rebuild it with:

```bash
cd rlmbenchy/visualizers/web
npm install
npm run build
```

- The UI supports browsing recent local runs from `~/.local/state/lukleh/rlmbenchy/logs/rlm/`.
- Run `uv run rlmbenchy paths` to print the resolved log directory when using env overrides.
