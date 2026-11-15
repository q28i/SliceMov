"""Regression tests for Post Now and scheduling workflow fixes.
Covers all 10 required scenarios with mocked external platform APIs.
No real external uploads take place.
"""
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

# Set up isolated test environment before any studio imports
TEST_DATA = tempfile.mkdtemp(prefix="pc-postnow-")
os.environ["PEAKCUT_DATA"] = TEST_DATA
os.environ.update(
    DATABASE_URL="",
    PEAKCUT_ACCOUNTS="1",
    PEAKCUT_PUBLIC_URL="https://clips.example.com",
    PEAKCUT_VERIFY_EMAIL="0",
    GOOGLE_CLIENT_ID="",
    GOOGLE_CLIENT_SECRET="",
    GOOGLE_CLIENT_FILE="",
)
sys.path.insert(0, ".")

from fastapi.testclient import TestClient
from studio import accounts, auth, config, creators, ctx, db, jobs, posting, server

db.init()

fails = []


def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r} (expected {want!r})"))
    if not ok:
        fails.append(n)


BASE = "https://clips.example.com"


def create_user(email, name="User"):
    u, _ = auth._create(email, name, password_hash="x")
    cl = TestClient(server.app, base_url=BASE, follow_redirects=False)
    cl.cookies.set(auth.COOKIE, auth.start_session(u.id))
    return u, cl


user, client = create_user("testuser@example.com", "TestUser")

# Mock platform upload functions and tracking
uploads_made = []


def mock_youtube_upload(acc, path, title, cap, hashtags, privacy):
    uploads_made.append(("youtube", acc["id"], title, privacy))
    return f"yt_id_{len(uploads_made)}", f"https://youtube.com/shorts/test_{len(uploads_made)}"


def mock_tiktok_upload(acc, path, title_cap, privacy):
    uploads_made.append(("tiktok", acc["id"], title_cap, privacy))
    return f"tt_id_{len(uploads_made)}", f"https://tiktok.com/@user/video/test_{len(uploads_made)}"


def mock_instagram_upload(acc, path, cap, job_id):
    uploads_made.append(("instagram", acc["id"], cap, job_id))
    return f"ig_id_{len(uploads_made)}", f"https://instagram.com/reel/test_{len(uploads_made)}"


accounts.youtube_upload = mock_youtube_upload
accounts.tiktok_upload = mock_tiktok_upload
accounts.instagram_upload = mock_instagram_upload

# Helper to create a fake connected account in the database
with ctx.as_user(user.id):
    yt_acc = accounts._put({
        "id": "acc_yt_1", "user": user.id, "platform": "youtube", "name": "Test YT Channel",
        "label": "YouTube", "tokens": {"token": "x"}, "expires": time.time() + 3600, "detail": ""
    })
    tt_acc = accounts._put({
        "id": "acc_tt_1", "user": user.id, "platform": "tiktok", "name": "@testtiktok",
        "label": "TikTok", "tokens": {"token": "x"}, "expires": time.time() + 3600, "detail": ""
    })

# Helper to create a creator and finished video job with clips
def make_video(creator_id, prefix="c", n_clips=1):
    with ctx.as_user(user.id):
        j = jobs.create({"type": "file", "path": "", "name": f"gameplay_{prefix}.mp4"}, {}, enqueue=False, creator=creator_id)
        clips_dir = Path(j["dir"]) / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        for i in range(n_clips):
            cid = f"{prefix}_clip_{i+1:02d}"
            (clips_dir / f"{cid}.mp4").write_bytes(b"\x00" * 2000)
            (clips_dir / f"{cid}.jpg").write_bytes(b"\x00" * 500)
            j["clips"].append({
                "id": cid, "status": "done", "file": f"{cid}.mp4", "cover": f"{cid}.jpg",
                "title": f"Epic Moment {i+1}", "hook": f"Watch this {i+1}", "start": i * 10, "end": (i + 1) * 10,
                "score": 85, "hashtags": ["gaming", "clip"]
            })
        j["status"] = "done"
        jobs.save(j)
        return j


print("\n--- Running Posting Regression Scenarios ---")

