"""
Spiral Studios â Main Render Engine

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

    def render(self) -> str:
        """
        Execute the full render pipeline:
        1. Prepare scene clips
        2. Build filtergraph (effects + transitions)
        3. Run FFmpeg
        4. Return output path
        """
        start_time = time.time()
        logger.info(f"Starting render: {self.script.get('title', 'Untitled')}")
        logger.info(f"Resolution: {self.width}x{self.height} @ {self.fps}fps, CRF: {self.crf}")
        logger.info(f"Scenes: {len(self.scenes)}, Narration: {self.narration_path is not None}")

        # === Step 1: Prepare scene clips ===
        scene_inputs = []
        for scene in self.scenes:
            sid = scene["scene_id"]
            dur = scene["duration_seconds"]
            clip_path = self._prepare_scene_clips(sid, dur)
            scene_inputs.append((sid, clip_path, dur))
            logger.info(f"  Scene {sid}: {dur}s â {os.path.basename(clip_path)}")

        # === Step 2: Build filtergraph ===
        builder = FilterGraphBuilder(self.width, self.height, self.fps)
        scene_labels = []
        scene_durations = []

        for i, (sid, clip_path, dur) in enumerate(scene_inputs):
            text = None
            for s in self.scenes:
                if s["scene_id"] == sid:
                    text = s.get("text_overlay")
                    break

            label = builder.build_scene_pipeline(
                input_index=i,
                duration=dur,
                text_overlay=text,
                ken_burns=self.ken_burns,
                color_grade=self.color_grade,
                vignette=self.vignette,
            )
            scene_labels.append(label)
            scene_durations.append(dur)

        # === Step 3: Chain with transitions ===
        final_video = builder.build_transitions(
            scene_labels, scene_durations,
            transition=self.transition,
            xfade_duration=config.CROSSFADE_DURATION
        )

        # === Step 4: Build FFmpeg command ===
        input_args = []
        for _, clip_path, _ in scene_inputs:
            input_args.extend(["-i", clip_path])

        # Add narration audio
        audio_map = []
        if self.narration_path and os.path.exists(self.narration_path) and os.path.getsize(self.narration_path) > 100:
            narration_idx = len(scene_inputs)
            input_args.extend(["-i", self.narration_path])
            # Map audio directly (skip loudnorm filter to avoid stream issues)
            audio_map = ["-map", f"{narration_idx}:a"]
            logger.info(f"  Narration: {self.narration_path} ({os.path.getsize(self.narration_path)} bytes)")
        else:
            # Silent audio
            audio_map = ["-an"]

        filtergraph = builder.get_filtergraph()

        # Write filtergraph to file (can be very long)
        fg_file = os.path.join(config.TEMP_DIR, "filtergraph.txt")
        with open(fg_file, "w") as f:
            f.write(filtergraph)

        logger.info(f"Filtergraph: {len(filtergraph)} chars, {len(builder.filters)} filters")

        # === Step 5: Run FFmpeg ===
        # Build audio codec args only if we have audio
        audio_codec_args = []
        if "-an" not in audio_map:
            audio_codec_args = [
                "-c:a", config.DEFAULT_AUDIO_CODEC,
                "-b:a", config.DEFAULT_AUDIO_BITRATE,
                "-shortest",
            ]

        cmd = [
            config.FFMPEG_BIN, "-y",
            *input_args,
            "-filter_complex", filtergraph,
            "-map", f"[{final_video}]",
            *audio_map,
            "-c:v", config.DEFAULT_CODEC,
            "-preset", self.preset,
            "-crf", str(self.crf),
            "-pix_fmt", config.DEFAULT_PIXEL_FORMAT,
            *audio_codec_args,
            "-movflags", "+faststart",
            self.output_path
        ]

        logger.info(f"Running FFmpeg...")
        logger.info(f"Full command: {' '.join(cmd)}")
        logger.info(f"Filtergraph file: {fg_file}")
        # Log filtergraph content for debugging
        with open(fg_file, 'r') as _fg:
            fg_content = _fg.read()
            logger.info(f"Filtergraph ({len(fg_content)} chars): {fg_content[:500]}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour max
        )

        elapsed = time.time() - start_time

        if result.returncode != 0:
            logger.error(f"FFmpeg failed (exit {result.returncode})")
            logger.error(f"stderr: {result.stderr[-2000:]}")
            raise RuntimeError(f"FFmpeg render failed: {result.stderr[-500:]}")

        # === Step 6: Report ===
        file_size_mb = os.path.getsize(self.output_path) / (1024 * 1024)
        output_duration = self._get_clip_duration(self.output_path)

        logger.info(f"Render complete!")
        logger.info(f"  Output: {self.output_path}")
        logger.info(f"  Duration: {output_duration:.1f}s")
        logger.info(f"  File size: {file_size_mb:.1f} MB")
        logger.info(f"  Render time: {elapsed:.1f}s")
        logger.info(f"  Speed: {output_duration/elapsed:.1f}x realtime")

        return self.output_path


def render_from_json(
    script_path: str,
    clips_dir: str,
    narration_path: str = None,
    output_path: str = None,
    width: int = 1920,
    height: int = 1080,
) -> str:
    """
    Convenience function: render a video from a script JSON file.

    Expects clips organized as: clips_dir/scene_{id}/clip_001.mp4
    """
    with open(script_path, "r") as f:
        script = json.load(f)

    # Auto-discover clips
    clip_paths = {}
    for scene in script.get("scenes", []):
        sid = scene["scene_id"]
        scene_dir = os.path.join(clips_dir, f"scene_{sid}")
        if os.path.isdir(scene_dir):
            clips = sorted([
                os.path.join(scene_dir, f)
                for f in os.listdir(scene_dir)
                if f.endswith((".mp4", ".webm", ".mov"))
            ])
            clip_paths[sid] = clips

    engine = RenderEngine(
        script=script,
        clip_paths=clip_paths,
        narration_path=narration_path,
        output_path=output_path,
        width=width,
        height=height,
    )

    return engine.render()
