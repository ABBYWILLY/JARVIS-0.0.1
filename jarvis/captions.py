"""Prepared emotional captions, advanced by approximate PCM word groups.

Only ``prepare_caption`` interprets language. A window uses cached source
offsets and optional font measurements; it never classifies or tokenizes text.
Fractions estimate pronunciation and are not word-level audio timestamps.
"""
from bisect import bisect_right
from dataclasses import dataclass
import math
import re

from .spectrum import analyze_passages, emotional_spans


MAX_TEXT = 4000
MAX_WORDS = 12
_WORDS = re.compile(r"\S+", re.UNICODE)


@dataclass(frozen=True)
class CaptionMark:
    start: int
    end: int
    tone: str


@dataclass(frozen=True)
class CaptionWindow:
    text: str = ""
    marks: tuple[CaptionMark, ...] = ()


@dataclass(frozen=True)
class CaptionPlan:
    text: str
    words: tuple[tuple[int, int], ...] = ()
    marks: tuple[CaptionMark, ...] = ()

    @classmethod
    def from_dict(cls, value):
        """Restore worker metadata without repeating linguistic analysis."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict) or not isinstance(value.get("text"), str):
            raise ValueError("invalid caption metadata")
        text = value["text"]
        if len(text) > MAX_TEXT:
            raise ValueError("caption metadata exceeds text limit")
        for field in ("words", "marks"):
            items = value.get(field, ())
            if not isinstance(items, (tuple, list)) or len(items) > MAX_TEXT:
                raise ValueError("invalid caption metadata")
        try:
            words = tuple(tuple(pair) for pair in value.get("words", ()))
            marks = tuple(mark if isinstance(mark, CaptionMark) else CaptionMark(**mark)
                          for mark in value.get("marks", ()))
        except (TypeError, ValueError):
            raise ValueError("invalid caption metadata") from None
        previous = 0
        for pair in words:
            if (len(pair) != 2 or any(type(position) is not int for position in pair)
                    or not previous <= pair[0] < pair[1] <= len(text)):
                raise ValueError("invalid caption word offsets")
            previous = pair[1]
        previous = 0
        for mark in marks:
            if (type(mark.start) is not int or type(mark.end) is not int
                    or not previous <= mark.start < mark.end <= len(text)
                    or not isinstance(mark.tone, str)):
                raise ValueError("invalid caption mark offsets")
            previous = mark.end
        return cls(text, words, marks)

    def window(self, fraction, max_words=MAX_WORDS, measure=None, width=None):
        """Show up to four word groups, coloring only estimated spoken words.

        Up to two following words can supply neutral reading context. Optional
        ``measure`` accepts a string (for example ``tkinter.font.Font.measure``).
        Fitting retains the current word, then recent context, in two lines.
        """
        try:
            fraction = float(fraction)
        except (TypeError, ValueError, OverflowError):
            fraction = 0.0
        if not math.isfinite(fraction) or fraction <= 0 or not self.words:
            return CaptionWindow()
        fraction = min(1.0, fraction)
        try:
            limit = min(MAX_WORDS, max(0, int(max_words)))
        except (TypeError, ValueError, OverflowError):
            limit = MAX_WORDS
        if not limit:
            return CaptionWindow()
        spoken = min(len(self.words), max(1, math.ceil(fraction * len(self.words))))
        end = min(len(self.words), 3 * math.ceil(spoken / 3), spoken + limit - 1)
        start = max(0, end - limit)
        try:
            width = float(width)
        except (TypeError, ValueError, OverflowError):
            width = 0.0
        fitting = callable(measure) and math.isfinite(width) and width > 0
        tokens = [(left, right, self.text[left:right]) for left, right in self.words[start:end]]
        lines = _layout(tokens, measure if fitting else None, width)
        # Future context must never push the word currently being spoken away.
        while len(lines) > 2 and end > spoken:
            end -= 1
            tokens.pop()
            lines = _layout(tokens, measure, width)
        lines = lines[-2:]
        if not lines or not lines[0]:
            return CaptionWindow()
        parts, positions = [], []
        cursor = 0
        for line_index, line in enumerate(lines):
            for token_index, (left, right, value) in enumerate(line):
                separator = "\n" if line_index and not token_index else " " if token_index else ""
                parts.append(separator)
                cursor += len(separator)
                parts.append(value)
                # An ellipsis replaces the entire oversized token and is neutral.
                if value == self.text[left:right]:
                    positions.append((left, right, cursor))
                cursor += len(value)
        text = "".join(parts)
        if not positions:
            return CaptionWindow(text)
        source_start, source_end = positions[0][0], min(positions[-1][1], self.words[spoken - 1][1])
        marks = []
        first = bisect_right(self.marks, source_start, key=lambda mark: mark.end)
        for index in range(first, len(self.marks)):
            mark = self.marks[index]
            if mark.start >= source_end:
                break
            for left, right, output in positions:
                begin, finish = max(left, mark.start), min(right, mark.end, source_end)
                if begin >= finish:
                    continue
                mapped = CaptionMark(output + begin - left, output + finish - left, mark.tone)
                if (marks and marks[-1].tone == mapped.tone
                        and mark.start <= left and text[marks[-1].end:mapped.start].isspace()):
                    previous = marks.pop()
                    mapped = CaptionMark(previous.start, mapped.end, mapped.tone)
                marks.append(mapped)
        return CaptionWindow(text, tuple(marks))


def _layout(tokens, measure, width):
    """Wrap whole cached tokens; no character/emoji sequence is ever split."""
    lines = [[]]
    line_text = ""
    ellipsis_fits = None
    for left, right, value in tokens:
        if measure is not None and measure(value) > width:
            if ellipsis_fits is None:
                ellipsis_fits = measure("…") <= width
            value = "…" if ellipsis_fits else ""
        if not value:
            continue
        candidate = line_text + " " + value if line_text else value
        if measure is not None and line_text and measure(candidate) > width:
            lines.append([])
            line_text = value
        else:
            line_text = candidate
        lines[-1].append((left, right, value))
    return lines


def prepare_caption(text, mode="thematic"):
    """Bound and prepare one text arrival, preserving original Python offsets.

    Markdown is left intact when supplied: the shared spectrum scanner masks
    markup, quotes, code and destinations while retaining source positions.
    Callers normally supply the already cleaned display text.
    """
    text = str(text or "")
    if len(text) > MAX_TEXT:
        # Stop at a complete token; never cut a composed emoji or combining mark.
        boundary = max((i for i, char in enumerate(text[:MAX_TEXT + 1]) if char.isspace()), default=0)
        text = text[:boundary].rstrip() if boundary else "…"
    words = tuple(match.span() for match in _WORDS.finditer(text))
    marks = []
    for event in analyze_passages(text, mode=mode):
        if event.tone.name == "neutralité":
            continue
        marks.extend(CaptionMark(event.start + left, event.start + right, event.tone.name)
                     for left, right in emotional_spans(event.text, event.tone, mode=mode))
    return CaptionPlan(text, words, tuple(marks))
