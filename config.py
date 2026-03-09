"""
Spiral Studios — Render Engine Configuration
"""
import os

# === Paths ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(BASE_DIR, "workspace")
CLIPS_DIR = os.path.join(WORK_DIR, "clips")
AUDIO_DIR = os.path.join(WORK_DIR, "audio")
OUTPUT_DIR = os.path.join(WORK_DIR, "output")
TEMP_DIR = os.path.join(WORK_DIR, "temp")

# === FFmpeg ===
FFMPEG_BIN = "ffmpeg"
FFPROBE_BIN = "ffprobe"

# === Fonts ===
FONT_BOLD = os.environ.get(
    "FONT_BOLD",
    "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"
)
FONT_REGULAR = os.environ.get(
    "FONT_REGULAR",
    "/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf"
)

# === Video Defaults ===
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_FPS = 30
DEFAULT_CODEC = "libx264"
DEFAULT_PRESET = "medium"  # ultrafast|superfast|veryfast|faster|fast|medium|slow|slower|veryslow
DEFAULT_CRF = 20  # 18=visually lossless, 23=default, 28=low quality
DEFAULT_AUDIO_CODEC = "aac"
DEFAULT_AUDIO_BITRATE = "192k"
DEFAULT_PIXEL_FORMAT = "yuv420p"

# === Effects Defaults ===
CROSSFADE_DURATION = 0.8  # seconds
KEN_BURNS_ZOOM = 1.05  # 5% zoom over clip duration
TEXT_FONT_SIZE = 52
TEXT_COLOR = "white"
TEXT_BORDER_WIDTH = 3
TEXT_BORDER_COLOR = "black"
TEXT_POSITION_Y = "(h-th-h*0.12)"  # 12% from bottom
TEXT_FADE_IN = 0.6  # seconds
TEXT_FADE_OUT = 0.6  # seconds

# === API Keys (from environment) ===
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "uaXmxAsXACgEChuJxq9s")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# === Create directories ===
for d in [WORK_DIR, CLIPS_DIR, AUDIO_DIR, OUTPUT_DIR, TEMP_DIR]:
    os.makedirs(d, exist_ok=True)
