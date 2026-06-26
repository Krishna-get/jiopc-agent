import os
import time
from xdg.DesktopEntry import DesktopEntry


def run_part_c(apps: list, logger):
    for app in apps:
        t_start = time.monotonic()

        name = app['name']
        desktop_file = app['desktop_file']
        expected_category = app['start_menu_category']

        # Check 1: does the .desktop file exist at all?
        if not os.path.exists(desktop_file):
            duration_ms = int((time.monotonic() - t_start) * 1000)
            logger.log('C', name, 'MISSING', duration_ms,
                       f".desktop not found at {desktop_file}")
            continue

        # Check 2: correct start menu category?
        try:
            entry = DesktopEntry(desktop_file)
            categories = entry.getCategories()

            if expected_category not in categories:
                duration_ms = int((time.monotonic() - t_start) * 1000)
                logger.log('C', name, 'MISPLACED', duration_ms,
                           f"expected category '{expected_category}' but got {categories}")
                continue

        except Exception as e:
            duration_ms = int((time.monotonic() - t_start) * 1000)
            logger.log('C', name, 'FAIL', duration_ms,
                       f"error parsing .desktop file: {e}")
            continue

        # Check 3: desktop folder presence
        desktop_folder = app.get('desktop_folder', '')
        folder_result = check_desktop_folder(name, desktop_folder, desktop_file)

        duration_ms = int((time.monotonic() - t_start) * 1000)

        if folder_result is None:
            logger.log('C', name, 'PASS', duration_ms,
                       f"present, category='{expected_category}'")
        elif folder_result:
            logger.log('C', name, 'PASS', duration_ms,
                       f"present, category='{expected_category}', folder='{desktop_folder}'")
        else:
            logger.log('C', name, 'MISPLACED', duration_ms,
                       f".desktop exists and category ok, but not found in desktop folder '{desktop_folder}'")


def check_desktop_folder(app_name: str, folder_name: str, desktop_file: str) -> bool:
    """
    Check if the app's .desktop file exists inside ~/Desktop/<folder_name>/.
    Matches by:
      1. Exact filename match (most reliable — uses the known desktop_file path)
      2. Fuzzy app name match (fallback)
    Returns True if found, False if not found, None if folder doesn't exist.
    """
    if not folder_name:
        return None

    desktop_base = os.path.expanduser("~/Desktop")
    folder_path = os.path.join(desktop_base, folder_name)

    if not os.path.isdir(folder_path):
        return None

    expected_filename = os.path.basename(desktop_file)

    for fname in os.listdir(folder_path):
        if not fname.endswith('.desktop'):
            continue

        # Match 1: exact filename from YAML desktop_file path
        if fname == expected_filename:
            return True

        # Match 2: fuzzy app name match as fallback
        normalized_fname = fname.lower().replace('-', '').replace('_', '').replace('.', '')
        normalized_name = app_name.lower().replace(' ', '').replace('-', '').replace('_', '')
        if normalized_name in normalized_fname:
            return True

    return False
