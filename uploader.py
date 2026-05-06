from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

import requests

from log_utils import get_logger


logger = get_logger("uploader")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def require(name: str) -> str:
    v = env(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


# ----------------------------
# Instagram Graph API (Business / Creator + Facebook Page)
# NOTE: Graph API requires *publicly accessible* media URLs for publishing.
# GitHub Pages can host PDFs; images/videos usually need a public URL too.
# ----------------------------


def _graph_error_message(resp: requests.Response) -> str:
    try:
        payload = resp.json()
    except ValueError:
        return resp.text.strip() or f"HTTP {resp.status_code}"

    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return json.dumps(payload, ensure_ascii=False)

    message = str(error.get("message") or f"HTTP {resp.status_code}")
    code = error.get("code")
    error_type = error.get("type")
    subcode = error.get("error_subcode")
    if "token" in message.lower() or code in {190}:
        message = f"Instagram token issue: {message}"
    details = [part for part in [error_type, f"code={code}" if code else "", f"subcode={subcode}" if subcode else ""] if part]
    return f"{message} ({', '.join(details)})" if details else message


def _graph_post(*, url: str, data: dict[str, str]) -> dict:
    try:
        resp = requests.post(url, data=data, timeout=60)
    except requests.RequestException as exc:
        raise RuntimeError(f"Instagram Graph API request failed: {exc}") from exc
    if not resp.ok:
        raise RuntimeError(_graph_error_message(resp))
    try:
        payload = resp.json()
    except ValueError as exc:
        raise RuntimeError("Instagram Graph API returned non-JSON data.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Instagram Graph API returned an unexpected payload shape.")
    return payload


def _ensure_docs_base_url(base: str) -> str:
    base = (base or "").strip().rstrip("/")
    if not base:
        return base
    return base if base.endswith("/docs") else f"{base}/docs"


def instagram_create_image_container(*, image_url: str, caption: str = "") -> str:
    """
    Creates an IG media container for an image (for carousel).
    Requires:
      - INSTAGRAM_TOKEN (long-lived access token)
      - INSTAGRAM_IG_USER_ID
    """
    token = require("INSTAGRAM_TOKEN")
    ig_user_id = require("INSTAGRAM_IG_USER_ID")
    url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
    payload = _graph_post(
        url=url,
        data={
            "image_url": image_url,
            "caption": caption,
            "is_carousel_item": "true",
            "access_token": token,
        },
    )
    container_id = str(payload.get("id") or "").strip()
    if not container_id:
        raise RuntimeError(f"Instagram did not return a media container ID for image URL: {image_url}")
    return container_id


def instagram_create_carousel_container(*, children: list[str], caption: str) -> str:
    if len(children) < 2:
        raise RuntimeError("Instagram carousel publish requires at least 2 child media containers.")
    token = require("INSTAGRAM_TOKEN")
    ig_user_id = require("INSTAGRAM_IG_USER_ID")
    url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
    payload = _graph_post(
        url=url,
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(children),
            "caption": caption,
            "access_token": token,
        },
    )
    container_id = str(payload.get("id") or "").strip()
    if not container_id:
        raise RuntimeError("Instagram did not return a carousel container ID.")
    return container_id


def instagram_publish(*, creation_id: str) -> str:
    token = require("INSTAGRAM_TOKEN")
    ig_user_id = require("INSTAGRAM_IG_USER_ID")
    url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish"
    payload = _graph_post(url=url, data={"creation_id": creation_id, "access_token": token})
    published_id = str(payload.get("id") or "").strip()
    if not published_id:
        raise RuntimeError("Instagram publish succeeded without returning a media ID.")
    return published_id


def post_instagram_carousel(*, image_urls: list[str], caption: str) -> str:
    """
    Publish a carousel from public image URLs.
    """
    if len(image_urls) < 2:
        raise RuntimeError("Instagram carousel upload requires at least 2 public image URLs.")
    child_ids = [instagram_create_image_container(image_url=u) for u in image_urls]
    creation_id = instagram_create_carousel_container(children=child_ids, caption=caption)
    return instagram_publish(creation_id=creation_id)


def _join_url(base: str, path: str) -> str:
    base = _ensure_docs_base_url(base).rstrip("/")
    path = (path or "").strip().lstrip("/")
    return f"{base}/{path}"


def post_instagram_carousel_from_pages_assets(*, slide_filenames: list[str], caption: str) -> str:
    """
    Zero-cost hosting via GitHub Pages.

    Requirements:
      - GITHUB_PAGES_BASE_URL: base URL where `docs/` is served.
        Example (recommended): https://<user>.github.io/<repo>
        Then slides should be available at: <base>/assets/<slide_file>

      - Slides must be deployed publicly *before* calling this.

    Implements the exact 3-step carousel flow:
      1) Create item containers for each image URL
      2) Create carousel container from those item container IDs
      3) Publish carousel container
    """
    if len(slide_filenames) < 2:
        raise RuntimeError("docs/assets/manifest.json must contain at least 2 slides for an Instagram carousel.")
    base = _ensure_docs_base_url(require("GITHUB_PAGES_BASE_URL"))
    image_urls = [_join_url(base, f"assets/{name}") for name in slide_filenames]
    child_ids = [instagram_create_image_container(image_url=u) for u in image_urls]
    carousel_id = instagram_create_carousel_container(children=child_ids, caption=caption)
    return instagram_publish(creation_id=carousel_id)


# ----------------------------
# YouTube Data API v3 upload
# Auth model: OAuth refresh token (recommended for GitHub Actions).
#
# Secrets:
# - YT_CLIENT_ID
# - YT_CLIENT_SECRET
# - YT_REFRESH_TOKEN
# - YT_CHANNEL_ID (optional; API uses default channel of the credential)
# ----------------------------


def _youtube_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    client_id = require("YT_CLIENT_ID")
    client_secret = require("YT_CLIENT_SECRET")
    refresh_token = require("YT_REFRESH_TOKEN")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    return build("youtube", "v3", credentials=creds)


def upload_youtube_video(
    *,
    video_path: str,
    title: str,
    description: str,
    tags: Optional[list[str]] = None,
    category_id: str = "22",
    privacy_status: str = "public",
    thumbnail_path: Optional[str] = None,
) -> str:
    """
    Uploads a video to YouTube, returns the videoId.
    """
    from googleapiclient.http import MediaFileUpload

    youtube = _youtube_service()
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {"privacyStatus": privacy_status},
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            logger.info("Upload progress: %s%%", pct)

    vid = str((resp or {}).get("id") or "").strip()
    if not vid:
        raise RuntimeError("YouTube upload completed without returning a video ID.")

    if thumbnail_path:
        try:
            youtube.thumbnails().set(videoId=vid, media_body=MediaFileUpload(thumbnail_path)).execute()
        except Exception as exc:
            logger.warning("Thumbnail upload skipped/failed: %s", exc)

    return vid

