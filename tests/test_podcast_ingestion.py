"""Regression tests for audio podcast ingestion and vertical waveform rendering."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
from studio import media, render, tools

fails = []


def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r} (expected {want!r})"))
    if not ok:
        fails.append(n)


def test_podcast_ingestion_and_render():
    tools.setup()

    # 1. Test site_allowed for direct audio links
    check("site_allowed accepts .mp3", media.site_allowed("https://cdn.example.com/episode.mp3"), True)
    check("site_allowed accepts .m4a", media.site_allowed("https://cdn.example.com/show/ep1.m4a?token=xyz"), True)
    check("site_allowed accepts .wav", media.site_allowed("https://podcasts.org/audio/test.wav"), True)

    tmpdir = Path(tempfile.mkdtemp(prefix="pc-test-podcast-"))
    try:
        audio_file = tmpdir / "sample_episode.mp3"
        thumb_file = tmpdir / "thumb.jpg"
        out_clip = tmpdir / "rendered_clip.mp4"

        # Generate a 2-second synthetic sine wave audio file with ffmpeg
        res = subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:a", "libmp3lame", "-b:a", "128k", str(audio_file)
        ], capture_output=True, text=True)
        check("ffmpeg synthesized test mp3", res.returncode, 0)

        # 2. Test media.probe on audio-only file
        info = media.probe(audio_file)
        check("probe detected audio file", bool(info), True)
        check("probe has_audio is True", info.get("has_audio"), True)
        check("probe has_video is False", info.get("has_video"), False)
        check("probe assigned vertical width 1080", info.get("width"), 1080)
        check("probe assigned vertical height 1920", info.get("height"), 1920)
        check("probe duration ~2.0s", 1.8 <= info.get("duration", 0) <= 2.2, True)

        # 3. Test media.save_thumb on audio-only file
        thumb_ok = media.save_thumb(job_dir=tmpdir, video=audio_file)
        thumb_path = tmpdir / "clips" / "thumb.jpg"
        check("thumbnail generated successfully", thumb_ok, True)
        check("thumbnail file exists", thumb_path.exists() and thumb_path.stat().st_size > 500, True)

        # 4. Test render.render_podcast_clip
        clip_data = {
            "start": 0.0,
            "end": 2.0,
            "style": "clean_podcast",
            "hook": "VALUABLE INSIGHT",
        }
        clip_words = [
            {"w": "Welcome", "s": 0.1, "e": 0.5},
            {"w": "to", "s": 0.55, "e": 0.75},
            {"w": "the", "s": 0.8, "e": 0.95},
            {"w": "podcast", "s": 1.0, "e": 1.6},
        ]
        res = render.render_podcast_clip(
            src=audio_file,
            out_dir=tmpdir / "clips",
            name="clip_test",
            clip=clip_data,
            words=clip_words,
            title="Episode 42: Building the Future",
            uploader="Creator Talk",
        )

        out_clip = tmpdir / "clips" / "clip_test.mp4"
        check("rendered podcast video exists", out_clip.exists() and out_clip.stat().st_size > 1000, True)

        # Verify output video tracks and resolution with media.probe
        out_info = media.probe(out_clip)
        check("output has video stream", out_info.get("has_video"), True)
        check("output has audio stream", out_info.get("has_audio"), True)
        check("output width is 1080", out_info.get("width"), 1080)
        check("output height is 1920", out_info.get("height"), 1920)

    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    test_podcast_ingestion_and_render()
    if fails:
        sys.exit(1)
