"""Regression tests for universal clipping profiles and heuristic fallbacks."""
import os
import sys

sys.path.insert(0, ".")
from studio import clipping_profiles

fails = []


def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r} (expected {want!r})"))
    if not ok:
        fails.append(n)


def test_profiles():
    expected = {"livestream", "podcast", "gaming", "interview", "educational", "general"}
    check("all 6 clipping profiles defined", set(clipping_profiles.PROFILES.keys()), expected)

    prof = clipping_profiles.get_profile("nonexistent_profile")
    check("fallback profile is general", prof["id"], "general")

    gaming = clipping_profiles.get_profile("gaming")
    check("gaming profile keywords include gaming categories", "clutch" in gaming["categories"] or "fail" in gaming["categories"], True)

    podcast = clipping_profiles.get_profile("podcast")
    check("podcast head prompt emphasizes coherence", "coherent" in podcast["head_prompt"].lower() or "standalone" in podcast["head_prompt"].lower(), True)

    edu = clipping_profiles.get_profile("educational")
    check("educational head prompt emphasizes explanations", "explanation" in edu["head_prompt"].lower() or "insight" in edu["head_prompt"].lower(), True)

    empty_clips = clipping_profiles.fallback_by_speech_density([], n=5, min_len=15, max_len=60, duration=100.0)
    check("empty words yield empty candidate clips", len(empty_clips), 0)

    # 100 simulated word tokens across 60 seconds with conversational flow
    words = []
    t = 0.0
    vocab = ["Now", "the", "secret", "reason", "behind", "this", "breakthrough", "is", "that", "we", "discovered", "the", "key", "solution", "to", "the", "entire", "problem"]
    while t < 60.0:
        w = vocab[int(t * 3) % len(vocab)]
        words.append({"w": w, "s": round(t, 2), "e": round(t + 0.3, 2)})
        t += 0.45

    clips = clipping_profiles.fallback_by_speech_density(
        words, n=3, min_len=15, max_len=45, duration=60.0
    )

    check("density fallback produces candidate clips", 1 <= len(clips) <= 3, True)
    if clips:
        c = clips[0]
        check("clip bounds are valid", c["end"] > c["start"] and (c["end"] - c["start"]) >= 15, True)
        check("clip has virality score", c.get("score", 0) >= 50, True)
        check("clip has title and hook", bool(c.get("title") and c.get("hook")), True)


if __name__ == "__main__":
    test_profiles()
    if fails:
        sys.exit(1)
