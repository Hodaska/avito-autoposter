"""Разведка формы Авито. ТОЛЬКО ЧТЕНИЕ: подключается к открытому Chrome (порт 9222),
ничего не кликает и не вводит. Для каждой вкладки Авито сохраняет URL, скриншот и
список полей/кнопок в папку debug\\recon (папка с персональными данными, наружу не выносить)."""
import json, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "debug" / "recon"
OUT.mkdir(parents=True, exist_ok=True)

JS = """() => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const pick = (sel) => [...document.querySelectorAll(sel)].filter(vis).map(e => ({
    tag: e.tagName.toLowerCase(), type: e.type || null, name: e.name || null,
    id: e.id || null, marker: e.getAttribute('data-marker'),
    role: e.getAttribute('role'), aria: e.getAttribute('aria-label'),
    placeholder: e.getAttribute('placeholder'),
    text: (e.innerText || e.value || '').trim().slice(0, 80)
  }));
  return {
    url: location.href, title: document.title,
    headings: [...document.querySelectorAll('h1,h2,h3')].filter(vis).map(e => e.innerText.trim().slice(0, 100)),
    inputs: pick('input,textarea,select'),
    buttons: pick('button,[role=button],a[data-marker]'),
    markers: [...new Set([...document.querySelectorAll('[data-marker]')].map(e => e.getAttribute('data-marker')))]
  };
}"""

with sync_playwright() as p:
    br = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=15000)
    n = 0
    for ctx in br.contexts:
        for page in ctx.pages:
            if "avito.ru" not in page.url:
                continue
            n += 1
            tag = f"{int(time.time())}_{n}"
            try:
                data = page.evaluate(JS)
                page.screenshot(path=str(OUT / f"{tag}.png"), full_page=True)
                (OUT / f"{tag}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"[{n}] {data['url']}  полей: {len(data['inputs'])}, кнопок: {len(data['buttons'])} -> {tag}")
            except Exception as e:
                print(f"[{n}] ошибка: {e}")
    if n == 0:
        print("Вкладок Авито не найдено. Открой Авито в окне, запущенном через start_chrome.bat.")
    # соединение закрываем без закрытия самого Chrome
    br.close()
