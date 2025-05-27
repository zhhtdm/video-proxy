import aiohttp
import aiofiles
from aiohttp import web
from pathlib import Path
import os, hashlib, time
import logging
from dotenv import load_dotenv
import asyncio
import random
from lzhgetlogger import get_logger

load_dotenv()  # 默认加载当前目录下的 .env 文件

HOST = os.getenv("HOST", '127.0.0.1')
APP_PATH = os.getenv("APP_PATH", "")
PORT = int(os.getenv("PORT", 8000))
MAX_CACHE_SIZE = int(os.getenv("CACHE_SIZE_GB", 2)) * 1024 * 1024 * 1024
CACHE_DIR = Path(os.getenv("CACHE_DIR", "/tmp/mp4cache"))
ACCESS_TOKEN = os.getenv("TOKEN", "")

logger = get_logger()

CACHE_DIR.mkdir(parents=True, exist_ok=True)

def get_cache_path(url: str) -> Path:
    h = hashlib.sha256(url.encode()).hexdigest()
    return CACHE_DIR / f"{h}.mp4"

def update_mtime(path: Path):
    now = time.time()
    os.utime(path, (now, now))

def get_cache_size() -> int:
    return sum(f.stat().st_size for f in CACHE_DIR.glob("*.mp4"))

def clean_cache_if_needed():
    total = get_cache_size()
    if total <= MAX_CACHE_SIZE:
        return
    files = sorted(CACHE_DIR.glob("*.mp4"), key=lambda f: f.stat().st_mtime)
    for f in files:
        try:
            total -= f.stat().st_size
            f.unlink()
            if total <= MAX_CACHE_SIZE:
                break
        except:
            pass

async def stream_file(response, path, start, end):
    async with aiofiles.open(path, "rb") as f:
        await f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = await f.read(min(8192, remaining))
            if not chunk:
                break
            try:
                await response.write(chunk)
            except (aiohttp.web.HTTPException, ConnectionResetError, aiohttp.ClientConnectionError):
                # print("Client disconnected during cache stream.")
                break
            remaining -= len(chunk)
    try:
        await response.write_eof()
    except:
        pass

async def fetch_mp4(request):
    token = request.query.get("token")
    url:str = request.query.get("url")
    filename = url.split("/")[-1]

    if token != ACCESS_TOKEN:
        await asyncio.sleep(random.randrange(1,5))
        return web.Response(status=403, text="Forbidden: Invalid token")
    if not url or not url.endswith(".mp4"):
        return web.Response(status=400, text="Invalid or missing .mp4 URL")

    cache_path = get_cache_path(url)
    range_header = request.headers.get("Range")

    if cache_path.exists():
        update_mtime(cache_path)
        file_size = cache_path.stat().st_size
        start = 0
        end = file_size - 1
        status = 200

        if range_header and range_header.startswith("bytes="):
            status = 206
            parts = range_header.replace("bytes=", "").split("-")
            start = int(parts[0])
            if parts[1]:
                end = int(parts[1])
        length = end - start + 1

        response = web.StreamResponse(
            status=status,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(length),
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes {start}-{end}/{file_size}" if status == 206 else "",
                "Content-Disposition": f'inline; filename="{filename}"'
            }
        )
        await response.prepare(request)
        await stream_file(response, cache_path, start, end)
        return response

    # 不在缓存中 → 下载保存
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return web.Response(status=resp.status, text="Upstream error")

                content_length = int(resp.headers.get("Content-Length", 0))
                tmp_path = cache_path.with_suffix(".part")

                written_bytes = 0
                response = web.StreamResponse(
                    status=200,
                    headers={
                        "Content-Type": resp.headers.get("Content-Type", "video/mp4"),
                        "Content-Length": str(content_length),
                        "Accept-Ranges": "bytes",
                        "Content-Disposition": f'inline; filename="{filename}"'
                    }
                )
                await response.prepare(request)

                written_bytes = int(0)
                async with aiofiles.open(tmp_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        await f.write(chunk)
                        written_bytes += len(chunk)
                        try:
                            await response.write(chunk)
                        except (aiohttp.web.HTTPException, ConnectionResetError, aiohttp.ClientConnectionError):
                            # print("Client disconnected during fetch stream.")
                            break

                # 判断是否完整
                if written_bytes == content_length and content_length > 0:
                    tmp_path.rename(cache_path)
                    clean_cache_if_needed()
                    # print("Saved complete video to cache.")
                else:
                    tmp_path.unlink(missing_ok=True)
                    # print(f"Deleted incomplete cache file: {tmp_path.name}")

                try:
                    await response.write_eof()
                except:
                    pass

                return response

    except Exception as e:
        return web.Response(status=500, text=f"Error: {str(e)}")

app = web.Application()
app.router.add_get("/"+APP_PATH, fetch_mp4)

if __name__ == "__main__":
    web.run_app(app, host=HOST, port=PORT)

