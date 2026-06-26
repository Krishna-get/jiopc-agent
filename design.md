# Design Document — JioPC Automated Testing Agent

## Architecture Overview

The agent is structured as five layers: a YAML-driven configuration, a shared
runner core, three independent testing components (A, B, C), a structured logger,
and a post-run LLM analysis layer. All layers are loosely coupled — each part can
run independently, and the LLM layer requires no changes to add new analysis logic.

```
jiopc-agent.yaml
      │
      ▼
  Runner Core (src/runner.py)
      │
      ├── Part C: Desktop Presence (parts/part_c.py)
      │       PyXDG — reads .desktop files, checks categories and folders
      │
      ├── Part B: Native App Health (parts/part_b.py)
      │       subprocess + psutil — launches, monitors, cleans up
      │
      └── Part A: Web App Testing (parts/part_a.py)
              Selenium + Firefox headless — loads URLs, checks elements
                      │
                      ▼
            Logger (src/logger.py)
            JSON Lines → ~/.local/share/jiopc/agent/test_run_<ts>.log
                      │
                      ▼
            LLM Analysis (analyse.py)
            prompt + log → PROMOTE / HOLD
```

## Component Design

### Runner Core (src/runner.py)

Reads YAML at startup. Executes parts in order C → B → A (cheapest to most
expensive). Each part is wrapped in a try/except so a crash in one part never
prevents the others from running and the log summary is always written. Returns
exit code 0 on all-pass, non-zero on any FAIL, MISSING, MISPLACED, or DEGRADED.
BLOCKED is not treated as a failure.

### Logger (src/logger.py)

Writes one JSON object per line to the log file. Every record contains:
`ts`, `component`, `name`, `result`, `duration_ms`, `detail`.
Final line is a summary block with total counts and per-component breakdown.
Prints colour-coded terminal output during the run.

`all_passed()` returns False if any of FAIL, MISSING, MISPLACED, or DEGRADED
is non-zero — all four are treated as gate failures. BLOCKED is not a failure.

### Part A — Web App Testing

Technology: Selenium 4 + Firefox (snap) + geckodriver.

