import os
import re
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", "/mnt/nas/media")).resolve()

app = FastAPI()

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/watch/{filename}", response_class=HTMLResponse)
async def watch_video(request: Request, filename: str):
    return templates.TemplateResponse(
        "index.html", {"request": request, "filename": filename}
    )


@app.get("/download/{filename}")
async def get_file(filename: str):
    file_path = os.path.join(MEDIA_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path,
                        media_type="video/mp4",
                        filename=filename)


CHUNK_SIZE = 1024 * 1024  # 1 MB

@app.get("/stream/{filename}")
async def stream_video(request: Request, filename: str):
    file_path = os.path.join(NAS_DIR, filename)

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
