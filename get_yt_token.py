from __future__ import annotations

"""
Generate a YouTube OAuth refresh token (for headless GitHub Actions uploads).

Prereqs (one-time):
1) Create a Google Cloud project
2) Enable "YouTube Data API v3"
3) Configure OAuth consent screen (External) and publish in testing
4) Create OAuth Client ID: "Desktop app"
5) Download the client secrets JSON and save it as: client_secret.json (in this repo root)

Then run:
  pip install -r requirements.txt
  python get_yt_token.py

It will open a browser window. After you approve, it prints:
  - YT_CLIENT_ID
  - YT_CLIENT_SECRET
  - YT_REFRESH_TOKEN
"""

import json
import os
from pathlib import Path


def main() -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets_path = Path("client_secret.json")
    if not secrets_path.exists():
        raise SystemExit("Missing client_secret.json in repo root (download OAuth Desktop client JSON).")

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]

    # Important: access_type=offline + prompt=consent => refresh_token is issued.
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), scopes=scopes)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline", include_granted_scopes="true")

    # Extract client_id/secret from file for convenience
    raw = json.loads(secrets_path.read_text(encoding="utf-8"))
    installed = raw.get("installed") or raw.get("web") or {}
    client_id = installed.get("client_id", "")
    client_secret = installed.get("client_secret", "")

    if not creds.refresh_token:
        raise SystemExit(
            "No refresh_token returned. Common fixes:\n"
            "- Make sure you used a Desktop OAuth client\n"
            "- Ensure prompt='consent' and access_type='offline'\n"
            "- Revoke the app access in Google Account and run again\n"
        )

    print("\nAdd these to GitHub Secrets:\n")
    print(f"YT_CLIENT_ID={client_id}")
    print(f"YT_CLIENT_SECRET={client_secret}")
    print(f"YT_REFRESH_TOKEN={creds.refresh_token}\n")


if __name__ == "__main__":
    main()

