import os
import uuid
import json
import time
import threading
import re
import shutil
from pathlib import Path
from flask import Flask, request, jsonify, send_file, Response, render_template, stream_with_context
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

# ── Configuration ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# In-memory job store  { job_id: { status, progress, speed, eta, filename, error, title, url } }
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()

# ── Helpers ────────────────────────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    """Remove characters that are unsafe in filenames."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)[:200]


def is_twitter_url(url: str) -> bool:
    """Check if URL is a Twitter/X post."""
    return bool(re.search(r'(twitter\.com|x\.com)/\w+/status/', url))


def get_twitter_alternatives(url: str) -> list:
    """Generate alternative frontend URLs for Twitter/X videos.
    
    These frontends (fxtwitter, vxtwitter) act as proxies that
    expose the video without requiring authentication.
    """
    alternatives = []
    # Replace domain with alternative frontends
    for alt_domain in ['fxtwitter.com', 'vxtwitter.com']:
        alt = re.sub(r'(twitter\.com|x\.com)', alt_domain, url)
        alternatives.append(alt)
    return alternatives


class CancelledError(Exception):
    """Custom exception to abort downloads."""
    pass


def make_progress_hook(job_id: str):
    def hook(d):
        with jobs_lock:
            job = jobs.get(job_id)
            if job is None:
                raise CancelledError("Job deleted")
            if job.get("status") == "cancelled":
                raise CancelledError("User cancelled download")

            if d["status"] == "downloading":
                job["status"] = "downloading"
                job["progress"] = d.get("_percent_str", "0%").strip()
                job["speed"]    = d.get("_speed_str", "").strip()
                job["eta"]      = d.get("_eta_str", "").strip()
                raw = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
                job["percent"]  = round((raw / total) * 100, 1)
            elif d["status"] == "finished":
                job["status"]   = "merging"
                job["percent"]  = 99
                job["filename"] = d.get("filename", "")
    return hook


def run_download(job_id: str, url: str, ydl_opts: dict, cookie_file: str = None):
    """Execute yt-dlp download in a background thread."""
    try:
        download_success = False
        download_url = url

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            download_success = True
        except (yt_dlp.utils.DownloadError, Exception) as primary_err:
            # For Twitter/X URLs, try alternative frontends before giving up
            if is_twitter_url(url):
                for alt_url in get_twitter_alternatives(url):
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([alt_url])
                        download_success = True
                        download_url = alt_url
                        break
                    except Exception:
                        continue
                if not download_success:
                    raise primary_err
            else:
                raise primary_err
        
        # Check one last time if we were cancelled during finishing steps
        with jobs_lock:
            if jobs.get(job_id, {}).get("status") == "cancelled":
                raise CancelledError("User cancelled download")

        # Find the actual output file
        job_dir = DOWNLOAD_DIR / job_id
        files = list(job_dir.iterdir()) if job_dir.exists() else []
        # Exclude the temporary cookie file if it exists
        files = [f for f in files if f.name != "cookies.txt"]
        if files:
            final = max(files, key=lambda f: f.stat().st_size)
            with jobs_lock:
                jobs[job_id]["filename"]  = str(final)
                jobs[job_id]["basename"]  = final.name
                jobs[job_id]["status"]    = "done"
                jobs[job_id]["percent"]   = 100
        else:
            with jobs_lock:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"]  = "No output file found after download."
    except (yt_dlp.utils.DownloadError, CancelledError) as e:
        with jobs_lock:
            # If it was cancelled, preserve the 'cancelled' status
            if jobs.get(job_id, {}).get("status") == "cancelled":
                pass
            else:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"]  = str(e)
        # Clean up any partial downloads in the job directory
        job_dir = DOWNLOAD_DIR / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
    except Exception as e:
        with jobs_lock:
            if jobs.get(job_id, {}).get("status") == "cancelled":
                pass
            else:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"]  = f"Unexpected error: {e}"
        # Clean up
        job_dir = DOWNLOAD_DIR / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
    finally:
        # Clean up temporary cookie file if it was created for this thread
        if cookie_file and os.path.exists(cookie_file):
            try:
                os.unlink(cookie_file)
            except Exception:
                pass




# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/info", methods=["POST"])
def api_info():
    """Fetch video metadata (title, thumbnail, formats) without downloading."""
    data = request.get_json(force=True)
    url  = (data.get("url") or "").strip()
    cookies_text = (data.get("cookies") or "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "nocheckcertificate": True,  # Fixes local SSL certificate verify failed issues
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "http_headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        },
        "extractor_args": {
            "youtube": {
                # Use tv and creator clients which bypass IP-cookie matching bans
                "player_client": ["tv", "web_creator", "android", "ios", "web"],
                "skip": ["webpage"]
            }
        }
    }

    cookie_file_path = None
    if cookies_text:
        # Generate a temporary cookies file
        temp_id = str(uuid.uuid4())
        cookie_file_path = DOWNLOAD_DIR / f"cookies_{temp_id}.txt"
        with open(cookie_file_path, "w", encoding="utf-8") as f:
            f.write(cookies_text)
        ydl_opts["cookiefile"] = str(cookie_file_path)
    else:
        # If running locally (on localhost/127.0.0.1) and no manual cookies are provided,
        # automatically grab cookies from the user's browser to make it seamless!
        is_local = any(h in request.host for h in ["localhost", "127.0.0.1", "10.11.116"])
        if is_local:
            # We try Chrome first, fallback to Edge/Firefox
            ydl_opts["cookiesfrombrowser"] = ("chrome", "edge", "firefox", "safari")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        # Check if Twitter returned empty formats ("no video found")
        if is_twitter_url(url) and not info.get("formats"):
            raise yt_dlp.utils.DownloadError("No video found in tweet, trying alternatives...")
    except (yt_dlp.utils.DownloadError, Exception) as primary_err:
        # For Twitter/X URLs, try alternative frontends before giving up
        if is_twitter_url(url):
            for alt_url in get_twitter_alternatives(url):
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(alt_url, download=False)
                    if info and info.get("formats"):
                        # Success! Override the URL to the working alternative
                        info["original_url"] = url
                        info["webpage_url"] = url  # Keep original for display
                        break
                except Exception:
                    continue
            else:
                # All alternatives failed too
                err_msg = str(primary_err)
                if "no video" in err_msg.lower() or isinstance(primary_err, yt_dlp.utils.DownloadError):
                    return jsonify({"error": f"Could not extract video from this tweet. Twitter may require login cookies — paste them in ⚙️ Settings. Original error: {err_msg}"}), 422
                return jsonify({"error": f"Failed to fetch info: {err_msg}"}), 500
        else:
            if isinstance(primary_err, yt_dlp.utils.DownloadError):
                return jsonify({"error": str(primary_err)}), 422
            return jsonify({"error": f"Failed to fetch info: {primary_err}"}), 500
    finally:
        # Clean up info temp cookie file immediately
        if cookie_file_path and cookie_file_path.exists():
            try:
                cookie_file_path.unlink()
            except Exception:
                pass

    # Build format list (deduplicated, human-readable)
    formats_raw = info.get("formats") or []
    seen = set()
    formats = []

    # Best combined option always first
    formats.append({"id": "best", "label": "⭐ Best Quality (auto)", "ext": "mp4"})
    formats.append({"id": "bestvideo+bestaudio/best", "label": "🎬 Best Video + Best Audio", "ext": "mp4"})

    for f in reversed(formats_raw):  # highest quality last → reversed = best first
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        height  = f.get("height")
        fps     = f.get("fps")
        ext     = f.get("ext", "?")
        fid     = f.get("format_id", "")
        tbr     = f.get("tbr")

        if vcodec == "none" and acodec == "none":
            continue

        if vcodec != "none" and height:
            key = (height, ext)
            if key in seen:
                continue
            seen.add(key)
            fps_str = f" {int(fps)}fps" if fps and fps > 30 else ""
            tbr_str = f" ~{int(tbr)}k" if tbr else ""
            formats.append({
                "id":    fid,
                "label": f"🎥 {height}p{fps_str} ({ext}){tbr_str}",
                "ext":   ext,
            })
        elif vcodec == "none" and acodec != "none":
            key = ("audio", ext)
            if key in seen:
                continue
            seen.add(key)
            abr = f.get("abr")
            abr_str = f" {int(abr)}kbps" if abr else ""
            formats.append({
                "id":    fid,
                "label": f"🎵 Audio only ({ext}){abr_str}",
                "ext":   ext,
            })

    # Also add common audio-only presets
    formats.append({"id": "bestaudio[ext=m4a]/bestaudio", "label": "🎵 Best Audio (m4a)", "ext": "m4a"})
    formats.append({"id": "bestaudio", "label": "🎵 Best Audio (any)", "ext": "webm"})

    return jsonify({
        "title":      info.get("title", "Unknown"),
        "channel":    info.get("uploader") or info.get("channel", ""),
        "duration":   info.get("duration"),
        "thumbnail":  info.get("thumbnail"),
        "webpage_url": info.get("webpage_url", url),
        "extractor":  info.get("extractor_key", ""),
        "formats":    formats,
    })


