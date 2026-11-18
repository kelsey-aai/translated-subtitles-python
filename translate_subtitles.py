"""Default build: transcribe with AssemblyAI-STT-3.7, export the source SRT,
and translate the cue text through LLM Gateway. Timestamps are copied from
the source file unchanged, so every translated cue keeps exact timing.

Usage:
    python translate_subtitles.py video.mp4 --languages es fr
"""
import argparse
import json
import os
import time
from pathlib import Path

import requests

from subtitles import Cue, parse_srt, to_srt, to_vtt

BASE_URL = "https://api.assemblyai.com"
GATEWAY_URL = "https://llm-gateway.assemblyai.com/v1/chat/completions"
SPEECH_MODELS = ["assemblyai-stt-3-7"]
LLM_MODEL = "claude-haiku-4-5-20251001"  # any LLM Gateway model works
BATCH_SIZE = 40


def headers():
    return {"authorization": os.environ["ASSEMBLYAI_API_KEY"]}


def upload(path: str) -> str:
    with open(path, "rb") as f:
        response = requests.post(f"{BASE_URL}/v2/upload", headers=headers(), data=f)
    response.raise_for_status()
    return response.json()["upload_url"]


def transcribe(audio_url: str) -> dict:
    data = {
        "audio_url": audio_url,
        "speech_models": SPEECH_MODELS,
        "language_detection": True,
    }
    response = requests.post(f"{BASE_URL}/v2/transcript", headers=headers(), json=data)
    response.raise_for_status()
    transcript_id = response.json()["id"]

    while True:
        transcript = requests.get(
            f"{BASE_URL}/v2/transcript/{transcript_id}", headers=headers()
        ).json()
        if transcript["status"] == "completed":
            return transcript
        if transcript["status"] == "error":
            raise RuntimeError(f"Transcription failed: {transcript['error']}")
        time.sleep(3)


def export_source(transcript_id: str, fmt: str, chars_per_caption: int = 42) -> str:
    response = requests.get(
        f"{BASE_URL}/v2/transcript/{transcript_id}/{fmt}",
        headers=headers(),
        params={"chars_per_caption": chars_per_caption},
    )
    response.raise_for_status()
    return response.text


def translate_batch(texts: list, language: str) -> list:
    prompt = (
        f"Translate each subtitle line into the language with ISO code '{language}'. "
        "Return only a JSON array of strings, same length and order as the input. "
        "Keep line breaks inside an item.\n\n" + json.dumps(texts, ensure_ascii=False)
    )
    response = requests.post(
        GATEWAY_URL,
        headers=headers(),
        json={
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4000,
        },
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    translated = json.loads(content[content.find("[") : content.rfind("]") + 1])
    if len(translated) != len(texts):
        raise ValueError("LLM returned a different number of cues; retry this batch")
    return translated


def translate_cues(cues: list, language: str) -> list:
    out = []
    for i in range(0, len(cues), BATCH_SIZE):
        batch = cues[i : i + BATCH_SIZE]
        texts = translate_batch([cue.text for cue in batch], language)
        out.extend(Cue(cue.start, cue.end, text) for cue, text in zip(batch, texts))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("media", help="local file path or public URL")
    parser.add_argument("--languages", nargs="+", default=["es", "fr"])
    parser.add_argument("--out", default="subtitles")
    args = parser.parse_args()

    audio_url = args.media if args.media.startswith("http") else upload(args.media)
    transcript = transcribe(audio_url)

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    stem = Path(args.media).stem
    source = transcript.get("language_code") or "src"

    srt = export_source(transcript["id"], "srt")
    (out / f"{stem}.{source}.srt").write_text(srt)
    (out / f"{stem}.{source}.vtt").write_text(export_source(transcript["id"], "vtt"))

    cues = parse_srt(srt)
    for language in args.languages:
        translated = translate_cues(cues, language)
        (out / f"{stem}.{language}.srt").write_text(to_srt(translated))
        (out / f"{stem}.{language}.vtt").write_text(to_vtt(translated))
        print(f"{language}: {len(translated)} cues, timings copied from the source SRT")


if __name__ == "__main__":
    main()
