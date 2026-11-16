"""Post queue: decides when each finished clip goes to which account, posts it, and tracks views."""
import secrets
import threading
import time
from pathlib import Path

import json

from . import accounts, alerts, config, creators, ctx, jobs, live

_lock = threading.RLock()
_wake = threading.Event()
_FILE = config.DATA_DIR / "posts.json"
try:
    _posts: list = json.loads(_FILE.read_text(encoding="utf-8")) if _FILE.exists() else []
except ValueError:
    _posts = []


def wake():
    """Wake the posting worker immediately when a job is ready or expedited."""
    _wake.set()


def _mine() -> list:
    u = ctx.uid()
    return [p for p in _posts if p.get("user") == u]
OPEN = ("scheduled", "posting")


def _save():
    with _lock:
        tmp = _FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(_posts, indent=1), encoding="utf-8")
        tmp.replace(_FILE)


def _day(t):
    return time.strftime("%Y-%m-%d", time.localtime(t))


def _mirror(p):
    """Copy the post's state onto its clip so the clip card can show it."""
    job = jobs.get(p["job"])
    clip = next((c for c in job["clips"] if c["id"] == p["clip"]), None) if job else None
    if clip is not None:
        clip.setdefault("posts", {})[p["id"]] = {
            k: p.get(k) for k in ("id", "account", "account_name", "platform", "status", "url", "due_at", "error")
        }
        jobs.save(job)


def _next_slot(account_id, gap_min, cap):
    """Earliest time that respects the gap between posts and the daily cap for this account."""
    mine = [p for p in _mine() if p["account"] == account_id and p["status"] in OPEN + ("posted",)]
    t = max(time.time(), max((p.get("posted_at") or p["due_at"] for p in mine), default=0) + gap_min * 60)
    for _ in range(30):
        if sum(1 for p in mine if _day(p.get("posted_at") or p["due_at"]) == _day(t)) < cap:
            break
        lt = time.localtime(t + 86400)
        t = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 9, 0, 0, 0, 0, -1))  # 9:00 next day
    return t


class EnqueueResult(list):
    """List of posts newly queued or expedited, with metadata about already-present items."""
    def __init__(self, items=None, made=None, expedited=None, already_posted=None, already_uploading=None, already_scheduled=None):
        super().__init__(items or [])
        self.made = made or []
        self.expedited = expedited or []
        self.already_posted = already_posted or []
        self.already_uploading = already_uploading or []
        self.already_scheduled = already_scheduled or []


def enqueue(job, clip, account_ids, now=False) -> EnqueueResult:
    c = creators.get(job["creator"]) or creators.DEFAULTS
    made = []
    expedited = []
    already_posted = []
    already_uploading = []
    already_scheduled = []

    with _lock:
        mine = _mine()
        for aid in account_ids:
            acc = accounts.get(aid)
            if not acc:
                continue

            existing = [p for p in mine if p.get("job") == job["id"] and p.get("clip") == clip["id"] and p.get("account") == aid]

            # Already successfully published: never duplicate
            posted_post = next((p for p in existing if p["status"] == "posted"), None)
            if posted_post:
                already_posted.append(posted_post)
                continue

            # Currently uploading: let it finish
            posting_post = next((p for p in existing if p["status"] == "posting"), None)
            if posting_post:
                already_uploading.append(posting_post)
                continue

            # Already scheduled: if now=True, move due time to now immediately; otherwise keep slot
            scheduled_post = next((p for p in existing if p["status"] == "scheduled"), None)
            if scheduled_post:
                if now:
                    scheduled_post["due_at"] = time.time()
                    scheduled_post["expedited"] = True
                    scheduled_post["error"] = None
                    expedited.append(scheduled_post)
                    wake()
                else:
                    already_scheduled.append(scheduled_post)
                continue

            # If previously cancelled or failed, reactivate this post record
            reusable_post = next((p for p in existing if p["status"] in ("cancelled", "failed")), None)
            due = time.time() if now else _next_slot(aid, c["post_gap_min"], c["daily_cap"])
            if reusable_post:
                reusable_post.update(status="scheduled", due_at=due, tries=0, error=None,
                                     expedited=bool(now),
                                     title=clip.get("title") or clip.get("hook") or "Clip",
                                     score=clip.get("score", 0))
                made.append(reusable_post)
                if now:
                    wake()
            else:
                p = {"id": secrets.token_hex(8), "user": ctx.uid(), "job": job["id"], "clip": clip["id"], "creator": job["creator"],
                     "account": aid, "account_name": acc["name"], "platform": acc["platform"], "status": "scheduled",
                     "due_at": due, "expedited": bool(now), "created": time.time(), "title": clip.get("title") or clip.get("hook") or "Clip",
                     "score": clip.get("score", 0), "tries": 0, "url": "", "remote_id": "", "error": None, "views": None}
                _posts.append(p)
                made.append(p)
                if now:
                    wake()

        if made or expedited:
            _save()

    for p in made + expedited:
        _mirror(p)

    return EnqueueResult(
        items=made + expedited,
        made=made,
        expedited=expedited,
        already_posted=already_posted,
        already_uploading=already_uploading,
        already_scheduled=already_scheduled,
    )