@app.route("/api/download", methods=["POST"])
def api_download():
    """Start a download job and return a job_id."""
    data      = request.get_json(force=True)
    url       = (data.get("url") or "").strip()
    format_id = (data.get("format_id") or "best").strip()
    cookies_text = (data.get("cookies") or "").strip()

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    job_id  = str(uuid.uuid4())
    job_dir = DOWNLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Build yt-dlp options
    ydl_opts: dict = {
        "format":           format_id,
        "outtmpl":          str(job_dir / "%(title)s.%(ext)s"),
        "quiet":            True,
        "no_warnings":      True,
        "noplaylist":       True,
        "nocheckcertificate": True,  # Fixes local SSL certificate verify failed issues
        "merge_output_format": "mp4",
        "progress_hooks":   [make_progress_hook(job_id)],
        "postprocessors": [
            {
                "key":            "FFmpegMetadata",
                "add_metadata":   True,
            }
        ],
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "http_headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        },
        "extractor_args": {
            "youtube": {
                # Use tv and creator clients which bypass IP-cookie matching bans
                "player_client": ["tv", "web_creator", "android", "ios", "web"],
                "skip": ["webpage"]
            }
        },
        # Retries / resilience
        "retries":          5,
        "fragment_retries": 10,
        "ignoreerrors":     False,
    }

    # Write cookies to job directory if provided
    cookie_file_path = None
    if cookies_text:
        cookie_file_path = job_dir / "cookies.txt"
        with open(cookie_file_path, "w", encoding="utf-8") as f:
            f.write(cookies_text)
        ydl_opts["cookiefile"] = str(cookie_file_path)
    else:
        # If running locally and no manual cookies provided, auto-grab from browser
        is_local = any(h in request.host for h in ["localhost", "127.0.0.1", "10.11.116"])
        if is_local:
            ydl_opts["cookiesfrombrowser"] = ("chrome", "edge", "firefox", "safari")

    # Audio-only: convert to mp3
    if "bestaudio" in format_id and "video" not in format_id:
        ydl_opts["postprocessors"].insert(0, {
            "key":            "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        })
        ydl_opts["outtmpl"] = str(job_dir / "%(title)s.%(ext)s")

    with jobs_lock:
        jobs[job_id] = {
            "status":   "queued",
            "percent":  0,
            "progress": "0%",
            "speed":    "",
            "eta":      "",
            "filename": "",
            "basename": "",
            "error":    "",
            "url":      url,
        }

    thread = threading.Thread(
        target=run_download, 
        args=(job_id, url, ydl_opts, str(cookie_file_path) if cookie_file_path else None), 
        daemon=True
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/progress/<job_id>")
def api_progress(job_id: str):
    """Server-Sent Events stream for real-time progress updates."""
    def generate():
        while True:
            with jobs_lock:
                job = jobs.get(job_id)
            if job is None:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break
            payload = json.dumps({
                "status":   job["status"],
                "percent":  job["percent"],
                "progress": job["progress"],
                "speed":    job["speed"],
                "eta":      job["eta"],
                "basename": job["basename"],
                "error":    job["error"],
            })
            yield f"data: {payload}\n\n"
            if job["status"] in ("done", "error"):
                break
            time.sleep(0.5)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/file/<job_id>")
def api_file(job_id: str):
    """Serve the downloaded file for browser download and clean it up immediately after."""
    with jobs_lock:
        job = jobs.get(job_id)

    if not job or job["status"] != "done":
        return jsonify({"error": "File not ready or job not found"}), 404

    filepath = Path(job["filename"])
    if not filepath.exists():
        return jsonify({"error": "File missing on disk"}), 404

    # We read the file, and delete it once the transfer finishes
    def stream_and_remove():
        try:
            with open(filepath, "rb") as f:
                yield from f
        finally:
            # Clean up the file and its job directory after streaming is complete
            try:
                if filepath.exists():
                    filepath.unlink()
                job_dir = filepath.parent
                if job_dir.exists() and job_dir != DOWNLOAD_DIR:
                    shutil.rmtree(job_dir, ignore_errors=True)
            except Exception as e:
                app.logger.error(f"Error cleaning up file: {e}")

    # Remove the job from the active jobs list so it doesn't show up as downloadable anymore
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = "cleaned"

    return Response(
        stream_and_remove(),
        headers={
            "Content-Disposition": f'attachment; filename="{filepath.name}"',
            "Content-Type": "application/octet-stream"
        }
    )



@app.route("/api/history")
def api_history():
    """Return list of completed/errored jobs."""
    with jobs_lock:
        result = [
            {
                "job_id":   jid,
                "status":   j["status"],
                "basename": j["basename"],
                "url":      j["url"],
                "error":    j["error"],
            }
            for jid, j in jobs.items()
        ]
    return jsonify(result[::-1])  # newest first


@app.route("/api/cancel/<job_id>", methods=["POST"])
def api_cancel(job_id: str):
    """Mark a job as cancelled to stop the active thread."""
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            job["status"] = "cancelled"
            job["percent"] = 0
            job["progress"] = "Cancelled"
    return jsonify({"ok": True})


@app.route("/api/delete/<job_id>", methods=["DELETE"])
def api_delete(job_id: str):
    """Delete a job and its downloaded files."""
    with jobs_lock:
        jobs.pop(job_id, None)
    job_dir = DOWNLOAD_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    return jsonify({"ok": True})


if __name__ == "__main__":
    import webbrowser
    # Ensure we always run from the directory containing app.py
    os.chdir(BASE_DIR)
    PORT = 7878
    print("\n" + "="*55)
    print("  VDownloader  --  Local Video Downloader")
    print(f"  Running at:  http://localhost:{PORT}")
    print("="*55 + "\n")
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)

