"""
Video synthesis pipeline: LoadExistingTutorial → GenerateVideoScript
→ GenerateVisuals → GenerateAudio → AssembleVideo
"""

import logging

from nodes.load_existing_tutorial import LoadExistingTutorial
from nodes.generate_video_script import GenerateVideoScript
from nodes.generate_visuals import GenerateVisuals
from nodes.generate_audio import GenerateAudio
from nodes.assemble_video import AssembleVideo
from pipeline.pocketflow import AsyncFlow

logger = logging.getLogger(__name__)


def build_video_pipeline() -> AsyncFlow:
    load = LoadExistingTutorial()
    script = GenerateVideoScript()
    visuals = GenerateVisuals()
    audio = GenerateAudio()
    assemble = AssembleVideo()

    transitions = {
        "LoadExistingTutorial": {"default": script},
        "GenerateVideoScript": {"default": visuals},
        "GenerateVisuals": {"default": audio},
        "GenerateAudio": {"default": assemble},
        "AssembleVideo": {},
    }

    return AsyncFlow(start=load, transitions=transitions)


async def run_video_pipeline(shared: dict) -> None:
    job_id = shared["job_id"]
    logger.info("Video pipeline starting for job %s", job_id)
    flow = build_video_pipeline()
    await flow.run(shared)
    logger.info("Video pipeline completed for job %s", job_id)