def on_clip_ready(job, clip):
    """Called once when a clip first finishes rendering."""
    uid = job.get("user") or ctx.uid()
    with ctx.as_user(uid):
        c = creators.get(job["creator"])
        if not c or not c["autopost"] or not c["accounts"]:
            return
        if clip.get("score", 0) < c["post_min_score"]:
            return  # includes hand-made clips (score 0): those wait for you to press Post
        made = enqueue(job, clip, c["accounts"])
        if made:
            creators.log(c["id"], f"Queued for {len(made)} account(s): {clip.get('title') or clip.get('hook')}")


def _caption(clip, creator):
    tags = " ".join("#" + h for h in clip.get("hashtags", []))
    return "\n\n".join(x for x in (clip.get("description", ""), tags, creator.get("post_footer", "")) if x)


def _post(p):
    import hashlib
    job = jobs.get(p["job"])
    clip = next((c for c in job["clips"] if c["id"] == p["clip"]), None) if job else None
    acc = accounts.get(p["account"])
    try:
        if not clip or clip.get("status") != "done":
            raise RuntimeError("The clip no longer exists or is not finished.")
        if not acc:
            raise RuntimeError("That account was disconnected.")
        path = Path(job["dir"]) / "clips" / clip["file"]
        if not path.is_file():
            raise RuntimeError("The rendered clip file is missing.")
        try:
            with path.open("rb") as f:
                p["fingerprint"] = hashlib.sha256(f.read()).hexdigest()[:32]
        except Exception:
            pass

        creator = creators.get(job["creator"]) or dict(creators.DEFAULTS, name="clips")
        title, cap = clip.get("title") or clip.get("hook") or "Clip", _caption(clip, creator)

        def on_session(sid):
            p["session_id"] = str(sid)
            _save()
            _mirror(p)

        # Deterministic Session Verification: If a session ID was recorded, check if it completed remotely
        if p.get("session_id"):
            if acc["platform"] == "youtube":
                found_id, found_url = accounts.youtube_check_session(acc, p["session_id"], path.stat().st_size)
            elif acc["platform"] == "instagram":
                found_id, found_url = accounts.instagram_check_session(acc, p["session_id"])
            elif acc["platform"] == "tiktok":
                found_id, found_url = accounts.tiktok_check_session(acc, p["session_id"])
            else:
                found_id, found_url = None, None

            if found_id:
                p.update(status="posted", posted_at=time.time(), remote_id=found_id, url=found_url,
                         error=None, expedited=False, ambiguous=False)
                creators.log(p["creator"], f"Verified existing remote session completed on {acc['name']}: {title}")
                _save()
                _mirror(p)
                return

        try:
            if acc["platform"] == "youtube":
                rid, url = accounts.youtube_upload(acc, path, title, cap + "\n\n#Shorts", clip.get("hashtags", []), creator["privacy"], on_session=on_session)
            elif acc["platform"] == "instagram":
                rid, url = accounts.instagram_upload(acc, path, f"{title}\n\n{cap}", job["id"], on_session=on_session)
            elif acc["platform"] == "tiktok":
                rid, url = accounts.tiktok_upload(acc, path, f"{title}\n\n{cap}", creator["privacy"], on_session=on_session)
            else:
                raise RuntimeError("That kind of account is no longer supported.")
        except TypeError as te:
            if "on_session" in str(te):
                if acc["platform"] == "youtube":
                    rid, url = accounts.youtube_upload(acc, path, title, cap + "\n\n#Shorts", clip.get("hashtags", []), creator["privacy"])
                elif acc["platform"] == "instagram":
                    rid, url = accounts.instagram_upload(acc, path, f"{title}\n\n{cap}", job["id"])
                elif acc["platform"] == "tiktok":
                    rid, url = accounts.tiktok_upload(acc, path, f"{title}\n\n{cap}", creator["privacy"])
                else:
                    raise
            else:
                raise
        p.update(status="posted", posted_at=time.time(), remote_id=rid, url=url, error=None, expedited=False, ambiguous=False)
        creators.log(p["creator"], f"Posted to {acc['name']}: {title}")
    except Exception as e:  # noqa: BLE001
        err_msg = str(e)[-300:]
        p["error"] = err_msg

        # An outcome is ambiguous if an upload session was registered or if the failure was a network/transfer timeout
        is_ambiguous = bool(p.get("session_id")) or any(term in err_msg.lower() for term in (
            "timeout", "timed out", "connection reset", "broken pipe", "stream", "remote disconnected",
            "transfer", "readtimeout", "connecttimeout"
        ))

        if is_ambiguous:
            # NEVER automatically retry an ambiguous upload: halt retries to prevent duplicate remote posts
            p.update(status="failed", ambiguous=True,
                     error=f"Upload outcome uncertain: {err_msg}. Automatic retry halted to prevent duplicate posts. Use Reconcile or Review.")
            creators.log(p["creator"], f"Upload ambiguous for {acc['name'] if acc else 'account'}: {p.get('title')}. Automatic retry halted.")
            alerts.notify(f"upload ambiguous on {p.get('account_name', 'account')} ({p.get('title')}): {err_msg[:150]}", kind="post")
        else:
            p["tries"] += 1
            if p["tries"] < 3 and clip and acc:
                p.update(status="scheduled", due_at=time.time() + 600, ambiguous=False)
            else:
                p.update(status="failed", ambiguous=False)
                creators.log(p["creator"], f"Post failed on {p['account_name']}: {p['error']}")
                alerts.notify(f"post failed on {p['account_name']} ({p['title']}): {p['error'][:200]}", kind="post")
    _save()
    _mirror(p)


