import os
"""
Spiral Studios Ã¢ÂÂ FFmpeg Effects & Filter Graph Builder

Builds complex FFmpeg filtergraphs for cinematic travel video production.
Supports: Ken Burns zoom, crossfades, text overlays, color grading, vignette.
"""
import shlex
from typing import List, Optional, Tuple
from . import config


def build_ken_burns_filter(
    input_label: str,
    output_label: str,
    duration: float,
    width: int = config.DEFAULT_WIDTH,
    height: int = config.DEFAULT_HEIGHT,
    fps: int = config.DEFAULT_FPS,
    zoom_start: float = 1.0,
    zoom_end: float = None,
    pan_x: str = "iw/2-(iw/zoom/2)",
    pan_y: str = "ih/2-(ih/zoom/2)"
) -> str:
    """
    Ken Burns effect: slow zoom + optional pan.
    Uses zoompan filter to create cinematic movement on static or video clips.
    """
    if zoom_end is None:
        zoom_end = config.KEN_BURNS_ZOOM

    total_frames = int(duration * fps)
    # zoompan: z interpolates from zoom_start to zoom_end over total_frames
    zoom_expr = f"if(eq(on,0),{zoom_start},{zoom_start}+(on/{total_frames})*({zoom_end}-{zoom_start}))"

    return (
        f"[{input_label}]scale=-1:{height*2},"
        f"zoompan=z='{zoom_expr}':x='{pan_x}':y='{pan_y}'"
        f":d={total_frames}:s={width}x{height}:fps={fps}"
        f"[{output_label}]"
    )


