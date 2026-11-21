"""Единый Chrome с профилем Авито (profile_account). Работает всегда, окно СПРЯТАНО; сайт автовыкладки показывает его
и прячет обратно, ничего не перезапуская и не перезагружая. Весь трафик Chrome идёт через локальный прокси мимо VPN.
Используют: avito_watch.py (держит Chrome живым и читает счётчик сообщений) и app.py (показать / спрятать окно)."""
import ctypes, json, subprocess, sys, time, urllib.request
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import direct_proxy, settings

PROFILE = ROOT / "profile_account"
CDP = "http://127.0.0.1:9222"
START_URL = "https://www.avito.ru/profile/messenger"

user32 = ctypes.windll.user32
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def chrome_up():
    try:
        urllib.request.urlopen(CDP + "/json/version", timeout=1.5).read()
        return True
    except Exception:
        return False


def _main_pid():
    """PID главного процесса нашего Chrome (по профилю)."""
    cmd = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -match 'profile_account' "
           "-and $_.CommandLine -notmatch '--type=' } | Select-Object -First 1 -ExpandProperty ProcessId")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                       creationflags=0x08000000, timeout=30)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return None


def _windows():
    """Окна нашего Chrome (видимые и спрятанные)."""
    pid = _main_pid()
    found = []
    if not pid:
        return found

    def cb(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid:
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            # главное окно: класс Chrome_WidgetWin_1 с заголовком (свёрнутое окно тоже подходит, у него маленький размер)
            if cls.value == "Chrome_WidgetWin_1" and title.value:
                found.append(hwnd)
        return True
    user32.EnumWindows(EnumProc(cb), 0)
    return found


def is_visible():
    """Окно реально на экране: показано и не свёрнуто."""
    return any(user32.IsWindowVisible(h) and not user32.IsIconic(h) for h in _windows())


def set_visible(show):
    """Показать окно поверх всех (без перезагрузки страниц) или спрятать (пропадает и из панели задач)."""
    wins = _windows()
    for h in wins:
        if show:
            user32.ShowWindow(h, 5)  # SW_SHOW
            user32.ShowWindow(h, 9)  # SW_RESTORE (из свёрнутого состояния)
            user32.keybd_event(0x12, 0, 0, 0)  # Alt: разрешает перехват фокуса
            user32.SetForegroundWindow(h)
            user32.keybd_event(0x12, 0, 2, 0)
        else:
            user32.ShowWindow(h, 0)  # SW_HIDE
    return bool(wins)


def launch():
    """Запускает Chrome (если не запущен): профиль Авито, порт отладки, прокси мимо VPN; окно сразу прячется."""
    if chrome_up():
        return False
    direct_proxy.start()
    bypass = settings.load()["bypass_vpn"]
    proxy_flags = ([f"--proxy-server=http://127.0.0.1:{direct_proxy.PORT}",
                    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"] if bypass else [])
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    subprocess.Popen([
        settings.chrome_path(), "--remote-debugging-port=9222", f"--user-data-dir={PROFILE}", *proxy_flags,
        "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling", "--disable-features=CalculateNativeWinOcclusion",
        "--no-first-run", "--no-default-browser-check", START_URL],
        startupinfo=si, creationflags=0x00000008 | 0x00000200, close_fds=True)
    for _ in range(40):  # ждём порт и сразу прячем окно
        time.sleep(0.5)
        if chrome_up():
            break
    for _ in range(20):
        time.sleep(0.5)
        if set_visible(False):
            break
    return True


def kill():
    """Убивает ВСЕ процессы Chrome профиля Авито (только profile_account, обычный Chrome пользователя не трогает)."""
    cmd = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -match 'profile_account' } | "
           "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, creationflags=0x08000000, timeout=60)
    time.sleep(3)


def ensure():
    """Chrome запущен и спрятан (если его только что подняли). Возвращает True, если пришлось запускать."""
    return launch()
