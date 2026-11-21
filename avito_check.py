"""Раз в N минут: открывает Авито под вашим аккаунтом (profile_account), смотрит число непрочитанных сообщений
и при росте шлёт в Telegram «Авито +N». Токен бота берётся из secrets/telegram.json или из переменных окружения TG_TOKEN и TG_CHAT_ID (в репозиторий не попадает).
Запуск: python avito_check.py [--probe]  (--probe: показать, какие элементы страницы похожи на счётчик, для отладки)."""
import json, re, sys, time
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
STATE = ROOT / "data" / "avito_check_state.json"
SECRETS = ROOT / "secrets" / "telegram.json"  # {"token": "...", "chat_id": "..."}; в .gitignore
STATE.parent.mkdir(exist_ok=True)
PROBE = "--probe" in sys.argv


def load_secrets():
    """Токен и chat_id Telegram-бота: переменные TG_TOKEN / TG_CHAT_ID или файл secrets/telegram.json."""
    import os
    if os.environ.get("TG_TOKEN") and os.environ.get("TG_CHAT_ID"):
        return {"token": os.environ["TG_TOKEN"], "chat_id": os.environ["TG_CHAT_ID"]}
    return json.loads(SECRETS.read_text(encoding="utf-8-sig"))


def tg(text):
    """Отправка в Telegram с 3 попытками; любые сбои пишутся в data/telegram.log (раньше исключение глоталось молча). Возвращает True/False."""
    import time as _t
    sec = load_secrets()
    err = ""
    for i in range(3):
        try:
            r = requests.post(f"https://api.telegram.org/bot{sec['token']}/sendMessage",
                              json={"chat_id": sec["chat_id"], "text": text}, timeout=20)
            if r.status_code == 200:
                return True
            err = f"HTTP {r.status_code}: {r.text[:120]}".replace(sec["token"], "***")
        except Exception as e:
            err = (type(e).__name__ + ": " + str(e)[:150]).replace(sec["token"], "***")
        _t.sleep(3)
    # запасной путь: отдельный процесс Python (чистая сеть, без состояния наблюдателя) + диагностика причины в лог
    diag = ""
    try:
        import socket, subprocess, sys
        try:
            ip = socket.getaddrinfo("api.telegram.org", 443, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
            s0 = _t.time()
            socket.create_connection((ip, 443), timeout=6).close()
            diag = f" | сокет в {ip}: ок за {_t.time() - s0:.1f} с"
        except Exception as e2:
            diag = f" | сокет: {type(e2).__name__} {str(e2)[:60]}"
        code = ("import os,requests,sys;"
                "r=requests.post('https://api.telegram.org/bot'+os.environ['TG_TOKEN']+'/sendMessage',json={'chat_id':os.environ['TG_CHAT_ID'],'text':sys.argv[1]},timeout=20);"
                "sys.exit(0 if r.status_code==200 else 1)")
        exe = Path(sys.executable).with_name("python.exe")
        import os
        rc = subprocess.run([str(exe if exe.exists() else sys.executable), "-c", code, text],
                            env={**os.environ, "TG_TOKEN": sec["token"], "TG_CHAT_ID": str(sec["chat_id"])},
                            timeout=40, creationflags=0x08000000).returncode
        if rc == 0:
            with open(STATE.parent / "telegram.log", "a", encoding="utf-8") as f:
                f.write(_t.strftime("%Y-%m-%d %H:%M:%S ") + "основная отправка не прошла (" + err[:60] + ")" + diag + ", ушло через подпроцесс" + chr(10))
            return True
        diag += f" | подпроцесс: код {rc}"
    except Exception as e3:
        diag += f" | подпроцесс: {type(e3).__name__} {str(e3)[:60]}"
    err += diag
    try:
        with open(STATE.parent / "telegram.log", "a", encoding="utf-8") as f:
            f.write(_t.strftime("%Y-%m-%d %H:%M:%S ") + "не ушло «" + text[:40] + "»: " + err + chr(10))
    except Exception:
        pass
    print("telegram не ушёл:", err)
    return False


def load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"unread": 0, "fails": 0, "alerted": ""}


JS_COUNT = """() => {
  const out = [];
  for (const el of document.querySelectorAll('a[href*="messenger"], [data-marker*="messenger"], [data-marker*="message"], [data-marker*="counter"]')) {
    const t = (el.innerText || '').trim();
    const m = t.match(/(\\d+)\\s*$/) || t.match(/^(\\d+)/);
    out.push({marker: el.getAttribute('data-marker') || '', href: el.getAttribute('href') || '', text: t.slice(0, 40), num: m ? parseInt(m[1]) : null});
  }
  return out;
}"""


def read_unread(page):
    page.goto("https://www.avito.ru/profile/messenger", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    title = page.title()
    if "Доступ ограничен" in title:
        return None, "block"
    if page.locator('[data-marker="header/login-button"], a[href*="#login"]').count() and "messenger" not in page.url:
        return None, "login"
    items = page.evaluate(JS_COUNT)
    if PROBE:
        print("title:", title, "| url:", page.url)
        for it in items:
            print(it)
    # 1) счётчик в шапке рядом с «Сообщения»; 2) число в заголовке вкладки вида «(2) ...»
    chats = [it["num"] for it in items if it["marker"] == "header/unread-chats-counter" and it["num"] is not None]
    if chats:  # точный счётчик непрочитанных чатов в шапке
        return chats[0], "chats-counter"
    nums = [it["num"] for it in items if it["num"] is not None and ("messenger" in it["href"] or "messenger" in it["marker"]) and it["num"] < 1000]
    if nums:
        return max(nums), "header"
    m = re.match(r"\((\d+)\)", title)
    if m:
        return int(m.group(1)), "title"
    return 0, "none"


def main():
    st = load()
    with sync_playwright() as p:
        HEADLESS = "--headed" not in sys.argv  # по умолчанию без окна вообще (ничего в панели задач)
        ctx = p.chromium.launch_persistent_context(
            str(ROOT / "profile_account"), headless=HEADLESS, channel="chrome", viewport={"width": 1280, "height": 900}, locale="ru-RU",
            args=["--disable-quic", "--disable-blink-features=AutomationControlled", "--window-position=-32000,-32000"])
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            n, how = read_unread(page)
        finally:
            ctx.close()
    print("непрочитанных:", n, "| источник:", how)
    if n is None:
        st["fails"] = st.get("fails", 0) + 1
        if st["fails"] >= 3 and st.get("alerted") != how:
            tg("Авито: проверка не работает (" + ("слетел вход, запусти avito_login.py" if how == "login" else "блок по IP") + ")")
            st["alerted"] = how
    else:
        st["fails"], st["alerted"] = 0, ""
        if n > st.get("unread", 0):
            tg(f"Авито +{n - st.get('unread', 0)}" if n - st.get("unread", 0) > 1 else "Авито")
        st["unread"] = n
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
