"""Clipping profiles for different media genres: Livestream, Podcast, Gaming, Interview, Educational, General.

Each profile defines customized AI prompt rules, category taxonomies, recommended clip lengths,
and specialized non-AI fallbacks so PeakCut adapts its scout heuristics to the specific media type.
"""
import re
from typing import Dict, List, Optional
import numpy as np

PROFILES: Dict[str, dict] = {
    "livestream": {
        "id": "livestream",
        "label": "Livestream",
        "description": "High-energy reactions, funny moments, chat spikes, and clutch events.",
        "min_len": 15,
        "max_len": 60,
        "categories": ["funny", "fail", "clutch", "rage", "shock", "hype", "story", "other"],
        "head_prompt": (
            "You are a clip scout for livestream highlights (Twitch, Kick, YouTube Live).\n"
            "Below is a timestamped transcript of part of a video. Lines marked (LOUD) are where audio spiked "
            "(laughter, shouting, hype). Lines marked (CHAT) are where live chat exploded.\n\n"
            "Video title: {title}\nChannel: {uploader}\n\n"
            "Pick up to {n} moments that work as standalone viral clips: strong reactions, funny incidents, "
            "clutch plays, rage, shock, or sudden unexpected turns. Preserve context before and after the event."
        ),
        "rules_prompt": (
            "- Look for emotional peaks, laughter, sudden volume changes (LOUD), and chat explosions (CHAT).\n"
            "- Include the setup before the peak so viewers understand why it's funny or crazy.\n"
            "- End cleanly right after the payoff on a complete sentence; never mid-thought.\n"
            "- category: one of funny, fail, clutch, rage, shock, hype, story, other."
        ),
    },
    "podcast": {
        "id": "podcast",
        "label": "Podcast & Discussion",
        "description": "Coherent thoughts, actionable advice, debates, and memorable revelations.",
        "min_len": 30,
        "max_len": 90,
        "categories": ["insight", "advice", "debate", "story", "revelation", "hot_take", "quote", "other"],
        "head_prompt": (
            "You are an expert clip scout for long-form podcasts, talk shows, and audio discussions.\n"
            "Below is a timestamped transcript. Each line begins with [seconds].\n\n"
            "Podcast title: {title}\nHost/Creator: {uploader}\n\n"
            "Pick up to {n} moments that work as compelling, coherent standalone clips for YouTube Shorts, Reels, and TikTok: "
            "actionable advice, eye-opening revelations, intense debates, profound wisdom, or memorable stories. "
            "Prioritize deep substance, complete thoughts, and natural sentence completion over loud yelling."
        ),
        "rules_prompt": (
            "- Each clip MUST be a complete, self-contained thought, story, or argument from premise to conclusion.\n"
            "- Never start in the middle of a thought and never cut off an explanation midway.\n"
            "- Prioritize clarity, emotional resonance, actionable wisdom, and sentence completion.\n"
            "- category: one of insight, advice, debate, story, revelation, hot_take, quote, other."
        ),
    },
    "gaming": {
        "id": "gaming",
        "label": "Gaming Highlights",
        "description": "Clutch plays, epic fails, unexpected bugs, and gaming victories.",
        "min_len": 15,
        "max_len": 60,
        "categories": ["clutch", "fail", "victory", "rage", "funny", "bug", "skill", "other"],
        "head_prompt": (
            "You are a clip scout for gaming content (esports, let's plays, walkthroughs, speedruns).\n"
            "Below is a timestamped transcript with loudness markers.\n\n"
            "Game / Video title: {title}\nPlayer / Channel: {uploader}\n\n"
            "Pick up to {n} moments that showcase clutch gameplay, hilarious fails, unexpected bugs, "
            "victory moments, genuine gamer rage, or witty in-game commentary. "
            "Do not assume loud speech always indicates a good clip; look for actual gameplay significance."
        ),
        "rules_prompt": (
            "- Capture the entire sequence: the setup/build-up, the pivotal play, and the aftermath reaction.\n"
            "- Make sure a casual viewer can understand what just happened in the game.\n"
            "- End cleanly on the reaction or finished sentence.\n"
            "- category: one of clutch, fail, victory, rage, funny, bug, skill, other."
        ),
    },
    "interview": {
        "id": "interview",
        "label": "Interview & Q&A",
        "description": "Provocative questions, deep answers, personal stories, and emotional moments.",
        "min_len": 25,
        "max_len": 85,
        "categories": ["question_answer", "confession", "story", "debate", "insight", "humor", "other"],
        "head_prompt": (
            "You are a clip scout for interviews, Q&A sessions, and fireside chats.\n"
            "Below is a timestamped transcript.\n\n"
            "Interview title: {title}\nChannel: {uploader}\n\n"
            "Find up to {n} compelling question-and-answer exchanges, confessions, poignant stories, or sharp insights. "
            "CRITICALLY: Avoid clipping an answer without enough question context for the viewer to understand what is being answered."
        ),
        "rules_prompt": (
            "- Start on or immediately before the interviewer's question or the setup prompt.\n"
            "- Include the interviewee's complete response and conclusive takeaway.\n"
            "- Prioritize vulnerability, surprising answers, and memorable exchanges.\n"
            "- category: one of question_answer, confession, story, debate, insight, humor, other."
        ),
    },
    "educational": {
        "id": "educational",
        "label": "Educational & Explainer",
        "description": "Clear explanations, mind-blowing facts, tutorials, and key takeaways.",
        "min_len": 25,
        "max_len": 90,
        "categories": ["explanation", "fact", "how_to", "myth_busted", "concept", "summary", "other"],
        "head_prompt": (
            "You are a clip scout for educational videos, explainers, scientific breakdowns, and tutorials.\n"
            "Below is a timestamped transcript.\n\n"
            "Topic / Title: {title}\nPresenter: {uploader}\n\n"
            "Pick up to {n} concise, high-value explanations, counterintuitive facts, demonstrations, or 'aha!' moments. "
            "Prioritize factual integrity, clarity, and self-contained explanations that leave the viewer smarter."
        ),
        "rules_prompt": (
            "- The clip must clearly present the concept, problem, or fact, followed by the explanation.\n"
            "- It must stand on its own as a valuable lesson or fascinating takeaway.\n"
            "- Avoid incomplete multi-step instructions where crucial steps are omitted.\n"
            "- category: one of explanation, fact, how_to, myth_busted, concept, summary, other."
        ),
    },
    "general": {
        "id": "general",
        "label": "General Video",
        "description": "Universal clipping using scene flow, pacing, and standout moments.",
        "min_len": 20,
        "max_len": 75,
        "categories": ["highlight", "story", "funny", "moment", "quote", "takeaway", "other"],
        "head_prompt": (
            "You are a universal clip scout for general video content (vlogs, reviews, documentaries, entertainment).\n"
            "Below is a timestamped transcript.\n\n"
            "Video title: {title}\nChannel: {uploader}\n\n"
            "Find up to {n} moments that propose excellent short-form clips based on narrative flow, pacing, "
            "humor, and memorable statements."
        ),
        "rules_prompt": (
            "- Pick moments with natural beginnings and strong conclusions.\n"
            "- The clip must make sense on its own without requiring the entire video.\n"
            "- category: one of highlight, story, funny, moment, quote, takeaway, other."
        ),
    },
}

