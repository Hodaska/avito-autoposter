"""Локальный сайт автовыкладки: http://127.0.0.1:7777  (запуск: запуск_сайта.bat).
Только стандартная библиотека. Слушает ТОЛЬКО 127.0.0.1."""
import json, subprocess, tempfile, threading, time, urllib.request, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import browser_host, direct_proxy, filler, photos, textgen

HERE = Path(__file__).parent
CFG = HERE / "config.json"
SAMPLE_DIR = Path(tempfile.gettempdir()) / "avito_sample"


def load_cfg():
    if not CFG.exists():  # при первом запуске берём пример настроек
        CFG.write_text((HERE / "config.example.json").read_text(encoding="utf-8"), encoding="utf-8")
    return json.loads(CFG.read_text(encoding="utf-8"))


def chrome_up():
    return browser_host.chrome_up()


def browser_state(action):
    """action: show | hide | status. Окно единого Chrome показывается/прячется БЕЗ перезапуска и перезагрузки страниц."""
    started = browser_host.ensure()  # если Chrome почему-то не запущен, поднимет (спрятанным)
    if action == "show":
        browser_host.set_visible(True)
    elif action == "hide":
        browser_host.set_visible(False)
    res = {"chrome": chrome_up(), "started": started, "visible": browser_host.is_visible(), "logged_in": None, "blocked": False}
    if not res["chrome"]:
        res["error"] = "Chrome не поднялся на порту 9222."
        return res
    try:
        from cdp import chrome as cdp_chrome, avito_pages
        with cdp_chrome() as ctx:
            pages = avito_pages(ctx)
            if pages:
                pg = pages[0]
                res["blocked"] = "Доступ ограничен" in pg.title()
                res["logged_in"] = None if res["blocked"] else bool(pg.locator('[data-marker="header/username-button"]').count()) and not pg.locator('[data-marker="header/login-button"]').count()
    except Exception:
        pass
    return res


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path == "/":
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/config":
            return self._send(200, load_cfg())
        if self.path == "/api/status":
            return self._send(200, filler.STATE)
        if self.path == "/api/info":
            return self._send(200, self._info())
        if self.path.startswith("/sample/"):
            f = SAMPLE_DIR / Path(self.path[8:]).name
            if f.is_file():
                return self._send(200, f.read_bytes(), "image/jpeg")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            if self.path == "/api/config":
                CFG.write_text(json.dumps(self._json(), ensure_ascii=False, indent=2), encoding="utf-8")
                return self._send(200, {"ok": True})
            if self.path == "/api/preview":
                cfg = load_cfg()
                return self._send(200, textgen.make_batch(cfg, textgen.plan_from_config(cfg)))
            if self.path == "/api/photo-sample":
                key = self._json()["model"]
                cfg = load_cfg()
                out = SAMPLE_DIR / uuid.uuid4().hex[:8]
                files = photos.make_set(cfg["models"][key]["photo_dir"], out)
                return self._send(200, {"urls": [f"/sample/{f.parent.name}_{f.name}" for f in self._copy(files)]})
            if self.path == "/api/run":
                cfg = load_cfg()
                plan = textgen.plan_from_config(cfg)
                if not plan:
                    return self._send(400, {"error": "Количество объявлений равно нулю."})
                if not filler.start(cfg, plan):
                    return self._send(409, {"error": "Заполнение уже идёт."})
                return self._send(200, {"ok": True, "total": len(plan)})
            if self.path == "/api/browser":
                return self._send(200, browser_state(self._json().get("action", "status")))
            if self.path == "/api/stop":
                filler.STATE["stop"] = True
                return self._send(200, {"ok": True})
        except Exception as e:
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        self._send(404, {"error": "not found"})

    @staticmethod
    def _info():
        cfg = load_cfg()
        ph = {}
        for k, m in cfg["models"].items():
            try:
                ph[k] = len(photos.originals(m["photo_dir"]))
            except Exception:
                ph[k] = 0
        chrome_ok, forms = False, 0
        try:
            with urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=1.5) as r:
                tabs = json.loads(r.read())
            chrome_ok = True
            forms = sum(1 for t in tabs if t.get("type") == "page" and "avito.ru/additem" in t.get("url", ""))
        except Exception:
            pass
        return {"chrome": chrome_ok, "forms": forms, "photos": ph}

    @staticmethod
    def _copy(files):
        # раздаём из общей папки, чтобы можно было удалить рабочую
        SAMPLE_DIR.mkdir(exist_ok=True)
        res = []
        for f in files:
            dst = SAMPLE_DIR / f"{f.parent.name}_{f.name}"
            dst.write_bytes(f.read_bytes())
            res.append(dst)
        return res

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    SAMPLE_DIR.mkdir(exist_ok=True)
    direct_proxy.start()
    print("Сайт: http://127.0.0.1:7777  (Ctrl+C — остановить)")
    ThreadingHTTPServer(("127.0.0.1", 7777), H).serve_forever()
