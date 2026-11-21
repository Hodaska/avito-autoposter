"""Уникализация фото: при каждой загрузке заново, из ОРИГИНАЛОВ в папке модели. Оригиналы не меняются.
Берутся файлы с числовым именем (1.png, 2.jfif, ...) по порядку номеров, до 10 штук. Остальные файлы в папке игнорируются.
Сильные изменения: зум 18-26%, поворот 2-4,5°, тон/контраст/насыщенность, температура, гамма, диагональный градиент,
виньетка, шум, лёгкое размытие/резкость, EXIF вычищается, JPEG разного качества. Временные копии удаляются после загрузки."""
import math, random, re, secrets, shutil
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).parent.parent
EXT = {".png", ".jpg", ".jpeg", ".jfif", ".webp"}
MAX_PHOTOS = 10


def originals(folder):
    """Файлы с числовым именем по возрастанию номера."""
    d = ROOT / folder
    files = [p for p in d.iterdir() if p.suffix.lower() in EXT and re.fullmatch(r"\d+", p.stem)]
    return sorted(files, key=lambda p: int(p.stem))[:MAX_PHOTOS]


def _gradient(size, rng):
    """Диагональный градиент: слабая цветная заливка, плавно меняющаяся по кадру."""
    w, h = size
    ang = rng.uniform(0, 2 * math.pi)
    dx, dy = math.cos(ang), math.sin(ang)
    small = 64
    g = Image.new("L", (small, small))
    px = g.load()
    for y in range(small):
        for x in range(small):
            t = ((x / small - .5) * dx + (y / small - .5) * dy) + .5
            px[x, y] = int(max(0, min(1, t)) * 255)
    return g.resize((w, h), Image.BICUBIC)


def _vignette(size, strength):
    w, h = size
    small = 64
    v = Image.new("L", (small, small))
    px = v.load()
    for y in range(small):
        for x in range(small):
            d = math.hypot(x / small - .5, y / small - .5) / .7071
            px[x, y] = int(255 * (d ** 2) * strength)
    return v.resize((w, h), Image.BICUBIC)


def uniquify(path, rng):
    im = Image.open(path)
    if im.mode != "RGB":
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        im = bg
    w, h = im.size
    # поворот 2–4,5° в случайную сторону
    angle = rng.choice([-1, 1]) * rng.uniform(2.0, 4.5)
    im = im.rotate(angle, resample=Image.BICUBIC)
    # зум 18–26% (убирает пустые углы после поворота), небольшой сдвиг центра
    zoom = rng.uniform(0.18, 0.26)
    cw, ch = int(w * (1 - zoom)), int(h * (1 - zoom))
    x = (w - cw) // 2 + rng.randint(-int(w * 0.015), int(w * 0.015))
    y = (h - ch) // 2 + rng.randint(-int(h * 0.015), int(h * 0.015))
    x, y = max(0, min(x, w - cw)), max(0, min(y, h - ch))
    im = im.crop((x, y, x + cw, y + ch))
    scale = rng.uniform(0.94, 1.06)  # итоговый размер слегка отличается от исходного
    im = im.resize((max(400, int(w * scale)), max(400, int(h * scale))), Image.LANCZOS)
    # тон
    im = ImageEnhance.Brightness(im).enhance(rng.uniform(0.90, 1.10))
    im = ImageEnhance.Contrast(im).enhance(rng.uniform(0.90, 1.12))
    im = ImageEnhance.Color(im).enhance(rng.uniform(0.88, 1.12))
    gamma = rng.uniform(0.9, 1.12)
    im = im.point([int(255 * ((i / 255) ** gamma)) for i in range(256)] * 3)
    # температура: красный/синий в противоположные стороны
    r, g, b = im.split()
    t = rng.randint(-9, 9)
    r = r.point(lambda v: max(0, min(255, v + t)))
    b = b.point(lambda v: max(0, min(255, v - t)))
    im = Image.merge("RGB", (r, g, b))
    # диагональный градиент: цветная подсветка с плавным переходом
    tint = tuple(rng.randint(150, 255) for _ in range(3))
    k = rng.uniform(0.06, 0.14)
    mask = _gradient(im.size, rng).point(lambda v: int(v * k))
    im = Image.composite(Image.new("RGB", im.size, tint), im, mask)
    # виньетка
    if rng.random() < 0.7:
        vm = _vignette(im.size, rng.uniform(0.18, 0.40))
        im = Image.composite(Image.new("RGB", im.size, (0, 0, 0)), im, vm)
    # резкость/размытие
    if rng.random() < 0.5:
        im = im.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 0.7)))
    else:
        im = im.filter(ImageFilter.UnsharpMask(radius=rng.uniform(1, 2), percent=rng.randint(40, 90), threshold=2))
    # шум
    noise = Image.effect_noise(im.size, rng.uniform(25, 55)).convert("RGB")
    im = Image.blend(im, noise, rng.uniform(0.02, 0.05))
    return im


def make_set(folder, out_dir, count=None, seed=None):
    """Делает уникальные JPEG из оригиналов по порядку номеров, возвращает пути 01.jpg, 02.jpg, ... в том же порядке."""
    rng = random.Random(seed if seed is not None else secrets.randbits(64))
    src = originals(folder)
    if not src:
        raise FileNotFoundError(f"В папке {folder} нет файлов с числовым именем (1.png, 2.png ...)")
    if count:
        src = src[:count]
    rest = src[1:]
    rng.shuffle(rest)  # первое фото (№1) всегда первым, остальные в случайном порядке
    src = src[:1] + rest
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for i, p in enumerate(src, 1):
        dst = out_dir / f"{i:02d}.jpg"
        uniquify(p, rng).save(dst, "JPEG", quality=rng.randint(82, 92), optimize=True)  # без EXIF
        out.append(dst)
    return out


def cleanup(out_dir):
    shutil.rmtree(out_dir, ignore_errors=True)
