import os
import time
import shutil
import glob
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException


BOT_DETECTION_SIGNALS = [
    "just a moment", "checking your browser", "please wait",
    "enable javascript and cookies", "cf-challenge", "captcha",
    "are you human", "ddos-guard", "ray id",
]

ERROR_PAGE_SIGNALS = [
    "404 not found", "page not found", "500 internal server error",
    "this site can't be reached", "server not found", "this page isn't working",
]


def is_bot_challenged(driver) -> bool:
    try:
        title = (driver.title or "").lower()
        source = driver.page_source.lower()
        for signal in BOT_DETECTION_SIGNALS:
            if signal in title or signal in source:
                return True
        for selector in ["#cf-challenge-body", ".cf-error-details",
                         "input[name='captcha']", "#captcha-form"]:
            try:
                if driver.find_element(By.CSS_SELECTOR, selector):
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def is_error_or_blank_page(driver) -> bool:
    """Catches what Selenium itself won't raise on: a page that loads with
    4xx/5xx content, or an essentially empty body.
    Note: JS-heavy SPAs (e.g. JioCinema) may have empty body text but a
    valid title — we only flag blank if BOTH body and title are empty."""
    try:
        title = (driver.title or "").strip()
        source = driver.page_source.lower()
        body_text = driver.find_element(By.TAG_NAME, "body").text.strip()

        # Only flag as blank if body is empty AND title gives no signal
        if len(body_text) < 20 and len(title) < 5:
            return True

        for signal in ERROR_PAGE_SIGNALS:
            if signal in title.lower() or signal in source:
                return True
    except Exception:
        pass
    return False


def find_firefox_binary():
    # Prefer real snap binary — /usr/bin/firefox is a wrapper script
    # that Selenium rejects as "not a Firefox executable"
    for c in sorted(glob.glob("/snap/firefox/*/usr/lib/firefox/firefox"), reverse=True):
        if "current" not in c and os.access(c, os.X_OK):
            return c
    # Try /current symlink as fallback
    current = "/snap/firefox/current/usr/lib/firefox/firefox"
    if os.path.isfile(current) and os.access(current, os.X_OK):
        return current
    for c in ["/usr/lib/firefox/firefox", "/opt/firefox/firefox"]:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def find_geckodriver():
    which_path = shutil.which("geckodriver")
    if which_path:
        return which_path
    for c in ["/snap/bin/geckodriver", "/usr/bin/geckodriver", "/usr/local/bin/geckodriver"]:
        if os.path.isfile(c):
            return c
    return None


def make_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--width=1280")
    options.add_argument("--height=720")

    firefox_bin = find_firefox_binary()
    if not firefox_bin:
        raise RuntimeError("Firefox binary not found on this system")
    options.binary_location = firefox_bin

    geckodriver_path = find_geckodriver()
    if not geckodriver_path:
        raise RuntimeError("geckodriver not found on this system")
    service = Service(executable_path=geckodriver_path)

    driver = webdriver.Firefox(options=options, service=service)
    driver.set_page_load_timeout(30)
    return driver


def run_part_a(apps: list, logger):
    driver = None
    try:
        print("  [A] Starting Firefox...")
        driver = make_driver()
        print("  [A] Firefox ready")

        for app in apps:
            t_start = time.monotonic()
            name = app.get('name', 'UNKNOWN')

            try:
                url = app['url']
            except KeyError as e:
                logger.log('A', name, 'FAIL', 0, f"YAML missing required key: {e}")
                continue

            load_timeout = app.get('load_timeout_ms', 8000)
            bot_expected = app.get('bot_detection_expected', False)
            elements = app.get('elements', [])

            effective_timeout = max(load_timeout, 20000) / 1000

            try:
                driver.set_page_load_timeout(effective_timeout)
                driver.get(url)
            except TimeoutException:
                duration_ms = int((time.monotonic() - t_start) * 1000)
                logger.log('A', name, 'FAIL', duration_ms,
                           f"page load timeout after {effective_timeout}s")
                try:
                    driver.get("about:blank")
                except Exception:
                    pass
                continue
            except WebDriverException as e:
                duration_ms = int((time.monotonic() - t_start) * 1000)
                logger.log('A', name, 'FAIL', duration_ms,
                           f"browser error: {str(e)[:80]}")
                try:
                    driver.get("about:blank")
                except Exception:
                    pass
                continue

            load_ms = int((time.monotonic() - t_start) * 1000)

            if is_bot_challenged(driver):
                duration_ms = int((time.monotonic() - t_start) * 1000)
                status = "expected" if bot_expected else "unexpected"
                logger.log('A', name, 'BLOCKED', duration_ms,
                           f"bot detection challenge ({status}) — loaded in {load_ms}ms")
                continue

            if is_error_or_blank_page(driver):
                duration_ms = int((time.monotonic() - t_start) * 1000)
                logger.log('A', name, 'FAIL', duration_ms,
                           f"blank or error page — loaded in {load_ms}ms")
                continue

            slow_flag = f" SLOW (threshold={load_timeout}ms)" if load_ms > load_timeout else ""

            failed_elements = []
            for el in elements:
                selector = el.get('selector')
                description = el.get('description', selector)
                try:
                    found = driver.find_elements(By.CSS_SELECTOR, selector)
                    if not found:
                        failed_elements.append(description)
                except Exception:
                    failed_elements.append(description)

            duration_ms = int((time.monotonic() - t_start) * 1000)

            if failed_elements:
                logger.log('A', name, 'FAIL', duration_ms,
                           f"missing elements: {failed_elements} — loaded in {load_ms}ms{slow_flag}")
            else:
                logger.log('A', name, 'PASS', duration_ms,
                           f"all elements found — loaded in {load_ms}ms{slow_flag}")

            try:
                driver.delete_all_cookies()
            except Exception:
                pass

    except Exception as e:
        print(f"  [A] Fatal error: {e}")

    finally:
        if driver:
            try:
                driver.quit()
                print("  [A] Firefox closed")
            except Exception:
                pass