DEFAULT_PROFILE = "general"

DISCOURSE_MARKERS = {
    "because", "reason", "key", "secret", "truth", "important", "remember",
    "advice", "mistake", "lesson", "happened", "first", "always", "never",
    "fact", "realize", "discovered", "rule", "story", "imagine", "actually",
    "problem", "solution", "insight", "point", "answer", "question"
}


def get_profile(name: Optional[str]) -> dict:
    """Return profile dict for given name or default profile."""
    if not name or name not in PROFILES:
        return PROFILES[DEFAULT_PROFILE]
    return PROFILES[name]


get_clipping_profile = get_profile


def list_profiles() -> List[dict]:
    """Return list of all profile metadata for UI and API consumption."""
    return [
        {
            "id": p["id"],
            "label": p["label"],
            "description": p["description"],
            "min_len": p["min_len"],
            "max_len": p["max_len"],
            "categories": p["categories"],
        }
        for p in PROFILES.values()
    ]


def fallback_by_speech_density(words: list, n: int, min_len: int, max_len: int, duration: float) -> list:
    """Non-AI fallback for podcasts, interviews, and educational media.
    Instead of loud shouting, identifies dense, well-structured speech stretches
    with high discourse marker presence and consistent talking.
    """
    if not words or duration <= 0:
        return []

    # Slide a window across the duration
    step = 5.0
    candidates = []
    target_len = min(max_len, max(min_len, 45.0))
    t = 0.0

    while t + target_len <= duration:
        s, e = t, t + target_len
        window_words = [w for w in words if s <= w["s"] <= e]
        if len(window_words) >= 15:
            # Score by speech word count, density, and discourse markers
            text = " ".join(w["w"].lower() for w in window_words)
            marker_count = sum(1 for m in DISCOURSE_MARKERS if re.search(r"\b" + m + r"\b", text))
            wps = len(window_words) / target_len
            # Balanced score: steady conversational cadence (2.0 to 3.2 words/sec) + discourse markers
            cadence_score = max(0.0, 1.0 - abs(wps - 2.5) / 1.5)
            score = 50 + min(35, marker_count * 5) + int(cadence_score * 15)
            candidates.append((score, s, e, window_words))
        t += step

    candidates.sort(key=lambda x: -x[0])
    picks = []
    for sc, s, e, ww in candidates:
        if any(not (e <= p["start"] or s >= p["end"]) for p in picks):
            continue
        first_words = " ".join(w["w"] for w in ww[:5]).upper()
        picks.append({
            "start": s,
            "end": e,
            "score": sc,
            "category": "insight",
            "hook": first_words[:30] or "KEY INSIGHT",
            "title": f"Key Segment ({int(s)}s-{int(e)}s)",
            "description": "Selected by speech density and topic structure.",
            "hashtags": ["podcast", "insight", "discussion", "highlights", "clips"],
            "highlight_words": [w["w"] for w in ww if len(w["w"]) > 5][:4],
            "reason": "Identified coherent speech segment with strong topical flow.",
        })
        if len(picks) >= n:
            break

    picks.sort(key=lambda p: p["start"])
    return picks
