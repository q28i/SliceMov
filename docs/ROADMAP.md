# SliceMov / PeakCut Enhanced — Feature Roadmap

This document outlines future milestones and architectural enhancements for SliceMov, building on the universal clipping, multi-platform publishing, podcast rendering, and profile engines established in v2.0.

---

## Completed in Current Milestone (v2.0)

- [x] **P0: Post Now & Publishing State Engine Repair**:
  - Immediate Post Now processing without unintended scheduling delays.
  - Expediting existing scheduled jobs without creating duplicate queue items.
  - Safe reconciliation state for network failures and unknown upload states.
  - Controlled retries for failed posts and race condition prevention.
  - Preservation of multi-channel live stream recording buffers and clipping.
- [x] **P1: Universal Media Ingestion**:
  - Live streams: YouTube, Twitch, Kick (with rolling buffer capture).
  - VODs and long-form video files (MP4, MOV, MKV, WebM, etc.).
  - Audio podcast files (MP3, WAV, M4A, AAC, OGG) with automatic video track synthesis.
  - RSS podcast feed parsing and single-click episode import.
- [x] **P1: 6 Universal Clipping Profiles**:
  - `livestream`: Reaction detection, chat spike triggers, emotion peaks.
  - `podcast`: Coherence, complete thoughts, actionable insights, sentence integrity.
  - `gaming`: Highlights, clutch victories, fails, game context.
  - `interview`: Question-and-answer context retention.
  - `educational`: Concise explanations, counter-intuitive facts, key takeaways.
  - `general`: Universal scene pacing, humor, standout moments.
  - Heuristic non-AI speech density & discourse marker fallback.
- [x] **P2: Audio Podcast Video Synthesizer**:
  - 1080x1920 vertical format.
  - Live animated audio waveform (`showwaves`).
  - Episode artwork card and title metadata.
  - Word-level burned-in ASS captions.
- [x] **P3: Multi-Platform Social Publishing**:
  - YouTube Shorts (official OAuth2 & Data API v3).
  - Instagram Reels (official Meta Graph API).
  - TikTok (official Content Posting API with compliant manual export fallback).
  - Fully independent per-platform state tracking and batch publishing.
- [x] **P4: Visual Presets & Layouts**:
  - 9 visual presets: `bounce`, `hype`, `clean`, `streamer_bold`, `karaoke`, `gaming_hype`, `clean_podcast`, `minimal`, `high_contrast`.
  - 5 layouts: `blur`, `zoom`, `crop`, `original`, `square`.
  - Hardware accelerated rendering via local NVIDIA NVENC (`h264_nvenc`).

---

## Milestone 2.1: OpenFilm Timeline Interoperability

- [ ] **OpenFilm Project Exporter**:
  - Generate a zipped `film.html` bundle containing source video, ASS-to-CSS animated captions, and declarative tracks.
  - Allow users to download and inspect projects in any modern browser without external software.
- [ ] **Dual-Engine Rendering Option**:
  - Primary: Ultra-fast local NVENC FFmpeg pipeline (300-600x real-time).
  - Secondary: Headless Chromium frame capture for complex CSS/WebGL shaders and visual effects.

---

## Milestone 2.2: Intelligent Computer Vision & Face Tracking

- [ ] **Dynamic Face & Speaker Centering**:
  - Integrate lightweight, local face tracking (MediaPipe or OpenCV Haar cascades) to dynamically pan the 9:16 vertical crop to follow the active speaker.
  - Split-screen two-person podcast layout (interviewer top, guest bottom) automatically detected via face detection.
- [ ] **Active Speaker Detection**:
  - Audio-visual synchrony to switch focal point when multiple speakers take turns talking.

---

## Milestone 2.3: AI B-Roll & Visual Enrichment

- [ ] **Automatic B-Roll Insertion**:
  - Analyze transcript nouns and concepts to suggest and overlay contextual free stock video (Pexels / Pixabay API).
- [ ] **Interactive Dynamic Waveforms**:
  - Additional customizable waveform visualizers (circular spectrum, bar frequency analyzer, glow pulses).
- [ ] **Sound Effects & Stingers**:
  - Subtle transition whooshes and punctuation audio effects at topic boundaries.

---

## Milestone 2.4: Multilingual Dubbing & Lip Sync

- [ ] **Local Multilingual Speech-to-Speech**:
  - Seamlessly dub clips into Spanish, Hindi, German, Japanese using local voice cloning (e.g. Coqui TTS / XTTS).
- [ ] **Automatic Dual-Language Captions**:
  - Display original audio with secondary translated subtitles underneath for global audience engagement.

