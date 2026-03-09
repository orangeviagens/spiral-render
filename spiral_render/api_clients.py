"""
Spiral Studios — API Clients

Clients for external services: Pexels, ElevenLabs, Anthropic, Supabase.
Uses only 'requests' library (stdlib-compatible).
"""
import json
import os
import logging
import requests
from typing import Dict, List, Optional

from . import config

logger = logging.getLogger("spiral_render.api")


# ============================================================
# PEXELS — Stock Video Search & Download
# ============================================================

class PexelsClient:
    """Search and download stock footage from Pexels."""

    BASE_URL = "https://api.pexels.com"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.PEXELS_API_KEY
        self.session = requests.Session()
        self.session.headers["Authorization"] = self.api_key

    def search_videos(
        self,
        query: str,
        orientation: str = "landscape",
        size: str = "large",
        per_page: int = 10,
        min_duration: int = 5,
    ) -> List[Dict]:
        """
        Search for videos. Returns list of video info dicts.
        Each has: id, url, duration, width, height, download_url
        """
        resp = self.session.get(
            f"{self.BASE_URL}/videos/search",
            params={
                "query": query,
                "orientation": orientation,
                "size": size,
                "per_page": per_page,
            }
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for video in data.get("videos", []):
            if video.get("duration", 0) < min_duration:
                continue

            # Find best quality file (prefer 1080p)
            files = sorted(
                video.get("video_files", []),
                key=lambda f: abs((f.get("height") or 0) - 1080)
            )
            if files and (files[0].get("height") or 0) >= 720:
                results.append({
                    "id": video["id"],
                    "duration": video["duration"],
                    "width": files[0].get("width"),
                    "height": files[0].get("height"),
                    "download_url": files[0]["link"],
                    "quality": f"{files[0].get('width')}x{files[0].get('height')}",
                })

        return results

    def download_clip(self, url: str, output_path: str) -> str:
        """Download a video clip to local file."""
        logger.info(f"Downloading clip: {os.path.basename(output_path)}")
        resp = self.session.get(url, stream=True)
        resp.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"  Downloaded: {size_mb:.1f} MB")
        return output_path

    def fetch_clips_for_scene(
        self,
        query: str,
        scene_id: int,
        needed_duration: float,
        max_clips: int = 5,
    ) -> List[str]:
        """
        Search and download clips for a scene.
        Downloads enough clips to cover the needed duration.
        Returns list of local file paths.
        """
        scene_dir = os.path.join(config.CLIPS_DIR, f"scene_{scene_id}")
        os.makedirs(scene_dir, exist_ok=True)

        videos = self.search_videos(query, per_page=max_clips)
        downloaded = []
        total_duration = 0

        for i, video in enumerate(videos):
            if total_duration >= needed_duration:
                break

            clip_path = os.path.join(scene_dir, f"clip_{i:03d}.mp4")
            if not os.path.exists(clip_path):
                self.download_clip(video["download_url"], clip_path)

            downloaded.append(clip_path)
            total_duration += video["duration"]

        return downloaded


# ============================================================
# ELEVENLABS — Text-to-Speech
# ============================================================

class ElevenLabsClient:
    """Generate narration audio using ElevenLabs TTS."""

    BASE_URL = "https://api.elevenlabs.io/v1"

    def __init__(self, api_key: str = None, voice_id: str = None):
        self.api_key = api_key or config.ELEVENLABS_API_KEY
        self.voice_id = voice_id or config.ELEVENLABS_VOICE_ID
        self.session = requests.Session()
        self.session.headers["xi-api-key"] = self.api_key

    def generate_speech(
        self,
        text: str,
        output_path: str,
        model: str = "eleven_multilingual_v2",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
    ) -> str:
        """
        Generate speech audio from text.
        Returns path to output MP3 file.
        """
        logger.info(f"Generating narration ({len(text)} chars)...")

        resp = self.session.post(
            f"{self.BASE_URL}/text-to-speech/{self.voice_id}",
            headers={"Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": model,
                "voice_settings": {
                    "stability": stability,
                    "similarity_boost": similarity_boost,
                }
            }
        )
        resp.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(resp.content)

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"  Narration saved: {size_mb:.1f} MB")
        return output_path

    def generate_narration_from_script(
        self,
        script: Dict,
        output_path: str = None,
    ) -> str:
        """
        Combine all scene narrations into one audio file.
        """
        if output_path is None:
            output_path = os.path.join(config.AUDIO_DIR, "narration.mp3")

        # Combine all narration text with pauses
        full_text = ""
        for scene in script.get("scenes", []):
            narration = scene.get("narration", "")
            full_text += narration + " ... "  # ellipsis = natural pause

        return self.generate_speech(full_text.strip(), output_path)


