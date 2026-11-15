# Social Publishing Subsystem Guide

SliceMov features an independent, multi-platform publishing engine designed to distribute rendered clips to YouTube, Instagram, and TikTok using their official developer APIs.

---

## Architecture Principles

1. **Platform Independence**:
   Every publishing target (e.g. YouTube account #1, Instagram account #2, TikTok account #3) maintains its own completely decoupled job record.
   - If TikTok fails due to missing permissions, YouTube and Instagram succeed independently.
   - A single clip can be published to multiple accounts simultaneously or across different schedules.
2. **Idempotency & Race Safety**:
   - Submissions use database transactions and atomic file locking to prevent duplicate upload jobs.
   - Rapidly pressing **Post Now** expedites existing scheduled records rather than spawning redundant jobs.
3. **Safe Reconciliation**:
   - If a network dropout occurs while uploading a clip, the post record enters an uncertain state rather than automatically retrying.
   - Calling `/api/posts/{id}/reconcile` queries the remote API with the post's `remote_id` to verify if the video landed remotely.
   - If confirmed on the remote platform, the post is marked `posted`. If absent, it is safely scheduled for immediate retry without duplicating.

---

## Platform Requirements & Implementations

### 1. YouTube Shorts

- **API Used**: YouTube Data API v3 (`videos.insert`).
- **Authentication**: Official Google OAuth 2.0 with scopes:
  - `https://www.googleapis.com/auth/youtube.upload`
  - `https://www.googleapis.com/auth/youtube.readonly`
- **Upload Mechanism**: Direct / Resumable HTTP POST with metadata:
  - Title (up to 100 characters).
  - Description including relevant hashtags and `#Shorts`.
  - Privacy status: `public`, `unlisted`, or `private`.
- **Status Verification**: Verified via `videos.list(part="status,statistics", id=...)`.

### 2. Instagram Reels

- **API Used**: Meta Graph API for Instagram (`/{ig-user-id}/media` and `/{ig-user-id}/media_publish`).
- **Account Requirements**:
  - Must be an **Instagram Business** or **Creator** account.
  - Must be linked to a **Facebook Page**.
- **Upload Mechanism**:
  1. Initialize video container with video URL and caption: `POST /{ig-user-id}/media?media_type=REELS&video_url=...`.
  2. Poll container status until status code is `FINISHED`.
  3. Publish container: `POST /{ig-user-id}/media_publish?creation_id=...`.
- **Media Delivery Requirement**:
  Instagram requires the media file to be accessible via a public URL during container creation. SliceMov utilizes `PEAKCUT_PUBLIC_URL` to serve the signed clip asset to Instagram's ingestion servers.

### 3. TikTok

- **API Used**: Official TikTok Content Posting API v2 (`/v2/post/publish/video/init/`).
- **Authentication**: Official TikTok Login Kit / OAuth 2.0:
  - `video.upload`
  - `video.publish`
- **Application Review & Scopes**:
  - Unaudited developer apps on TikTok are restricted from making public feed posts directly without platform approval.
  - TikTok videos posted by unreviewed apps may appear only under the creator's private videos.
- **Audited App Compliance**:
  - SliceMov strictly respects privacy options returned by TikTok's API (`privacy_level_options`).
  - Never misrepresents a private upload as public.
- **Compliant Manual Upload Fallback**:
  - When direct API permissions are pending or unavailable, SliceMov provides one-click MP4 clip download with copied title, description, and hashtags for manual upload via TikTok Web Studio.

---

## State Transition Machine

```
                   +-------------+
                   |  Not Queued |
                   +-------------+
                          |
             [Add to Queue / Post Now]
                          v
                   +-------------+
                   |  Scheduled  |<------------------------+
                   +-------------+                         |
                          |                                |
               [Worker tick / Post Now]                    |
                          v                                |
                   +-------------+                         |
                   |   Posting   |                         |
                   +-------------+                         |
                     /         \                           |
              [Success]       [Failure]                    |
                  /               \                        |
                 v                 v                       |
         +-------------+     +-------------+               |
         |   Posted    |     |   Failed    |               |
         +-------------+     +-------------+               |
                |               /          \               |
                |          [Retry]    [Reconcile]          |
                |             /              \             |
                |            v                v            |
                |      +-------------+   +----------------+|
                |      |  Scheduled  |   | Verified Remote||
                |      +-------------+   +----------------+|
                |                             |            |
                +-----------------------------+------------+
```

---

## API Endpoints

- `POST /api/posts`: Queue or expedite posts for specific accounts (`{job, clip, accounts, now}`).
- `POST /api/posts/{id}/cancel`: Cancel a pending scheduled post.
- `POST /api/posts/{id}/retry`: Safely retry a failed post.
- `POST /api/posts/{id}/reconcile`: Query remote platform status to resolve uncertain or failed uploads.
- `DELETE /api/accounts/{id}`: Disconnect a connected social account.

