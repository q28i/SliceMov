# OpenFilm Research & Future Integration Blueprint

## Executive Summary

OpenFilm is an open-source (MIT-licensed), programmatic, HTML/CSS/JS-based video editing engine. Rather than using proprietary timeline formats (like Premiere's XML or Final Cut's FCPXML), OpenFilm treats video timelines as declarative web documents (`film.html`) rendered via headless browser automation or native WebRTC pipelines.

This document details OpenFilm's internal architecture, compares it to SliceMov's current pipeline, designs an export interoperability bridge, and plans a multi-phase integration roadmap that maintains SliceMov's lightweight, free-first nature.

---

## 1. OpenFilm Architectural Analysis

### The `film.html` Timeline Format
OpenFilm represents a video project as a single, self-contained HTML file called `film.html`. Key concepts:

1. **Temporal Media Fragments**:
   Video and audio elements use standard W3C Media Fragments URI syntax for trimming:
   ```html
   <video src="assets/raw_stream.mp4#t=14.5,42.0" class="track-video"></video>
   ```
2. **Layer Compositing via CSS Grid & Absolute Coordinates**:
   Visual placement, scaling, blurring, and transitions are declared purely in CSS:
   ```css
   .clip-vertical-blur {
     position: absolute;
     width: 1080px;
     height: 1920px;
     overflow: hidden;
   }
   .bg-blur {
     filter: blur(20px) brightness(0.6);
     transform: scale(2.2);
   }
   ```
3. **Audio Bus & Crossfades**:
   Audio tracks are declared via `<audio>` elements with Web Audio API nodes or data attributes specifying gain, fades, and ducking curves:
   ```html
   <audio src="assets/audio.mp3#t=14.5,42.0" data-gain="1.0" data-fade-in="0.5"></audio>
   ```
4. **Captions & Overlays**:
   Captions are native HTML/SVG elements styled with CSS animations, eliminating the rigid styling limitations of `.ass` subtitles:
   ```html
   <div class="caption-container">
     <span class="word active" style="color: #00FFCC">BREAKTHROUGH</span>
   </div>
   ```

### OpenFilm Rendering Pipeline
- In production, OpenFilm drives headless Chromium (via Puppeteer/Playwright) to capture each frame via Chrome DevTools Protocol (CDP) `Page.screencastFrame` or `captureScreenshot`, feeding raw RGBA frames into an FFmpeg stdin pipe:
  ```
  [film.html (DOM)] -> [Chromium Headless] -> [Raw RGBA stream] -> [FFmpeg pipe] -> [output.mp4]
  ```
- **Strengths**: Unlimited visual flexibility (any CSS animation, WebGL shader, SVG morphing works).
- **Trade-offs for SliceMov**: Headless browser rendering is significantly slower than native C/GPU FFmpeg (averaging 5-15 fps vs 300-600 fps with NVENC), and bundles a ~300MB Chromium dependency.

---

## 2. SliceMov vs. OpenFilm Comparison

| Capability | SliceMov (Current) | OpenFilm |
|---|---|---|
| **Timeline Engine** | FFmpeg filtergraphs + ASS subtitles | Declarative HTML5/CSS DOM |
| **Render Speed** | 300x - 600x real-time (NVENC hardware) | 0.5x - 2.0x real-time (Chromium frame capture) |
| **Dependencies** | Python + FFmpeg (~90MB) | Node.js + Chromium + FFmpeg (~400MB) |
| **Caption Flexibility** | High (ASS word highlighting, 9 presets) | Infinite (full web typography & CSS animations) |
| **Live Streaming Buffer** | Built-in rolling buffer & live clipper | VOD / Post-production oriented |
| **Social Publishing** | Built-in YouTube, Instagram, TikTok | External publishing not included |

---

## 3. SliceMov -> OpenFilm Interoperability Bridge

To provide OpenFilm capabilities without bloating SliceMov's core or slowing down rendering, SliceMov implements a project bundle exporter.

### Export Architecture
When a user clicks "Export to OpenFilm" in SliceMov:
1. SliceMov creates a clean directory `openfilm_project_<job_id>/`:
   ```
   openfilm_project_abc123/
   ├── film.html             <-- Declarative timeline
   ├── style.css             <-- Typography and transitions
   └── assets/
       ├── source.mp4        <-- Symlink or copy of raw footage
       └── captions.json     <-- Word-level timestamp payload
   ```
2. **Generated `film.html` Template**:
   ```html
   <!DOCTYPE html>
   <html lang="en">
   <head>
     <meta charset="utf-8">
     <title>{{ title }} - OpenFilm Timeline</title>
     <style>
       * { margin: 0; padding: 0; box-sizing: border-box; }
       body { width: 1080px; height: 1920px; background: #000; overflow: hidden; }
       .layer-bg { position: absolute; width: 100%; height: 100%; filter: blur(30px); transform: scale(2.2); }
       .layer-fg { position: absolute; width: 1080px; height: 1920px; object-fit: contain; }
       .captions { position: absolute; bottom: 350px; width: 100%; text-align: center; }
       .word { font-family: 'Montserrat', sans-serif; font-size: 72px; font-weight: 900; color: #fff; }
       .word.highlight { color: #00FFCC; transform: scale(1.15); }
     </style>
   </head>
   <body>
     <!-- Video Track with Media Fragment Trim -->
     <video class="layer-bg" src="assets/source.mp4#t={{ start }},{{ end }}" muted></video>
     <video class="layer-fg" src="assets/source.mp4#t={{ start }},{{ end }}"></video>

     <!-- Word-Level Captions Container -->
     <div class="captions" id="caption-box"></div>

     <script>
       const words = {{ words_json }};
       // Browser-native timing sync
     </script>
   </body>
   </html>
   ```

---

## 4. Future Milestone Roadmap

- **Milestone 2.1: OpenFilm Project Export**:
  Add `POST /api/jobs/{id}/clips/{cid}/export-openfilm` returning a zipped `film.html` bundle.
- **Milestone 2.2: Dual-Engine Switch**:
  Allow users to toggle between "Fast FFmpeg NVENC Render" (instant generation) and "High-Fidelity Web Render" (for complex CSS animations and B-roll overlays).
- **Milestone 2.3: Visual Web Inspector**:
  Embed OpenFilm's interactive preview in an iframe within SliceMov's clip editor for pixel-perfect drag-and-drop repositioning of subtitles and stickers.

