import argparse
import sys
import os
import subprocess


def main():
    parser = argparse.ArgumentParser(description='JioPC Automated Testing Agent')
    parser.add_argument('--config', required=True, help='Path to YAML config file')
    parser.add_argument('--part', choices=['A', 'B', 'C'], help='Run only a specific part')
    parser.add_argument('--analyse', action='store_true', help='Run LLM analysis after testing')
    parser.add_argument('--no-parallel', action='store_true',
                        help='Disable parallel execution of Part A and Part C')
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Error: config file not found: {args.config}")
        sys.exit(1)

    from src.runner import Runner
    runner = Runner(args.config, parallel=not args.no_parallel)

    parts = [args.part] if args.part else ['A', 'B', 'C']
    success = runner.run(parts=parts)

    if args.analyse:
        print("\n--- LLM Analysis ---")
        log_path = runner.logger.log_path
        subprocess.run(["python3", "analyse.py", "--log", log_path])

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