# ==============================================================================
# Scenario 1: Fresh clip -> Post now -> immediate processing
# ==============================================================================
with ctx.as_user(user.id):
    c1 = creators.create({"name": "Creator1", "post_gap_min": 60, "daily_cap": 5})
    j1 = make_video(c1["id"], prefix="s1", n_clips=1)
    clip1 = j1["clips"][0]
    uploads_before = len(uploads_made)

    r = client.post("/api/posts", json={"job": j1["id"], "clip": clip1["id"], "accounts": ["acc_yt_1"], "now": True})
    check("S1: API accepts Post now on fresh clip", r.status_code, 200)
    check("S1: Queued count is 1", r.json().get("queued"), 1)

    # Verify post in _posts has due_at <= now
    posts_user = posting._mine()
    p1 = next((p for p in posts_user if p["job"] == j1["id"] and p["clip"] == clip1["id"] and p["account"] == "acc_yt_1"), None)
    check("S1: Post record created", p1 is not None)
    check("S1: Post due_at is immediate", p1["due_at"] <= time.time() + 1 if p1 else False)

    # Let the worker process it
    posting._post(p1)
    check("S1: Post transitioned to posted", p1["status"], "posted")
    check("S1: Upload function was invoked", len(uploads_made), uploads_before + 1)
    check("S1: URL assigned", bool(p1.get("url")))

    # Verify clip mirrored
    j1_fresh = jobs.get(j1["id"])
    c1_fresh = next(c for c in j1_fresh["clips"] if c["id"] == clip1["id"])
    check("S1: Clip mirrored post status is posted", c1_fresh.get("posts", {}).get(p1["id"], {}).get("status"), "posted")


# ==============================================================================
# Scenario 2: Fresh clip auto-queued by on_clip_ready() -> Post now -> expedited
# ==============================================================================
with ctx.as_user(user.id):
    c2 = creators.create({"name": "CreatorAuto", "autopost": True, "accounts": ["acc_yt_1"], "post_min_score": 50, "post_gap_min": 120, "daily_cap": 3})
    j2 = make_video(c2["id"], prefix="s2", n_clips=1)
    clip2 = j2["clips"][0]

    # Simulate on_clip_ready auto-queueing the clip for future slot
    posting.on_clip_ready(j2, clip2)
    posts_user = posting._mine()
    p2 = next((p for p in posts_user if p["job"] == j2["id"] and p["clip"] == clip2["id"] and p["account"] == "acc_yt_1"), None)
    check("S2: on_clip_ready created scheduled post", p2 is not None and p2["status"] == "scheduled")
    orig_post_id = p2["id"]
    orig_due = p2["due_at"]

    # Now simulate user opening clip dialog and clicking "Post now"
    uploads_before = len(uploads_made)
    r2 = client.post("/api/posts", json={"job": j2["id"], "clip": clip2["id"], "accounts": ["acc_yt_1"], "now": True})
    check("S2: Post now succeeds on auto-scheduled clip (no 400 error)", r2.status_code, 200)

    # Verify original post was expedited (same ID, due_at moved to now, no duplicate)
    posts_for_clip2 = [p for p in posting._mine() if p["job"] == j2["id"] and p["clip"] == clip2["id"] and p["account"] == "acc_yt_1"]
    check("S2: No duplicate post created", len(posts_for_clip2), 1)
    p2_updated = posts_for_clip2[0]
    check("S2: Post ID preserved", p2_updated["id"], orig_post_id)
    check("S2: due_at updated to now", p2_updated["due_at"] <= time.time() + 1)
    check("S2: due_at was earlier than or equal to original", p2_updated["due_at"] <= orig_due)


# ==============================================================================
# Scenario 3: Scheduled clip -> Publish now -> original job reused & expedited
# ==============================================================================
with ctx.as_user(user.id):
    c3 = creators.create({"name": "CreatorManual", "post_gap_min": 60})
    j3 = make_video(c3["id"], prefix="s3", n_clips=1)
    clip3 = j3["clips"][0]

    # Manually add to queue (now=False)
    r_queue = client.post("/api/posts", json={"job": j3["id"], "clip": clip3["id"], "accounts": ["acc_yt_1"], "now": False})
    check("S3: Add to queue succeeds", r_queue.status_code, 200)
    p3 = next((p for p in posting._mine() if p["job"] == j3["id"] and p["clip"] == clip3["id"] and p["account"] == "acc_yt_1"), None)
    check("S3: Scheduled post exists", p3 is not None and p3["status"] == "scheduled")
    p3_id = p3["id"]

    # User clicks "Publish now" (now=True)
    r_pub = client.post("/api/posts", json={"job": j3["id"], "clip": clip3["id"], "accounts": ["acc_yt_1"], "now": True})
    check("S3: Publish now succeeds", r_pub.status_code, 200)

    posts_for_clip3 = [p for p in posting._mine() if p["job"] == j3["id"] and p["clip"] == clip3["id"] and p["account"] == "acc_yt_1"]
    check("S3: Exactly one post exists", len(posts_for_clip3), 1)
    check("S3: Post ID preserved", posts_for_clip3[0]["id"], p3_id)
    check("S3: due_at expedited to now", posts_for_clip3[0]["due_at"] <= time.time() + 1)


