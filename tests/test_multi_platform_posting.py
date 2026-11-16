"""Regression tests for multi-platform posting independence and reconciliation."""
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

TEST_DATA = tempfile.mkdtemp(prefix="pc-multi-post-")
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
from studio import accounts, auth, creators, ctx, db, jobs, posting, server

db.init()
BASE = "https://clips.example.com"


def create_user(email, name="User"):
    u, _ = auth._create(email, name, password_hash="x")
    cl = TestClient(server.app, base_url=BASE, follow_redirects=False)
    cl.cookies.set(auth.COOKIE, auth.start_session(u.id))
    return u, cl


user, client = create_user("multiuser@example.com", "MultiUser")

fails = []


def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r} (expected {want!r})"))
    if not ok:
        fails.append(n)


def setup_clip():
    with ctx.as_user(user.id):
        c = creators.create({"name": "Interview Channel", "post_gap_min": 60, "daily_cap": 5})
        job = jobs.create({"type": "file", "path": "", "name": "interview.mp4"}, {}, enqueue=False, creator=c["id"])
        job_dir = Path(job["dir"]) / "clips"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "clip_1.mp4").write_bytes(b"\x00" * 2000)
        (job_dir / "clip_1.jpg").write_bytes(b"\x00" * 500)

        clip = {
            "id": "clip_1",
            "file": "clip_1.mp4",
            "cover": "clip_1.jpg",
            "status": "done",
            "start": 10.0,
            "end": 45.0,
            "title": "Pro Interview Highlight",
            "hook": "Must watch this",
            "description": "Valuable insight from guest.",
            "hashtags": ["interview", "insights"],
            "posts": {},
        }
        job["clips"] = [clip]
        job["status"] = "done"
        jobs.save(job)
        return job["id"], clip["id"]


