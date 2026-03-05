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

ALLOWED_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm"}
ALLOWED_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif", ".heic"}
ALLOWED_EXTS = ALLOWED_VIDEO_EXTS | ALLOWED_PHOTO_EXTS

PHOTO_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".heic": "image/heic",
}

app = FastAPI()

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def join_media(rel_path: str) -> Path:
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
        raise HTTPException(status_code=404, detail="Folder not found")

    items = []
    for p in sorted(folder.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        if p.is_dir():
            rel = str(p.relative_to(MEDIA_DIR))
            items.append({
                "type": "dir",
                "name": p.name,
                "browse_path": rel,
            })
        elif p.is_file():
            ext = p.suffix.lower()
            if ext in ALLOWED_VIDEO_EXTS:
                rel = str(p.relative_to(MEDIA_DIR))
                items.append({
                    "type": "video",
                    "name": p.name,
                    "rel": rel,
                    "watch_url": f"/watch/{quote(rel)}",
                })
            elif ext in ALLOWED_PHOTO_EXTS:
                rel = str(p.relative_to(MEDIA_DIR))
                items.append({
                    "type": "photo",
                    "name": p.name,
                    "rel": rel,
                    "watch_url": f"/photo/{quote(rel)}",
                    "thumb_url": f"/image/{quote(rel)}",
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


@app.get("/watch/{filename:path}", response_class=HTMLResponse)
async def watch_video(request: Request, filename: str):
    return templates.TemplateResponse(
        "index.html", {"request": request, "filename": filename}
    )


@app.get("/photo/{filename:path}", response_class=HTMLResponse)
async def view_photo(request: Request, filename: str):
    file_path = join_media(filename)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="no file")
    if file_path.suffix.lower() not in ALLOWED_PHOTO_EXTS:
        raise HTTPException(status_code=400, detail="extension not allowed")

    #prev/next navigation
    parent = file_path.parent
    siblings = sorted(
        [p for p in parent.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_PHOTO_EXTS],
        key=lambda x: x.name.lower(),
    )
    idx = next((i for i, p in enumerate(siblings) if p == file_path), None)
    prev_url = None
    next_url = None
    if idx is not None:
        if idx > 0:
            prev_rel = str(siblings[idx - 1].relative_to(MEDIA_DIR))
            prev_url = f"/photo/{quote(prev_rel)}"
        if idx < len(siblings) - 1:
            next_rel = str(siblings[idx + 1].relative_to(MEDIA_DIR))
            next_url = f"/photo/{quote(next_rel)}"

    folder_rel = "" if parent == MEDIA_DIR else str(parent.relative_to(MEDIA_DIR))

    return templates.TemplateResponse(
        "photo.html",
        {
            "request": request,
            "filename": filename,
            "image_url": f"/image/{quote(filename)}",
            "display_name": file_path.name,
            "prev_url": prev_url,
            "next_url": next_url,
            "back_url": f"/browse?path={quote(folder_rel)}",
        },
    )


@app.get("/image/{filename:path}")
async def serve_image(filename: str):
    file_path = join_media(filename)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    ext = file_path.suffix.lower()
    if ext not in ALLOWED_PHOTO_EXTS:
        raise HTTPException(status_code=400, detail="Not a supported photo format")
    mime = PHOTO_MIME_TYPES.get(ext, "application/octet-stream")
    return FileResponse(path=file_path, media_type=mime)


@app.get("/download/{filename:path}")
async def get_file(filename: str):
    file_path = join_media(filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path, media_type="video/mp4", filename=filename)


CHUNK_SIZE = 1024 * 1024  # 1 MB


@app.get("/stream/{filename:path}")
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