_last_posted_by_account: dict = {}


def _run():
    while True:
        _wake.wait(timeout=15)
        _wake.clear()
        due = sorted(
            [p for p in list(_posts) if p["status"] == "scheduled" and p["due_at"] <= time.time() and p.get("user")],
            key=lambda x: (0 if x.get("expedited") else 1, x["due_at"])
        )
        for p in due:
            try:
                with ctx.as_user(p["user"]):
                    if accounts.settings()["paused"]:
                        continue

                    # Rate-limit / restart pacing protection:
                    # If multiple scheduled posts for the same account are overdue after restart,
                    # pace them out according to creator's post_gap_min unless explicitly expedited (Post Now).
                    aid = p.get("account")
                    if aid and not p.get("expedited"):
                        c = creators.get(p.get("creator")) or dict(creators.DEFAULTS, name="clips")
                        gap_sec = max(60, int((c.get("post_gap_min") or 60) * 60))
                        last_t = _last_posted_by_account.get(aid, 0)
                        now_t = time.time()
                        if last_t and (now_t - last_t) < gap_sec:
                            with _lock:
                                if p["status"] == "scheduled":
                                    p["due_at"] = last_t + gap_sec
                                    _save()
                            _mirror(p)
                            continue

                    with _lock:
                        if p["status"] != "scheduled":
                            continue
                        p["status"] = "posting"
                        _save()
                    _mirror(p)
                    _post(p)
                    if aid and p.get("status") == "posted":
                        _last_posted_by_account[aid] = time.time()
            except Exception:  # noqa: BLE001
                pass


