"""Постоянный наблюдатель. Держит живым ОДИН Chrome с профилем Авито (окно спрятано, см. автовыкладка\\browser_host.py),
подключается к нему по CDP и раз в минуту читает с экрана счётчик непрочитанных чатов (без перезагрузки страницы).
При росте шлёт в Telegram «Авито». Сайт автовыкладки показывает это же окно и прячет обратно, ничего не перезапуская.
Запуск: pythonw avito_watch.py (автозапуск — задача «AvitoWatch»)."""
import json, random, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
from avito_check import ROOT, STATE, tg, load, JS_COUNT

sys.path.insert(0, str(ROOT / "автовыкладка"))
import browser_host

URL = "https://www.avito.ru/profile/messenger"
READ_EVERY = 60          # секунд между чтениями счётчика (чтение с уже открытой страницы, запросов к Авито не делает)
LOG = ROOT / "data" / "avito_watch.log"
ALIVE = ROOT / "data" / "avito_watch.alive"  # метка «я жив» раз в минуту, её проверяет avito_guard.py


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def read(page):
    title = page.title()
    if "Доступ ограничен" in title:
        return None, "block"
    if page.locator('[data-marker="header/login-button"]').count():
        return None, "login"
    for it in page.evaluate(JS_COUNT):
        if it["marker"] == "header/unread-chats-counter" and it["num"] is not None:
            return it["num"], "ok"
    return 0, "ok"  # счётчика нет на странице = непрочитанных нет


def open_page(page):
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)


def get_page(ctx):
    """Вкладка сообщений: берём существующую (без перезагрузки), если её нет — используем первую вкладку или открываем новую."""
    for pg in ctx.pages:
        if "avito.ru/profile/messenger" in pg.url:
            return pg
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    open_page(pg)
    return pg


def main():
    st = load()
    fails = 0
    conn_fails = 0   # подряд неудачных подключений к Chrome по CDP (после перезагрузки Chrome иногда «зависает»: порт открыт, Playwright таймаутится)
    log("запуск наблюдателя, Chrome " + ("поднят заново" if browser_host.ensure() else "уже работал"))
    with sync_playwright() as p:
        while True:
            try:
                br = p.chromium.connect_over_cdp(browser_host.CDP, timeout=20000)
            except Exception as e:
                log("нет связи с Chrome: " + str(e)[:80].replace("\n", " "))
                conn_fails += 1
                if conn_fails >= 5 and browser_host.chrome_up():  # Chrome жив, но не отвечает: перезапускаем только его (вход хранится в профиле)
                    log("Chrome завис (5 неудач подряд), перезапускаю его")
                    try:
                        tg("Авито: Chrome зависал, перезапускаю автоматически.")
                    except Exception:
                        pass
                    browser_host.kill()
                    conn_fails = 0
                time.sleep(15)
                browser_host.ensure()
                continue
            conn_fails = 0
            try:
                ctx = br.contexts[0]
                page = get_page(ctx)
            except Exception as e:  # Chrome ещё грузится или вкладка упала: не вылетаем, пробуем заново
                log("не удалось открыть вкладку сообщений: " + str(e)[:100].replace(chr(10), " "))
                time.sleep(20)
                continue
            log("подключён к Chrome, непрочитанных в состоянии: %s" % st.get("unread"))
            ALIVE.write_text(str(time.time()))
            while br.is_connected():
                if browser_host.direct_proxy.ensure_running():
                    log("прокси мимо VPN не отвечал, запущен заново")
                try:
                    if page.is_closed():
                        page = get_page(ctx)
                    n, how = read(page)
                except Exception as e:
                    n, how = None, "error"
                    log("ошибка чтения: " + str(e)[:120].replace("\n", " "))
                if not br.is_connected():
                    break
                if n is None:
                    fails += 1
                    log(f"проблема: {how} (подряд {fails})")
                    if fails == 3 and how in ("block", "login"):
                        tg("Авито: наблюдатель не работает (" + ("слетел вход, открой сайт автовыкладки и войди" if how == "login" else "Авито просит проверку или блок по IP, открой сайт автовыкладки и пройди её") + ")")
                    ALIVE.write_text(str(time.time()))
                    if fails >= 3:
                        time.sleep(10 * 60)  # при проблемах не долбим Авито
                    try:
                        open_page(page)
                    except Exception:
                        pass
                else:
                    fails = 0
                    prev = st.get("unread", 0)
                    sent = True
                    if n > prev:
                        sent = tg("Авито" if n - prev == 1 else f"Авито +{n - prev}")
                        log(f"сообщение: {prev} -> {n}" + ("" if sent else " (TELEGRAM НЕ УШЁЛ, см. telegram.log)"))
                    if n != prev and sent:  # не отправилось в Telegram: состояние не меняем, повторим в следующем цикле
                        st["unread"] = n
                        STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
                ALIVE.write_text(str(time.time()))
                time.sleep(READ_EVERY + random.randint(-5, 5))
            log("Chrome закрыт, поднимаю заново")
            time.sleep(5)
            browser_host.ensure()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # упали при старте или в работе: пишем в лог и сообщаем в Telegram, дальше перезапустит задача
        import traceback
        log("ПАДЕНИЕ: " + traceback.format_exc()[-600:].replace("\n", " | "))
        try:
            tg("Авито: наблюдатель упал (" + type(e).__name__ + ": " + str(e)[:150] + "). Сейчас попробую перезапустить.")
        except Exception:
            pass
        raise
