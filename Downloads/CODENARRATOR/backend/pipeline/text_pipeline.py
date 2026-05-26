"""
Text generation pipeline: FetchRepo → IdentifyAbstractions → AnalyzeRelationships
→ OrderChapters → WriteChapters → CombineTutorial
"""

import logging
import os
from pathlib import Path

from nodes.fetch_repo import FetchRepo
from nodes.identify_abstractions import IdentifyAbstractions
from nodes.analyze_relationships import AnalyzeRelationships
from nodes.order_chapters import OrderChapters
from nodes.write_chapters import WriteChapters
from nodes.combine_tutorial import CombineTutorial
from pipeline.pocketflow import AsyncFlow

logger = logging.getLogger(__name__)

_OUTPUT_BASE = Path(os.environ.get("OUTPUT_DIR", "./output"))


def build_text_pipeline() -> AsyncFlow:
    fetch = FetchRepo()
    identify = IdentifyAbstractions()
    relationships = AnalyzeRelationships()
    order = OrderChapters()
    write = WriteChapters()
    combine = CombineTutorial()

    transitions = {
        "FetchRepo": {"default": identify},
        "IdentifyAbstractions": {"default": relationships},
        "AnalyzeRelationships": {"default": order},
        "OrderChapters": {"default": write},
        "WriteChapters": {"default": combine},
        "CombineTutorial": {},
    }

    return AsyncFlow(start=fetch, transitions=transitions)


async def run_text_pipeline(shared: dict) -> None:
    job_id = shared["job_id"]
    output_dir = _OUTPUT_BASE / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    shared["output_dir"] = str(output_dir)

    logger.info("Text pipeline starting for job %s", job_id)
    flow = build_text_pipeline()
    await flow.run(shared)
    logger.info("Text pipeline completed for job %s", job_id)
