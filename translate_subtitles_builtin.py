"""Alternative build: AssemblyAI-STT-3.7 with AssemblyAI's built-in Translation.

One request transcribes the video and translates each speaker turn
(`match_original_utterance`). Each translated turn is split into cues, so
timing inside a long turn is approximate. For exact cue timing, use
translate_subtitles.py (the default build).

Usage:
    python translate_subtitles_builtin.py video.mp4 --languages es fr
"""
import argparse
import os
import time
from pathlib import Path

import requests

from subtitles import split_utterance, to_srt, to_vtt

BASE_URL = "https://api.assemblyai.com"
# AssemblyAI-STT-3.7 is on Translation's supported-models list:
# https://www.assemblyai.com/docs/speech-understanding/translation
# For audio outside its 32 languages, use ["assemblyai-stt-3-7", "universal-2"].
SPEECH_MODELS = ["assemblyai-stt-3-7"]


def headers():
    return {"authorization": os.environ["ASSEMBLYAI_API_KEY"]}


def upload(path: str) -> str:
    with open(path, "rb") as f:
        response = requests.post(f"{BASE_URL}/v2/upload", headers=headers(), data=f)
    response.raise_for_status()
    return response.json()["upload_url"]


def transcribe_and_translate(audio_url: str, languages: list) -> dict:
    data = {
        "audio_url": audio_url,
        "speech_models": SPEECH_MODELS,
        "language_detection": True,
        "speaker_labels": True,
        "speech_understanding": {
            "request": {
                "translation": {
                    "target_languages": languages,
                    "match_original_utterance": True,
                }
            }
        },
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


def translated_cues(transcript: dict, language: str) -> list:
    cues = []
    for utterance in transcript["utterances"]:
        text = utterance.get("translated_texts", {}).get(language)
        if text:
            cues.extend(split_utterance(text, utterance["start"], utterance["end"]))
    return cues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("media", help="local file path or public URL")
    parser.add_argument("--languages", nargs="+", default=["es", "fr"])
    parser.add_argument("--out", default="subtitles")
    args = parser.parse_args()

    audio_url = args.media if args.media.startswith("http") else upload(args.media)
    transcript = transcribe_and_translate(audio_url, args.languages)

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    stem = Path(args.media).stem
    source = transcript.get("language_code") or "src"

    (out / f"{stem}.{source}.srt").write_text(export_source(transcript["id"], "srt"))
    (out / f"{stem}.{source}.vtt").write_text(export_source(transcript["id"], "vtt"))

    for language in args.languages:
        cues = translated_cues(transcript, language)
        (out / f"{stem}.{language}.srt").write_text(to_srt(cues))
        (out / f"{stem}.{language}.vtt").write_text(to_vtt(cues))
        print(f"{language}: {len(cues)} cues")


if __name__ == "__main__":
    main()
