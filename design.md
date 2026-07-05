# Design Document — JioPC Automated Testing Agent

## Architecture Overview

The agent is structured as six layers: a YAML-driven configuration, a shared
runner core, three independent testing components (A, B, C), a structured logger,
a trend analysis module, and a post-run LLM analysis layer with email delivery.

```
jiopc-agent.yaml
      │
      ▼
  Runner Core (src/runner.py)
      │
      ├── [Thread 1] Part C: Desktop Presence (parts/part_c.py)  ─┐
      │       PyXDG — reads .desktop files                         ├─ parallel
      ├── [Thread 2] Part A: Web App Testing (parts/part_a.py)   ─┘
      │       Selenium + Firefox headless
      │
      └── Part B: Native App Health (parts/part_b.py)  ← sequential
              subprocess + psutil
                      │
                      ▼
            Logger (src/logger.py)
            JSON Lines → ~/.local/share/jiopc/agent/test_run_<ts>.log
                      │
                      ▼
            Trend Analysis (src/trend.py)
            trend_history.json → regression/improvement report
                      │
                      ▼
            LLM Analysis (analyse.py)
            prompt + log → PROMOTE / HOLD
                      │
                      ▼
            Email Summary (src/emailer.py)
            HTML report → SMTP → recipient
```

## Component Design

### Runner Core (src/runner.py)

Reads YAML at startup. Executes parts in order: Part C and Part A run in parallel
threads, then Part B runs sequentially. Each part is wrapped in try/except so a
crash in one never prevents others from running and the summary is always written.

Parallel execution uses Python `threading.Thread` — safe because Part C is pure
file I/O and Part A is pure network I/O with no shared mutable state. Part B must
remain sequential because it launches GUI apps that compete for display and audio
resources.

A `--no-parallel` flag allows engineers to fall back to sequential execution if
needed (e.g. debugging, resource-constrained environments).

Returns exit code 0 on all-pass, non-zero on any FAIL, MISSING, MISPLACED, or
DEGRADED. BLOCKED is not a failure.

### Logger (src/logger.py)

Writes one JSON object per line to the log file. Every record contains:
`ts`, `component`, `name`, `result`, `duration_ms`, `detail`.
Final line is a summary block with total counts and per-component breakdown.
All results are also stored in `self.all_results` for trend analysis consumption.

`all_passed()` returns False if any of FAIL, MISSING, MISPLACED, or DEGRADED
is non-zero — all four are treated as gate failures. BLOCKED is excluded.

### Trend Analysis (src/trend.py)

After every run, saves a summary entry to
`~/.local/share/jiopc/agent/trend_history.json` (max 50 entries, oldest pruned).
Each entry stores: timestamp, log path, counts, and per-test result map.

On each run, compares current results against the previous entry and classifies:
- **Regression**: was PASS/BLOCKED, now FAIL/MISSING/MISPLACED/DEGRADED
- **Improvement**: was FAIL/MISSING/MISPLACED/DEGRADED, now PASS/BLOCKED

Prints a pass-rate trend table for the last 5 runs with a "◄ current" marker.
The LLM prompt is instructed to treat regressions as HOLD signals regardless
of total pass count.

### Part A — Web App Testing

Technology: Selenium 4 + Firefox (snap) + geckodriver.

**Why Selenium and not Playwright:** Playwright does not support Ubuntu 26.04
(confirmed during development). Selenium with Firefox snap is the correct choice.

One Firefox instance is shared across all URL tests to avoid the ~10s per-instance
startup overhead. Each URL gets its own page load with timeout.

**Firefox binary discovery:** Uses a fallback chain — snap revision paths sorted
descending, then standard locations. `/usr/bin/firefox` is deliberately skipped
— it is a shell wrapper script that Selenium rejects with "binary is not a Firefox
executable". Auto-detected at runtime so the agent works across snap revisions.

**Bot detection:** Checks page title and source for known signals. Returns BLOCKED
not FAIL. `bot_detection_expected: true` in YAML suppresses the "unexpected" flag.

**Blank/error page detection:** Checks both body text length and title. JS-heavy
SPAs like JioCinema render empty body in headless mode but have a valid title —
both must be absent before flagging as blank, avoiding false FAILs.

Result types: PASS, FAIL (timeout, missing element, error page), BLOCKED.

### Part B — Native App Health

Technology: subprocess + psutil.

**Why Xvfb was dropped:** Xvfb creates `/tmp/.X<n>-lock` which violates the
"nothing written to /tmp" constraint. Stale lock files from crashed instances
also caused repeated agent termination during development. The agent uses the
engineer's existing LxQt session DISPLAY instead.

**Full Exec= command line:** Launches using the full command from the .desktop
`Exec=` field (not just the binary) — required for apps with mandatory arguments.
`%U`, `%f`, `%F` field codes are stripped before launching.

