# Installation Guide

This guide is written based on real installation experience on Ubuntu 24.04 LTS
with LxQt. Follow it exactly in order — skipping steps causes hard-to-debug errors.

---

## Prerequisites

- Ubuntu 24.04 LTS with LxQt desktop session running
- Internet connection
- You must be logged into the LxQt desktop session (not just a terminal)
  — Part B launches GUI apps and needs an active display

---

## Step 1 — Install system packages

```bash
sudo apt update
sudo apt install -y python3-pip xvfb
```

---

## Step 2 — Install Firefox via snap (if not already installed)

Firefox must be installed as a **snap** — the apt version does not include
geckodriver. Check first:

```bash
firefox --version
geckodriver --version
```

If either command fails:

```bash
sudo snap install firefox
```

After installing, verify both work:

```bash
firefox --version      # should print: Mozilla Firefox 152.x.x
geckodriver --version  # should print: geckodriver 0.36.x
```

> **Important:** Do NOT install `firefox-geckodriver` via apt — that package
> does not exist on Ubuntu 24.04/26.04. geckodriver comes bundled with the
> Firefox snap automatically.

---

## Step 3 — Install Python packages

```bash
pip3 install selenium psutil pyyaml pyxdg httpx \
    --break-system-packages \
    --ignore-installed
```

> **Why `--ignore-installed`?** Ubuntu pre-installs some pip packages (like
> `certifi`) via apt. Without this flag, pip refuses to overwrite them and
> the install fails with an "uninstall-no-record-file" error.

Verify:

```bash
python3 -c "from selenium import webdriver; print('selenium OK')"
python3 -c "import psutil; print('psutil OK')"
python3 -c "import yaml; print('pyyaml OK')"
python3 -c "from xdg.DesktopEntry import DesktopEntry; print('pyxdg OK')"
python3 -c "import httpx; print('httpx OK')"
```

All five should print OK. If any fail, re-run the pip install above.

> **Note:** Do NOT use Playwright — it does not support Ubuntu 26.04 and
> installation will fail with "Playwright does not support chromium/firefox
> on ubuntu26.04-x64". This project uses Selenium instead.

---

## Step 4 — Install or extract the project

**Option A — from Git:**

```bash
cd ~
git clone <your-repo-url> jiopc-agent
cd jiopc-agent
```

**Option B — from .deb:**

```bash
sudo dpkg -i jiopc-agent.deb
cd /usr/local/lib/jiopc-agent
```

---

## Step 5 — Find the real Firefox binary path

This is the most common source of errors. Selenium needs the **real** Firefox
binary, not the `/usr/bin/firefox` wrapper script (which it rejects with
"binary is not a Firefox executable").

Run this to find the correct path:

```bash
find /snap/firefox -name "firefox" -type f 2>/dev/null | sort -r | head -3
```

You should see output like:

```
/snap/firefox/current/usr/lib/firefox/firefox
/snap/firefox/8521/usr/lib/firefox/firefox
/snap/firefox/8107/usr/lib/firefox/firefox
```

The agent auto-detects this path dynamically — you do not need to hardcode it.
But if Part A fails with "binary is not a Firefox executable", run:

```bash
python3 -c "
import sys
sys.path.insert(0, '.')
from parts.part_a import find_firefox_binary
print('Detected:', find_firefox_binary())
"
```

It should print a path like `/snap/firefox/8521/usr/lib/firefox/firefox`.
If it prints `None`, the snap is not installed — go back to Step 2.

---

## Step 6 — Create desktop folders for Part C

Part C checks that apps are present in the correct desktop folders. These
folders must be created once before running the agent:

```bash
cd ~/jiopc-agent   # or /usr/local/lib/jiopc-agent if installed via .deb

python3 -c "
import yaml, os
with open('jiopc-agent.yaml') as f:
    config = yaml.safe_load(f)
desktop_base = os.path.expanduser('~/Desktop')
for app in config['desktop_presence']:
    folder = app.get('desktop_folder')
    desktop_file = app['desktop_file']
    if not folder or not os.path.exists(desktop_file):
        continue
    folder_path = os.path.join(desktop_base, folder)
    os.makedirs(folder_path, exist_ok=True)
    link_path = os.path.join(folder_path, os.path.basename(desktop_file))
    if not os.path.exists(link_path):
        os.symlink(desktop_file, link_path)
        print(f'Linked {os.path.basename(desktop_file)} -> {folder}/')
print('Done.')
"
```

