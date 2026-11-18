"""Helpers for building SRT and WebVTT files from timed text."""
from dataclasses import dataclass
from typing import List


@dataclass
class Cue:
    start: int  # milliseconds
    end: int  # milliseconds
    text: str


def _wrap(words: List[str], max_chars: int) -> List[str]:
    """Pack words into lines of at most max_chars characters."""
    lines: List[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if line and len(candidate) > max_chars:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def split_utterance(
    text: str, start: int, end: int, max_chars: int = 42, max_lines: int = 2
) -> List[Cue]:
    """Split one translated utterance into subtitle-sized cues.

    Each cue holds up to `max_lines` lines of `max_chars` characters. The
    utterance's time span is shared across cues by character count, so
    timing inside a long turn is approximate.
    """
    lines = _wrap(text.split(), max_chars)
    if not lines:
        return []
    blocks = [lines[i : i + max_lines] for i in range(0, len(lines), max_lines)]
    sizes = [sum(len(line) for line in block) for block in blocks]
    total = sum(sizes)
    duration = end - start
    cues: List[Cue] = []
    cursor = start
    for i, (block, size) in enumerate(zip(blocks, sizes)):
        cue_end = end if i == len(blocks) - 1 else cursor + round(duration * size / total)
        cues.append(Cue(cursor, cue_end, "\n".join(block)))
        cursor = cue_end
    return cues


def _timestamp(ms: int, sep: str) -> str:
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{sep}{millis:03d}"


def to_srt(cues: List[Cue]) -> str:
    blocks = []
    for i, cue in enumerate(cues, start=1):
        timing = f"{_timestamp(cue.start, ',')} --> {_timestamp(cue.end, ',')}"
        blocks.append(f"{i}\n{timing}\n{cue.text}\n")
    return "\n".join(blocks)


def to_vtt(cues: List[Cue]) -> str:
    blocks = ["WEBVTT\n"]
    for cue in cues:
        timing = f"{_timestamp(cue.start, '.')} --> {_timestamp(cue.end, '.')}"
        blocks.append(f"{timing}\n{cue.text}\n")
    return "\n".join(blocks)


def parse_srt(srt: str) -> List[Cue]:
    """Parse an SRT string into cues (used by the LLM Gateway variant)."""

    def to_ms(stamp: str) -> int:
        hms, millis = stamp.strip().split(",")
        h, m, s = (int(x) for x in hms.split(":"))
        return ((h * 60 + m) * 60 + s) * 1000 + int(millis)

    cues: List[Cue] = []
    for block in srt.strip().split("\n\n"):
        lines = [line for line in block.strip().splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start, end = lines[1].split("-->")
        cues.append(Cue(to_ms(start), to_ms(end), "\n".join(lines[2:])))
    return cues