# ==============================================================================
# Scenario 4: Two simultaneous Post now requests -> exactly one upload
# ==============================================================================
with ctx.as_user(user.id):
    c4 = creators.create({"name": "CreatorConcurrent"})
    j4 = make_video(c4["id"], prefix="s4", n_clips=1)
    clip4 = j4["clips"][0]

    errors = []
    responses = []

    def call_post_now():
        try:
            r = client.post("/api/posts", json={"job": j4["id"], "clip": clip4["id"], "accounts": ["acc_yt_1"], "now": True})
            responses.append(r)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=call_post_now)
    t2 = threading.Thread(target=call_post_now)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    check("S4: No network/thread exceptions", len(errors), 0)
    check("S4: Both calls returned success (200)", all(r.status_code == 200 for r in responses))

    posts_for_clip4 = [p for p in posting._mine() if p["job"] == j4["id"] and p["clip"] == clip4["id"] and p["account"] == "acc_yt_1"]
    check("S4: Exactly one post created despite race", len(posts_for_clip4), 1)

    # Process upload
    uploads_before = len(uploads_made)
    posting._post(posts_for_clip4[0])
    check("S4: Exactly one upload performed", len(uploads_made), uploads_before + 1)


# ==============================================================================
# Scenario 5: Already published clip -> no duplicate, clear response
# ==============================================================================
with ctx.as_user(user.id):
    # Clip 4 was already posted above!
    p4 = posts_for_clip4[0]
    check("S5: Post is in posted state", p4["status"], "posted")
    uploads_before = len(uploads_made)

    # User attempts to post again
    r_dup = client.post("/api/posts", json={"job": j4["id"], "clip": clip4["id"], "accounts": ["acc_yt_1"], "now": True})
    check("S5: Second post attempt does not return 400 error", r_dup.status_code, 200)
    check("S5: No new upload performed", len(uploads_made), uploads_before)

    # Check response communicates already posted status
    resp_data = r_dup.json()
    check("S5: Response indicates already posted", resp_data.get("already_posted", 0) > 0 or "posted" in resp_data.get("message", "").lower())


# ==============================================================================
# Scenario 6: Failed clip -> retry works
# ==============================================================================
with ctx.as_user(user.id):
    c6 = creators.create({"name": "CreatorFail"})
    j6 = make_video(c6["id"], prefix="s6", n_clips=1)
    clip6 = j6["clips"][0]

    # Create post that fails
    client.post("/api/posts", json={"job": j6["id"], "clip": clip6["id"], "accounts": ["acc_yt_1"], "now": True})
    p6 = next(p for p in posting._mine() if p["job"] == j6["id"] and p["clip"] == clip6["id"] and p["account"] == "acc_yt_1")

    # Simulate failure
    p6["status"] = "failed"
    p6["error"] = "YouTube quota exceeded for the day"
    posting._save()
    posting._mirror(p6)

    check("S6: Post marked as failed", p6["status"], "failed")

    # Call retry API
    r_retry = client.post(f"/api/posts/{p6['id']}/retry")
    check("S6: Retry endpoint returns 200", r_retry.status_code, 200)

    p6_after = next(p for p in posting._mine() if p["id"] == p6["id"])
    check("S6: Status reset to scheduled", p6_after["status"], "scheduled")
    check("S6: due_at reset to now", p6_after["due_at"] <= time.time() + 1)
    check("S6: error cleared", p6_after["error"], None)


# ==============================================================================
# Scenario 7: Disconnected account -> clean error
# ==============================================================================
with ctx.as_user(user.id):
    yt_temp = accounts._put({
        "id": "acc_yt_temp", "user": user.id, "platform": "youtube", "name": "Temp Channel",
        "label": "YouTube", "tokens": {"token": "x"}, "expires": time.time() + 3600, "detail": ""
    })

    c7 = creators.create({"name": "CreatorDisconnect"})
    j7 = make_video(c7["id"], prefix="s7", n_clips=1)
    clip7 = j7["clips"][0]

    client.post("/api/posts", json={"job": j7["id"], "clip": clip7["id"], "accounts": ["acc_yt_temp"], "now": True})
    p7 = next(p for p in posting._mine() if p["job"] == j7["id"] and p["clip"] == clip7["id"] and p["account"] == "acc_yt_temp")

    # Now disconnect the account
    accounts.remove("acc_yt_temp")

    # Attempt post processing
    posting._post(p7)
    check("S7: Post failed due to disconnected account", p7["status"], "failed")
    check("S7: Clear error message stored", "disconnected" in (p7.get("error") or "").lower())


