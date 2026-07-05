import json
import os
import threading                          # ADD
from datetime import datetime, timezone


class Logger:
    def __init__(self, log_dir: str):
        self.log_dir = os.path.expanduser(log_dir)
        os.makedirs(self.log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        self.log_path = os.path.join(self.log_dir, f"test_run_{timestamp}.log")
        self._lock = threading.Lock()     # ADD
        self.counts = {
            "total": 0,
            "pass": 0,
            "fail": 0,
            "blocked": 0,
            "degraded": 0,
            "missing": 0,
            "misplaced": 0,
        }
        self.by_component = {
            "A": {"total": 0, "pass": 0, "fail": 0, "blocked": 0},
            "B": {"total": 0, "pass": 0, "fail": 0, "degraded": 0},
            "C": {"total": 0, "pass": 0, "missing": 0, "misplaced": 0},
        }
        self.all_results = []
        print(f"[Logger] Log file: {self.log_path}")

    def log(self, component: str, name: str, result: str, duration_ms: int, detail: str):
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "component": component,
            "name": name,
            "result": result,
            "duration_ms": duration_ms,
            "detail": detail,
        }
        with self._lock:                  # ADD
            with open(self.log_path, "a") as f:
                f.write(json.dumps(record) + "\n")
            self.all_results.append(record)
            self.counts["total"] += 1
            result_key = result.lower()
            if result_key in self.counts:
                self.counts[result_key] += 1
            comp = self.by_component.get(component, {})
            comp["total"] = comp.get("total", 0) + 1
            if result_key in comp:
                comp[result_key] += 1

        symbol = {"PASS": "✓", "FAIL": "✗", "BLOCKED": "⊘",
                  "DEGRADED": "⚠", "MISSING": "✗", "MISPLACED": "⚠"}.get(result, "?")
        print(f"  [{component}] {symbol} {name}: {result} ({duration_ms}ms) — {detail}")

    def write_summary(self):
        summary = {
            "summary": True,
            "total": self.counts["total"],
            "pass": self.counts["pass"],
            "fail": self.counts["fail"],
            "blocked": self.counts["blocked"],
            "degraded": self.counts["degraded"],
            "missing": self.counts["missing"],
            "misplaced": self.counts["misplaced"],
            "by_component": self.by_component,
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(summary) + "\n")
        print(f"\n{'='*50}")
        print(f"SUMMARY: {self.counts['pass']}/{self.counts['total']} passed")
        print(f"  FAIL={self.counts['fail']} BLOCKED={self.counts['blocked']} "
              f"DEGRADED={self.counts['degraded']} MISSING={self.counts['missing']} "
              f"MISPLACED={self.counts['misplaced']}")
        print(f"  Log: {self.log_path}")
        print(f"{'='*50}")

    def all_passed(self) -> bool:
        return (
            self.counts["fail"] == 0
            and self.counts["missing"] == 0
            and self.counts["degraded"] == 0
            and self.counts["misplaced"] == 0
        )