def test_multi_platform_independence_and_reconcile():
    yt_acc = {
        "id": "acc_yt_multi", "user": user.id, "platform": "youtube", "name": "My YT Shorts",
        "label": "YouTube", "tokens": {"token": "x"}, "expires": time.time() + 3600, "detail": ""
    }
    ig_acc = {
        "id": "acc_ig_multi", "user": user.id, "platform": "instagram", "name": "My IG Reels",
        "label": "Instagram", "tokens": {"token": "x"}, "expires": time.time() + 3600, "detail": ""
    }
    tt_acc = {
        "id": "acc_tt_multi", "user": user.id, "platform": "tiktok", "name": "My TikTok",
        "label": "TikTok", "tokens": {"token": "x"}, "expires": time.time() + 3600, "detail": ""
    }
    with ctx.as_user(user.id):
        accounts._put(yt_acc)
        accounts._put(ig_acc)
        accounts._put(tt_acc)

    jid, cid = setup_clip()

    # Track uploads
    posted = []

    def mock_yt(acc, path, title, cap, tags, priv, on_session=None):
        if on_session:
            on_session("https://upload.youtube.com/upload_session_mock")
        posted.append("yt")
        return "yt_vid_99", "https://youtube.com/shorts/yt_vid_99"

    def mock_ig(acc, path, cap, job_id, on_session=None):
        if on_session:
            on_session("ig_container_mock_88")
        posted.append("ig")
        return "ig_media_88", "https://instagram.com/reel/ig_media_88"

    def mock_tt(acc, path, cap, priv, on_session=None):
        posted.append("tt_failed")
        raise RuntimeError("TikTok API requires audited developer status for public feed posting.")

    accounts.youtube_upload = mock_yt
    accounts.instagram_upload = mock_ig
    accounts.tiktok_upload = mock_tt

    # 1. Queue all 3 accounts: YT immediate, IG immediate, TT immediate
    res = client.post("/api/posts", json={
        "job": jid, "clip": cid, "accounts": [yt_acc["id"], ig_acc["id"], tt_acc["id"]], "now": True
    })
    check("multi-post request returns 200", res.status_code, 200)

    # Process posts synchronously via posting._post
    with ctx.as_user(user.id):
        mine = [p for p in posting._mine() if p["job"] == jid and p["clip"] == cid]
        check("found 3 scheduled posts in queue", len(mine), 3)

        tt_p = next(p for p in mine if p["platform"] == "tiktok")
        # Set tries to 2 so next failure causes final 'failed' state
        tt_p["tries"] = 2

        for p in mine:
            posting._post(p)

        # Verify clip posts state in db
        j = jobs.get(jid)
        clip = j["clips"][0]
        posts = clip.get("posts", {})

        check("clip has 3 distinct post records", len(posts), 3)

        yt_post = next((p for p in posts.values() if p["platform"] == "youtube"), None)
        ig_post = next((p for p in posts.values() if p["platform"] == "instagram"), None)
        tt_post = next((p for p in posts.values() if p["platform"] == "tiktok"), None)

        check("youtube post exists", bool(yt_post), True)
        check("instagram post exists", bool(ig_post), True)
        check("tiktok post exists", bool(tt_post), True)

        # Verify platform independence: YT and IG succeeded, TT failed without blocking the others
        check("youtube status is posted", yt_post.get("status"), "posted")
        check("youtube url is present", yt_post.get("url"), "https://youtube.com/shorts/yt_vid_99")

        check("instagram status is posted", ig_post.get("status"), "posted")
        check("instagram url is present", ig_post.get("url"), "https://instagram.com/reel/ig_media_88")

        check("tiktok status is failed", tt_post.get("status"), "failed")
        check("tiktok has error message", "audited" in tt_post.get("error", "").lower(), True)

    # 2. Test retry on failed post without touching successful YouTube or Instagram posts
    with patch("studio.accounts.tiktok_upload") as mock_tt_ok:
        mock_tt_ok.return_value = ("tt_ok_77", "https://tiktok.com/@user/video/tt_ok_77")
        res_retry = client.post(f"/api/posts/{tt_post['id']}/retry")
        check("retry returns 200", res_retry.status_code, 200)

        with ctx.as_user(user.id):
            p_tt_retrying = next(p for p in posting._mine() if p["id"] == tt_post["id"])
            posting._post(p_tt_retrying)

            j_after = jobs.get(jid)
            tt_after = j_after["clips"][0]["posts"][tt_post["id"]]
            check("tiktok status after retry is posted", tt_after.get("status"), "posted")

            # YouTube and Instagram remain unchanged and were not re-uploaded
            check("youtube still posted", j_after["clips"][0]["posts"][yt_post["id"]]["status"], "posted")
            check("instagram still posted", j_after["clips"][0]["posts"][ig_post["id"]]["status"], "posted")

    # 3. Test reconcile endpoint
    # Create a post in uncertain state with remote_id on YouTube
    with ctx.as_user(user.id):
        p_reconcile = {
            "id": "post_rec_1", "job": jid, "clip": cid, "account": yt_acc["id"], "user": user.id,
            "creator": "c_1", "account_name": "My YT Shorts", "platform": "youtube", "title": "Rec Test",
            "caption": "test", "status": "failed", "error": "Network timeout waiting for response",
            "remote_id": "yt_remote_verified", "url": None, "due_at": time.time(), "tries": 3,
            "views": 0, "comments": 0, "likes": 0
        }
        posting._posts.append(p_reconcile)
        posting._save()
        posting._mirror(p_reconcile)

    with patch("studio.accounts.youtube_views", return_value={"yt_remote_verified": 42}):
        res_rec = client.post("/api/posts/post_rec_1/reconcile")
        check("reconcile returns 200", res_rec.status_code, 200)
        rec_data = res_rec.json()
        check("reconcile reconciled True", rec_data.get("reconciled"), True)
        check("reconcile status is posted", rec_data.get("status"), "posted")
        check("reconcile restored url", "https://youtube.com/shorts/yt_remote_verified" in rec_data.get("url", ""), True)

    # 4. Test Ambiguous outcome handling: Never automatically retry ambiguous upload
    with ctx.as_user(user.id):
        p_ambig = {
            "id": "post_ambig_1", "job": jid, "clip": cid, "account": yt_acc["id"], "user": user.id,
            "creator": "c_1", "account_name": "My YT Shorts", "platform": "youtube", "title": "Ambig Test",
            "caption": "test", "status": "scheduled", "due_at": time.time(), "tries": 0,
            "views": 0, "comments": 0, "likes": 0
        }
        posting._posts.append(p_ambig)
        posting._save()

    def mock_yt_timeout(*args, **kwargs):
        if kwargs.get("on_session"):
            kwargs["on_session"]("https://upload.youtube.com/session_timeout_test")
        raise RuntimeError("httpx.ReadTimeout: The read operation timed out during data transfer")

    with patch("studio.accounts.youtube_upload", side_effect=mock_yt_timeout):
        with ctx.as_user(user.id):
            p_to_run = next(p for p in posting._mine() if p["id"] == "post_ambig_1")
            posting._post(p_to_run)

            p_res = next(p for p in posting._mine() if p["id"] == "post_ambig_1")
            check("ambiguous upload marked failed", p_res["status"], "failed")
            check("ambiguous flag is True", p_res.get("ambiguous", False), True)
            check("session_id was preserved", p_res.get("session_id"), "https://upload.youtube.com/session_timeout_test")
            check("status is not scheduled (no auto-retry)", p_res["status"] != "scheduled", True)

            # 5. Deterministic session reconciliation
            with patch("studio.accounts.youtube_check_session", return_value=("yt_session_vid_123", "https://youtube.com/shorts/yt_session_vid_123")):
                res_rec_session = client.post("/api/posts/post_ambig_1/reconcile")
                check("reconcile using session_id returned 200", res_rec_session.status_code, 200)
                check("reconcile using session_id reconciled True", res_rec_session.json().get("reconciled"), True)
                p_rec = next(p for p in posting._mine() if p["id"] == "post_ambig_1")
                check("status updated to posted", p_rec["status"], "posted")
                check("remote_id is session resolved ID", p_rec["remote_id"], "yt_session_vid_123")


if __name__ == "__main__":
    test_multi_platform_independence_and_reconcile()
    if fails:
        sys.exit(1)
