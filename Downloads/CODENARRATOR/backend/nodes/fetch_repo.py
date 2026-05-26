"""
FetchRepo node — crawls a GitHub repository and populates shared["files"].
Supports HTTPS (GitHub REST API) and SSH (git clone fallback).
"""

import asyncio
import base64
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, List, Tuple

import httpx

from pipeline.pocketflow import AsyncNode
from utils.file_scorer import (
    HARD_CRAWL_LIMIT,
    INCLUDE_EXTENSIONS,
    filter_and_score,
    should_exclude,
)

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_CLONE_TIMEOUT = 120
_MAX_FILE_BYTES = 1_000_000  # 1 MB


def _parse_github_url(url: str):
    url = url.strip().rstrip("/")
    # HTTPS: https://github.com/owner/repo or https://github.com/owner/repo.git
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2), "https"
    # SSH: git@github.com:owner/repo.git
    m = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2), "ssh"
    raise ValueError(f"Cannot parse GitHub URL: {url!r}")


class FetchRepo(AsyncNode):
    max_retries = 2

    async def prep(self, shared: dict) -> dict:
        return {
            "repo_url":     shared["repo_url"],
            "job_id":       shared["job_id"],
            "github_token": shared.get("github_token"),  # OAuth token for private repos
        }

    async def exec(self, prep_result: dict) -> dict:
        repo_url     = prep_result["repo_url"]
        github_token = prep_result.get("github_token")
        owner, repo_name, url_type = _parse_github_url(repo_url)
        logger.info("FetchRepo: %s/%s (type=%s, auth=%s)", owner, repo_name, url_type, bool(github_token))

        files: List[Tuple[str, str]] = []

        if url_type == "https":
            files = await _fetch_via_api(owner, repo_name, github_token=github_token)
        else:
            files = await _fetch_via_clone(repo_url)

        if not files:
            raise ValueError(
                f"Repository {owner}/{repo_name} has no matching files after filtering. "
                "Ensure the repo is public and contains supported source files."
            )

        return {"files": files, "owner": owner, "repo_name": repo_name}

    async def post(self, shared: dict, prep_result: Any, exec_result: dict) -> str:
        shared["files"] = exec_result["files"]
        shared["owner"] = exec_result["owner"]
        shared["repo_name"] = exec_result["repo_name"]
        logger.info("FetchRepo: retained %d files", len(shared["files"]))
        return "default"


# ── GitHub REST API path ──────────────────────────────────────────────────────

async def _fetch_via_api(owner: str, repo: str, github_token: str = "") -> List[Tuple[str, str]]:
    # Per-request OAuth token takes priority over env token
    token = github_token or os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    tree_url = f"{_GITHUB_API}/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"

    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(2):
            resp = await client.get(tree_url, headers=headers)
            if resp.status_code == 403:
                raise PermissionError(
                    f"Repository {owner}/{repo} is private or access is forbidden (HTTP 403)."
                )
            if resp.status_code == 404:
                raise FileNotFoundError(
                    f"Repository {owner}/{repo} not found (HTTP 404). Check the URL."
                )
            if resp.status_code == 429 or (
                resp.status_code == 403 and "rate limit" in resp.text.lower()
            ):
                if attempt == 0:
                    logger.warning("GitHub API rate limit hit. Sleeping 60s...")
                    await asyncio.sleep(60)
                    continue
                raise RuntimeError("GitHub API rate limit exceeded after retry.")
            resp.raise_for_status()
            break

        tree_data = resp.json()

    if tree_data.get("truncated"):
        logger.warning("GitHub tree is truncated — large repo, using available files.")

    blobs = [
        item for item in tree_data.get("tree", [])
        if item.get("type") == "blob"
    ]

    if not blobs:
        raise ValueError("Repository appears to be empty.")

    # Filter early, hard cap before scoring
    candidates = []
    for item in blobs:
        path = item.get("path", "")
        ext = Path(path).suffix.lower()
        if ext not in INCLUDE_EXTENSIONS:
            continue
        if should_exclude(path):
            continue
        size = item.get("size", 0)
        if size > _MAX_FILE_BYTES:
            logger.warning("Skipping large file (%.1f KB): %s", size / 1024, path)
            continue
        candidates.append((path, item.get("sha", ""), size))
        if len(candidates) >= HARD_CRAWL_LIMIT:
            logger.warning("Hit hard crawl limit of %d files.", HARD_CRAWL_LIMIT)
            break

    # Fetch blob contents concurrently (batch of 20)
    files: List[Tuple[str, str]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(candidates), 20):
            batch = candidates[i : i + 20]
            tasks = [
                _fetch_blob(client, owner, repo, sha, path, headers)
                for path, sha, _ in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for (path, sha, _), result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.warning("Failed to fetch %s: %s", path, result)
                elif result:
                    files.append((path, result))

    return filter_and_score(files)


async def _fetch_blob(
    client: httpx.AsyncClient, owner: str, repo: str,
    sha: str, path: str, headers: dict,
) -> str:
    url = f"{_GITHUB_API}/repos/{owner}/{repo}/git/blobs/{sha}"
    resp = await client.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    content_b64 = data.get("content", "")
    raw = base64.b64decode(content_b64)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        # Binary file — skip
        return ""


# ── SSH/clone fallback ────────────────────────────────────────────────────────

async def _fetch_via_clone(repo_url: str) -> List[Tuple[str, str]]:
    tmp = tempfile.mkdtemp(prefix="code_narrator_")
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth=1", repo_url, tmp,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_CLONE_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(
                f"git clone timed out after {_CLONE_TIMEOUT}s for {repo_url}"
            )
        if proc.returncode != 0:
            raise RuntimeError(
                f"git clone failed for {repo_url}:\n{stderr.decode('utf-8', errors='replace')}"
            )

        files: List[Tuple[str, str]] = []
        root = Path(tmp)
        for fp in root.rglob("*"):
            if not fp.is_file():
                continue
            rel = str(fp.relative_to(root)).replace("\\", "/")
            ext = fp.suffix.lower()
            if ext not in INCLUDE_EXTENSIONS:
                continue
            if should_exclude(rel):
                continue
            size = fp.stat().st_size
            if size > _MAX_FILE_BYTES:
                logger.warning("Skipping large file (%.1f KB): %s", size / 1024, rel)
                continue
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                logger.warning("Skipping unreadable file %s: %s", rel, exc)
                continue
            files.append((rel, content))
            if len(files) >= HARD_CRAWL_LIMIT:
                break

        return filter_and_score(files)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
