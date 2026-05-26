"""
File scoring heuristic for ranking repository files by importance.
Score(f) = W_ext(f) + W_name(f) + W_path(f) + W_size(f)
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

FAST_MAX_FILES = 220
HARD_CRAWL_LIMIT = 450

INCLUDE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java",
    ".rs", ".cpp", ".c", ".h", ".cs", ".rb", ".php",
    ".swift", ".kt", ".scala", ".md",
    ".ipynb", ".r", ".rmd", ".sql", ".sh", ".yaml", ".yml", ".json",
}

EXCLUDE_PATTERNS = [
    r"node_modules[\\/]",
    r"\.git[\\/]",
    r"__pycache__[\\/]",
    r"[\\/]dist[\\/]",
    r"[\\/]build[\\/]",
    r"\.next[\\/]",
    r"[\\/]coverage[\\/]",
    r"\.min\.js$",
    r"\.lock$",
    r"\.sum$",
    r"\.mod$",
]

_EXCLUDE_RE = re.compile("|".join(EXCLUDE_PATTERNS), re.IGNORECASE)

_EXT_WEIGHTS = {
    ".py": 30,
    ".ts": 24, ".tsx": 24,
    ".js": 20, ".jsx": 20,
    ".go": 18,
    ".java": 15,
    ".md": 10,
}

_NAME_KEYWORDS = {
    "main", "core", "pipeline", "router", "server",
    "app", "index", "cli", "engine", "base",
}

_PATH_PENALTIES = {
    "test", "tests", "__pycache__", "node_modules",
    "dist", "build", ".git", "docs", "examples",
    "fixtures", "migrations", "vendor",
}


def _w_ext(path: str) -> int:
    ext = Path(path).suffix.lower()
    if ext == ".md":
        name = Path(path).stem.lower()
        if name != "readme":
            return 0
    return _EXT_WEIGHTS.get(ext, 0)


def _w_name(path: str) -> int:
    stem = Path(path).stem.lower()
    for kw in _NAME_KEYWORDS:
        if kw in stem:
            return 18
    return 0


def _w_path(path: str) -> int:
    parts = set(Path(path).parts)
    if parts & _PATH_PENALTIES:
        return -22
    return 0


def _w_size(size_bytes: int) -> int:
    return 10 if 500 <= size_bytes <= 50_000 else 0


def score_file(path: str, size_bytes: int) -> int:
    return _w_ext(path) + _w_name(path) + _w_path(path) + _w_size(size_bytes)


def should_exclude(path: str) -> bool:
    return bool(_EXCLUDE_RE.search(path))


def filter_and_score(
    files: List[Tuple[str, str]],  # (path, content)
) -> List[Tuple[str, str]]:
    """
    Filter by include/exclude rules and return top FAST_MAX_FILES by score.
    Input list is already capped at HARD_CRAWL_LIMIT by the caller.
    """
    scored: List[Tuple[int, str, str]] = []
    for path, content in files:
        if should_exclude(path):
            continue
        ext = Path(path).suffix.lower()
        if ext not in INCLUDE_EXTENSIONS:
            continue
        size = len(content.encode("utf-8", errors="replace"))
        s = score_file(path, size)
        scored.append((s, path, content))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [(p, c) for _, p, c in scored[:FAST_MAX_FILES]]
