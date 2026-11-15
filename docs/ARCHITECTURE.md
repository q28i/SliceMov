# SliceMov / PeakCut Enhanced — System Architecture

## Overview

SliceMov (PeakCut Enhanced) is a modular, free-first, locally-hosted AI clipping and publishing application. It transforms long-form media—such as YouTube/Twitch/Kick livestreams, recorded videos, audio podcasts, and interviews—into short-form vertical videos (9:16) with word-level captions, visual presets, and multi-platform distribution.

The system is architected around four independent, decoupled subsystems:

```
+---------------------------------------------------------------------------------------------------+
|                                      SliceMov Core Subsystems                                     |
+---------------------------------------------------------------------------------------------------+
|  A. MEDIA INGESTION                                                                               |
|  - Stream Capture (YouTube / Twitch / Kick rolling buffer)                                        |
|  - Video Ingestion (MP4 / MOV / MKV / WebM)                                                       |
|  - Audio Podcast Ingestion (MP3 / WAV / M4A / AAC / OGG)                                          |
|  - RSS Feed Ingestion (xml.etree parser, episode downloader)                                      |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|  B. CLIPPING ENGINE                                                                               |
|  - Transcription: On-device FastConformer (Parakeet TDT / CTC) or Whisper fallback               |
|  - 6 Universal Clipping Profiles: Livestream, Podcast, Gaming, Interview, Educational, General    |
|  - AI Decision Engine: Candidate boundary detection, hook scoring, titles, hashtags              |
|  - Heuristic Fallback: Speech density & discourse markers analysis when offline / non-AI          |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|  C. RENDERING & CLIP OUTPUT                                                                       |
|  - Hardware Acceleration: NVIDIA NVENC (h264_nvenc) with automatic x264 fallback                 |
|  - Dynamic Vertical Video: 9:16 (1080x1920), 1:1 square, or original aspect                      |
|  - Subtitle Engine: Accurate word-level ASS captions with 9 customizable visual styling presets  |
|  - Podcast Generator: Audio visualizer (live waveform, gradient card, metadata banner)            |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|  D. DISTRIBUTION & SOCIAL PUBLISHING                                                              |
|  - Multi-Platform Independence: YouTube Shorts, Instagram Reels, TikTok                          |
|  - Resilient Queue: Post Now, automatic gap enforcement, daily rate caps                          |
|  - State Engine: scheduled -> posting -> posted / failed / reconcile                              |
|  - Reconciliation & Fallbacks: Remote status checks, unblocking retries, compliant manual MP4     |
+---------------------------------------------------------------------------------------------------+
```

---

## Subsystem A: Media Ingestion

### Supported Formats & Sources
- **Live Streams**: YouTube Live, Twitch, Kick (rolling buffer capture via streamlink / yt-dlp).
- **VODs & Remote Video URLs**: YouTube, Twitch VODs, Kick recordings.
- **Local Video Uploads**: `.mp4`, `.mov`, `.mkv`, `.webm`, `.m4v`, `.ts`, `.flv`.
- **Audio Podcasts**: `.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg`.
- **Podcast RSS Feeds**: Standard RSS 2.0 XML with `<enclosure>` audio tracks and iTunes extensions (`studio/rss.py`).

### Unified Ingestion Pipeline
1. **Source Probing (`studio/media.py`)**:
   Uses `ffprobe` to inspect audio and video streams without failing on audio-only media.
   - For audio-only sources: Sets `has_video = False`, `has_audio = True`, and initializes default canvas dimensions to vertical 1080x1920.
2. **Metadata Contract**:
   Every source maintains consistent state stored in SQLite / JSON:
   - `id`: Unique job identifier.
   - `source_type`: `stream`, `file`, `url`, `rss_podcast`.
   - `title`: Extracted or user-specified media title.
   - `uploader`: Original creator or podcast host.
   - `duration`: Total duration in seconds.
   - `has_video`: Boolean flag indicating visual track presence.
   - `has_audio`: Boolean flag indicating audio track presence.
   - `profile`: Selected clipping profile (defaulting to `general`).
   - `creator`: Optional creator workspace isolation.

---

## Subsystem B: Clipping Engine