# ============================================================
# ANTHROPIC — Script Generation
# ============================================================

class AnthropicClient:
    """Generate video scripts using Claude AI."""

    BASE_URL = "https://api.anthropic.com/v1"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.ANTHROPIC_API_KEY
        self.session = requests.Session()
        self.session.headers.update({
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        })

    def generate_script(
        self,
        channel: str,
        topic: str,
        duration_minutes: int = 5,
        num_scenes: int = 8,
    ) -> Dict:
        """
        Generate a complete video script with scenes.
        Returns parsed JSON with title, description, tags, scenes.
        """
        prompt = f"""Generate a YouTube video script for the channel "{channel}" about: {topic}

Requirements:
- Total duration: approximately {duration_minutes} minutes
- {num_scenes} scenes
- Each scene has: scene_id, scene_description (for stock footage search), narration (spoken text), duration_seconds, text_overlay (short text shown on screen)
- Narration should be engaging, cinematic, with dramatic pauses marked by "..."
- Include a hook opening, main content, and CTA closing

Return ONLY valid JSON with this structure:
{{
  "title": "...",
  "description": "...",
  "tags": ["..."],
  "scenes": [
    {{
      "scene_id": 1,
      "scene_description": "...",
      "narration": "...",
      "duration_seconds": 15,
      "text_overlay": "..."
    }}
  ]
}}"""

        resp = self.session.post(
            f"{self.BASE_URL}/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        resp.raise_for_status()
        data = resp.json()

        # Parse response
        text = data["content"][0]["text"]
        # Extract JSON from potential markdown code blocks
        if "```" in text:
            text = text.split("```json")[-1].split("```")[0] if "```json" in text else text.split("```")[1].split("```")[0]

        return json.loads(text.strip())


# ============================================================
# SUPABASE — Storage Upload
# ============================================================

class SupabaseStorageClient:
    """Upload files to Supabase Storage."""

    def __init__(self, url: str = None, key: str = None):
        self.url = (url or config.SUPABASE_URL).rstrip("/")
        self.key = key or config.SUPABASE_KEY
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.key}",
            "apikey": self.key,
        })

    def upload_file(
        self,
        bucket: str,
        remote_path: str,
        local_path: str,
        content_type: str = None,
    ) -> str:
        """
        Upload a file to Supabase Storage.
        Returns the public URL.
        """
        if content_type is None:
            ext = os.path.splitext(local_path)[1].lower()
            content_type = {
                ".mp4": "video/mp4",
                ".mp3": "audio/mpeg",
                ".png": "image/png",
                ".jpg": "image/jpeg",
            }.get(ext, "application/octet-stream")

        with open(local_path, "rb") as f:
            resp = self.session.post(
                f"{self.url}/storage/v1/object/{bucket}/{remote_path}",
                headers={"Content-Type": content_type},
                data=f,
            )

        if resp.status_code in (200, 201):
            public_url = f"{self.url}/storage/v1/object/public/{bucket}/{remote_path}"
            logger.info(f"Uploaded to: {public_url}")
            return public_url
        else:
            # Try upsert
            with open(local_path, "rb") as f:
                resp = self.session.put(
                    f"{self.url}/storage/v1/object/{bucket}/{remote_path}",
                    headers={"Content-Type": content_type},
                    data=f,
                )
            resp.raise_for_status()
            public_url = f"{self.url}/storage/v1/object/public/{bucket}/{remote_path}"
            return public_url
