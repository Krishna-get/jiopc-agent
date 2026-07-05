# JioPC Automated Testing Agent — Challenge 02

A scripted validation framework that tests a freshly patched JioPC OS Image for
regressions across web apps, native app health, and desktop application presence.
Results are written to a structured JSON Lines log, analysed by an LLM layer that
produces a plain-language PROMOTE / HOLD recommendation, and emailed to a
configured recipient.

## What It Does

| Part | What is tested |
|------|----------------|
| A | Web apps — reachability, UI element presence, load time, bot detection |
| B | Native apps — .desktop existence, binary launchability, memory/CPU at T+5s |
| C | Desktop presence — .desktop in correct folder and start menu category |

## Quick Start

```bash
# Run all three parts (C + A in parallel, then B)
python3 jiopc_agent.py --config jiopc-agent.yaml

# Run a single part
python3 jiopc_agent.py --config jiopc-agent.yaml --part C   # fastest, under 1s
python3 jiopc_agent.py --config jiopc-agent.yaml --part B
python3 jiopc_agent.py --config jiopc-agent.yaml --part A

# Run all parts then analyse with LLM + send email
python3 jiopc_agent.py --config jiopc-agent.yaml --analyse

# Disable parallel execution (sequential fallback)
python3 jiopc_agent.py --config jiopc-agent.yaml --no-parallel
```

## LLM Analysis

```bash
export LLM_BASE_URL=https://api.groq.com/openai/v1
export LLM_MODEL=llama3-8b-8192
export LLM_API_KEY=your_groq_key_here

# Analyse + send email
python3 analyse.py --log ~/.local/share/jiopc/agent/test_run_<timestamp>.log

# Analyse only, skip email
python3 analyse.py --log ~/.local/share/jiopc/agent/test_run_<timestamp>.log --no-email
```

Works with any OpenAI-compatible endpoint — swap the three environment variables
for OpenAI, Mistral, local Ollama, or any other provider.

## Expected Output

```
SUMMARY: 23/26 passed
  FAIL=0 BLOCKED=3 DEGRADED=0 MISSING=0 MISPLACED=0
```

The 3 BLOCKED results are expected — JioSaavn, YouTube, and Cloudflare use
bot detection that blocks headless browsers. BLOCKED is not a failure.

Cloudflare occasionally times out instead of returning a challenge page, in which
case it is logged as FAIL. This is non-deterministic and depends on Cloudflare's
infrastructure — not a bug in the agent. See Known Limitations for details.

## Trend Analysis

Every run appends a summary to `~/.local/share/jiopc/agent/trend_history.json`.
After each run the agent automatically compares results against the previous run
and prints a regression/improvement report:

```
TREND ANALYSIS (vs run at 2026-06-25 20:07:00)
  ⚠ REGRESSIONS (1) — these were passing before:
    [C] Featherpad: PASS → MISPLACED
  Pass rate trend (last 3 runs):
    2026-06-25 20:07:00  23/26 passed (88%)  BLOCKED=3
    2026-06-25 20:35:01  23/26 passed (88%)  BLOCKED=3  ◄ current
```

## Email Summary

After LLM analysis, a formatted HTML summary email is sent to the configured
recipient. Configure SMTP settings in `jiopc-agent.yaml` under the `email` key.
Tested with Mailtrap (sandbox) and compatible with any SMTP provider.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All required tests passed |
| 1 | One or more FAIL, MISSING, MISPLACED, or DEGRADED results |

BLOCKED does not affect the exit code.

## Log Location

```
~/.local/share/jiopc/agent/test_run_<timestamp>.log
```

JSON Lines format — one JSON record per test, summary block at end.
Trend history: `~/.local/share/jiopc/agent/trend_history.json`

## Result Types

| Result | Meaning |
|--------|---------|
| PASS | Test succeeded |
| FAIL | Test failed — critical issue |
| BLOCKED | Bot/CAPTCHA challenge detected — not a system failure |
| DEGRADED | Process launched but crashed before health check |
| MISSING | .desktop file not found anywhere on system |
| MISPLACED | .desktop exists but wrong folder or start menu category |

## Benchmark Results

| Metric | Result | Limit |
|--------|--------|-------|
| Full run p50 (parallel) | ~84s | < 300s |
| Full run p95 (parallel) | ~109s | < 300s |
| Full run sequential | 88–115s | < 300s |
| Peak RAM (agent only) | ~53 MB | < 150 MB |
| Sustained CPU | ~1–3% | < 20% |
| Part C alone | < 1s | < 30s |

p50 = median run time. p95 = worst-case run time across all measured runs.
See `benchmarks/benchmark_report.md` for full methodology.

## Dependencies

- Python 3.11+
- `selenium`, `psutil`, `pyyaml`, `pyxdg`, `httpx`
- Firefox + geckodriver (installed via snap — **not apt**)

> Do NOT use Playwright — it does not support Ubuntu 26.04.
> Do NOT install `firefox-geckodriver` via apt — that package does not exist.
> See INSTALL.md for the correct installation steps.

## Project Structure

```
jiopc-agent/
├── jiopc_agent.py              # Entry point (--part, --analyse, --no-parallel)
├── analyse.py                  # LLM analysis + email (--no-email to skip)
├── jiopc-agent.yaml            # All test case definitions + email config
├── prompts/
│   └── analyse_log.txt         # LLM prompt file
├── src/
│   ├── runner.py               # Orchestration — C+A parallel, then B
│   ├── logger.py               # Thread-safe JSON Lines logging
│   ├── trend.py                # Trend analysis + regression detection
│   └── emailer.py              # SMTP email summary
├── parts/
│   ├── part_a.py               # Web app testing (Selenium + Firefox)
│   ├── part_b.py               # Native app health (subprocess + psutil)
│   └── part_c.py               # Desktop presence (PyXDG + file checks)
├── .github/
│   └── workflows/
│       └── jiopc-agent.yml     # GitHub Actions CI/CD pipeline
├── benchmarks/
│   └── benchmark_report.md     # CPU, RAM, timing, parallel vs sequential
├── screenshots/                # VM screenshots for submission
├── packaging/
│   └── jiopc-agent.deb         # Installable .deb package
├── test_run_*.log              # Sample log from a real VM run
├── sample_analysis.txt         # Sample LLM analysis output
├── README.md
├── INSTALL.md
└── design.md
```

## Bonus Goals Implemented

| Goal | Status |
|------|--------|
| Trend analysis — regression detection across runs | ✓ |
| Summary email via SMTP after analysis | ✓ |
| CI/CD pipeline (GitHub Actions) | ✓ |
| Parallel execution (Part A + C concurrent, thread-safe) | ✓ |

## Known Limitations

- JioSaavn and YouTube always return BLOCKED in headless mode — expected,
  marked `bot_detection_expected: true` in YAML.
- Cloudflare and JioSaavn use bot-detection infrastructure that
  non-deterministically either serves a challenge page (BLOCKED) or stalls
  the connection until timeout (FAIL). Both are correct agent responses —
  the agent cannot predict which will occur. A future improvement would be
  treating timeouts on `bot_detection_expected` URLs as BLOCKED to avoid
  false regression alerts in trend analysis.
- Firefox snap binary path is auto-detected but depends on snap revisions
  present on the machine.
- Desktop folder symlinks must be created once before Part C — see INSTALL.md.
