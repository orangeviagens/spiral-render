"""
Spiral Studios — Full Production Pipeline

End-to-end: Script → Narration → Stock Footage → Render → Upload
This is the orchestrator that ties everything together.
"""
import json
import os
import time
import logging
from typing import Dict, Optional

from . import config
from .render_engine import RenderEngine
from .api_clients import (
    PexelsClient,
    ElevenLabsClient,
    AnthropicClient,
    SupabaseStorageClient,
)

logger = logging.getLogger("spiral_render.pipeline")


class ProductionPipeline:
    """
    Full video production pipeline.

    Usage:
        pipeline = ProductionPipeline()

        # Option A: Generate everything from a topic
        result = pipeline.produce(
            channel="Hidden Escapes",
            topic="5 Forgotten Underground Cities",
            duration_minutes=5
        )

        # Option B: Render from existing script + narration
        result = pipeline.render_from_script(
            script_path="script.json",
            narration_path="narration.mp3"
        )
    """

    def __init__(
        self,
        width: int = config.DEFAULT_WIDTH,
        height: int = config.DEFAULT_HEIGHT,
    ):
        self.width = width
        self.height = height
        self.pexels = PexelsClient()
        self.elevenlabs = ElevenLabsClient()
        self.anthropic = AnthropicClient()
        self.storage = SupabaseStorageClient()

    def produce(
        self,
        channel: str,
        topic: str,
        duration_minutes: int = 5,
        num_scenes: int = 8,
        upload: bool = True,
    ) -> Dict:
        """
        Full production pipeline from topic to uploaded video.

        Returns dict with: video_path, video_url, script, narration_path, etc.
        """
        start_time = time.time()
        logger.info(f"=== PRODUCTION START: {channel} — {topic} ===")

        # === Step 1: Generate Script ===
        logger.info("Step 1/5: Generating script...")
        script = self.anthropic.generate_script(
            channel=channel,
            topic=topic,
            duration_minutes=duration_minutes,
            num_scenes=num_scenes,
        )

        # Save script
        script_path = os.path.join(config.WORK_DIR, "script.json")
        with open(script_path, "w") as f:
            json.dump(script, f, indent=2)
        logger.info(f"  Script: {script['title']} ({len(script['scenes'])} scenes)")

        # === Step 2: Generate Narration ===
        logger.info("Step 2/5: Generating narration...")
        narration_path = self.elevenlabs.generate_narration_from_script(script)
        logger.info(f"  Narration: {narration_path}")

        # === Step 3: Download Stock Footage ===
        logger.info("Step 3/5: Downloading stock footage...")
        clip_paths = {}
        for scene in script["scenes"]:
            sid = scene["scene_id"]
            query = scene.get("scene_description", "")
            duration = scene["duration_seconds"]

            clips = self.pexels.fetch_clips_for_scene(
                query=query,
                scene_id=sid,
                needed_duration=duration,
                max_clips=5,
            )
            clip_paths[sid] = clips
            logger.info(f"  Scene {sid}: {len(clips)} clips downloaded")

        # === Step 4: Render Video ===
        logger.info("Step 4/5: Rendering video...")
        engine = RenderEngine(
            script=script,
            clip_paths=clip_paths,
            narration_path=narration_path,
            width=self.width,
            height=self.height,
        )
        video_path = engine.render()

        # === Step 5: Upload ===
        video_url = None
        narration_url = None
        if upload:
            logger.info("Step 5/5: Uploading to storage...")
            slug = script["title"].replace(" ", "_")[:50].lower()
            ts = int(time.time())

            video_url = self.storage.upload_file(
                bucket="videos",
                remote_path=f"{channel.lower().replace(' ', '_')}/{slug}_{ts}.mp4",
                local_path=video_path,
            )

            narration_url = self.storage.upload_file(
                bucket="audio",
                remote_path=f"{channel.lower().replace(' ', '_')}/{slug}_{ts}.mp3",
                local_path=narration_path,
            )
        else:
            logger.info("Step 5/5: Upload skipped")

        elapsed = time.time() - start_time
        logger.info(f"=== PRODUCTION COMPLETE in {elapsed:.0f}s ===")

        return {
            "title": script["title"],
            "description": script.get("description", ""),
            "tags": script.get("tags", []),
            "script": script,
            "script_path": script_path,
            "narration_path": narration_path,
            "narration_url": narration_url,
            "video_path": video_path,
            "video_url": video_url,
            "duration_seconds": sum(s["duration_seconds"] for s in script["scenes"]),
            "resolution": f"{self.width}x{self.height}",
            "scenes_count": len(script["scenes"]),
            "production_time_seconds": elapsed,
        }

    def render_from_script(
        self,
        script_path: str,
        narration_path: str,
        clips_dir: str = None,
        output_path: str = None,
        download_clips: bool = True,
    ) -> Dict:
        """
        Render from an existing script and narration file.
        Optionally downloads clips from Pexels.
        """
        with open(script_path, "r") as f:
            script = json.load(f)

        clip_paths = {}

        if download_clips:
            logger.info("Downloading clips from Pexels...")
            for scene in script["scenes"]:
                sid = scene["scene_id"]
                query = scene.get("scene_description", "")
                duration = scene["duration_seconds"]
                clips = self.pexels.fetch_clips_for_scene(
                    query=query, scene_id=sid,
                    needed_duration=duration, max_clips=5,
                )
                clip_paths[sid] = clips
        elif clips_dir:
            # Load from local directory
            for scene in script["scenes"]:
                sid = scene["scene_id"]
                scene_dir = os.path.join(clips_dir, f"scene_{sid}")
                if os.path.isdir(scene_dir):
                    clip_paths[sid] = sorted([
                        os.path.join(scene_dir, f)
                        for f in os.listdir(scene_dir)
                        if f.endswith((".mp4", ".webm", ".mov"))
                    ])

        engine = RenderEngine(
            script=script,
            clip_paths=clip_paths,
            narration_path=narration_path,
            output_path=output_path,
            width=self.width,
            height=self.height,
        )

        video_path = engine.render()

        return {
            "title": script["title"],
            "video_path": video_path,
            "resolution": f"{self.width}x{self.height}",
        }
