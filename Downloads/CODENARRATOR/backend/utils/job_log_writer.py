"""
JobLogWriter: file-like object that captures stdout/stderr and buffers log lines.
Also provides _infer_progress() to map log content to 0-100% progress.
"""

import contextlib
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

LOG_BUFFER_MAX = 2_000

_CHAPTER_TOTAL_RE = re.compile(r"CHAPTER_TOTAL:\s*(\d+)")
_CHAPTER_READY_RE = re.compile(r"CHAPTER_READY:\s*(\S+\.md)")

_KEYWORD_PROGRESS: List[Tuple[str, int]] = [
    ("FetchRepo", 10),
    ("IdentifyAbstractions", 25),
    ("AnalyzeRelationships", 40),
    ("OrderChapters", 50),
    ("WriteChapters", 55),
    ("CombineTutorial", 90),
    ("completed", 100),
    ("GenerateVideoScript", 92),
    ("GenerateVisuals", 95),
    ("GenerateAudio", 97),
    ("AssembleVideo", 99),
]


class JobLogWriter:
    """
    Captures writes to stdout/stderr and appends timestamped log entries
    into an in-memory buffer capped at LOG_BUFFER_MAX entries.
    """

    def __init__(self) -> None:
        self._lines: List[Dict] = []
        self._chapter_total: int = 0
        self._chapters_ready: List[str] = []

    # ── file-like interface ──────────────────────────────────────────────

    def write(self, text: str) -> int:
        if not text or text == "\n":
            return len(text)
        for line in text.splitlines():
            line = line.rstrip()
            if not line:
                continue
            entry = {"timestamp": time.time(), "message": line}
            if len(self._lines) >= LOG_BUFFER_MAX:
                self._lines.pop(0)
            self._lines.append(entry)
            self._parse_signals(line)
        return len(text)

    def flush(self) -> None:
        pass

    # ── public API ───────────────────────────────────────────────────────

    @property
    def lines(self) -> List[Dict]:
        return self._lines

    @property
    def chapter_total(self) -> int:
        return self._chapter_total

    @property
    def chapters_ready(self) -> List[str]:
        return self._chapters_ready

    def since(self, n: int) -> List[Dict]:
        return self._lines[n:]

    def infer_progress(self) -> int:
        return _infer_progress(self._lines, self._chapter_total, self._chapters_ready)

    # ── internal ─────────────────────────────────────────────────────────

    def _parse_signals(self, line: str) -> None:
        m = _CHAPTER_TOTAL_RE.search(line)
        if m:
            self._chapter_total = int(m.group(1))
        m = _CHAPTER_READY_RE.search(line)
        if m:
            fname = m.group(1)
            if fname not in self._chapters_ready:
                self._chapters_ready.append(fname)

    @contextlib.contextmanager
    def capture(self):
        """Context manager: redirect sys.stdout + sys.stderr to this writer."""
        with contextlib.redirect_stdout(self), contextlib.redirect_stderr(self):  # type: ignore[arg-type]
            yield self


def _infer_progress(
    lines: List[Dict],
    chapter_total: int,
    chapters_ready: List[str],
) -> int:
    """Heuristic: map log content to 0-100% progress integer."""
    progress = 0
    full_log = " ".join(entry["message"] for entry in lines)

    for keyword, pct in _KEYWORD_PROGRESS:
        if keyword.lower() in full_log.lower():
            progress = max(progress, pct)

    if chapter_total > 0 and chapters_ready:
        chapter_progress = 55 + int(
            (len(chapters_ready) / chapter_total) * 30
        )
        progress = max(progress, min(chapter_progress, 85))

    return min(progress, 100)
