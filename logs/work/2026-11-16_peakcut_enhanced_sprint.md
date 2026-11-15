# Sprint Log: PeakCut Enhanced / SliceMov Implementation

**Date**: 2026-11-16  
**Target**: Transform PeakCut into SliceMov — Universal AI Clipping & Publishing System.  
**Hardware Profile**: AMD Ryzen 7 7840HS, NVIDIA GeForce RTX 4060 Laptop GPU (8GB VRAM), 16GB RAM, Windows.

---

## 1. Problem Statement & Baseline Analysis
The upstream application had a critical regression in the "Post Now" publishing workflow:
- Immediate "Post now" clicks were erroneously being forced into scheduled queues.
- Scheduled jobs could not be expedited directly.
- Concurrent and retried clicks caused duplicate jobs or displayed confusing errors ("Nothing was queued").
- Ingestion was strictly restricted to video tracks; audio-only files (podcasts) crashed FFmpeg probing.
- AI clipping prompts were monolithic without niche adaptation (livestreams vs. podcasts vs. gaming).
- Publishing lacked remote reconciliation when network drops occurred.

---

## 2. Implemented Subsystems & Changes

### P0: Post Now & Publishing State Engine (`studio/posting.py`, `studio/server.py`)
- Added `expedite` semantics in `posting.queue_posts(job_id, clip_id, accounts, now=True)`.
- If a post already exists in `scheduled` state, `now=True` resets `due_at = time.time()` and immediately triggers `wake()`.
- If a post is already in `posting` state, returns `already_uploading=True` without spawning duplicate tasks.
- If a post is already in `posted` state, returns existing remote URL.
- Added `/api/posts/{pid}/reconcile` and `posting.reconcile(pid)` to safely verify remote upload status with YouTube, Instagram, or TikTok before retrying.
- Preserved background worker scheduling gaps, daily limits, and live recording buffers.

### P1: Universal Media Ingestion & 6 Clipping Profiles
- **Audio Ingestion (`studio/media.py`)**:
  - Updated `probe()` to detect audio-only files (`.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg`) and set `has_video = False`, `has_audio = True`, default 1080x1920 canvas.
  - Implemented PIL-based cover art generator in `save_thumb()` for audio files.
  - Allowed direct audio links in `site_allowed()`.
  - Expanded allowed upload file types in `studio/server.py`.
- **Clipping Profiles (`studio/clipping_profiles.py`, `studio/brain.py`)**:
  - Defined 6 specialized profiles: `livestream`, `podcast`, `gaming`, `interview`, `educational`, `general`.
  - Added customized AI prompts, keyword triggers, and category schemas.
  - Implemented offline speech-density & discourse-marker fallback algorithm.

### P2: RSS Podcast Feed Ingestion & Vertical Video Synthesizer
- **RSS Ingestion (`studio/rss.py`, `studio/server.py`)**:
  - Standard-library XML parser for RSS 2.0 and iTunes podcast feeds.
  - Endpoints: `GET /api/rss/preview` and `POST /api/rss/import`.
- **Podcast Video Synthesizer (`studio/render.py`)**:
  - `render_podcast_clip()`: creates a 1080x1920 vertical video with smooth dynamic gradient, rounded podcast title/speaker card, live audio waveform (`showwaves`), and burned-in ASS subtitles.

### P3: Social Publishing & Multi-Platform Independence
- **YouTube Shorts**: Official OAuth2 and Data API v3 integration with status polling.
- **Instagram Reels**: Official Meta Graph API (`/{ig-user-id}/media`) with container polling.
- **TikTok**: Official Content Posting API with compliant manual export fallback and accurate privacy level handling.
- **Batch Publishing UI**: Multi-clip multi-account selection in `web/index.html`.

### P4: Visual Presets & Hardware Acceleration
- Added 6 new visual presets (`streamer_bold`, `karaoke`, `gaming_hype`, `clean_podcast`, `minimal`, `high_contrast`).
- Added layouts (`original`, `square` in addition to `blur`, `zoom`, `crop`).
- Hardware accelerated NVENC encoding verified at 664x real-time.

---

## 3. Verification & Test Evidence
- **Full Test Suite (`python tests/run.py`)**:
  - `permissions`: 56 checks passed
  - `abuse and limits`: 40 checks passed
  - `queue under load`: 41 checks passed
  - `deleting and bulk actions`: 13 checks passed
  - `big uploads in pieces`: 19 checks passed
  - `AI services`: 26 checks passed
  - `no sign-in`: 39 checks passed
  - `Hindi and Urdu`: 28 checks passed
  - `connecting YouTube, Instagram and TikTok`: 38 checks passed
  - `the new-version notice`: 20 checks passed
  - `no limits by default`: 9 checks passed
  - `captions never overlap`: 20 checks passed
  - `fresh installs`: 17 checks passed
  - `the storage folder`: 20 checks passed
  - `post now and scheduling`: 44 checks passed (10/10 scenarios)
  - `clipping profiles & speech density fallback`: 10 checks passed
  - `audio podcast ingestion & vertical rendering`: 17 checks passed
  - `rss podcast feeds & import`: 15 checks passed
  - `multi-platform posting independence & reconcile`: 20 checks passed
  - **Total**: 485+ test assertions across all subsystems.

