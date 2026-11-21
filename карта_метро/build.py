"""Собирает карта.html из статистика_выкладок.csv + метро.json + шаблон.html.
Запуск: python карта_метро/build.py  (берёт статистика_выкладок.csv, а если её нет, статистика_выкладок.пример.csv)
Правила: строка с пометкой «не перевыложено» дополняет ПРЕДЫДУЩЕЕ объявление на том же месте (история просмотров), а не создаёт новое."""
import csv, json
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
_REAL = HERE.parent / "статистика_выкладок.csv"
CSV = _REAL if _REAL.exists() else HERE.parent / "статистика_выкладок.пример.csv"  # свои данные или пример
CITY = {"Москва": "msk", "Санкт-Петербург": "spb", "Ленинградская обл.": "spb"}
MODEL = {"17": "17", "17 Pro Max": "17pm", "": "?"}
ALIAS = {"Крылатская": "Крылатское", "Мурино, Девяткино": "Девяткино"}  # записано на слух / не станция


def norm(s):
    return s.strip().lower().replace("ё", "е")


def main():
    metro = json.loads((HERE / "метро.json").read_text(encoding="utf-8"))
    index = {c: {norm(n): n for n in metro[c]["stations"]} for c in metro}
    ads, unmatched = [], []
    with open(CSV, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            city = CITY[r["Город"]]
            place = ALIAS.get(r["Место (метро/район)"], r["Место (метро/район)"])
            station = index[city].get(norm(place))
            if not station:
                unmatched.append(place)
                continue
            run, views, days = int(r["Выкладка №"]), int(r["Просмотров"]), int(r["Срок, дней"])
            model = MODEL.get(r.get("Модель", ""), "?")
            note = r["Заметка"].strip()
            if r["Место (метро/район)"] in ALIAS and ALIAS[r["Место (метро/район)"]] != r["Место (метро/район)"]:
                note = (note + "; " if note else "") + "в таблице записано как «" + r["Место (метро/район)"] + "»"
            if "не перевыложено" in note:
                prev = [a for a in ads if a["city"] == city and a["station"] == station and a["run"] < run]
                if prev:
                    a = prev[-1]
                    a["history"].append({"days": days, "views": views})
                    if a["model"] == "?":
                        a["model"] = model
                    continue
            ads.append({"city": city, "station": station, "model": model, "run": run, "note": note,
                        "history": [{"days": days, "views": views}]})
    data = {"metro": metro, "ads": ads, "unmatched": sorted(set(unmatched)), "updated": date.today().strftime("%d.%m.%Y"),
            "note": "Сроки выкладки приблизительные; на просмотры влияют время публикации, цена и позиция в выдаче, поэтому выводы осторожные."}
    html = (HERE / "шаблон.html").read_text(encoding="utf-8").replace(
        "__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    (HERE / "карта.html").write_text(html, encoding="utf-8")
    print(f"объявлений: {len(ads)}, не найдено на карте: {sorted(set(unmatched))}")


if __name__ == "__main__":
    main()
