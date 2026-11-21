"""Тексты объявлений: один шаблон (шаблон_описания.txt) + уникальная подмена символов.
Разрешённая подмена (читаемая): а→a, е→e/E, о→o/0, з→3. Латинские слова, цифры и адрес не трогаются.
Структуру шаблона можно менять в файле шаблона (например, раз в неделю), код менять не нужно."""
import random, re, secrets
from pathlib import Path

HERE = Path(__file__).parent
TEMPLATE = HERE / "шаблон_описания.txt"


def sub(text, rng):
    def word(m):
        w = m.group(0)
        if re.search(r"[\d@]", w):
            return w
        out = []
        for ch in w:
            if rng.random() < 0.5:
                if ch == "а":
                    ch = "a"
                elif ch == "е":
                    ch = "E" if rng.random() < .3 else "e"
                elif ch == "Е":
                    ch = "E"
                elif ch == "о":
                    ch = "0" if rng.random() < .25 else "o"
                elif ch == "з":
                    ch = "3"
            out.append(ch)
        return "".join(out)
    return re.sub(r"[A-Za-zА-Яа-яЁё]+", word, text)


def _letters(line):
    return len(re.findall(r"[A-Za-zА-Яа-я]", line))


# {n} модель, {m} память, {s} SIM; слово «новый» в начале, середине или конце, чтобы заголовки одной модели не совпадали
TITLE_FORMS = ["{n} {m} {s}", "Новый {n} {m} {s}", "{n} {m} {s} новый", "{n} {m} {s}, новый",
               "{n} новый {m} {s}", "{n} {m} новый {s}", "{n}, {m}, {s}, новый", "Новый {n}, {m}, {s}",
               "{n} {m}, новый, {s}", "{n} новый, {m}, {s}"]


def make_batch(cfg, plan, seed=None):
    """plan: список ключей моделей по порядку, напр. ['pm17','i17','i17'].
    Возвращает список объявлений: key, title, desc, chars."""
    template = TEMPLATE.read_text(encoding="utf-8").strip()
    rng = random.Random(seed if seed is not None else secrets.randbits(64))
    used = {}
    title_n = {}
    title_pool = {}
    result = []
    for key in plan:
        m = cfg["models"][key]
        clean = template.format(NAME=f"{m['name']} {m['mem']}, {m['color']}", MEM=m["mem"], COLOR=m["color"],
                                OTHERS=m["others"], SIM=cfg["sim_text"], ADDR=cfg["address"], NEED=m["need"])
        lines = []
        for line in clean.split("\n"):
            seen = used.setdefault(line, set())
            cand = line
            for _ in range(400):
                cand = sub(line, rng)
                if cand not in seen:
                    break
            seen.add(cand)
            lines.append(cand)
        n = title_n.get(key, 0)
        title_n[key] = n + 1
        if n == 0:
            title_pool[key] = rng.sample(TITLE_FORMS, len(TITLE_FORMS))
        form = title_pool[key][n % len(TITLE_FORMS)]
        title = form.format(n=m["name"], m=m["mem"], s=cfg["sim"])
        assert len(title) <= 50, title
        color_char = m["color"].capitalize()
        chars = {"Модель": m["name"], "Встроенная память": m["mem_char"], "SIM-карты": cfg["sim"], "Цвет": color_char}
        result.append({"key": key, "title": title, "desc": "\n".join(lines), "chars": chars, "price": m["price"]})
    return result


def plan_from_config(cfg):
    plan = []
    for key, m in cfg["models"].items():
        plan += [key] * int(m.get("count", 0))
    random.shuffle(plan)
    return plan
