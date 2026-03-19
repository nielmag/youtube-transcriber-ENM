"""
YouTube Transcriber Web App

Paste a YouTube URL → fetches captions → Claude cleans & organizes →
download a Word document with exec summary + full transcript.
"""
import io
import logging
import os
import threading

import anthropic
from flask import Flask, jsonify, render_template, request, send_file

import jobs
from claude_process import clean_transcript, create_executive_summary
from transcribe import fetch_captions
from word_export import export_to_word

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

logger.info(f"ANTHROPIC_API_KEY loaded: {'YES' if ANTHROPIC_API_KEY else 'NO'}")
logger.info(f"ASSEMBLYAI_API_KEY loaded: {'YES' if ASSEMBLYAI_API_KEY else 'NO'}")


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(job_id: str, url: str):
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        jobs.update(job_id, status="fetching", progress=10,
                    message="Fetching YouTube captions...")
        result = fetch_captions(url)

        if result is None:
            # No captions — fall back to AssemblyAI
            if not ASSEMBLYAI_API_KEY:
                jobs.update(job_id, status="error",
                            error="No captions found and ASSEMBLYAI_API_KEY is not configured.")
                return

            jobs.update(job_id, status="fetching", progress=20,
                        message="No captions found — transcribing audio with AssemblyAI...")

            from assemblyai_transcribe import transcribe_url_with_assemblyai

            def aai_status(msg):
                jobs.update(job_id, message=msg)

            aai_result = transcribe_url_with_assemblyai(url, ASSEMBLYAI_API_KEY, aai_status)
            if not aai_result:
                jobs.update(job_id, status="error",
                            error="Transcription failed. The video may be private or unavailable.")
                return

            # Get title via YouTube oEmbed API (no auth needed)
            from transcribe import extract_video_id
            video_id = extract_video_id(url) or url
            title = video_id
            try:
                oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
                r = requests.get(oembed_url, timeout=10)
                if r.ok:
                    title = r.json().get("title", video_id)
            except Exception:
                pass

            result = {"title": title, "video_id": video_id, "segments": aai_result["segments"]}

        jobs.update(job_id, title=result["title"])

        jobs.update(job_id, status="cleaning", progress=40,
                    message="Cleaning and organizing transcript with Claude...")
        clean_text = clean_transcript(result["segments"], client, CLAUDE_MODEL)

        jobs.update(job_id, status="summarizing", progress=70,
                    message="Creating executive summary...")
        summary_text = create_executive_summary(result["segments"], client, CLAUDE_MODEL)

        jobs.update(job_id, status="exporting", progress=90,
                    message="Generating Word document...")
        docx_bytes = export_to_word(result["title"], clean_text, summary_text)

        jobs.update(job_id, status="done", progress=100,
                    message="Done!", docx_bytes=docx_bytes)

    except Exception as e:
        jobs.update(job_id, status="error", error=str(e))


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "api_key_configured": bool(ANTHROPIC_API_KEY),
    })


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/transcribe", methods=["POST"])
def transcribe():
    try:
        data = request.get_json()
        url = (data or {}).get("url", "").strip()
        if not url:
            return jsonify({"error": "URL is required"}), 400
        if not ANTHROPIC_API_KEY:
            return jsonify({"error": "ANTHROPIC_API_KEY not configured"}), 500

        job_id = jobs.create(url)
        threading.Thread(target=run_pipeline, args=(job_id, url), daemon=True).start()
        return jsonify({"job_id": job_id})
    except Exception as e:
        logger.exception("Error in /transcribe route")
        return jsonify({"error": str(e)}), 500


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get_safe(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/download/<job_id>")
def download(job_id):
    job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        return "Not ready", 404

    docx_bytes = job.get("docx_bytes")
    if not docx_bytes:
        return "File not available", 404

    title = job.get("title", "transcript")
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:80].strip()

    return send_file(
        io.BytesIO(docx_bytes),
        as_attachment=True,
        download_name=f"{safe_title}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, host="0.0.0.0", port=5000)
