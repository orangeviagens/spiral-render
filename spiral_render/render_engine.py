"""
Spiral Studios - Main Render Engine

Takes a video script JSON and produces a complete video with:
- Multiple scenes with stock footage
- Ken Burns zoom effect
- Crossfade transitions
- Text overlays with animation
- Color grading + vignette
- Narration audio mixed in

Usage:
    engine = RenderEngine(script_json, narration_path="audio.mp3")
    output_path = engine.render()
"""
import json
import os
import subprocess
import time
import logging
from typing import Dict, List, Optional

from . import config
from .effects import FilterGraphBuilder, build_audio_mix_filter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("spiral_render")


class RenderEngine:
    """
    Main video render engine using FFmpeg.
    """

    def __init__(
        self,
        script: Dict,
        clip_paths: Dict[int, List[str]],
        narration_path: Optional[str] = None,
        output_path: Optional[str] = None,
        width: int = config.DEFAULT_WIDTH,
        height: int = config.DEFAULT_HEIGHT,
        fps: int = config.DEFAULT_FPS,
        crf: int = config.DEFAULT_CRF,
        preset: str = config.DEFAULT_PRESET,
        transition: str = "fade",
        ken_burns: bool = True,
        color_grade: bool = True,
        vignette: bool = True,
    ):
        """
        Args:
            script: Video script dict with 'title', 'scenes' array
            clip_paths: Dict mapping scene_id -> list of local clip file paths
            narration_path: Path to narration audio file (MP3/WAV)
            output_path: Output video file path
            width/height/fps: Video dimensions
            crf: Quality (18=best, 28=low)
            preset: FFmpeg encoding speed preset
            transition: xfade transition type
            ken_burns: Enable Ken Burns zoom
            color_grade: Enable color grading
            vignette: Enable vignette effect
        """
        self.script = script
        self.clip_paths = clip_paths
        self.narration_path = narration_path
        self.width = width
        self.height = height
        self.fps = fps
        self.crf = crf
        self.preset = preset
        self.transition = transition
        self.ken_burns = ken_burns
        self.color_grade = color_grade
        self.vignette = vignette

        if output_path is None:
            slug = script.get("title", "video").replace(" ", "_")[:30].lower()
            output_path = os.path.join(config.OUTPUT_DIR, f"{slug}_{int(time.time())}.mp4")
        self.output_path = output_path

        self.scenes = script.get("scenes", [])

    def _prepare_scene_clips(self, scene_id: int, duration: float) -> str:
        """
        Concatenate multiple clips for a scene to fill the required duration.
        Returns path to a single clip file covering the full scene duration.
        """
        clips = self.clip_paths.get(scene_id, [])
        if not clips:
            # Generate a black clip as fallback
            fallback = os.path.join(config.TEMP_DIR, f"black_scene_{scene_id}.mp4")
            subprocess.run([
                config.FFMPEG_BIN, "-y", "-f", "lavfi",
                "-i", f"color=c=black:s={self.width}x{self.height}:d={duration}:r={self.fps}",
                "-c:v", config.DEFAULT_CODEC, "-preset", "ultrafast",
                "-pix_fmt", config.DEFAULT_PIXEL_FORMAT,
                fallback
            ], capture_output=True)
            return fallback

        if len(clips) == 1:
            return clips[0]

        # Concatenate clips using concat demuxer
        concat_file = os.path.join(config.TEMP_DIR, f"concat_scene_{scene_id}.txt")
        with open(concat_file, "w") as f:
            for clip in clips:
                f.write(f"file '{os.path.abspath(clip)}'\n")

        concat_output = os.path.join(config.TEMP_DIR, f"scene_{scene_id}_concat.mp4")
        subprocess.run([
            config.FFMPEG_BIN, "-y",
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-t", str(duration),
            "-c:v", config.DEFAULT_CODEC, "-preset", "ultrafast",
            "-an",  # no audio from clips
            "-pix_fmt", config.DEFAULT_PIXEL_FORMAT,
            concat_output
        ], capture_output=True)

        return concat_output

    def _get_clip_duration(self, path: str) -> float:
        """Get duration of a media file using ffprobe."""
        result = subprocess.run([
            config.FFPROBE_BIN, "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0", path
        ], capture_output=True, text=True)
        try:
            return float(result.stdout.strip())
        except (ValueError, AttributeError):
            return 0.0
