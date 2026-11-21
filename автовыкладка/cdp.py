"""Подключение к уже открытому Chrome (start_chrome.bat, порт 9222). Сам Chrome не закрывает."""
from contextlib import contextmanager
from pathlib import Path
from playwright.sync_api import sync_playwright

DEBUG = Path(__file__).parent / "debug"
DEBUG.mkdir(exist_ok=True)

DUMP_JS = """() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const pick = sel => [...document.querySelectorAll(sel)].filter(vis).map(e => ({
    tag: e.tagName.toLowerCase(), type: e.type || null, name: e.name || null, id: e.id || null,
    marker: e.getAttribute('data-marker'), role: e.getAttribute('role'), aria: e.getAttribute('aria-label'),
    placeholder: e.getAttribute('placeholder'), href: e.getAttribute('href'),
    text: (e.innerText || e.value || '').trim().slice(0, 80)}));
  return {url: location.href, title: document.title,
    headings: [...document.querySelectorAll('h1,h2,h3,legend,label')].filter(vis).map(e => e.innerText.trim().slice(0, 80)),
    inputs: pick('input,textarea,select,[contenteditable=true]'),
    buttons: pick('button,[role=button],[role=option],[role=radio],a[data-marker]')};
}"""


@contextmanager
def chrome():
    with sync_playwright() as p:
        br = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=15000)
        try:
            yield br.contexts[0]
        finally:
            br.close()  # только разрывает соединение, окно остаётся


def avito_pages(ctx):
    return [pg for pg in ctx.pages if "avito.ru" in pg.url]