def _get_available_font(preferred: str = config.FONT_BOLD) -> str:
    """Return preferred font path or a fallback that exists."""
    candidates = [
        preferred,
        config.FONT_BOLD,
        config.FONT_REGULAR,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for f in candidates:
        if os.path.exists(f):
            return f
    return ""  # empty = skip text overlay


def build_text_overlay_filter(
    input_label: str,
    output_label: str,
    text: str,
    start_time: float,
    end_time: float,
    font_size: int = config.TEXT_FONT_SIZE,
    font_file: str = "",
    color: str = config.TEXT_COLOR,
    border_w: int = config.TEXT_BORDER_WIDTH,
    border_color: str = config.TEXT_BORDER_COLOR,
    y_position: str = config.TEXT_POSITION_Y,
    fade_in: float = config.TEXT_FADE_IN,
    fade_out: float = config.TEXT_FADE_OUT,
) -> str:
    """
    Animated text overlay with fade in/out.
    Text appears centered horizontally, positioned at y_position.
    """
    # Escape special characters for FFmpeg drawtext
        # Resolve font
    font_file = font_file or _get_available_font()
    if not font_file:
        # No font available Ã¢ÂÂ pass through without text
        return f"[{input_label}]null[{output_label}]"

    escaped_text = (
        text.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("%", "%%")
    )

    # Alpha expression for fade in/out
    alpha_expr = (
        f"if(lt(t-{start_time},{fade_in}),"
        f"(t-{start_time})/{fade_in},"
        f"if(gt(t,{end_time}-{fade_out}),"
        f"({end_time}-t)/{fade_out},1))"
    )

    return (
        f"[{input_label}]drawtext="
        f"fontfile='{font_file}':"
        f"text='{escaped_text}':"
        f"fontsize={font_size}:"
        f"fontcolor={color}@1:"
        f"borderw={border_w}:"
        f"bordercolor={border_color}@0.8:"
        f"x=(w-tw)/2:"
        f"y={y_position}:"
        f"alpha='{alpha_expr}':"
        f"enable='between(t,{start_time},{end_time})'"
        f"[{output_label}]"
    )


def build_fade_filter(
    input_label: str,
    output_label: str,
    fade_in_duration: float = 0.5,
    fade_out_duration: float = 0.5,
    total_duration: float = 0,
) -> str:
    """
    Fade in at start, fade out at end.
    """
    filters = []
    if fade_in_duration > 0:
        filters.append(f"fade=t=in:st=0:d={fade_in_duration}")
    if fade_out_duration > 0 and total_duration > 0:
        fade_out_start = total_duration - fade_out_duration
        filters.append(f"fade=t=out:st={fade_out_start}:d={fade_out_duration}")

    if not filters:
        return f"[{input_label}]null[{output_label}]"

    return f"[{input_label}]{','.join(filters)}[{output_label}]"


def build_color_grade_filter(
    input_label: str,
    output_label: str,
    brightness: float = 0.0,
    contrast: float = 1.0,
    saturation: float = 1.1,
    gamma: float = 1.0,
) -> str:
    """
    Color grading: adjust brightness, contrast, saturation, gamma.
    Gives footage a more cinematic look.
    """
    return (
        f"[{input_label}]eq="
        f"brightness={brightness}:"
        f"contrast={contrast}:"
        f"saturation={saturation}:"
        f"gamma={gamma}"
        f"[{output_label}]"
    )


def build_vignette_filter(
    input_label: str,
    output_label: str,
    angle: str = "PI/4",
) -> str:
    """
    Vignette effect: darkens edges for cinematic feel.
    """
    return f"[{input_label}]vignette=angle={angle}[{output_label}]"


def build_xfade_filter(
    input_a: str,
    input_b: str,
    output_label: str,
    offset: float,
    duration: float = config.CROSSFADE_DURATION,
    transition: str = "fade",
) -> str:
    """
    Crossfade transition between two video streams.
    Transitions: fade, fadeblack, fadewhite, distance, wipeleft, wiperight,
                 wipeup, wipedown, slideleft, slideright, slideup, slidedown,
                 smoothleft, smoothright, circlecrop, rectcrop, dissolve,
                 pixelize, diagtl, diagtr, diagbl, diagbr, hlslice, hrslice
    """
    return (
        f"[{input_a}][{input_b}]xfade="
        f"transition={transition}:"
        f"duration={duration}:"
        f"offset={offset}"
        f"[{output_label}]"
    )


def build_audio_mix_filter(
    narration_label: str,
    output_label: str,
) -> str:
    """
    Audio processing: normalize narration.
    """
    return (
        f"[{narration_label}]"
        f"loudnorm=I=-16:LRA=11:TP=-1.5"
        f"[{output_label}]"
    )


class FilterGraphBuilder:
    """
    High-level builder that constructs the complete FFmpeg filtergraph
    for a multi-scene video with transitions, text overlays, and audio.
    """

    def __init__(
        self,
        width: int = config.DEFAULT_WIDTH,
        height: int = config.DEFAULT_HEIGHT,
        fps: int = config.DEFAULT_FPS,
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.filters: List[str] = []
        self._counter = 0

    def _label(self, prefix: str = "v") -> str:
        self._counter += 1
        return f"{prefix}{self._counter}"

    def build_scene_pipeline(
        self,
        input_index: int,
        duration: float,
        text_overlay: Optional[str] = None,
        ken_burns: bool = True,
        color_grade: bool = True,
        vignette: bool = True,
        fade_in: float = 0.3,
        fade_out: float = 0.3,
    ) -> str:
        """
        Build complete filter chain for a single scene:
        input Ã¢ÂÂ scale Ã¢ÂÂ ken_burns Ã¢ÂÂ color_grade Ã¢ÂÂ vignette Ã¢ÂÂ fade Ã¢ÂÂ text Ã¢ÂÂ output
        """
        current = f"{input_index}:v"

        # Step 1: Scale + set timing
        scaled = self._label("sc")
        self.filters.append(
            f"[{current}]scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
            f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1,fps={self.fps},"
            f"trim=duration={duration},setpts=PTS-STARTPTS"
            f"[{scaled}]"
        )
        current = scaled

        # Step 2: Ken Burns zoom (lightweight scale+crop approach)
        if ken_burns:
            kb = self._label("kb")
            # Use scale animation: upscale slightly, then crop center
            # This is much faster than zoompan filter
            zoom_pct = 5  # 5% zoom
            w_big = int(self.width * (1 + zoom_pct / 100))
            h_big = int(self.height * (1 + zoom_pct / 100))
            # Animate crop position from top-left toward center
            total_frames = int(duration * self.fps)
            crop_x = f"(in_w-{self.width})*t/{duration}"
            crop_y = f"(in_h-{self.height})*t/{duration}"
            self.filters.append(
                f"[{current}]scale={w_big}:{h_big},"
                f"crop={self.width}:{self.height}:{crop_x}:{crop_y}"
                f"[{kb}]"
            )
            current = kb

        # Step 3: Color grading
        if color_grade:
            cg = self._label("cg")
            self.filters.append(
                build_color_grade_filter(current, cg, saturation=1.15, contrast=1.05)
            )
            current = cg

        # Step 4: Vignette
        if vignette:
            vig = self._label("vg")
            self.filters.append(build_vignette_filter(current, vig))
            current = vig

        # Step 5: Fade in/out
        if fade_in > 0 or fade_out > 0:
            fd = self._label("fd")
            self.filters.append(
                build_fade_filter(current, fd, fade_in, fade_out, duration)
            )
            current = fd

        # Step 6: Text overlay
        if text_overlay:
            txt = self._label("tx")
            text_start = 0.8  # text appears 0.8s into scene
            text_end = duration - 0.5
            self.filters.append(
                build_text_overlay_filter(
                    current, txt, text_overlay,
                    start_time=text_start, end_time=text_end
                )
            )
            current = txt

        return current

    def build_transitions(
        self,
        scene_labels: List[str],
        scene_durations: List[float],
        transition: str = "fade",
        xfade_duration: float = config.CROSSFADE_DURATION,
    ) -> str:
        """
        Chain multiple scenes together with crossfade transitions.
        Returns the final output label.
        """
        if len(scene_labels) == 1:
            return scene_labels[0]

        current = scene_labels[0]
        cumulative_offset = scene_durations[0] - xfade_duration

        for i in range(1, len(scene_labels)):
            out = self._label("xf")
            self.filters.append(
                build_xfade_filter(
                    current, scene_labels[i], out,
                    offset=cumulative_offset,
                    duration=xfade_duration,
                    transition=transition
                )
            )
            current = out
            # Next offset: add this scene's duration minus one crossfade
            cumulative_offset += scene_durations[i] - xfade_duration

        return current

    def get_filtergraph(self) -> str:
        """Return the complete filtergraph string."""
        return ";".join(self.filters)
