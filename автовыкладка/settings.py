"""Необязательные настройки установки: файл settings.json в корне репозитория (он в .gitignore, у каждого свой).
Поддерживаемые ключи (все необязательные):
  bypass_vpn  true/false  Пускать Chrome с Авито мимо VPN через локальный прокси direct_proxy.py (по умолчанию true).
                          Поставьте false, если VPN нет или Авито и так открывается.
  gateway     "192.168.0.1"  IP роутера. Если не указан, определяется автоматически по физической сетевой карте.
  chrome_path "C:/путь/к/chrome.exe"  Если Chrome стоит не в стандартном месте."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "settings.json"
DEFAULTS = {"bypass_vpn": True, "gateway": "", "chrome_path": ""}


def load():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(FILE.read_text(encoding="utf-8-sig")))
    except Exception:
        pass
    return cfg


def chrome_path():
    p = load()["chrome_path"]
    if p and Path(p).exists():
        return p
    import os
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            c = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if c.exists():
                return str(c)
    raise FileNotFoundError("Chrome не найден. Установите Google Chrome или укажите chrome_path в settings.json")
