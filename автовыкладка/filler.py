"""Заполнитель форм Авито. Для каждого объявления открывает новую вкладку кликом по «Разместить объявление»,
заполняет поля и ОСТАВЛЯЕТ вкладку открытой. Адрес, доставку, кнопку «Продолжить» и публикацию НЕ трогает — это делает человек.
При любом незнакомом экране или несовпадении — останавливается (вкладка остаётся как есть)."""
import random, re, tempfile, threading, time, uuid
from pathlib import Path

import photos, textgen
from cdp import chrome, DEBUG

STATE = {"running": False, "stop": False, "done": 0, "total": 0, "step": "", "error": "", "log": []}
SPEED = {"type_desc": (15, 45), "type_field": (60, 150), "pause": (500, 1400), "between": (5000, 12000)}


class Stop(Exception):
    pass


def say(msg):
    STATE["step"] = msg
    STATE["log"].append(time.strftime("%H:%M:%S ") + msg)
    del STATE["log"][:-60]


def pause(pg, kind="pause"):
    if STATE["stop"]:
        raise Stop("остановлено пользователем")
    a, b = SPEED[kind]
    pg.wait_for_timeout(random.randint(a, b))


def type_text(pg, text, kind="type_field"):
    a, b = SPEED[kind]
    for i, ch in enumerate(text):
        if ch == "\n":
            pg.keyboard.press("Enter")
        else:
            pg.keyboard.type(ch)
        pg.wait_for_timeout(random.randint(a, b))
        if i % 40 == 0 and STATE["stop"]:
            raise Stop("остановлено пользователем")


def m(marker, op="="):
    return f'[data-marker{op}"{marker}"]'


def exact(text):
    return re.compile(r"^\s*" + re.escape(text) + r"\s*$")


def need(loc, what, timeout=10000):
    try:
        loc.first.wait_for(state="visible", timeout=timeout)
    except Exception:
        raise Stop(f"не нашла на странице: {what}")
    return loc.first


def check_page(pg):
    t = pg.title()
    if "Доступ ограничен" in t or pg.locator("text=Подтвердите, что вы не робот").count() or "captcha" in pg.url:
        raise Stop("Авито показал проверку/ограничение доступа — остановилась")
    if pg.locator(m("header/login-button")).count():
        raise Stop("в этом Chrome не выполнен вход в Авито")


def click(pg, loc, what):
    el = need(loc, what)
    el.scroll_into_view_if_needed()
    pg.wait_for_timeout(random.randint(250, 600))
    el.click()
    pause(pg)


def pick_dropdown(pg, field, value, what):
    click(pg, pg.locator(m(field)), what)
    opts = pg.locator(m(field + "/custom-option", "^="))
    need(opts, f"варианты поля «{what}»")
    opt = opts.filter(has_text=exact(value))
    if not opt.count():
        have = [o.strip() for o in opts.all_inner_texts()]
        pg.keyboard.press("Escape")
        raise Stop(f"в поле «{what}» нет варианта «{value}». Есть: {', '.join(have)}")
    click(pg, opt, f"{what}: {value}")
    got = pg.locator(m(field)).first.inner_text().strip()
    if value not in got:
        raise Stop(f"поле «{what}» не приняло значение «{value}» (сейчас: «{got}»)")


def fill_condition(pg, cfg):
    """Блок «Состояние»: история смартфона, комплект (галочки), упаковка."""
    click(pg, pg.locator(m("params[184667]/option", "^=")).filter(has_text=exact(cfg["history"])), "История смартфона")
    for item in cfg["kit"]:
        lab = need(pg.locator(m("params[148127][]/option", "^=")).filter(has_text=exact(item)), f"Комплект: {item}")
        box = lab.locator("input")
        if not box.is_checked():
            click(pg, lab, f"Комплект: {item}")
            if not box.is_checked():
                raise Stop(f"не получилось отметить «{item}» в комплекте")
    click(pg, pg.locator(m("params[167055]/option", "^=")).filter(has_text=exact(cfg["package"])), "Упаковка смартфона")


