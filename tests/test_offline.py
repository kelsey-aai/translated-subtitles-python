"""Offline tests: the HTTP layer is mocked, so no API key or network is needed.

Run: python -m unittest discover -s tests
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ASSEMBLYAI_API_KEY", "test-key")

import subtitles  # noqa: E402
import translate_subtitles  # noqa: E402
import translate_subtitles_universal2  # noqa: E402

# Shape copied from the response example in the AssemblyAI translation docs.
TRANSCRIPT = {
    "id": "abc123",
    "status": "completed",
    "language_code": "en",
    "utterances": [
        {
            "speaker": "A",
            "start": 240,
            "end": 26560,
            "text": "Smoke from hundreds of wildfires in Canada is triggering air quality alerts...",
            "translated_texts": {
                "es": "El humo de cientos de incendios forestales en Canadá está provocando "
                "alertas de calidad del aire en todo Estados Unidos, desde Maine hasta "
                "Maryland y Minnesota, según los meteorólogos."
            },
        },
        {
            "speaker": "B",
            "start": 28060,
            "end": 28620,
            "text": "Good morning.",
            "translated_texts": {"es": "Buenos días."},
        },
    ],
}

SOURCE_SRT = """1
00:00:00,240 --> 00:00:02,100
Smoke from hundreds of wildfires

2
00:00:02,100 --> 00:00:04,000
in Canada is triggering alerts
"""


class FakeResponse:
    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class SplitTests(unittest.TestCase):
    def test_cues_cover_the_utterance(self):
        u = TRANSCRIPT["utterances"][0]
        cues = subtitles.split_utterance(u["translated_texts"]["es"], u["start"], u["end"])
        self.assertGreater(len(cues), 1)
        self.assertEqual(cues[0].start, 240)
        self.assertEqual(cues[-1].end, 26560)
        for a, b in zip(cues, cues[1:]):
            self.assertEqual(a.end, b.start)
        for cue in cues:
            lines = cue.text.split("\n")
            self.assertLessEqual(len(lines), 2)
            self.assertTrue(all(len(line) <= 42 for line in lines))

    def test_srt_and_vtt_format(self):
        cues = [subtitles.Cue(240, 3_723_004, "Hola")]
        self.assertIn("00:00:00,240 --> 01:02:03,004", subtitles.to_srt(cues))
        vtt = subtitles.to_vtt(cues)
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertIn("00:00:00.240 --> 01:02:03.004", vtt)

    def test_parse_srt_round_trip(self):
        cues = subtitles.parse_srt(SOURCE_SRT)
        self.assertEqual(len(cues), 2)
        self.assertEqual(subtitles.parse_srt(subtitles.to_srt(cues)), cues)


class Universal2AlternativeTests(unittest.TestCase):
    def test_request_and_files(self):
        posted = {}

        def fake_post(url, headers=None, json=None, data=None):
            posted["url"], posted["json"] = url, json
            return FakeResponse({"id": "abc123"})

        def fake_get(url, headers=None, params=None):
            if url.endswith("/srt"):
                return FakeResponse(text=SOURCE_SRT)
            if url.endswith("/vtt"):
                return FakeResponse(text="WEBVTT\n")
            return FakeResponse(TRANSCRIPT)

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            translate_subtitles_universal2.requests, "post", fake_post
        ), mock.patch.object(translate_subtitles_universal2.requests, "get", fake_get), mock.patch.object(
            sys, "argv", ["x", "https://example.com/video.mp4", "--languages", "es", "--out", tmp]
        ):
            translate_subtitles_universal2.main()
            files = sorted(p.name for p in Path(tmp).iterdir())
            es = (Path(tmp) / "video.es.srt").read_text()

        translation = posted["json"]["speech_understanding"]["request"]["translation"]
        self.assertTrue(translation["match_original_utterance"])
        self.assertTrue(posted["json"]["speaker_labels"])
        self.assertEqual(posted["json"]["speech_models"], ["universal-2"])
        self.assertEqual(files, ["video.en.srt", "video.en.vtt", "video.es.srt", "video.es.vtt"])
        self.assertIn("Buenos días.", es)


class DefaultBuildTests(unittest.TestCase):
    def test_default_pipeline_request_and_files(self):
        posted = []

        def fake_post(url, headers=None, json=None, data=None):
            posted.append((url, json))
            if url.endswith("/v2/transcript"):
                return FakeResponse({"id": "abc123"})
            texts = __import__("json").loads(json["messages"][0]["content"].split("\n\n", 1)[1])
            reply = [f"ES: {t}" for t in texts]
            return FakeResponse({"choices": [{"message": {"content": __import__("json").dumps(reply)}}]})

        def fake_get(url, headers=None, params=None):
            if url.endswith("/srt"):
                return FakeResponse(text=SOURCE_SRT)
            if url.endswith("/vtt"):
                return FakeResponse(text="WEBVTT\n")
            return FakeResponse({"id": "abc123", "status": "completed", "language_code": "en"})

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            translate_subtitles.requests, "post", fake_post
        ), mock.patch.object(translate_subtitles.requests, "get", fake_get), mock.patch.object(
            sys, "argv", ["x", "https://example.com/video.mp4", "--languages", "es", "--out", tmp]
        ):
            translate_subtitles.main()
            files = sorted(p.name for p in Path(tmp).iterdir())
            es = subtitles.parse_srt((Path(tmp) / "video.es.srt").read_text())

        url, body = posted[0]
        self.assertTrue(url.endswith("/v2/transcript"))
        self.assertEqual(body["speech_models"], ["assemblyai-stt-3-7"])
        self.assertNotIn("speech_understanding", body)
        self.assertTrue(posted[1][0].startswith("https://llm-gateway.assemblyai.com/"))
        self.assertEqual(files, ["video.en.srt", "video.en.vtt", "video.es.srt", "video.es.vtt"])
        source = subtitles.parse_srt(SOURCE_SRT)
        self.assertEqual([(c.start, c.end) for c in es], [(c.start, c.end) for c in source])
        self.assertTrue(all(c.text.startswith("ES: ") for c in es))

    def test_timings_are_unchanged(self):
        def fake_post(url, headers=None, json=None):
            texts = __import__("json").loads(json["messages"][0]["content"].split("\n\n", 1)[1])
            reply = [f"ES: {t}" for t in texts]
            return FakeResponse({"choices": [{"message": {"content": __import__("json").dumps(reply)}}]})

        source = subtitles.parse_srt(SOURCE_SRT)
        with mock.patch.object(translate_subtitles.requests, "post", fake_post):
            out = translate_subtitles.translate_cues(source, "es")
        self.assertEqual([(c.start, c.end) for c in out], [(c.start, c.end) for c in source])
        self.assertTrue(all(c.text.startswith("ES: ") for c in out))

    def test_length_mismatch_raises(self):
        def fake_post(url, headers=None, json=None):
            return FakeResponse({"choices": [{"message": {"content": "[\"uno\"]"}}]})

        with mock.patch.object(translate_subtitles.requests, "post", fake_post):
            with self.assertRaises(ValueError):
                translate_subtitles.translate_batch(["a", "b"], "es")


if __name__ == "__main__":
    unittest.main()
