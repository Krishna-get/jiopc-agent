import yaml
import os
import time
import threading
from src.logger import Logger
from src.trend import save_run, load_history, print_trend_report


class Runner:
    def __init__(self, config_path: str, parallel: bool = True):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.logger = Logger(self.config['agent']['log_dir'])
        self.cool_down = self.config['agent'].get('cool_down_seconds', 2)
        self.parallel = parallel

    def _run_part_a(self):
        try:
            from parts.part_a import run_part_a
            run_part_a(self.config['web_apps'], self.logger)
        except Exception as e:
            print(f"  [A] FATAL: Part A crashed: {e}")

    def _run_part_c(self):
        try:
            from parts.part_c import run_part_c
            run_part_c(self.config['desktop_presence'], self.logger)
        except Exception as e:
            print(f"  [C] FATAL: Part C crashed: {e}")

    def _run_part_b(self):
        try:
            from parts.part_b import run_part_b
            run_part_b(self.config['native_apps'], self.logger, self.cool_down)
        except Exception as e:
            print(f"  [B] FATAL: Part B crashed: {e}")

    def run(self, parts: list = None):
        if parts is None:
            parts = ['A', 'B', 'C']

        print(f"\n{'='*50}")
        print(f"JioPC Testing Agent — starting run")
        print(f"Parts: {parts} | Parallel: {self.parallel}")
        print(f"{'='*50}\n")

        t_start = time.monotonic()

        run_a = 'A' in parts
        run_b = 'B' in parts
        run_c = 'C' in parts

        # Phase 1: Part C and Part A
        if run_c and run_a and self.parallel:
            print("--- Part C + Part A running in parallel ---")
            t_c = threading.Thread(target=self._run_part_c, name="Part-C")
            t_a = threading.Thread(target=self._run_part_a, name="Part-A")
            t_c.start()
            t_a.start()
            t_c.join()
            t_a.join()
        else:
            if run_c:
                print("\n--- Part C: Desktop & Start Menu Presence ---")
                self._run_part_c()
            if run_a:
                print("\n--- Part A: Web App Testing ---")
                self._run_part_a()

        # Phase 2: Part B always sequential
        if run_b:
            print("\n--- Part B: Native App Health ---")
            self._run_part_b()

        total_ms = int((time.monotonic() - t_start) * 1000)
        print(f"\nTotal run time: {total_ms / 1000:.1f}s")

        self.logger.write_summary()

        # Trend analysis
        history = load_history()
        current_entry = save_run(
            self.logger.log_path,
            self.logger.counts,
            self.logger.all_results
        )
        history.append(current_entry)
        print_trend_report(current_entry, history)

        return self.logger.all_passed()
