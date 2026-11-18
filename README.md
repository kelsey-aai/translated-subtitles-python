# Translated subtitles (SRT and VTT) with AssemblyAI

Companion code for the AssemblyAI blog post [How to create translated subtitles (SRT and VTT) with an API](https://www.assemblyai.com/blog/create-multi-lingual-subtitles-with-assemblyai-and-deepl).

One video in, one subtitle file per language out:

```
subtitles/video.en.srt   subtitles/video.en.vtt
subtitles/video.es.srt   subtitles/video.es.vtt
subtitles/video.fr.srt   subtitles/video.fr.vtt
```

## Default build: AssemblyAI-STT-3.7 + LLM Gateway

`translate_subtitles.py` transcribes the video with AssemblyAI-STT-3.7 (`assemblyai-stt-3-7`), exports the
source-language SRT and VTT, and translates the cue text through
[LLM Gateway](https://www.assemblyai.com/products/llm-gateway) in batches of 40. Each translation is written
back into its original timestamp, so cue timing is exact. Change `LLM_MODEL` to any LLM Gateway model.

## Alternative: AssemblyAI-STT-3.7 with built-in Translation

`translate_subtitles_builtin.py` sends one request that transcribes and translates each speaker turn
(`speech_understanding` Translation with `match_original_utterance`), then splits each translated turn into
cues by character share. Timing is exact at each speaker turn and approximate inside a long one.

This script sets `speech_models` to `assemblyai-stt-3-7`, which is on the
[Translation supported-models list](https://www.assemblyai.com/docs/speech-understanding/translation).
For audio outside its 32 languages, set `SPEECH_MODELS` to `["assemblyai-stt-3-7", "universal-2"]`.
Cost per audio hour: AssemblyAI-STT-3.7 $0.21, speaker labels $0.02, Translation $0.06.

| Script | How it translates | Cue timing |
|---|---|---|
| `translate_subtitles.py` (default) | AssemblyAI-STT-3.7 transcript, source SRT, cue text translated through LLM Gateway | Exact: copied from the source SRT |
| `translate_subtitles_builtin.py` | AssemblyAI-STT-3.7 + built-in Translation, per-utterance translations | Approximate inside a speaker turn |

## Setup

Python 3.9+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ASSEMBLYAI_API_KEY=your-api-key   # https://www.assemblyai.com/dashboard/signup
```

## Run

```bash
# Default: AssemblyAI-STT-3.7 + LLM Gateway, local file or public URL
python translate_subtitles.py video.mp4 --languages es fr

# Alternative: AssemblyAI-STT-3.7 + built-in Translation
python translate_subtitles_builtin.py video.mp4 --languages es fr
```

Use a file in a browser player:

```html
<video controls src="video.mp4">
  <track kind="subtitles" src="subtitles/video.es.vtt" srclang="es" label="Español">
  <track kind="subtitles" src="subtitles/video.fr.vtt" srclang="fr" label="Français">
</video>
```

## Tests

The tests mock every HTTP call, so they run without an API key or network:

```bash
python -m unittest discover -s tests -v
```

## Pricing

Speech-to-text, LLM Gateway tokens and the Translation add-on are billed separately. See [assemblyai.com/pricing](https://www.assemblyai.com/pricing).