You should see 15 lines of "Linked ... -> folder/" followed by "Done."

> This only needs to be run once. The symlinks persist across sessions
> because they live in your home directory (~/.Desktop/).

---

## Step 7 — Verify the full installation

```bash
cd ~/jiopc-agent
python3 jiopc_agent.py --help
```

Expected output:

```
usage: jiopc_agent.py [-h] --config CONFIG [--part {A,B,C}] [--analyse]
JioPC Automated Testing Agent
options:
  -h, --help            show this help message and exit
  --config CONFIG       Path to YAML config file
  --part {A,B,C}        Run only a specific part
  --analyse             Run LLM analysis after testing
```

Run a quick smoke test (Part C — no internet, no apps launched, under 1 second):

```bash
python3 jiopc_agent.py --config jiopc-agent.yaml --part C
```

Expected: `SUMMARY: 15/15 passed`

---

## Step 8 — Run the full agent

```bash
python3 jiopc_agent.py --config jiopc-agent.yaml
```

This takes approximately 84–115 seconds (parallel mode default). Expected final output:

```
SUMMARY: 23/26 passed
  FAIL=0 BLOCKED=3 DEGRADED=0 MISSING=0 MISPLACED=0
```

The 3 BLOCKED results are expected — JioSaavn, YouTube, and Cloudflare use
bot detection that blocks headless browsers. This is not a failure.
Cloudflare may occasionally time out instead of serving a challenge page,
in which case it logs as FAIL — this is non-deterministic and not a bug.

---

## Step 9 — LLM analysis (optional)

```bash
export LLM_BASE_URL=https://api.groq.com/openai/v1
export LLM_MODEL=llama3-8b-8192
export LLM_API_KEY=your_groq_key_here

python3 analyse.py --log ~/.local/share/jiopc/agent/test_run_<timestamp>.log
```

Works with any OpenAI-compatible provider — swap the environment variables
for OpenAI, Mistral, Ollama, etc.

---

## Troubleshooting

### "binary is not a Firefox executable"

Selenium is picking up `/usr/bin/firefox` which is a shell wrapper, not the
real binary. The agent auto-detects the snap binary — if it's failing, check:

```bash
find /snap/firefox -name "firefox" -type f | sort -r | head -3
```

If this returns nothing, Firefox snap is not installed — go back to Step 2.

---

### "geckodriver not found" or "no such file"

```bash
which geckodriver          # should return /snap/bin/geckodriver
ls /snap/bin/geckodriver   # should exist
```

If missing, reinstall the Firefox snap:

```bash
sudo snap install firefox
```

Also make sure `/snap/bin` is in your PATH:

```bash
echo $PATH | grep snap
# If not there:
export PATH=$PATH:/snap/bin
```

---

### Part B apps not cleaned up (orphaned processes)

If the agent crashed mid-run, kill leftover app processes manually:

```bash
pkill -f featherpad
pkill -f feathernotes
pkill -f audacious
pkill -f qterminal
pkill -f gucharmap
```

---

### Xvfb stale lock file

If you see "Server is already active for display 99":

```bash
rm -f /tmp/.X99-lock
```

> Note: The agent no longer uses Xvfb by default — it uses your existing
> LxQt session display. This error only appears if you manually started Xvfb
> earlier and it crashed.

---

### pip install fails with "uninstall-no-record-file" for certifi

```bash
pip3 install selenium psutil pyyaml pyxdg httpx \
    --break-system-packages \
    --ignore-installed
```

The `--ignore-installed` flag skips packages that were installed by apt.

---

### Part C shows MISPLACED for all apps

The desktop folders were not created. Run Step 6 again.

---

### Log file not found

Logs are written to `~/.local/share/jiopc/agent/`. List them with:

```bash
ls -lt ~/.local/share/jiopc/agent/
```
