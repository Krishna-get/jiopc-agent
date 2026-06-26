# JioPC Automated Testing Agent — Challenge 02

A scripted validation framework that tests a freshly patched JioPC OS Image for
regressions across web apps, native app health, and desktop application presence.
Results are written to a structured JSON Lines log, then analysed by an LLM layer
that produces a plain-language PROMOTE / HOLD recommendation.

## What It Does

| Part | What is tested |
|------|----------------|
| A | Web apps — reachability, UI element presence, load time, bot detection |
| B | Native apps — .desktop existence, binary launchability, memory/CPU at T+5s |
| C | Desktop presence — .desktop in correct folder and start menu category |

## Quick Start

```bash
# Run all three parts
python3 jiopc_agent.py --config jiopc-agent.yaml

# Run a single part
python3 jiopc_agent.py --config jiopc-agent.yaml --part C   # fastest, under 1s
python3 jiopc_agent.py --config jiopc-agent.yaml --part B
python3 jiopc_agent.py --config jiopc-agent.yaml --part A

# Run everything then analyse with LLM
python3 jiopc_agent.py --config jiopc-agent.yaml --analyse
```

## LLM Analysis

```bash
export LLM_BASE_URL=https://api.anthropic.com/v1
export LLM_MODEL=claude-haiku-4-5-20251001
export LLM_API_KEY=your_api_key_here

python3 analyse.py --log ~/.local/share/jiopc/agent/test_run_<timestamp>.log
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
| Full run time p50 | 102s | < 300s |
| Full run time p95 | 109s | < 300s |
| Peak RAM (agent only) | ~53 MB | < 150 MB |
| Sustained CPU | ~1–3% | < 20% |
| Part C alone | < 1s | < 30s |

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
├── jiopc_agent.py              # Entry point
├── analyse.py                  # LLM analysis script
├── jiopc-agent.yaml            # All test case definitions (YAML)
├── prompts/
│   └── analyse_log.txt         # LLM prompt file
├── src/
│   ├── runner.py               # Orchestration — runs C → B → A
│   └── logger.py               # JSON Lines logging + terminal output
├── parts/
│   ├── part_a.py               # Web app testing (Selenium + Firefox)
│   ├── part_b.py               # Native app health (subprocess + psutil)
│   └── part_c.py               # Desktop presence (PyXDG + file checks)
├── benchmarks/
│   └── benchmark_report.md     # CPU, RAM, timing results
├── screenshots/                # VM screenshots for submission
├── packaging/
│   └── jiopc-agent.deb         # Installable .deb package
├── test_run_*.log              # Sample log from a real VM run
├── sample_analysis.txt         # Sample LLM analysis output
├── README.md
├── INSTALL.md
└── design.md
```

## Known Limitations

- JioSaavn and YouTube always return BLOCKED in headless mode due to bot
  detection — this is correct behaviour, marked `bot_detection_expected: true`.
- Khan Academy occasionally exceeds the 10s load threshold on slow networks —
  it still passes since the threshold triggers a SLOW flag, not a FAIL.
- Firefox snap binary path is auto-detected but depends on snap revisions
  present on the machine.
- No parallel execution — parts run sequentially to stay within CPU budget.
- Desktop folder symlinks must be created once before Part C runs — see INSTALL.md.
