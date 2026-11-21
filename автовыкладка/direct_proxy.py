"""Локальный прокси 127.0.0.1:8899, который выпускает весь трафик нашего Chrome В ОБХОД VPN.
Исходящие соединения привязываются к адресу сетевой карты (Ethernet), поэтому они идут мимо туннеля VPN (Happ),
а сайты видят домашний российский IP. Chrome ходит в прокси по loopback, его VPN не трогает.
Поддерживает HTTPS (CONNECT) и обычный HTTP. Работает ОТДЕЛЬНЫМ процессом (pythonw direct_proxy.py): его запускают
по необходимости наблюдатель (avito_watch.py), browser_host.py и сайт (app.py) через ensure_running()."""
import asyncio, socket, subprocess, sys, time
from pathlib import Path

PORT = 8899
_GW = None


def gateway():
    """IP роутера: settings.json (gateway) или автоопределение по физической сетевой карте (не VPN-адаптер)."""
    global _GW
    if _GW:
        return _GW
    import settings
    gw = settings.load()["gateway"]
    if not gw:
        cmd = ("(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | Get-NetIPConfiguration | "
               "Where-Object IPv4DefaultGateway | Select-Object -First 1).IPv4DefaultGateway.NextHop")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                           creationflags=0x08000000, timeout=30)
        gw = r.stdout.strip()
    if not gw:
        raise RuntimeError("Не удалось определить IP роутера. Укажите gateway в settings.json")
    _GW = gw
    return gw


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((gateway(), 9))
        return s.getsockname()[0]
    finally:
        s.close()


async def pipe(r, w):
    try:
        while True:
            data = await r.read(65536)
            if not data:
                break
            w.write(data)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass


async def handle(cr, cw, src):
    try:
        head = await asyncio.wait_for(cr.readuntil(b"\r\n\r\n"), 30)
        line, _, rest = head.partition(b"\r\n")
        method, target, ver = line.decode("latin1").split(" ", 2)
        if method.upper() == "CONNECT":
            host, _, port = target.rpartition(":")
            ur, uw = await asyncio.wait_for(asyncio.open_connection(host.strip("[]"), int(port), local_addr=(src, 0)), 20)
            cw.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await cw.drain()
        else:
            from urllib.parse import urlsplit
            u = urlsplit(target)
            host, port = u.hostname, u.port or 80
            ur, uw = await asyncio.wait_for(asyncio.open_connection(host, port, local_addr=(src, 0)), 20)
            path = (u.path or "/") + ("?" + u.query if u.query else "")
            hdrs = b"\r\n".join(h for h in rest.split(b"\r\n") if not h.lower().startswith((b"proxy-connection", b"connection")))
            uw.write(f"{method} {path} {ver}\r\n".encode("latin1") + hdrs + b"\r\nConnection: close\r\n\r\n")
            await uw.drain()
        await asyncio.gather(pipe(cr, uw), pipe(ur, cw))
    except Exception:
        try:
            cw.close()
        except Exception:
            pass


def serve():
    async def main():
        # адрес карты определяем на каждое соединение: DHCP может поменять его, а сеть при загрузке поднимается не сразу
        srv = await asyncio.start_server(lambda r, w: handle(r, w, local_ip()), "127.0.0.1", PORT)
        async with srv:
            await srv.serve_forever()
    asyncio.run(main())


def alive():
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=0.5).close()
        return True
    except OSError:
        return False


def ensure_running():
    """Прокси живёт ОТДЕЛЬНЫМ процессом (не зависит от наблюдателя и сайта): если не отвечает, запускает его.
    Возвращает True, если пришлось запускать."""
    import settings
    if not settings.load()["bypass_vpn"] or alive():
        return False
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    subprocess.Popen([str(pyw if pyw.exists() else exe), str(Path(__file__).resolve())],
                     cwd=str(Path(__file__).parent), creationflags=0x00000008 | 0x00000200, close_fds=True)
    for _ in range(20):
        time.sleep(0.3)
        if alive():
            break
    return True


start = ensure_running  # прежнее имя


if __name__ == "__main__":
    while True:  # при сбое (например, сеть ещё не поднялась) пробуем снова
        try:
            serve()
        except Exception:
            time.sleep(5)
