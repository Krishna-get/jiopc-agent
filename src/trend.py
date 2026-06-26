import json
import os
from datetime import datetime, timezone


HISTORY_FILE = os.path.expanduser("~/.local/share/jiopc/agent/trend_history.json")


def load_history() -> list:
    """Load all past run summaries."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def save_run(log_path: str, counts: dict, results: list):
    """Append current run summary to history file."""
    history = load_history()

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "log_path": log_path,
        "counts": counts,
        "results": {
            r["name"]: {
                "component": r["component"],
                "result": r["result"],
                "detail": r["detail"],
            }
            for r in results
        }
    }

    history.append(entry)

    # Keep last 50 runs only
    if len(history) > 50:
        history = history[-50:]

    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

    return entry


def detect_regressions(current: dict, previous: dict) -> list:
    """
    Compare current run results against previous run.
    Returns list of regression dicts.
    """
    regressions = []
    improvements = []

    BAD_RESULTS = {"FAIL", "MISSING", "MISPLACED", "DEGRADED"}
    GOOD_RESULTS = {"PASS", "BLOCKED"}

    prev_results = previous.get("results", {})
    curr_results = current.get("results", {})

    for name, curr in curr_results.items():
        prev = prev_results.get(name)
        if not prev:
            continue  # new test, not a regression

        prev_result = prev["result"]
        curr_result = curr["result"]

        if prev_result in GOOD_RESULTS and curr_result in BAD_RESULTS:
            regressions.append({
                "name": name,
                "component": curr["component"],
                "was": prev_result,
                "now": curr_result,
                "detail": curr["detail"],
            })
        elif prev_result in BAD_RESULTS and curr_result in GOOD_RESULTS:
            improvements.append({
                "name": name,
                "component": curr["component"],
                "was": prev_result,
                "now": curr_result,
            })

    return regressions, improvements


def print_trend_report(current: dict, history: list):
    """Print regression/improvement report comparing against last run."""
    if len(history) < 2:
        print("\n[Trend] Not enough history for trend analysis (need at least 2 runs)")
        return

    previous = history[-2]  # second to last (last is current)
    prev_ts = previous.get("ts", "unknown")[:19].replace("T", " ")

    regressions, improvements = detect_regressions(current, previous)

    print(f"\n{'='*50}")
    print(f"TREND ANALYSIS (vs run at {prev_ts})")
    print(f"{'='*50}")

    if not regressions and not improvements:
        print("  No changes detected — results identical to previous run ✓")
    else:
        if regressions:
            print(f"\n  ⚠ REGRESSIONS ({len(regressions)}) — these were passing before:")
            for r in regressions:
                print(f"    [{r['component']}] {r['name']}: {r['was']} → {r['now']}")
                print(f"         {r['detail']}")

        if improvements:
            print(f"\n  ✓ IMPROVEMENTS ({len(improvements)}) — these are now passing:")
            for r in improvements:
                print(f"    [{r['component']}] {r['name']}: {r['was']} → {r['now']}")

    # Show pass rate trend across last 5 runs
    recent = history[-5:]
    if len(recent) >= 2:
        print(f"\n  Pass rate trend (last {len(recent)} runs):")
        for entry in recent:
            ts = entry.get("ts", "")[:19].replace("T", " ")
            counts = entry.get("counts", {})
            total = counts.get("total", 0)
            passed = counts.get("pass", 0)
            blocked = counts.get("blocked", 0)
            pct = round(passed / total * 100) if total else 0
            marker = "◄ current" if entry is history[-1] else ""
            print(f"    {ts}  {passed}/{total} passed ({pct}%)  BLOCKED={blocked}  {marker}")

    print(f"{'='*50}")
    print(f"  Full history: {HISTORY_FILE}")
    print(f"{'='*50}\n")
