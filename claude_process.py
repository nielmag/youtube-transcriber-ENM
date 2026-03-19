"""Cleans transcripts and creates executive summaries using Claude."""


def format_timestamped(segments: list) -> str:
    lines = []
    for seg in segments:
        minutes = int(seg["start"]) // 60
        seconds = int(seg["start"]) % 60
        lines.append(f"[{minutes:02d}:{seconds:02d}] {seg['text']}")
    return "\n".join(lines)


def clean_transcript(segments: list, client, model: str) -> str:
    """Returns clean transcript text with ## section headers and paragraphs."""
    timestamped = format_timestamped(segments)

    message = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": f"""You are a professional transcript editor. Below is a raw video transcript with timestamps.

Your task:
1. Remove all timestamps
2. Fix obvious transcription errors and remove filler words (um, uh, you know, like)
3. Organize into logical paragraphs — each paragraph should cover one coherent thought
4. Add clear section headers using ## Markdown format wherever the topic meaningfully changes
5. Preserve ALL substantive content — do not summarize or omit information

Return ONLY the clean transcript text. No preamble, no commentary, no markdown code fences.

RAW TRANSCRIPT:
{timestamped}"""}],
    )
    return message.content[0].text


def create_executive_summary(segments: list, client, model: str) -> str:
    """Returns an executive summary with timestamps."""
    timestamped = format_timestamped(segments)

    message = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": f"""You are summarizing a video transcript. Below is a timestamped transcript.

Write an executive summary that:
1. Opens with 2-3 sentences describing what the video covers (no timestamp)
2. Lists key topics with timestamps in the format: [MM:SS] Topic name
3. Ends with 2-4 bullet point key takeaways (no timestamps)

Requirements:
- Keep total length under 4500 characters
- Use plain text only
- Timestamps should reference when each topic actually starts

Return ONLY the summary text. No preamble, no commentary.

TRANSCRIPT:
{timestamped}"""}],
    )
    return message.content[0].text
