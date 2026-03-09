# Spiral Render Engine

Spiral Studios — AI Video Render Engine

**Stack:** Python 3.11 + FFmpeg + Docker

## Quick Start

```bash
git clone https://github.com/orangeviagens/spiral-render.git
cd spiral-render
cp .env.example .env
# Edit .env with your API keys
docker compose up -d --build
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /render | Start full video production (async) |
| GET | /status/:id | Check job status |
| GET | /health | Health check |
| GET | /jobs | List all jobs |

## Architecture

```
Topic → Claude AI Script → ElevenLabs Narration → Pexels Stock → FFmpeg Render → Supabase Upload
```