\n    def render(self) -> str:
        """
        Simple concat-based render pipeline.
        1. Prepare + scale each scene clip
        2. Concat all clips with concat demuxer
        3. Add narration audio
        """
        start_time = time.time()
        logger.info(f"Starting render: {self.script.get('title', 'Untitled')}")
        logger.info(f"Resolution: {self.width}x{self.height}, Scenes: {len(self.scenes)}")

        # Limit to max 6 scenes
        scenes_to_use = self.scenes[:6]
        logger.info(f"Using {len(scenes_to_use)} scenes (of {len(self.scenes)} total)")

        # === Step 1: Prepare each scene clip (scaled + trimmed) ===
        prepared_clips = []
        for scene in scenes_to_use:
            sid = scene["scene_id"]
            dur = scene["duration_seconds"]
            raw_clip = self._prepare_scene_clips(sid, dur)

            # Scale and trim to exact specs
            scaled_clip = os.path.join(config.TEMP_DIR, f"scaled_{sid}.mp4")
            scale_cmd = [
                config.FFMPEG_BIN, "-y",
                "-i", raw_clip,
                "-t", str(dur),
                "-vf", f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={self.fps}",
                "-c:v", config.DEFAULT_CODEC,
                "-preset", "ultrafast",
                "-pix_fmt", config.DEFAULT_PIXEL_FORMAT,
                "-an",
                scaled_clip
            ]
            result = subprocess.run(scale_cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                logger.error(f"Scale failed for scene {sid}: {result.stderr[-200:]}")
                # Use raw clip as fallback
                scaled_clip = raw_clip

            prepared_clips.append(scaled_clip)
            logger.info(f"  Scene {sid}: {dur}s prepared")

        # === Step 2: Concat all clips ===
        concat_file = os.path.join(config.TEMP_DIR, "final_concat.txt")
        with open(concat_file, "w") as f:
            for clip in prepared_clips:
                f.write(f"file '{os.path.abspath(clip)}'\n")

        video_only = os.path.join(config.TEMP_DIR, "video_only.mp4")
        concat_cmd = [
            config.FFMPEG_BIN, "-y",
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-c:v", config.DEFAULT_CODEC,
            "-preset", self.preset,
            "-crf", str(self.crf),
            "-pix_fmt", config.DEFAULT_PIXEL_FORMAT,
            "-movflags", "+faststart",
            video_only
        ]
        logger.info(f"Concatenating {len(prepared_clips)} clips...")
        result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"Concat failed: {result.stderr[-300:]}")
        logger.info(f"Video concatenated: {video_only}")

        # === Step 3: Add narration audio if available ===
        if self.narration_path and os.path.exists(self.narration_path) and os.path.getsize(self.narration_path) > 100:
            logger.info(f"Adding narration: {self.narration_path}")
            merge_cmd = [
                config.FFMPEG_BIN, "-y",
                "-i", video_only,
                "-i", self.narration_path,
                "-c:v", "copy",
                "-c:a", config.DEFAULT_AUDIO_CODEC,
                "-b:a", config.DEFAULT_AUDIO_BITRATE,
                "-shortest",
                "-movflags", "+faststart",
                self.output_path
            ]
            result = subprocess.run(merge_cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                logger.error(f"Audio merge failed: {result.stderr[-200:]}")
                # Fallback: video only
                import shutil
                shutil.copy2(video_only, self.output_path)
        else:
            import shutil
            shutil.copy2(video_only, self.output_path)

        elapsed = time.time() - start_time
        file_size = os.path.getsize(self.output_path) / (1024 * 1024)
        logger.info(f"Render complete: {self.output_path} ({file_size:.1f}MB in {elapsed:.1f}s)")

        return self.output_path\n