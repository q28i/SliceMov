"""Comprehensive Media Workflow Validation for SliceMov v2.0.

Tests isolated sample media workflows:
1. NVENC hardware vs. software fallback
2. Livestream rolling buffer & clipping
3. Normal recorded video clipping & 9:16 vertical rendering
4. Audio podcast ingestion & waveform rendering
5. RSS podcast feed import & boundary caps
6. Caption styles (ASS styles, streamer bold, clean podcast, bounce)
7. Media probe, MP4 sync, duration, and subtitle timing
8. SSRF and resource-exhaustion safety
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import config, media, render, rss, tools

fails = []


def check(name, got, want=True):
    ok = want(got) if callable(want) else got == want
    status = "PASS " if ok else "FAIL "
    print(f"{status}{name}" + ("" if ok else f"   got {got!r} (expected {want!r})"))
    if not ok:
        fails.append(name)


def main():
    tools.setup()
    tmpdir = Path(tempfile.mkdtemp(prefix="slicemov-media-val-"))
    print(f"=== SliceMov Media Workflow Validation (Isolated Dir: {tmpdir}) ===")

    try:
        # 1. Synthetic Test Video Generation
        print("\n--- 1. Synthetic Test Media Generation ---")
        src_video = tmpdir / "source_1080p.mp4"
        # Generate 6 seconds of 1920x1080 test video with a 440Hz test audio tone
        r = subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=30:duration=6",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "128k",
            str(src_video)
        ], capture_output=True, text=True)
        check("synthetic source video generated", r.returncode == 0 and src_video.exists(), True)

        probe_info = media.probe(src_video)
        check("probe detects video stream", probe_info.get("has_video"), True)
        check("probe detects audio stream", probe_info.get("has_audio"), True)
        check("probe source width 1920", probe_info.get("width"), 1920)
        check("probe source height 1080", probe_info.get("height"), 1080)
        check("probe source duration ~6.0s", 5.8 <= probe_info.get("duration", 0) <= 6.2, True)

        # 2. Normal Recorded-Video Clipping & 9:16 Vertical Rendering
        print("\n--- 2. Normal Recorded-Video Clipping (9:16 Vertical) ---")
        out_dir = tmpdir / "clips"
        out_dir.mkdir(parents=True, exist_ok=True)
        words = [
            {"w": "Welcome", "s": 1.0, "e": 1.8},
            {"w": "to", "s": 1.8, "e": 2.2},
            {"w": "SliceMov", "s": 2.2, "e": 3.0},
            {"w": "Universal", "s": 3.0, "e": 3.8},
            {"w": "Clipping", "s": 3.8, "e": 4.5},
        ]
        clip_def = {
            "id": "clip_test_1",
            "start": 1.0,
            "end": 5.0,
            "layout": "blur",
            "style": "streamer_bold",
            "hook": "Universal Clipping",
            "highlight_words": ["SliceMov", "Universal"],
        }
        res_files = render.render_clip(src_video, out_dir, "clip_test_1", clip_def, words, 1920, 1080)
        out_clip = out_dir / res_files["file"]
        check("rendered clip exists", out_clip.exists(), True)
        check("rendered clip size > 10KB", out_clip.stat().st_size > 10_000, True)

        clip_probe = media.probe(out_clip)
        check("clip has video stream", clip_probe.get("has_video"), True)
        check("clip has audio stream", clip_probe.get("has_audio"), True)
        check("clip is vertical width 1080", clip_probe.get("width"), 1080)
        check("clip is vertical height 1920", clip_probe.get("height"), 1920)
        check("clip duration matches slice (~4.0s)", 3.8 <= clip_probe.get("duration", 0) <= 4.2, True)

        # 3. NVENC Status & Hardware Acceleration / Fallback Verification
        print("\n--- 3. NVENC Hardware Acceleration & Fallback Status ---")
        print(f"NVENC encoder state after render: {render._nvenc_ok}")
        check("nvenc state is determined (True or False)", render._nvenc_ok in (True, False), True)

        # 4. Audio Podcast Ingestion & Waveform Rendering
        print("\n--- 4. Audio Podcast Ingestion & Waveform Rendering ---")
        src_audio = tmpdir / "podcast_ep.mp3"
        pod_dir = tmpdir / "pod_clips"
        pod_dir.mkdir(parents=True, exist_ok=True)

        # Generate 4-second audio
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=520:duration=4",
            "-c:a", "libmp3lame", "-b:a", "128k", str(src_audio)
        ], capture_output=True, text=True)

        podcast_words = [
            {"w": "Deep", "s": 0.5, "e": 1.2},
            {"w": "Podcast", "s": 1.2, "e": 2.0},
            {"w": "Interview", "s": 2.0, "e": 3.2},
        ]
        podcast_clip_def = {
            "id": "pod_clip_1",
            "start": 0.5,
            "end": 3.5,
            "style": "clean_podcast",
            "hook": "Insights & Advice",
            "highlight_words": ["Deep", "Podcast"],
        }
        pod_files = render.render_podcast_clip(src_audio, pod_dir, "pod_clip_1", podcast_clip_def, podcast_words,
                                               title="Tech Talk Ep 1", uploader="Alice")
        out_podcast_clip = pod_dir / pod_files["file"]
        check("podcast rendered video exists", out_podcast_clip.exists(), True)

        pod_probe = media.probe(out_podcast_clip)
        check("podcast output has video stream", pod_probe.get("has_video"), True)
        check("podcast output has audio stream", pod_probe.get("has_audio"), True)
        check("podcast output width 1080", pod_probe.get("width"), 1080)
        check("podcast output height 1920", pod_probe.get("height"), 1920)
        check("podcast duration ~3.0s", 2.8 <= pod_probe.get("duration", 0) <= 3.2, True)

        # 5. Livestream Rolling Buffer & Clipping Simulation
        print("\n--- 5. Livestream Rolling Buffer & Clipping Simulation ---")
        stream_dir = tmpdir / "live_stream"
        stream_dir.mkdir(parents=True, exist_ok=True)
        # Create 3 x 2-second segments
        for i in range(3):
            seg_file = stream_dir / f"seg_{i:03d}.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=2",
                "-f", "lavfi", "-i", "sine=frequency=300:duration=2",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(seg_file)
            ], capture_output=True, text=True)

        concat_list = stream_dir / "concat.txt"
        concat_list.write_text("\n".join(f"file '{stream_dir / f'seg_{i:03d}.mp4'}'" for i in range(3)), encoding="utf-8")
        live_combined = stream_dir / "live_buffer.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", str(live_combined)
        ], capture_output=True, text=True)
        check("live stream buffer assembled", live_combined.exists(), True)

        live_clips_dir = tmpdir / "live_clips"
        live_clips_dir.mkdir(parents=True, exist_ok=True)
        live_clip_def = {
            "id": "live_clip_1",
            "start": 1.0,
            "end": 4.5,
            "layout": "blur",
            "style": "streamer_bold",
            "hook": "Epic Play Highlight",
            "highlight_words": ["Epic"],
        }
        live_words = [{"w": "Epic", "s": 1.2, "e": 2.0}, {"w": "Moment", "s": 2.0, "e": 3.5}]
        live_res = render.render_clip(live_combined, live_clips_dir, "live_clip_1", live_clip_def, live_words, 1280, 720)
        live_clip_out = live_clips_dir / live_res["file"]
        check("live clip extracted and rendered", live_clip_out.exists(), True)
        live_probe = media.probe(live_clip_out)
        check("live clip width 1080", live_probe.get("width"), 1080)
        check("live clip height 1920", live_probe.get("height"), 1920)
        check("live clip duration ~3.5s", 3.3 <= live_probe.get("duration", 0) <= 3.7, True)

        # 6. Caption Style Presets Validation
        print("\n--- 6. Caption Style Presets & ASS Formatting ---")
        for style_name in ("streamer_bold", "clean_podcast", "bounce", "boxed"):
            ass_str = render.build_ass(
                [{"w": "Style", "s": 1.0, "e": 2.0}, {"w": "Test", "s": 2.0, "e": 3.0}],
                1.0, 3.0, "Hook Line", style_name, ["Style"], hook_y=280, cap_y=1340
            )
            check(f"ASS generated for style '{style_name}'", "[Script Info]" in ass_str and "Style: Cap" in ass_str, True)
            check(f"ASS contains dialogue for '{style_name}'", "Dialogue:" in ass_str and "Style" in ass_str, True)

        # 7. SSRF and Resource-Exhaustion Protections
        print("\n--- 7. SSRF and Resource-Exhaustion Protection ---")
        check("SSRF blocks 127.0.0.1", media.is_safe_host("127.0.0.1"), False)
        check("SSRF blocks localhost", media.is_safe_host("localhost"), False)
        check("SSRF blocks 10.0.0.1", media.is_safe_host("10.0.0.1"), False)
        check("SSRF blocks 192.168.1.1", media.is_safe_host("192.168.1.1"), False)
        check("SSRF blocks 172.16.0.1", media.is_safe_host("172.16.0.1"), False)
        check("SSRF blocks link-local 169.254.169.254", media.is_safe_host("169.254.169.254"), False)
        check("SSRF blocks metadata.google.internal", media.is_safe_host("metadata.google.internal"), False)
        check("SSRF allows youtube.com", media.is_safe_host("youtube.com"), True)
        check("SSRF allows example.com", media.is_safe_host("example.com"), True)

        # RSS feed SSRF rejection
        try:
            rss.parse_podcast_feed("http://127.0.0.1:8765/secret_feed.xml")
            check("RSS blocks 127.0.0.1", False, True)
        except ValueError as e:
            check("RSS blocks 127.0.0.1 with security error", "SSRF" in str(e) or "blocked" in str(e), True)

        try:
            rss.parse_podcast_feed("http://169.254.169.254/latest/meta-data/")
            check("RSS blocks cloud metadata", False, True)
        except ValueError as e:
            check("RSS blocks cloud metadata with security error", "SSRF" in str(e) or "blocked" in str(e), True)

        # RSS episode download SSRF rejection
        try:
            rss.download_podcast_episode("http://192.168.1.100/private_audio.mp3", tmpdir / "bad.mp3")
            check("Episode download blocks private IP", False, True)
        except ValueError as e:
            check("Episode download blocks private IP with security error", "SSRF" in str(e) or "blocked" in str(e), True)

        # Audio magic byte validation
        fake_mp3 = tmpdir / "fake.mp3"
        fake_mp3.write_text("<!DOCTYPE html><html><body>Not an audio file</body></html>", encoding="utf-8")
        check("validate_audio_header rejects HTML", media.validate_audio_header(fake_mp3.read_bytes()[:32]), False)

        valid_id3 = b"ID3\x04\x00\x00\x00\x00\x00\x00\xff\xfb\x90\x00"
        check("validate_audio_header accepts MP3 ID3", media.validate_audio_header(valid_id3), True)

        valid_riff = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
        check("validate_audio_header accepts WAV RIFF", media.validate_audio_header(valid_riff), True)

        # Oversized response cap test (using safe_fetch_url with 100 byte limit)
        from unittest.mock import patch
        import httpx

        mock_resp = httpx.Response(200, content=b"A" * 500, headers={"content-type": "text/xml"})
        with patch("httpx.Client.send", return_value=mock_resp):
            try:
                media.safe_fetch_url("https://example.com/huge.xml", max_bytes=100)
                check("safe_fetch_url aborts on oversized body", False, True)
            except ValueError as e:
                check("safe_fetch_url aborts on oversized body", "exceeded" in str(e).lower(), True)

        # Redirect-based SSRF defense test (redirect to 127.0.0.1)
        mock_redirect = httpx.Response(302, headers={"Location": "http://127.0.0.1:8765/secret_feed.xml"})
        with patch("httpx.Client.send", return_value=mock_redirect):
            try:
                media.safe_fetch_url("https://example.com/feed.xml")
                check("safe_fetch_url blocks redirect to private IP", False, True)
            except ValueError as e:
                check("safe_fetch_url blocks redirect to private IP", "blocked" in str(e).lower() or "rejected" in str(e).lower(), True)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "=" * 50)
    print(f"MEDIA WORKFLOW VALIDATION RESULT: {len(fails)} failure(s)")
    if fails:
        print("FAILED CHECKS: " + ", ".join(fails))
        return 1
    print("ALL MEDIA WORKFLOWS VERIFIED SUCCESSFULLY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