**Process matching:** Uses launched PID first, then name/cmdline filtered to
processes created at or after launch time — prevents matching pre-existing
instances of the same app.

**Safe cleanup:** Process tree always terminated in `finally` block. Self-PID
check prevents the agent from accidentally killing itself. Configurable cool-down
(default 2s) between apps prevents resource contention.

Result types: PASS, FAIL (binary missing, process timeout), DEGRADED (crashed).

### Part C — Desktop & Start Menu Presence

Technology: PyXDG (`xdg.DesktopEntry`). Read-only — no app launching, no network.
Completes in under 1 second for all 15 apps. Safe to run in parallel with Part A.

Checks .desktop file exists, parses `Categories=`, compares against YAML expected
category, then checks file/symlink presence inside `~/Desktop/<folder>/`.

**Desktop folder matching:** Uses exact filename from YAML `desktop_file` as
primary match key — correctly handles apps like GNOME Calculator whose filename
(`org.gnome.Calculator.desktop`) doesn't match display name. Fuzzy name match
as secondary fallback.

Result types: PASS, MISSING (.desktop not found), MISPLACED (wrong category/folder).

### LLM Analysis Layer (analyse.py)

Model-agnostic — API base URL, model, and key from environment variables.
Supports Anthropic native API and any OpenAI-compatible endpoint.
`--no-email` flag skips email delivery for quick analysis without notification.

### Email Summary (src/emailer.py)

Sends a formatted HTML email after LLM analysis. Includes PROMOTE/HOLD
recommendation with colour-coded header (green/red), pass/fail counts, full
analysis text, and log file path. Plain-text fallback included for email clients
that don't render HTML. SMTP credentials configured in YAML under `email:` key.
Tested with Mailtrap sandbox — compatible with any SMTP provider.

## YAML Schema

```yaml
agent:
  log_dir: string           # log output path
  llm_prompt_file: string   # path to LLM prompt
  cool_down_seconds: int    # pause between Part B launches (default: 2)

email:                      # optional — omit to skip email
  smtp_host: string
  smtp_port: int
  smtp_user: string
  smtp_pass: string
  sender: string
  recipient: string

web_apps:                   # Part A
  - name: string
    url: string
    load_timeout_ms: int
    bot_detection_expected: bool
    elements:
      - selector: string    # CSS selector
        description: string

native_apps:                # Part B
  - name: string
    desktop_file: string
    process_name: string
    launch_timeout_s: int

desktop_presence:           # Part C
  - name: string
    desktop_file: string
    desktop_folder: string
    start_menu_category: string
```

## Technology Choices

| Area | Choice | Rationale |
|------|--------|-----------|
| Language | Python 3.11+ | Available on Ubuntu 24.04, rich automation ecosystem |
| Web testing | Selenium 4 + Firefox snap | Playwright does not support Ubuntu 26.04 |
| Browser binary | snap revision path | `/usr/bin/firefox` is a wrapper rejected by Selenium |
| Process management | psutil | Accurate VmRSS, clean process tree termination |
| .desktop parsing | PyXDG | Correct Freedesktop spec implementation |
| YAML | PyYAML | Standard, supports comments |
| LLM client | httpx | Supports both Anthropic and OpenAI-compatible APIs |
| Log format | JSON Lines | Machine-readable, streamable, LLM-consumable |
| Parallelism | threading.Thread | Part A (network) + Part C (file I/O) safely concurrent |
| Virtual display | Dropped — uses session DISPLAY | Avoids /tmp constraint + stale lock flakiness |
| Email | smtplib + MIME | Standard library, no extra dependencies |
| Trend storage | JSON file in home dir | Survives VM reassignment via NFS home |

## Bonus Goals

| Goal | Implementation |
|------|---------------|
| Trend analysis | src/trend.py — saves per-run summary, detects regressions |
| Summary email | src/emailer.py — HTML report via SMTP after LLM analysis |
| CI/CD pipeline | .github/workflows/jiopc-agent.yml — GitHub Actions |
| Parallel execution | threading.Thread in runner.py — Part A + C concurrent |

## Performance

| Metric | Measured | Limit |
|--------|----------|-------|
| Full run p50 | 102s | 300s |
| Full run p95 | 109s | 300s |
| Peak RAM (agent only) | ~53 MB | 150 MB |
| Sustained CPU | 1–3% | 20% |
| Part C alone | < 1s | 30s |

## Known Limitations

- Playwright not usable on Ubuntu 26.04 — Selenium is the correct replacement.
- Firefox snap binary path auto-detected but depends on snap revisions present.
- Bot-detection sites (JioSaavn, YouTube) always BLOCKED in headless mode.
- JS-heavy SPAs (JioCinema) render empty body — title used as secondary signal.
- No parallel execution for Part B — GUI app launches must be isolated.
- Desktop folder symlinks must be created once before Part C (see INSTALL.md).
