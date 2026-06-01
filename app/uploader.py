import os
import shutil
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse

from app.status import read_status_files


INCOMING_DIR = Path(os.getenv("INCOMING_DIR", "/data/incoming"))
READY_DIR = Path(os.getenv("READY_DIR", "/data/ready"))
PROCESSING_DIR = Path(os.getenv("PROCESSING_DIR", "/data/processing"))
FAILED_DIR = Path(os.getenv("FAILED_DIR", "/data/failed"))
STATUS_DIR = Path(os.getenv("STATUS_DIR", "/data/logs/status"))

app = FastAPI(title="AI Subtitle Uploader")


HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AI Subtitle Pipeline</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="15">

    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            background: #0f172a;
            color: #e5e7eb;
            padding: 24px;
        }}

        .box {{
            max-width: 620px;
            margin: auto;
            background: #111827;
            padding: 24px;
            border-radius: 18px;
        }}

        input, button {{
            width: 100%;
            padding: 14px;
            margin-top: 14px;
            border-radius: 12px;
            border: none;
            font-size: 16px;
            box-sizing: border-box;
        }}

        button {{
            background: #22c55e;
            color: #052e16;
            font-weight: bold;
        }}

        .delete {{
            background: #ef4444;
            color: white;
        }}

        a {{
            color: #38bdf8;
        }}

        .file {{
            display: flex;
            gap: 10px;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #334155;
            word-break: break-all;
        }}

        .file input {{
            width: auto;
            margin: 0;
        }}

        .status {{
            background: #020617;
            border: 1px solid #334155;
            border-radius: 14px;
            padding: 12px;
            margin: 10px 0;
        }}

        .status-top {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            font-weight: bold;
        }}

        .bar {{
            height: 10px;
            background: #1e293b;
            border-radius: 999px;
            overflow: hidden;
            margin-top: 8px;
        }}

        .bar-inner {{
            height: 100%;
            background: #22c55e;
        }}

        .muted {{
            color: #94a3b8;
            font-size: 14px;
            margin-top: 8px;
        }}
    </style>
</head>

<body>
    <div class="box">
        <h1>AI Subtitle Pipeline</h1>
        <p>Upload video. Server will create Ukrainian and English SRT files.</p>

        <form action="/upload" method="post" enctype="multipart/form-data">
            <input id="video-file" type="file" name="file" accept="video/*" required>
            <div id="file-name" class="muted">No file selected</div>
            <button type="submit">Upload video</button>
        </form>

        <h2>Processing status</h2>
        <div class="status-list">
            {statuses}
        </div>

        <h2>Ready files</h2>
        <form action="/delete" method="post">
            {files}
            {delete_button}
        </form>

        <p class="muted">Tip: download subtitles before deleting old files.</p>
    </div>

    <script>
        const fileInput = document.getElementById("video-file");
        const fileName = document.getElementById("file-name");

        fileInput.addEventListener("change", function () {{
            if (fileInput.files.length > 0) {{
                fileName.textContent = "Selected: " + fileInput.files[0].name;
            }} else {{
                fileName.textContent = "No file selected";
            }}
        }});
    </script>
</body>
</html>
"""


def list_ready_files():
    READY_DIR.mkdir(parents=True, exist_ok=True)

    return sorted(
        [p for p in READY_DIR.glob("*") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def render_statuses():
    statuses = read_status_files(STATUS_DIR)

    if not statuses:
        return "<p>No active jobs yet.</p>"

    html = ""

    for item in statuses[:20]:
        file = item.get("file", "unknown")
        status = item.get("status", "unknown")
        progress = int(item.get("progress", 0))
        message = item.get("message", "")
        updated_at = item.get("updated_at", "")

        html += f"""
        <div class="status">
            <div class="status-top">
                <span>{file}</span>
                <span>{status} — {progress}%</span>
            </div>
            <div class="bar">
                <div class="bar-inner" style="width: {progress}%"></div>
            </div>
            <div class="muted">{message}</div>
            <div class="muted">{updated_at}</div>
        </div>
        """

    return html


@app.get("/", response_class=HTMLResponse)
def index():
    ready_files = list_ready_files()

    if not ready_files:
        files_html = "<p>No ready files yet.</p>"
        delete_button = ""
    else:
        files_html = ""

        for file in ready_files[:50]:
            files_html += f"""
            <div class="file">
                <input type="checkbox" name="files" value="{file.name}">
                <a href="/download/{file.name}">{file.name}</a>
            </div>
            """

        delete_button = '<button class="delete" type="submit">Delete selected files</button>'

    return HTML.format(
        statuses=render_statuses(),
        files=files_html,
        delete_button=delete_button,
    )


@app.post("/upload")
def upload(file: UploadFile = File(...)):
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename).name
    target = INCOMING_DIR / safe_name

    with target.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return RedirectResponse("/", status_code=303)


@app.post("/delete")
def delete(files: list[str] = Form(default=[])):
    for filename in files:
        safe_name = Path(filename).name
        path = READY_DIR / safe_name

        if path.exists() and path.is_file():
            path.unlink()

        stem = safe_name
        for suffix in [".uk.srt", ".en.srt", ".done"]:
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]

        status_path = STATUS_DIR / f"{stem}.status.json"
        if status_path.exists() and status_path.is_file():
            status_path.unlink()

    return RedirectResponse("/", status_code=303)


@app.get("/download/{filename}")
def download(filename: str):
    safe_name = Path(filename).name
    path = READY_DIR / safe_name

    if not path.exists():
        return HTMLResponse("File not found", status_code=404)

    return FileResponse(path, filename=safe_name)