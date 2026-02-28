import os
import re
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", "/mnt/nas/media")).resolve()

ALLOWED_EXTS = {".mp4", ".mkv", ".mov", ".webm"}

app = FastAPI()

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

def join_media(rel_path: str) -> str:
    rel_path = rel_path.strip().lstrip("/")

    final_path = (MEDIA_DIR / rel_path).resolve()
    media_root = MEDIA_DIR.resolve()

    if final_path == media_root or media_root in final_path.parents:
        return final_path

    raise HTTPException(status_code=400, detail="Invalid path")


@app.get("/", response_class=HTMLResponse)
async def browse_root(request: Request):
    return await browse(request, path="")

@app.get("/browse", response_class=HTMLResponse)
async def browse(request: Request, path: str = ""):
    folder = join_media(path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="folder not found")
    items = []
    for p in sorted(folder.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        if p.is_dir():
            rel = str(p.relative_to(MEDIA_DIR))
            items.append({
                "type": "dir",
                "name": p.name,
                "browse_path": rel,
            })
        elif p.is_file() and p.suffix.lower() in ALLOWED_EXTS:
            rel = str(p.relative_to(MEDIA_DIR))
            items.append({
                "type": "file",
                "name": p.name,
                "rel": rel,
                # URL-safe path for linking
                "watch_url": f"/watch/{quote(rel)}",
            })

            parent_path = ""
            if folder != MEDIA_DIR:
                parent = folder.parent
                parent_path = "" if parent == MEDIA_DIR else str(parent.relative_to(MEDIA_DIR))

            return templates.TemplateResponse(
                "browse.html",
                {
                    "request": request,
                    "path": path,
                    "parent_path": parent_path,
                    "items": items,
                    "quote": quote,
                },
            )


@app.get("/watch/{filename}", response_class=HTMLResponse)
async def watch_video(request: Request, filename: str):
    return templates.TemplateResponse(
        "index.html", {"request": request, "filename": filename}
    )


@app.get("/download/{filename}")
async def get_file(filename: str):
    file_path = join_media(filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path,
                        media_type="video/mp4",
                        filename=filename)


CHUNK_SIZE = 1024 * 1024  # 1 MB

@app.get("/stream/{filename}")
async def stream_video(request: Request, filename: str):
    file_path = join_media(filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")

    start = 0
    end = file_size - 1

    if range_header:
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if match:
            start = int(match.group(1))
            if match.group(2):
                end = int(match.group(2))

    def file_iterator():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Content-Type": "video/mp4",
    }

    return StreamingResponse(
        file_iterator(),
        status_code=206,
        headers=headers,
        media_type="video/mp4",
    )