**Why Selenium and not Playwright:** Playwright does not support Ubuntu 26.04
(confirmed during development — installation fails with "Playwright does not
support chromium/firefox on ubuntu26.04-x64"). Selenium with Firefox snap is
the correct choice for this platform.

One Firefox instance is shared across all URL tests to avoid the ~10s per-instance
startup overhead of the snap binary. Each URL gets its own page load with timeout.

**Firefox binary discovery:** The agent uses a fallback chain to find the real
Firefox binary — snap revision paths sorted descending, then standard locations.
`/usr/bin/firefox` is deliberately skipped — it is a shell wrapper script that
Selenium rejects with "binary is not a Firefox executable". The real binary lives
at `/snap/firefox/<revision>/usr/lib/firefox/firefox`. This is auto-detected at
runtime so the agent works across snap revisions without code changes.

**geckodriver discovery:** Uses `shutil.which('geckodriver')` first, then checks
`/snap/bin/geckodriver` and other standard paths. geckodriver is bundled with the
Firefox snap — no separate installation is needed.

**Bot detection:** Checks page title and source for known signals (Cloudflare,
CAPTCHA, "just a moment"). Returns BLOCKED — not FAIL — for challenged pages.
`bot_detection_expected: true` in YAML suppresses the "unexpected" flag.

**Blank/error page detection:** Checks both body text length and page title.
JS-heavy SPAs like JioCinema render an empty body in headless mode but have a
valid title — both must be absent before a page is flagged as blank. This avoids
false FAILs on legitimate single-page applications.

Result types: PASS, FAIL (timeout, missing element, error page), BLOCKED.

### Part B — Native App Health

Technology: subprocess + psutil.

**Why Xvfb was dropped:** An earlier implementation used Xvfb (virtual
framebuffer) to isolate GUI app rendering. This was removed for two reasons:
(1) Xvfb creates `/tmp/.X<n>-lock` by design, which violates the constraint
"nothing written to /tmp or system paths"; (2) stale lock files from crashed
Xvfb instances caused repeated "Server is already active" errors that terminated
the agent mid-run. Since the agent is always run by an engineer inside an active
LxQt session, a real DISPLAY is always available — no virtual display is needed.

**Full Exec= command line:** Each app is launched using the full command parsed
from the `Exec=` field in the .desktop file, not just the binary name. This is
important for apps like mpv (`--player-operation-mode=pseudo-gui`) or Flatpak
entries (`flatpak run <app-id>`) that require arguments to start correctly.
`%U`, `%f`, `%F` and other field codes are stripped before launching.

**Process matching:** Uses the launched PID first, then falls back to name/cmdline
matching filtered to processes created at or after the launch timestamp. This
prevents accidentally matching a pre-existing instance of the same app that was
already running before the test.

**Safe process cleanup:** Process tree is always terminated in a `finally` block
regardless of test outcome. The agent checks `proc.pid != our_pid` before every
termination call to prevent accidentally killing itself. A configurable cool-down
(default 2s) between apps prevents resource contention.

Result types: PASS, FAIL (binary missing, process timeout), DEGRADED (crashed).

### Part C — Desktop & Start Menu Presence

Technology: PyXDG (`xdg.DesktopEntry`). Read-only — no app launching, no
network, completes in under 1 second for all 15 apps.

For each app: checks .desktop file exists at the path defined in YAML, parses
the `Categories=` field, compares against the expected category from YAML. Then
checks the app's .desktop file (or symlink) is present inside
`~/Desktop/<folder>/`.

**Desktop folder matching:** Uses the exact filename from the YAML `desktop_file`
path as the primary match key. This correctly handles apps like GNOME Calculator
whose filename (`org.gnome.Calculator.desktop`) does not match their display name
("GNOME Calculator"). A fuzzy name match is used as a secondary fallback for
cases where the filename convention differs.

**Desktop folder setup:** The `~/Desktop/<folder>/` directories and symlinks must
be created once before the agent runs. The INSTALL guide includes a one-time
setup script. On a real JioPC Gold Image, these folders would be pre-created as
part of the OS image build.

Result types: PASS, MISSING (.desktop not found), MISPLACED (wrong category
or wrong desktop folder).

### LLM Analysis Layer (analyse.py)

Model-agnostic — API base URL, model, and key from environment variables.
Supports Anthropic native API (`/v1/messages`) and any OpenAI-compatible
endpoint (`/v1/chat/completions`) — detected from the base URL string.

Reads the log file, injects it into the prompt, prints structured markdown
analysis to the terminal. The prompt instructs the LLM to produce: executive
summary, anomaly list by component, pattern detection, and a PROMOTE / HOLD
recommendation with rationale.

## YAML Schema

```yaml
agent:
  log_dir: string           # where logs are written
                            # default: ~/.local/share/jiopc/agent/
  llm_prompt_file: string   # path to LLM prompt file
  cool_down_seconds: int    # pause between Part B app launches (default: 2)

web_apps:                   # Part A — one entry per URL to test
  - name: string
    url: string
    load_timeout_ms: int    # original threshold for SLOW flag
    bot_detection_expected: bool  # true = BLOCKED is expected, not flagged
    elements:
      - selector: string    # CSS selector to check for presence
        description: string # human-readable name for log output

native_apps:                # Part B — one entry per app to health-check
  - name: string
    desktop_file: string    # absolute path to .desktop file
    process_name: string    # process name to match after launch
    launch_timeout_s: int   # seconds to wait for process to appear

desktop_presence:           # Part C — one entry per app to check
  - name: string
    desktop_file: string    # absolute path to .desktop file
    desktop_folder: string  # expected ~/Desktop/<folder> name
    start_menu_category: string  # expected value in Categories= field
```

## Technology Choices

| Area | Choice | Rationale |
|------|--------|-----------|
| Language | Python 3.11+ | Available on Ubuntu 24.04, rich automation ecosystem |
| Web testing | Selenium 4 + Firefox snap | Playwright does not support Ubuntu 26.04; Firefox snap is pre-installed |
| Browser binary | `/snap/firefox/<rev>/usr/lib/firefox/firefox` | `/usr/bin/firefox` is a wrapper script rejected by Selenium |
| Process management | psutil | Accurate VmRSS, cross-platform process tree termination |
| .desktop parsing | PyXDG | Correct Freedesktop spec implementation, handles Categories= reliably |
| YAML | PyYAML | Standard library, supports comments |
| LLM client | httpx | Lightweight, supports both Anthropic and OpenAI-compatible APIs |
| Log format | JSON Lines | Machine-readable, streamable, directly ingestible by LLM prompt |
| Virtual display | Dropped — uses session DISPLAY | Avoids /tmp lock file constraint violation and Xvfb startup flakiness |

## Data Flow

```
YAML config
    │
    ├─ Part C ─► os.path.exists() + PyXDG.getCategories() + os.listdir(Desktop/)
    │                 │
    │                 ▼ PASS / MISSING / MISPLACED
    │
    ├─ Part B ─► shutil.which() + subprocess.Popen() + psutil.Process()
    │                 │
    │                 ▼ PASS / FAIL / DEGRADED
    │
    └─ Part A ─► selenium.webdriver.Firefox() + driver.get() + find_elements()
                      │
                      ▼ PASS / FAIL / BLOCKED
                      │
                 Logger.log() ──► JSON Lines log file
                      │
                 Logger.write_summary() ──► summary block
                      │
                 analyse.py ──► LLM API ──► PROMOTE / HOLD
```

## Performance

| Metric | Measured | Limit |
|--------|----------|-------|
| Full run p50 | 102s | 300s |
| Full run p95 | 109s | 300s |
| Peak RAM (agent only) | ~53 MB | 150 MB |
| Sustained CPU | 1–3% | 20% |
| Part C alone | < 1s | 30s |

Part B overhead per app: ~10ms polling overhead per 500ms interval.
Cool-down of 2s between apps prevents false DEGRADED results from contention.

## Known Limitations

- **Playwright not usable:** Playwright does not support Ubuntu 26.04. Selenium
  with Firefox snap is the correct replacement — all Part A functionality is
  fully implemented.
- **Firefox snap binary path:** Detected dynamically but depends on snap
  revisions present on the machine. The agent picks the highest-numbered
  revision automatically.
- **Bot-detection sites:** JioSaavn and YouTube always return BLOCKED in headless
  mode — marked `bot_detection_expected: true` in YAML. This is real-world
  correct behaviour, not a system defect.
- **JS-heavy SPAs:** JioCinema renders an empty body in headless mode — the blank
  page check uses title as a secondary signal to avoid false FAILs.
- **No parallel execution:** Parts run sequentially to stay within the CPU budget.
- **Desktop folder setup:** `~/Desktop/<folder>/` symlinks must be created once
  before running Part C. On a real Gold Image this would be pre-configured.