# ==============================================================================
# Scenario 8: Multiple accounts -> independent posting state
# ==============================================================================
with ctx.as_user(user.id):
    c8 = creators.create({"name": "CreatorMulti"})
    j8 = make_video(c8["id"], prefix="s8", n_clips=1)
    clip8 = j8["clips"][0]

    # Queue YouTube first
    client.post("/api/posts", json={"job": j8["id"], "clip": clip8["id"], "accounts": ["acc_yt_1"], "now": False})

    # Now request Post now for BOTH YouTube and TikTok
    r_multi = client.post("/api/posts", json={"job": j8["id"], "clip": clip8["id"], "accounts": ["acc_yt_1", "acc_tt_1"], "now": True})
    check("S8: Multi-account post now returns 200", r_multi.status_code, 200)

    p_yt = next(p for p in posting._mine() if p["job"] == j8["id"] and p["clip"] == clip8["id"] and p["account"] == "acc_yt_1")
    p_tt = next(p for p in posting._mine() if p["job"] == j8["id"] and p["clip"] == clip8["id"] and p["account"] == "acc_tt_1")

    check("S8: YouTube post expedited", p_yt["due_at"] <= time.time() + 1)
    check("S8: TikTok post created with immediate due_at", p_tt["due_at"] <= time.time() + 1)
    check("S8: Independent platforms", (p_yt["platform"], p_tt["platform"]), ("youtube", "tiktok"))


# ==============================================================================
# Scenario 9: Application restart -> consistent state recovery
# ==============================================================================
with ctx.as_user(user.id):
    c9 = creators.create({"name": "CreatorRestart"})
    j9 = make_video(c9["id"], prefix="s9", n_clips=1)
    clip9 = j9["clips"][0]

    # Create a post and simulate it was interrupted mid-upload ("posting")
    client.post("/api/posts", json={"job": j9["id"], "clip": clip9["id"], "accounts": ["acc_yt_1"], "now": True})
    p9 = next(p for p in posting._mine() if p["job"] == j9["id"] and p["clip"] == clip9["id"] and p["account"] == "acc_yt_1")
    p9["status"] = "posting"
    posting._save()

    # Simulate restart: posting.start() handles interrupted uploads
    posting.start()
    p9_recovered = next(p for p in posting._mine() if p["id"] == p9["id"])
    check("S9: Interrupted posting is marked failed on restart", p9_recovered["status"], "failed")
    check("S9: Restart failure explains studio closed", "studio closed" in (p9_recovered.get("error") or "").lower())


# ==============================================================================
# Scenario 10: Normal queue -> posting gaps and daily caps preserved
# ==============================================================================
with ctx.as_user(user.id):
    c10 = creators.create({"name": "CreatorGaps", "post_gap_min": 45, "daily_cap": 2})
    j10 = make_video(c10["id"], prefix="s10", n_clips=3)

    # Queue clip 1 (normal queue)
    client.post("/api/posts", json={"job": j10["id"], "clip": j10["clips"][0]["id"], "accounts": ["acc_yt_1"], "now": False})
    p_slot1 = next(p for p in posting._mine() if p["job"] == j10["id"] and p["clip"] == j10["clips"][0]["id"] and p["account"] == "acc_yt_1")

    # Queue clip 2 (normal queue)
    client.post("/api/posts", json={"job": j10["id"], "clip": j10["clips"][1]["id"], "accounts": ["acc_yt_1"], "now": False})
    p_slot2 = next(p for p in posting._mine() if p["job"] == j10["id"] and p["clip"] == j10["clips"][1]["id"] and p["account"] == "acc_yt_1")

    gap_seconds = p_slot2["due_at"] - p_slot1["due_at"]
    check("S10: Normal queue respects post_gap_min (>= 45 min)", gap_seconds >= 45 * 60 - 5)

    # Creator settings remain untouched
    c10_check = creators.get(c10["id"])
    check("S10: Creator post_gap_min preserved", c10_check["post_gap_min"], 45)
    check("S10: Creator daily_cap preserved", c10_check["daily_cap"], 2)


print("\n==========================================")
print(f"RESULTS: {len(fails)} failure(s)")
if fails:
    print("Failed checks:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL 10 SCENARIOS PASSED")
    sys.exit(0)
