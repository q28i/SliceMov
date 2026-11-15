"""RSS Podcast Feed Ingestion Adapter.

Allows users to import audio podcast episodes directly from any standard RSS podcast feed
(e.g., Apple Podcasts feeds, Spotify-compatible RSS, Anchor, Libsyn, Buzzsprout, Substack).
Uses standard library xml.etree.ElementTree without extra dependencies.
"""
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PeakCut-Enhanced/2.0 PodcastScout",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def _clean_text(s: Optional[str], limit: int = 400) -> str:
    if not s:
        return ""
    # Strip HTML tags and control chars
    clean = re.sub(r"<[^>]+>", " ", s)
    clean = re.sub(r"[\x00-\x1f\x7f]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:limit]


def parse_podcast_feed(url_or_content: str, max_episodes: int = 25) -> dict:
    """Fetch and parse an RSS podcast feed into structured podcast and episode metadata."""
    if url_or_content.strip().startswith(("http://", "https://")):
        req = urllib.request.Request(url_or_content.strip(), headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read(10_000_000)  # max 10MB XML
    else:
        raw = url_or_content.encode("utf-8") if isinstance(url_or_content, str) else url_or_content

    root = ET.fromstring(raw)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("Not a valid RSS podcast feed (missing <channel>).")

    # Channel metadata
    title = _clean_text(channel.findtext("title") or "Podcast", 150)
    author = _clean_text(channel.findtext(f"{ITUNES_NS}author") or channel.findtext("managingEditor") or "Podcast Host", 100)
    desc = _clean_text(channel.findtext("description") or channel.findtext(f"{ITUNES_NS}summary") or "", 300)

    # Podcast image
    image_url = ""
    itunes_img = channel.find(f"{ITUNES_NS}image")
    if itunes_img is not None and itunes_img.attrib.get("href"):
        image_url = itunes_img.attrib["href"]
    elif channel.find("image") is not None:
        image_url = channel.find("image").findtext("url") or ""

    episodes: List[dict] = []
    items = channel.findall("item")
    for item in items[:max_episodes]:
        enclosure = item.find("enclosure")
        audio_url = ""
        length_bytes = 0
        if enclosure is not None:
            audio_url = enclosure.attrib.get("url") or ""
            try:
                length_bytes = int(enclosure.attrib.get("length") or 0)
            except ValueError:
                length_bytes = 0

        # Try to find audio link if not in enclosure
        if not audio_url:
            link = item.findtext("link") or ""
            if any(link.lower().endswith(ext) for ext in (".mp3", ".m4a", ".wav")):
                audio_url = link

        if not audio_url:
            continue

        ep_title = _clean_text(item.findtext("title") or "Episode", 150)
        ep_desc = _clean_text(item.findtext("description") or item.findtext(f"{ITUNES_NS}summary") or "", 250)
        pub_date = _clean_text(item.findtext("pubDate") or "", 60)
        duration_raw = _clean_text(item.findtext(f"{ITUNES_NS}duration") or "", 30)

        # Parse duration seconds if possible
        dur_sec = 0.0
        if ":" in duration_raw:
            parts = duration_raw.split(":")
            try:
                if len(parts) == 3:
                    dur_sec = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                elif len(parts) == 2:
                    dur_sec = float(parts[0]) * 60 + float(parts[1])
            except ValueError:
                dur_sec = 0.0
        elif duration_raw.isdigit():
            dur_sec = float(duration_raw)

        ep_image = ""
        ep_img_node = item.find(f"{ITUNES_NS}image")
        if ep_img_node is not None and ep_img_node.attrib.get("href"):
            ep_image = ep_img_node.attrib["href"]
        else:
            ep_image = image_url

        episodes.append({
            "title": ep_title,
            "description": ep_desc,
            "audio_url": audio_url,
            "enclosure_url": audio_url,
            "pub_date": pub_date,
            "duration": dur_sec,
            "duration_label": duration_raw or (f"{int(dur_sec // 60)}m" if dur_sec else ""),
            "image": ep_image,
            "size_bytes": length_bytes,
        })

    return {
        "title": title,
        "author": author,
        "description": desc,
        "image": image_url,
        "image_url": image_url,
        "episodes": episodes,
        "episode_count": len(episodes),
    }


def download_podcast_episode(audio_url: str, dest_path: Path, max_bytes: int = 500_000_000) -> Path:
    """Download an episode's audio file directly to a destination path."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(audio_url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp, dest_path.open("wb") as out:
        downloaded = 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            downloaded += len(chunk)
            if downloaded > max_bytes:
                raise ValueError("Episode audio exceeds maximum size limit (500MB).")
            out.write(chunk)
    return dest_path
