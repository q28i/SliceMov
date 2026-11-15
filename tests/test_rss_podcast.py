"""Regression tests for RSS podcast feed parsing and import."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

TEST_DATA = tempfile.mkdtemp(prefix="pc-rss-")
os.environ["PEAKCUT_DATA"] = TEST_DATA
os.environ.update(
    DATABASE_URL="",
    PEAKCUT_ACCOUNTS="1",
    PEAKCUT_PUBLIC_URL="https://clips.example.com",
    PEAKCUT_VERIFY_EMAIL="0",
)
sys.path.insert(0, ".")

from fastapi.testclient import TestClient
from studio import auth, db, rss, server

db.init()
BASE = "https://clips.example.com"


def create_user(email, name="User"):
    u, _ = auth._create(email, name, password_hash="x")
    cl = TestClient(server.app, base_url=BASE, follow_redirects=False)
    cl.cookies.set(auth.COOKIE, auth.start_session(u.id))
    return u, cl


user, client = create_user("testuser@example.com", "TestUser")

fails = []


def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r} (expected {want!r})"))
    if not ok:
        fails.append(n)


SAMPLE_PODCAST_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>The Engineering Mindset Podcast</title>
    <itunes:author>Sarah Connor</itunes:author>
    <description>Deep discussions on software architecture and system scaling.</description>
    <itunes:image href="https://example.com/podcast-cover.jpg"/>
    <item>
      <title>Episode 104: Scaling to 100M Requests</title>
      <description>We interview lead engineers on microservice orchestration.</description>
      <pubDate>Mon, 15 Nov 2026 12:00:00 GMT</pubDate>
      <enclosure url="https://example.com/audio/ep104.mp3" length="45000000" type="audio/mpeg"/>
      <itunes:duration>00:45:30</itunes:duration>
    </item>
    <item>
      <title>Episode 103: The Future of Local AI</title>
      <description>Exploring on-device neural processing and quantization.</description>
      <pubDate>Mon, 08 Nov 2026 12:00:00 GMT</pubDate>
      <enclosure url="https://example.com/audio/ep103.mp3" length="38000000" type="audio/mpeg"/>
      <itunes:duration>38:15</itunes:duration>
    </item>
  </channel>
</rss>
"""


def test_rss_subsystem():
    # 1. Direct XML parsing test
    feed = rss.parse_podcast_feed(SAMPLE_PODCAST_RSS)
    check("parsed feed title", feed.get("title"), "The Engineering Mindset Podcast")
    check("parsed feed author", feed.get("author"), "Sarah Connor")
    check("parsed feed cover image", feed.get("image_url"), "https://example.com/podcast-cover.jpg")
    check("parsed 2 episodes", len(feed.get("episodes", [])), 2)

    ep0 = feed["episodes"][0]
    check("ep0 title matches", ep0.get("title"), "Episode 104: Scaling to 100M Requests")
    check("ep0 enclosure url", ep0.get("enclosure_url"), "https://example.com/audio/ep104.mp3")
    check("ep0 duration in seconds", ep0.get("duration"), 45 * 60 + 30)

    ep1 = feed["episodes"][1]
    check("ep1 duration in seconds", ep1.get("duration"), 38 * 60 + 15)

    # 2. Test /api/rss/preview with mock
    with patch("studio.rss.parse_podcast_feed", return_value=feed):
        res = client.get("/api/rss/preview?url=https://example.com/feed.rss")
        check("preview endpoint returns 200", res.status_code, 200)
        data = res.json()
        check("preview response contains title", data.get("title"), "The Engineering Mindset Podcast")
        check("preview response contains episodes", len(data.get("episodes", [])), 2)

    # 3. Test /api/rss/import endpoint validation
    # Missing fields
    res = client.post("/api/rss/import", json={})
    check("import without payload returns 400", res.status_code, 400)

    # Valid import payload
    res = client.post("/api/rss/import", json={
        "feed_url": "https://example.com/feed.rss",
        "episode_url": "https://example.com/audio/ep104.mp3",
        "title": "Episode 104: Scaling to 100M Requests",
        "author": "Sarah Connor",
        "profile": "podcast"
    })
    check("import endpoint returns 200", res.status_code, 200)
    data = res.json()
    check("import response returns job id", bool(data.get("id")), True)
    check("import response has status queued", data.get("status"), "queued")


if __name__ == "__main__":
    test_rss_subsystem()
    if fails:
        sys.exit(1)