def open_form(ctx):
    home = None
    for pg in ctx.pages:
        if "avito.ru" in pg.url and "/additem" not in pg.url and pg.locator('a[href="/additem"]').count():
            home = pg
            break
    if home is None:
        home = ctx.new_page()
        home.goto("https://www.avito.ru/", wait_until="domcontentloaded", timeout=60000)
        home.wait_for_timeout(3000)
    check_page(home)
    link = need(home.locator('a[href="/additem"]'), "кнопка «Разместить объявление»")
    with ctx.expect_page(timeout=20000) as np:
        link.click(modifiers=["Control"])
    pg = np.value
    pg.wait_for_load_state("domcontentloaded", timeout=60000)
    pg.bring_to_front()
    pg.wait_for_timeout(random.randint(2500, 4000))
    check_page(pg)
    return pg


def fill_one(ctx, cfg, ad, n):
    md = cfg["models"][ad["key"]]
    say(f"№{n}: открываю форму")
    pg = open_form(ctx)

    if pg.locator(m("category-wizard/button")).count():
        click(pg, pg.locator(m("category-wizard/button")).filter(has_text=exact("Электроника")), "категория «Электроника»")
    say(f"№{n}: заголовок")
    title = need(pg.locator("#title"), "поле «Название объявления»")
    if title.input_value().strip():
        raise Stop("в новой форме уже есть название (Авито подставил черновик?) — остановилась, чтобы не испортить")
    title.click()
    type_text(pg, ad["title"])
    pause(pg)
    click(pg, pg.locator("button" + m("category-title")).filter(has_text="Мобильные телефоны"), "подсказка категории «Мобильные телефоны»")
    need(pg.locator(m("model/search-input")), "форма параметров телефона", 20000)
    pause(pg)

    say(f"№{n}: состояние и вид объявления")
    click(pg, pg.locator(m("params[110395]/option", "^=")).filter(has_text="Новый"), "Состояние: Новый")
    click(pg, pg.locator(m("params[2822]/option", "^=")).filter(has_text=cfg["ad_kind"]), "Вид объявления")

    say(f"№{n}: характеристики")
    brand = pg.locator(m("params[110618]/input")).first.input_value().strip()
    model = pg.locator(m("model/search-input")).first.input_value().strip()
    if brand != "Apple" or model != md["name"]:
        raise Stop(f"Авито определил модель как «{brand} {model}», а нужно «Apple {md['name']}»")
    pick_dropdown(pg, "memory_size", md["mem_char"], "Встроенная память")
    pick_dropdown(pg, "color", md["color_avito"], "Цвет")
    click(pg, pg.locator(m("params[184666]/option", "^=")).filter(has_text=exact(cfg["sim"])), "SIM-карты")
    if cfg.get("country"):
        fld = need(pg.locator(m("params[199748]/input")), "Страна происхождения")
        if fld.input_value().strip() != cfg["country"]:
            fld.scroll_into_view_if_needed()
            if pg.locator(m("params[199748]/clear")).count():
                pg.locator(m("params[199748]/clear")).first.click()
                pg.wait_for_timeout(random.randint(500, 900))
            fld.click()
            type_text(pg, cfg["country"])
            pause(pg)
            click(pg, pg.locator(m("params[199748]/option")).filter(has_text=exact(cfg["country"])), "страна в списке")
            if fld.input_value().strip() != cfg["country"]:
                raise Stop("страна происхождения не выбралась")

    say(f"№{n}: история, комплект, упаковка")
    fill_condition(pg, cfg)

    say(f"№{n}: готовлю и загружаю фото")
    tmp = Path(tempfile.gettempdir()) / ("avito_ph_" + uuid.uuid4().hex[:8])
    try:
        files = photos.make_set(md["photo_dir"], tmp)  # все оригиналы папки по порядку номеров, до 10
        inp = pg.locator(m("add/input")).first
        pg.locator(m("images")).first.scroll_into_view_if_needed()
        pause(pg)
        imgs = pg.locator(m("images") + " img")
        for k, f in enumerate(files, 1):  # по одной, чтобы порядок на Авито совпал с номерами
            inp.set_input_files(str(f))
            deadline = time.time() + 60
            while imgs.count() < k:
                if time.time() > deadline:
                    raise Stop(f"фото №{k} не загрузилось за 60 секунд")
                pg.wait_for_timeout(700)
            pg.wait_for_timeout(random.randint(400, 1100))
        busy = lambda: pg.locator(m("images") + ' [class*="loader"], ' + m("images") + ' [class*="progress"]').count()
        deadline = time.time() + 90
        while busy() and time.time() < deadline:
            pg.wait_for_timeout(1000)
        pg.wait_for_timeout(1000)
    finally:
        photos.cleanup(tmp)

    say(f"№{n}: описание")
    ed = need(pg.locator(m("description-html-editor") + " [role=textbox]"), "поле описания")
    ed.scroll_into_view_if_needed()
    pause(pg)
    ed.click()
    norm = lambda s: re.sub(r"\s+", "", s)
    if cfg.get("desc_mode", "paste") == "paste":
        pg.keyboard.insert_text(ad["desc"])  # как вставка из буфера: мгновенно, структура строк сохраняется
        pause(pg)
        if norm(ed.inner_text()) != norm(ad["desc"]):  # не вставилось — очищаем и печатаем
            pg.keyboard.press("Control+A")
            pg.keyboard.press("Delete")
            say(f"№{n}: вставка не сработала, печатаю описание")
            type_text(pg, ad["desc"], "type_desc")
    else:
        say(f"№{n}: печатаю описание (~2 минуты)")
        type_text(pg, ad["desc"], "type_desc")
    pause(pg)
    if norm(ed.inner_text()) != norm(ad["desc"]):
        raise Stop("описание в форме не совпало с подготовленным текстом — проверь его глазами")

    say(f"№{n}: цена")
    price = need(pg.locator("#price"), "поле «Цена»")
    price.scroll_into_view_if_needed()
    pause(pg)
    price.click()
    type_text(pg, str(int(md["price"])))
    pause(pg)
    if re.sub(r"\D", "", price.input_value()) != str(int(md["price"])):
        raise Stop("цена ввелась неверно")

    if cfg.get("offer_off", True):
        cb = pg.locator('input[name="params[195944]"]')
        if cb.count() and cb.first.is_checked():
            say(f"№{n}: выключаю «Предложение для заинтересованных покупателей»")
            cb.first.scroll_into_view_if_needed()
            cb.first.click(force=True)
            pause(pg)
            if cb.first.is_checked():
                raise Stop("не получилось выключить «Предложение для заинтересованных покупателей»")
    pg.screenshot(path=str(DEBUG / f"filled_{n}.png"), full_page=True)
    say(f"№{n}: готово, вкладка оставлена открытой")


def run(cfg, plan):
    """Заполняет формы по плану. Вызывать в отдельном потоке."""
    STATE.update(running=True, stop=False, done=0, total=len(plan), error="", step="подключаюсь к Chrome", log=[])
    try:
        ads = textgen.make_batch(cfg, plan)
        with chrome() as ctx:
            for n, ad in enumerate(ads, 1):
                fill_one(ctx, cfg, ad, n)
                STATE["done"] = n
                if n < len(ads):
                    say(f"пауза перед №{n + 1}")
                    pause(ctx.pages[0], "between")
        say("Все формы заполнены. Выбери адрес, выключи доставку и публикуй сам.")
    except Stop as e:
        STATE["error"] = str(e)
        say("СТОП: " + str(e))
    except Exception as e:
        STATE["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        say("ОШИБКА: " + STATE["error"])
    finally:
        STATE["running"] = False


def start(cfg, plan):
    if STATE["running"]:
        return False
    threading.Thread(target=run, args=(cfg, plan), daemon=True).start()
    return True
