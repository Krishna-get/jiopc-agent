import os
import time
import shutil
import subprocess
import psutil
from xdg.DesktopEntry import DesktopEntry


def get_exec_parts(desktop_file: str) -> list:
    """Full Exec= command from a .desktop file, with % placeholders stripped."""
    entry = DesktopEntry(desktop_file)
    exec_cmd = entry.getExec()
    parts = exec_cmd.split()
    return [p for p in parts if not p.startswith('%')]


def find_process(process_name: str, launched_pid: int, timeout_s: int, launch_time: float):
    """Poll for the process we just launched. Falls back to a name/cmdline
    match, but only among processes created at/after our launch time, so we
    never grab an unrelated already-running instance of the same app."""
    our_pid = os.getpid()
    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:
        try:
            p = psutil.Process(launched_pid)
            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                return p
        except psutil.NoSuchProcess:
            pass

        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                pid = proc.info['pid']
                if pid == our_pid:
                    continue
                if pid == launched_pid:
                    return proc
                if proc.info.get('create_time', 0) < launch_time - 1:
                    continue  # pre-existing process, not ours

                name = proc.info.get('name', '') or ''
                if process_name.lower() == name.lower():
                    return proc
                cmdline = proc.info.get('cmdline') or []
                if cmdline and process_name.lower() in os.path.basename(cmdline[0]).lower():
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(0.5)
    return None


def kill_process_tree(proc: psutil.Process):
    our_pid = os.getpid()
    try:
        if proc.pid == our_pid:
            print("  [B] WARNING: tried to kill ourselves, skipping")
            return
        children = [c for c in proc.children(recursive=True) if c.pid != our_pid]
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        proc.terminate()
        gone, alive = psutil.wait_procs([proc] + children, timeout=3)
        for p in alive:
            try:
                if p.pid != our_pid:
                    p.kill()
            except psutil.NoSuchProcess:
                pass
    except psutil.NoSuchProcess:
        pass


def run_part_b(apps: list, logger, cool_down: int = 2):
    # Engineers run this agent inside the live LxQt session, so a real
    # DISPLAY already exists — no virtual display needed. This also avoids
    # Xvfb's /tmp/.X<n>-lock file, which violates the "nothing written to
    # /tmp" constraint.
    display = os.environ.get('DISPLAY', ':0')
    env = {**os.environ, 'DISPLAY': display}
    print(f"  [B] Using existing session display {display}")

    for app in apps:
        t_start = time.monotonic()
        name = app.get('name', 'UNKNOWN')

        try:
            desktop_file = app['desktop_file']
            process_name = app['process_name']
        except KeyError as e:
            logger.log('B', name, 'FAIL', 0, f"YAML missing required key: {e}")
            continue

        launch_timeout = app.get('launch_timeout_s', 10)
        found_proc = None
        launched = None

        try:
            if not os.path.exists(desktop_file):
                duration_ms = int((time.monotonic() - t_start) * 1000)
                logger.log('B', name, 'FAIL', duration_ms,
                           f".desktop not found: {desktop_file}")
                continue

            exec_parts = get_exec_parts(desktop_file)
            if not exec_parts:
                duration_ms = int((time.monotonic() - t_start) * 1000)
                logger.log('B', name, 'FAIL', duration_ms,
                           "could not parse Exec= from .desktop")
                continue

            binary_path = shutil.which(exec_parts[0])
            if not binary_path:
                duration_ms = int((time.monotonic() - t_start) * 1000)
                logger.log('B', name, 'FAIL', duration_ms,
                           f"binary not found: {exec_parts[0]}")
                continue

            # Launch with the FULL command line, not just the binary name —
            # apps like mpv or Flatpak entries need their arguments.
            launch_cmd = [binary_path] + exec_parts[1:]
            launch_time = time.time()
            launched = subprocess.Popen(
                launch_cmd, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            print(f"  [B] Launched {name} PID={launched.pid} cmd={launch_cmd}")

            found_proc = find_process(process_name, launched.pid, launch_timeout, launch_time)

            if found_proc is None:
                duration_ms = int((time.monotonic() - t_start) * 1000)
                logger.log('B', name, 'FAIL', duration_ms,
                           f"process '{process_name}' did not appear within {launch_timeout}s")
                continue

            print(f"  [B] Found {name} PID={found_proc.pid}, waiting 5s...")
            time.sleep(5)

            if not found_proc.is_running() or found_proc.status() == psutil.STATUS_ZOMBIE:
                duration_ms = int((time.monotonic() - t_start) * 1000)
                logger.log('B', name, 'DEGRADED', duration_ms,
                           "process appeared but terminated before health check")
                continue

            try:
                mem_mb = round(found_proc.memory_info().rss / 1024 / 1024, 1)
                cpu_pct = round(found_proc.cpu_percent(interval=1.0), 1)
            except psutil.NoSuchProcess:
                duration_ms = int((time.monotonic() - t_start) * 1000)
                logger.log('B', name, 'DEGRADED', duration_ms,
                           "process disappeared during health check")
                continue

            duration_ms = int((time.monotonic() - t_start) * 1000)
            logger.log('B', name, 'PASS', duration_ms,
                       f"VmRSS={mem_mb}MB CPU={cpu_pct}% binary={binary_path}")

        except Exception as e:
            duration_ms = int((time.monotonic() - t_start) * 1000)
            logger.log('B', name, 'FAIL', duration_ms, f"unexpected error: {e}")

        finally:
            print(f"  [B] Cleaning up {name}...")
            if found_proc:
                kill_process_tree(found_proc)
            elif launched:
                try:
                    kill_process_tree(psutil.Process(launched.pid))
                except psutil.NoSuchProcess:
                    pass
            time.sleep(cool_down)
            print(f"  [B] {name} cleanup done")