def _stats_for(recent):
    for aid in {p["account"] for p in recent if p["platform"] == "youtube"}:
        acc = accounts.get(aid)
        if acc:
            views = accounts.youtube_views(acc, [p["remote_id"] for p in recent if p["account"] == aid])
            for p in recent:
                if p["account"] == aid and p["remote_id"] in views:
                    p["views"] = views[p["remote_id"]]
    for p in recent:
        acc = accounts.get(p["account"]) if p["platform"] == "instagram" else None
        if acc:
            v = accounts.instagram_views(acc, p["remote_id"])
            if v is not None:
                p["views"] = v


def _stats():
    while True:
        for uid in {p.get("user") for p in _posts if p.get("user")}:
            try:
                with ctx.as_user(uid):
                    _stats_for([p for p in _mine() if p["status"] == "posted" and time.time() - p["posted_at"] < 14 * 86400])
            except Exception:  # noqa: BLE001
                pass
        _save()
        time.sleep(1800)


def cancel(pid):
    with _lock:
        p = next((p for p in _mine() if p["id"] == pid), None)
        if not p or p["status"] != "scheduled":
            raise ValueError("Only posts that are still waiting can be cancelled.")
        p["status"] = "cancelled"
        _save()
    _mirror(p)


def retry(pid):
    with _lock:
        p = next((p for p in _mine() if p["id"] == pid), None)
        if not p or p["status"] not in ("failed", "cancelled"):
            raise ValueError("Only failed or cancelled posts can be retried.")
        p.update(status="scheduled", due_at=time.time(), tries=0, error=None)
        _save()
    _mirror(p)
    wake()


def reconcile(pid):
    """Check whether a post in an uncertain or failed state actually succeeded on the remote platform."""
    with _lock:
        p = next((p for p in _mine() if p["id"] == pid), None)
        if not p:
            raise ValueError("No such post found.")
        acc = accounts.get(p["account"])
        if not acc:
            raise ValueError("The connected account for this post was removed.")
        rid = p.get("remote_id")
        if rid:
            try:
                if p["platform"] == "youtube":
                    views = accounts.youtube_views(acc, [rid])
                    if rid in views:
                        p.update(status="posted", error=None, url=p.get("url") or f"https://youtube.com/shorts/{rid}")
                        _save()
                        _mirror(p)
                        return {"reconciled": True, "status": "posted", "url": p["url"]}
                elif p["platform"] == "instagram":
                    v = accounts.instagram_views(acc, rid)
                    if v is not None:
                        p.update(status="posted", error=None)
                        _save()
                        _mirror(p)
                        return {"reconciled": True, "status": "posted", "url": p.get("url", "")}
            except Exception:
                pass
        elif p.get("session_id"):
            # Verify persistent upload session deterministically
            try:
                job = jobs.get(p["job"])
                clip = next((c for c in job["clips"] if c["id"] == p["clip"]), None) if job else None
                path = Path(job["dir"]) / "clips" / clip["file"] if clip else None
                size = path.stat().st_size if path and path.is_file() else 0
                if p["platform"] == "youtube":
                    fid, furl = accounts.youtube_check_session(acc, p["session_id"], size)
                elif p["platform"] == "instagram":
                    fid, furl = accounts.instagram_check_session(acc, p["session_id"])
                elif p["platform"] == "tiktok":
                    fid, furl = accounts.tiktok_check_session(acc, p["session_id"])
                else:
                    fid, furl = None, None

                if fid:
                    p.update(status="posted", remote_id=fid, url=furl, error=None, ambiguous=False)
                    _save()
                    _mirror(p)
                    return {"reconciled": True, "status": "posted", "url": furl}
            except Exception:
                pass
        p.update(status="scheduled", due_at=time.time(), tries=0, error=None, ambiguous=False)
        _save()
    _mirror(p)
    wake()
    return {"reconciled": False, "status": "scheduled", "message": "Post safely rescheduled for immediate retry."}


