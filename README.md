# SliceMov

**SliceMov** is a universal, open-source AI clipping, speech-to-text transcription, media processing, and social publishing platform. Designed to run locally on your workstation or self-hosted on a dedicated server, SliceMov transforms long-form livestreams, podcasts, interviews, gaming videos, and educational media into viral, captioned 9:16 vertical shorts ready for publishing.

SliceMov builds upon the foundation of [PeakCut](https://github.com/haziqahmedqasmi/peakcut) by Haziq Ahmed Qasmi, substantially extending it with universal multi-format media ingestion, specialized AI clipping profiles, audio podcast visualization, GPU acceleration, enterprise SSRF protections, duplicate-upload prevention, and an active roadmap toward mobile Android support.

---

## Key Capabilities

### 1. Universal Media Ingestion
- **Livestreams & VODs:** Direct ingestion from YouTube, Twitch, and Kick. Records active livestreams in real-time into rolling memory/disk buffers and clips highlights as they happen.
- **Local Media & Formats:** Accepts video (`.mp4`, `.mov`, `.mkv`, `.webm`, `.m4v`, `.ts`, `.flv`) and pure audio formats (`.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg`).
- **Podcast RSS Feeds:** Ingest podcast feeds directly via RSS URL, with automatic XML sanitization, enclosure parsing, and episode selection.
- **Manual Clip Selection:** Precision range selection for human-curated segments.

### 2. Specialized Clipping Profiles
AI prompt contracts and discovery logic tailored to distinct content genres:
- **Livestream:** Prioritizes high emotional spikes, reaction moments, chat bursts, and self-contained humorous incidents.
- **Podcast:** Emphasizes strong standalone arguments, key insights, debates, advice, and coherent sentence boundaries.
- **Gaming:** Targets clutch victories, fails, hype plays, funny comms, and unexpected match outcomes.
- **Interview:** Isolates compelling questions, candid disclosures, and memorable anecdotes.
- **Educational:** Identifies standalone explanations, step-by-step guides, demonstrations, and actionable takeaways.
- **General Video:** Balanced viral engagement scoring for versatile content.

### 3. Audio Podcast Visualization & Layouts
- **Pure Audio to 9:16 Video:** Generates vertical video from audio sources with dynamic background canvases, blurred ambient backdrops, and animated multi-bar waveforms.
- **Visual Styles & Layouts:** Multiple framing options:
  - *Full vertical:* Centered face/content cropping.
  - *Split screen:* Multi-speaker top/bottom or facecam-over-gameplay framing.
  - *Podcast visualizer:* Dynamic waveform and branding on vertical canvas.
- **Kinetic Subtitles:** Hardware-rendered ASS subtitles with word-by-word active highlighting, emoji integration, and custom typography.

### 4. Hardware Acceleration & Local Processing
- **NVIDIA GPU Acceleration:** Automatic detection and utilization of NVENC (`h264_nvenc`) for ultrafast encoding, with seamless automatic fallback to `libx264` if unavailable.
- **Local Speech-to-Text:** Bundled offline ASR via Sherpa-ONNX (`parakeet-tdt`), with optional YouTube caption ingestion for instant clip discovery without redundant re-transcription.

### 5. Multi-Platform Publishing & Protection
- **Direct Social Integration:** One-click OAuth connecting YouTube Shorts, Instagram Reels, and TikTok.
- **Deterministic Upload Protection:** Session-based upload locks and persistent upload fingerprints prevent duplicate postings during network errors or ambiguous platform responses.
- **Paced Scheduling:** Smart queueing ensures staggered releases even following server restarts or unexpected downtime.
- **Instagram Direct Uploads:** Resumable direct byte uploads to Meta Graph API without mandating public HTTPS hosting.

### 6. Security Hardening
- **Anti-SSRF Protection:** Multi-layer private IP blocking, DNS rebinding mitigation, redirect chain inspection, and strict mime/magic-byte checks on all external URL imports.
- **Sandboxed Execution:** Path traversal defenses and short-folder clip generation to circumvent OS path length limitations (e.g. Windows MAX_PATH).

---

## Architecture Overview

```
                      ┌──────────────────────────────────────┐
                      │            Media Ingestion           │
                      │  YouTube • Twitch • Kick • RSS • Files│
                      └──────────────────┬───────────────────┘
                                         │
                      ┌──────────────────▼───────────────────┐
                      │    Speech-to-Text & Signal Engine    │
                      │  Sherpa-ONNX / Audio Amplitude Logs  │
                      └──────────────────┬───────────────────┘
                                         │
                      ┌──────────────────▼───────────────────┐
                      │          AI Brain & Profiles         │
                      │ Gemini • OpenAI • Groq • Ollama • XAI│
                      └──────────────────┬───────────────────┘
                                         │
                      ┌──────────────────▼───────────────────┐
                      │     Render & Compositing Engine      │
                      │  FFmpeg • NVENC • ASS Subtitles      │
                      └──────────────────┬───────────────────┘
                                         │
                      ┌──────────────────▼───────────────────┐
                      │     Publishing & Queue Management    │
                      │   YouTube Shorts • Instagram • TikTok│
                      └──────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites
- **Python:** 3.10 or newer.
- **FFmpeg:** Must be installed and present on your `PATH`.
  - Windows: `winget install Gyan.FFmpeg`
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`
- *(Optional)* NVIDIA GPU with CUDA/NVENC drivers for hardware-accelerated video rendering.

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/q28i/SliceMov.git
   cd SliceMov
   ```

2. **Set up a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start SliceMov:**
   ```bash
   python -m studio.server
   ```
   *(On first run, the local speech model ~480 MB downloads automatically).*

5. **Open the web dashboard:**
   Navigate to [http://127.0.0.1:8765](http://127.0.0.1:8765) (or your configured port). SliceMov opens directly to the dashboard with zero required setup.

6. **Configure AI (Bring Your Own Key):**
   Go to **Settings → AI**. Choose Google Gemini (free tier supported), OpenAI, Grok, Groq, Anthropic, OpenRouter, or local Ollama. Paste your key and click **Save and test**.

---

## Configuration & Environment Variables

SliceMov can be configured via environment variables or a `.env` file in the root directory (see `.env.example`). Both `SLICEMOV_*` and legacy `PEAKCUT_*` variables are supported.

| Variable | Default | Description |
|---|---|---|
| `SLICEMOV_PORT` | `8765` | Local port the HTTP server listens on |
| `SLICEMOV_DATA` | `./data` | Directory storing videos, clips, models, and database |
| `SLICEMOV_ACCOUNTS` | `0` | Set `1` to enable multi-user authentication (for public hosting) |
| `SLICEMOV_PUBLIC_URL` | `http://127.0.0.1:8765` | Public address (required for OAuth redirects and webhooks) |
| `SLICEMOV_AI_PROVIDER` | `gemini` | Default AI provider (`gemini`, `openai`, `groq`, `ollama`, etc.) |
| `SLICEMOV_UPDATE_REPO` | `q28i/SliceMov` | GitHub repository for background update checks |

---

## Testing & Quality Assurance

SliceMov includes a comprehensive automated test suite covering all media pipelines, anti-SSRF defenses, publishing safeguards, and API endpoints.

To run the full test suite in an isolated sandbox:
```bash
python tests/run.py
```

To run end-to-end media workflow validation (video/audio/podcast rendering & NVENC fallback):
```bash
python tests/validate_media_workflows.py
```

---

## Roadmap: Upcoming Android Support

SliceMov is actively architecting a native **Android client & mobile companion**:
- **Mobile Ingestion:** Share videos and links directly from the YouTube, Twitch, or podcast apps via Android's native Share Sheet.
- **On-the-Go Review:** Mobile-optimized swipe review interface for approving or discarding generated clips.
- **Remote Controller:** Connect to your home SliceMov server instance to monitor long-running livestream recordings and trigger clip renders remotely.
- **On-Device Lightweight Processing:** Exploration of on-device Whisper/Sherpa models for low-power mobile clipping.

---

## Upstream Attribution & License

SliceMov is open-source software licensed under the **[MIT License](LICENSE)**.

SliceMov originated as an enhanced, independent evolution of [PeakCut](https://github.com/haziqahmedqasmi/peakcut) by **Haziq Ahmed Qasmi**. We gratefully acknowledge the architecture and foundational concepts established by PeakCut and its contributors.

- Portions Copyright (c) 2026 PeakCut contributors
- Copyright (c) 2026 SliceMov contributors (`q28i`)
