"""Fetches captions from YouTube using the video ID."""
import re


def extract_video_id(url: str) -> str | None:
    """Extracts the YouTube video ID from any YouTube URL format."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/live/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fetch_captions(url: str) -> dict | None:
    """
    Fetches captions from YouTube for the given URL.
    Returns dict with 'title', 'video_id', 'segments', or None if unavailable.
    """
    from youtube_transcript_api import (
        YouTubeTranscriptApi,
        NoTranscriptFound,
        TranscriptsDisabled,
    )
    import yt_dlp

    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError(f"Could not extract video ID from URL: {url}")

    # Get the video title
    title = video_id
    try:
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                title = info.get("title", video_id)
    except Exception:
        pass  # title fallback to video_id

    # Fetch captions
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Prefer manual English captions, fall back to auto-generated
        try:
            transcript = transcript_list.find_manually_created_transcript(
                ["en", "en-US", "en-GB"]
            )
        except Exception:
            try:
                transcript = transcript_list.find_generated_transcript(
                    ["en", "en-US", "en-GB"]
                )
            except Exception:
                # Try any language and translate
                available = list(transcript_list)
                if not available:
                    return None
                transcript = available[0].translate("en")

        entries = transcript.fetch()

        segments = []
        for entry in entries:
            start = entry.get("start", 0)
            duration = entry.get("duration", 2.0)
            text = entry.get("text", "").replace("\n", " ").strip()
            if text:
                segments.append({
                    "start": start,
                    "end": start + duration,
                    "text": text,
                })

        return {"title": title, "video_id": video_id, "segments": segments}

    except (NoTranscriptFound, TranscriptsDisabled):
        return None