def overview() -> dict:
    today = _day(time.time())
    _posts = _mine()  # everything below is about the signed-in user only
    rows = []
    all_cs, all_js = creators.all_creators(), jobs.list_jobs()
    for c in all_cs:
        js = [j for j in all_js if j["creator"] == c["id"]]
        clips = [k for j in js for k in j["clips"] if k.get("status") == "done"]
        ps = [p for p in _posts if p["creator"] == c["id"]]
        views = sum(p["views"] or 0 for p in ps)
        rows.append({
            "id": c["id"], "name": c["name"],
            "state": "recording" if live.active_for(c["id"]) else "waiting" if c["auto_watch"] and c["channel"] else "idle",
            "autopost": c["autopost"] and bool(c["accounts"]),
            "clips_today": sum(1 for k in clips if _day(k.get("made_at", 0)) == today), "clips_total": len(clips),
            "posted_today": sum(1 for p in ps if p["status"] == "posted" and _day(p["posted_at"]) == today),
            "posted_total": sum(1 for p in ps if p["status"] == "posted"),
            "queued": sum(1 for p in ps if p["status"] in OPEN), "failed": sum(1 for p in ps if p["status"] == "failed"),
            "views": views, "earnings": round(views / 1000 * c["rate_per_1k"], 2)})
    names = {c["id"]: c["name"] for c in all_cs}
    queue = sorted((p for p in _posts if p["status"] in OPEN), key=lambda p: p["due_at"])
    done = sorted((p for p in _posts if p["status"] in ("posted", "failed")), key=lambda p: -(p.get("posted_at") or p["due_at"]))[:15]
    show = [{**{k: v for k, v in p.items() if k != "user"}, "creator_name": names.get(p["creator"], "")} for p in queue + done]
    # last 14 days, oldest first, for the home graph
    days = [_day(time.time() - 86400 * i) for i in range(13, -1, -1)]
    made, posted, views = {d: 0 for d in days}, {d: 0 for d in days}, {d: 0 for d in days}
    for j in all_js:
        for k in j["clips"]:
            d = _day(k.get("made_at") or j["created"])
            if k.get("status") == "done" and d in made:
                made[d] += 1
    for p in _posts:
        if p["status"] == "posted" and _day(p["posted_at"]) in posted:
            posted[_day(p["posted_at"])] += 1
            views[_day(p["posted_at"])] += p["views"] or 0
    daily = [{"day": d, "clips": made[d], "posted": posted[d], "views": views[d]} for d in days]
    return {"paused": accounts.settings()["paused"], "creators": rows, "posts": show, "daily": daily,
            "alerts": alerts.configured(), "recording": len(live.active_mine())}


def digest_text() -> str:
    o = overview()
    lines = ["PeakCut daily summary"]
    for r in o["creators"]:
        lines.append(f"- {r['name']}: {r['state']}, {r['clips_today']} clips today, {r['posted_today']} posted today, "
                     f"{r['queued']} waiting, {r['failed']} failed, {r['views']} views")
    if not o["creators"]:
        lines.append("No creators set up yet.")
    if o["paused"]:
        lines.append("Posting is paused.")
    return "\n".join(lines)


def start():
    with _lock:
        for p in _posts:
            if p["status"] == "posting":  # interrupted mid-upload last time
                p.update(status="failed", error="The studio closed during this upload. Check the account, then retry.")
        _save()
    jobs.on_clip_ready.append(on_clip_ready)
    threading.Thread(target=_run, daemon=True).start()
    threading.Thread(target=_stats, daemon=True).start()
    threading.Thread(target=alerts.digest_loop, args=(digest_text,), daemon=True).start()
    threading.Thread(target=alerts.keep_awake_loop,
                     args=(lambda: bool(live.active()) or any(p["status"] in OPEN for p in _posts),), daemon=True).start()
