import argparse
import os
import sys
import json
import httpx
import yaml


def main():
    parser = argparse.ArgumentParser(description='JioPC LLM Log Analyser')
    parser.add_argument('--log', required=True, help='Path to test run log file')
    parser.add_argument('--prompt', default='./prompts/analyse_log.txt',
                        help='Path to prompt file')
    parser.add_argument('--config', default='./jiopc-agent.yaml',
                        help='Path to YAML config (for email settings)')
    parser.add_argument('--no-email', action='store_true',
                        help='Skip sending summary email')
    args = parser.parse_args()

    # Read log
    if not os.path.exists(args.log):
        print(f"Error: log file not found: {args.log}")
        sys.exit(1)

    with open(args.log) as f:
        log_text = f.read()

    # Read prompt
    if not os.path.exists(args.prompt):
        print(f"Error: prompt file not found: {args.prompt}")
        sys.exit(1)

    with open(args.prompt) as f:
        prompt = f.read()

    # Read config
    config = {}
    if os.path.exists(args.config):
        with open(args.config) as f:
            config = yaml.safe_load(f) or {}

    # Extract counts from log summary block
    counts = {}
    for line in log_text.splitlines():
        try:
            record = json.loads(line)
            if record.get('summary'):
                counts = record
                break
        except Exception:
            pass

    # Read LLM config from environment
    base_url = os.environ.get('LLM_BASE_URL', 'https://api.anthropic.com/v1')
    model = os.environ.get('LLM_MODEL', 'claude-haiku-4-5-20251001')
    api_key = os.environ.get('LLM_API_KEY', '')

    if not api_key:
        print("Error: LLM_API_KEY environment variable not set")
        sys.exit(1)

    print(f"Analysing log: {args.log}")
    print(f"Model: {model}")
    print(f"Base URL: {base_url}")
    print("-" * 50)

    analysis_text = ""

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        if "anthropic" in base_url:
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
            payload = {
                "model": model,
                "max_tokens": 1024,
                "system": prompt,
                "messages": [
                    {"role": "user", "content": f"<log>\n{log_text}\n</log>"}
                ]
            }
            response = httpx.post(
                f"{base_url}/messages",
                headers=headers,
                json=payload,
                timeout=60
            )
            data = response.json()
            if "content" in data:
                analysis_text = data["content"][0]["text"]
            else:
                print("Error from API:", data)
                sys.exit(1)
        else:
            payload = {
                "model": model,
                "max_tokens": 1024,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"<log>\n{log_text}\n</log>"}
                ]
            }
            response = httpx.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            data = response.json()
            if "choices" in data:
                analysis_text = data["choices"][0]["message"]["content"]
            else:
                print("Error from API:", data)
                sys.exit(1)

        print(analysis_text)

        # Send email summary
        if not args.no_email:
            from src.emailer import send_summary_email
            send_summary_email(analysis_text, counts, args.log, config)

    except Exception as e:
        print(f"Error calling LLM: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
