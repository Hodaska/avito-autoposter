"""Сторож наблюдателя за Авито. Запускается задачей «AvitoGuard» при входе в Windows и каждые 5 минут.
Если метка data\avito_watch.alive старше 4 минут (или нет) два раза подряд, шлёт в Telegram «наблюдатель не работает»
и пробует запустить задачу AvitoWatch. Когда наблюдатель оживает, шлёт «снова работает».
Зависит только от стандартной библиотеки (чтобы работать, даже если сломан Python-окружение наблюдателя — нужен лишь сам Python)."""
import json, subprocess, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
ALIVE = ROOT / "data" / "avito_watch.alive"
STATE = ROOT / "data" / "avito_guard_state.json"
SECRETS = ROOT / "secrets" / "telegram.json"  # {"token": "...", "chat_id": "..."}; в .gitignore
PAUSED = ROOT / "data" / "watch_paused"  # ставит сайт автовыкладки на время работы своего Chrome
STALE = 4 * 60  # секунд без метки = наблюдатель не работает


def tg(text):
    try:
        import os
        sec = ({"token": os.environ["TG_TOKEN"], "chat_id": os.environ["TG_CHAT_ID"]} if os.environ.get("TG_TOKEN") and os.environ.get("TG_CHAT_ID")
               else json.loads(SECRETS.read_text(encoding="utf-8-sig")))
        req = urllib.request.Request(f"https://api.telegram.org/bot{sec['token']}/sendMessage",
                                     json.dumps({"chat_id": sec["chat_id"], "text": text}).encode(),
                                     {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20)
    except Exception:
        pass


def load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"bad": 0, "alerted": False}


def chrome_up():
    try:
        urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=2).read()
        return True
    except Exception:
        return False


def main():
    st = load()
    PAUSED.unlink(missing_ok=True)  # старый флаг паузы больше не используется (теперь наблюдатель работает всегда)
    try:
        age = time.time() - float(ALIVE.read_text())
    except Exception:
        age = 10 ** 9
    if age <= STALE:
        if st["alerted"]:
            tg("Авито: наблюдатель снова работает.")
        st = {"bad": 0, "alerted": False}
    else:
        st["bad"] += 1
        if st["bad"] >= 2 and not st["alerted"]:
            tg("Авито: наблюдатель не работает (нет сигнала жизни). Пробую перезапустить. Подробности в data/avito_watch.log.")
            st["alerted"] = True
        if st["bad"] >= 2:
            rc = subprocess.run(["powershell", "-NoProfile", "-Command", "Start-ScheduledTask AvitoWatch"],
                                creationflags=0x08000000, timeout=60).returncode  # CREATE_NO_WINDOW
            if rc != 0:  # задачи AvitoWatch нет (наблюдатель стартует из автозагрузки): запускаем напрямую
                import sys
                exe = Path(sys.executable)
                pyw = exe.with_name("pythonw.exe")
                subprocess.Popen([str(pyw if pyw.exists() else exe), str(ROOT / "avito_watch.py")], cwd=str(ROOT),
                                 creationflags=0x08000000 | 0x00000008, close_fds=True)
    STATE.write_text(json.dumps(st), encoding="utf-8")


if __name__ == "__main__":
    main()
