"""
Shared state schema and factory for pipeline runs.
The shared dict is the single source of truth passed through all nodes.
"""

from typing import Any, Dict, List, Optional, Tuple


def make_shared_state(
    job_id: str,
    repo_url: str,
    run_video: bool = False,
    language: str = "English",
    theme: str = "dark",
    voice: str = "en-US-AriaNeural",
    github_token: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        # Job metadata
        "job_id": job_id,
        "repo_url": repo_url,
        "run_video": run_video,
        "language": language,
        "theme": theme,
        "voice": voice,
        "github_token": github_token,   # OAuth token for private repos
        # FetchRepo output
        "files": [],           # List[Tuple[str, str]] — (path, content)
        "owner": "",
        "repo_name": "",
        # IdentifyAbstractions output
        "abstractions": [],    # List[dict] — {name, description, file_indices}
        # AnalyzeRelationships output
        "summary": "",
        "relationships": [],   # List[dict] — {from_abstraction, to_abstraction, label}
        # OrderChapters output
        "chapter_order": [],   # List[str] — ordered abstraction names
        # WriteChapters output
        "chapters": {},        # Dict[str, str] — {filename: markdown_content}
        # CombineTutorial output
        "output_dir": "",
        "index_md_path": "",
        # Video pipeline
        "video_script": [],    # List[dict] — segment specs
        "visual_paths": [],    # List[str] — PNG file paths
        "audio_paths": [],     # List[str] — MP3 file paths
        "video_path": "",      # Final MP4 path
    }
