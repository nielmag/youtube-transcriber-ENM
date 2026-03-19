"""
AssemblyAI transcription for YouTube URLs.
Downloads audio-only (much smaller than video), uploads to AssemblyAI, returns segments.
"""
import os
import tempfile
import time

import requests


def transcribe_url_with_assemblyai(youtube_url: str, api_key: str,
                                    status_callback=None) -> dict | None:
    """
    Downloads audio from a YouTube URL and transcribes with AssemblyAI.
    Returns dict with 'segments' list, or None on failure.
    """
    import yt_dlp

    def log(msg):
        if status_callback:
            status_callback(msg)

    base_url = "https://api.assemblyai.com/v2"
    headers = {"authorization": api_key}

    # Download audio-only to a temp file
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")

        log("Downloading audio from YouTube...")

        # Copy cookies to writable temp location (/etc/secrets is read-only)
        cookies_src = "/etc/secrets/youtube_cookies.txt"
        cookies_path = None
        if os.path.exists(cookies_src):
            import shutil
            cookies_path = os.path.join(tmpdir, "youtube_cookies.txt")
            shutil.copy2(cookies_src, cookies_path)

        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": audio_path,
            "quiet": False,  # show errors in logs
            "no_warnings": False,
            "cookiefile": cookies_path,
            # No ffmpeg postprocessor — upload m4a directly to AssemblyAI
        }

        # yt-dlp may append .mp3 extension
        actual_path = audio_path
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])

        # Find the downloaded file
        for fname in os.listdir(tmpdir):
            if fname != "youtube_cookies.txt" and not fname.startswith("."):
                candidate = os.path.join(tmpdir, fname)
                if os.path.isfile(candidate):
                    actual_path = candidate
                    break

        if not os.path.exists(actual_path):
            log("Audio download failed.")
            return None

        size_mb = os.path.getsize(actual_path) / 1024 / 1024
        log(f"Audio downloaded ({size_mb:.1f} MB). Uploading to AssemblyAI...")

        # Upload audio
        with open(actual_path, "rb") as f:
            upload_resp = requests.post(
                f"{base_url}/upload",
                headers=headers,
                data=f,
                timeout=300,
            )
        upload_resp.raise_for_status()
        audio_url = upload_resp.json()["upload_url"]

    # Submit transcription job
    log("Transcribing audio (1-5 minutes)...")
    resp = requests.post(
        f"{base_url}/transcript",
        headers=headers,
        json={"audio_url": audio_url},
        timeout=30,
    )
    resp.raise_for_status()
    transcript_id = resp.json()["id"]

    # Poll until complete
    polling_url = f"{base_url}/transcript/{transcript_id}"
    while True:
        poll = requests.get(polling_url, headers=headers, timeout=30)
        poll.raise_for_status()
        result = poll.json()

        if result["status"] == "completed":
            break
        elif result["status"] == "error":
            raise RuntimeError(f"AssemblyAI error: {result.get('error')}")

        time.sleep(5)

    # Convert to our segment format
    words = result.get("words") or []
    segments = []

    if words:
        SEGMENT_MS = 5000
        current_words = []
        current_start = None

        for i, word in enumerate(words):
            if current_start is None:
                current_start = word["start"]
            current_words.append(word["text"])

            duration = word["end"] - current_start
            is_last = (i == len(words) - 1)
            next_gap = (words[i + 1]["start"] - word["end"]) if not is_last else 0

            if duration >= SEGMENT_MS or next_gap > 1000 or is_last:
                segments.append({
                    "start": current_start / 1000.0,
                    "end": word["end"] / 1000.0,
                    "text": " ".join(current_words),
                })
                current_words = []
                current_start = None
    else:
        segments = [{"start": 0.0, "end": 0.0, "text": result.get("text", "")}]

    log(f"Transcription complete — {len(segments)} segments.")
    return {"segments": segments, "text": result.get("text", "")}