### Audio Extraction & Transcription
- Audio is extracted as 16kHz mono WAV.
- Transcription uses the local **FastConformer / Parakeet** neural speech model (`data/models`) or Whisper fallback, returning word-level timestamps `[{w, s, e}]`.

### Clipping Profiles (`studio/clipping_profiles.py`)
Provides tailored AI prompts, candidate segment lengths, and scoring criteria:
1. **Livestream**: Detects reactions, loud shouts, chat spikes, and emotional high points.
2. **Podcast**: Prioritizes deep substance, conversational insight, complete sentences, and self-contained arguments.
3. **Gaming**: Highlights clutch victories, epic fails, unexpected glitches, and gaming reactions without mistaking mere volume for quality.
4. **Interview**: Preserves the question-and-answer context so answers make sense independently.
5. **Educational**: Evaluates concise explanations, counter-intuitive facts, and key takeaways.
6. **General Video**: Evaluates narrative pacing, humor, and standout moments across generic video content.

### Non-AI Heuristic Fallback
When no AI provider key is set or when the AI service is unreachable:
- Analyzes speech density (target 2.0 - 3.2 words per second conversational cadence).
- Identifies discourse marker frequencies (`"because"`, `"reason"`, `"secret"`, `"truth"`, `"key"`).
- Automatically proposes top candidate clips with complete word-level bounds, hooks, and titles.

---

## Subsystem C: Rendering and Clip Output

### Hardware Accelerated Rendering (`studio/render.py`)
- **NVIDIA GPU Acceleration**: Probes for `h264_nvenc`. When available, encodes video using NVENC at 600x+ real-time speed.
- **CPU Fallback**: Falls back smoothly to `libx264` (`crf=21`, `preset=veryfast`) if NVENC is unavailable.

### Visual Layouts & Presets
- **Layouts**:
  - `blur`: 9:16 vertical video with blurred background fill.
  - `zoom`: 9:16 vertical video cropped to zoom on focal center.
  - `crop`: 9:16 filled canvas.
  - `original`: Keeps original source aspect ratio with black letterboxing.
  - `square`: 1:1 canvas for square feeds.
- **Visual Caption Presets**:
  - `streamer_bold`: Uppercase cyan highlighted subtitle with heavy drop shadow.
  - `karaoke`: Real-time word-by-word highlighted singing/rhythmic styling.
  - `gaming_hype`: Orange/gold bold high-impact styling.
  - `clean_podcast`: Inter/Poppins clean legible white subtitles for talk shows.
  - `minimal`: Muted monochrome aesthetic subtitle.
  - `high_contrast`: Yellow on black outline for maximum mobile readability.

### Audio Podcast Synthesizer (`render_podcast_clip`)
For audio-only media, synthesizes a dynamic 1080x1920 vertical video containing:
1. Smooth gradient background.
2. Rounded card displaying podcast episode artwork or generated podcast cover.
3. Live audio waveform (`showwaves` filter) perfectly synchronized with speech.
4. Burned-in ASS word-level captions.

---

## Subsystem D: Distribution and Social Publishing

### Supported Platforms
- **YouTube Shorts**: Official Google OAuth2 & YouTube Data API v3 (`videos.insert`). Supports public/unlisted/private visibility.
- **Instagram Reels**: Official Meta Graph API (`/{ig-user-id}/media` & `media_publish`). Supports professional / creator Instagram accounts linked to a Facebook Page.
- **TikTok**: Official TikTok Content Posting API. Respects audited creator scopes and includes compliant manual MP4 export fallback for unapproved apps.

### Publishing Reliability & Semantics
- **Post Now Expedite**: Bypasses internal scheduling delay and publishes immediately without creating duplicate posts.
- **Independent Tracking**: Every destination account maintains its own status (`scheduled`, `posting`, `posted`, `failed`, `cancelled`). A failure on TikTok never blocks YouTube or Instagram.
- **Reconciliation Engine (`POST /api/posts/{id}/reconcile`)**: If network interruptions occur during an upload, queries the remote platform's API using the stored `remote_id` to determine whether the post landed remotely. If verified, updates status to `posted`; if unverified, safely reschedules without duplicate uploads.

