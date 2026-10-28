"""Read public posts and comments through approved Reddit Data API access."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class RedditClient:
    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self._refresh_token()

    def _refresh_token(self):
        basic = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        request = Request(
            "https://www.reddit.com/api/v1/access_token",
            data=b"grant_type=client_credentials",
            headers={"Authorization": f"Basic {basic}", "User-Agent": self.user_agent,
                     "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        response = self._read(request)
        self.token = response["access_token"]
        self.token_expires_at = time.monotonic() + max(
            0, int(response.get("expires_in", 3600)) - 60
        )

    @staticmethod
    def _read(request: Request):
        for attempt in range(5):
            try:
                with urlopen(request, timeout=30) as response:
                    payload = json.load(response)
                    remaining = response.headers.get("X-Ratelimit-Remaining")
                    reset = response.headers.get("X-Ratelimit-Reset")
                    if remaining and reset and float(remaining) < 1:
                        time.sleep(max(0, float(reset)) + 1)
                    return payload
            except HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt == 4:
                    raise RuntimeError(f"Reddit returned HTTP {error.code}") from error
                retry = error.headers.get("Retry-After")
                time.sleep(float(retry) if retry else min(2 ** attempt, 30))
            except URLError as error:
                if attempt == 4:
                    raise RuntimeError(f"Network error: {error.reason}") from error
                time.sleep(min(2 ** attempt, 30))
        raise RuntimeError("Reddit request failed")

    def get(self, path: str, params: dict | None = None):
        if time.monotonic() >= self.token_expires_at:
            self._refresh_token()
        query = f"?{urlencode(params)}" if params else ""
        request = Request(
            f"https://oauth.reddit.com{path}{query}",
            headers={"Authorization": f"Bearer {self.token}",
                     "User-Agent": self.user_agent},
        )
        return self._read(request)


def listing_items(payload):
    return payload["data"]["children"]


def public_author(item):
    author = item.get("author")
    return author if author and author != "[deleted]" else None


def record_post(item):
    return {key: item.get(key) for key in
            ("id", "subreddit", "created_utc", "title", "selftext", "score",
             "num_comments", "permalink")} | {"author": public_author(item)}


def record_comment(item, post_id):
    return {key: item.get(key) for key in
            ("id", "subreddit", "created_utc", "body", "score", "parent_id",
             "permalink")} | {"post_id": post_id, "author": public_author(item)}


def write_jsonl(handle, item):
    handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def collect_comments(client, subreddit, post_id, handle):
    tree = client.get(f"/r/{subreddit}/comments/{post_id}",
                      {"limit": 500, "sort": "old"})
    if not isinstance(tree, list) or len(tree) != 2:
        raise RuntimeError(f"Unexpected comment tree for {post_id}")
    pending = deque(listing_items(tree[1]))
    seen_comments = set()
    requested_children = set()
    unresolved = 0
    while pending:
        thing = pending.popleft()
        kind, item = thing.get("kind"), thing.get("data", {})
        if kind == "t1":
            comment_id = item["id"]
            if comment_id not in seen_comments:
                seen_comments.add(comment_id)
                write_jsonl(handle, record_comment(item, post_id))
            replies = item.get("replies")
            if isinstance(replies, dict):
                pending.extend(listing_items(replies))
        elif kind == "more":
            children = [child for child in item.get("children", [])
                        if child not in requested_children]
            if not children and item.get("count", 0):
                unresolved += 1
            for offset in range(0, len(children), 100):
                batch = children[offset:offset + 100]
                requested_children.update(batch)
                result = client.get("/api/morechildren", {
                    "api_type": "json", "link_id": f"t3_{post_id}",
                    "children": ",".join(batch), "limit_children": "true",
                    "sort": "old",
                })
                pending.extend(result["json"]["data"]["things"])
    return {"comments": len(seen_comments), "unresolved_stubs": unresolved}


def collect_post(client, subreddit, item, posts_handle, comments_handle):
    post = record_post(item)
    if not post["id"]:
        raise RuntimeError("Post without an ID")
    write_jsonl(posts_handle, post)
    counts = collect_comments(client, subreddit, post["id"], comments_handle)
    return post, counts


def collect_subreddit(client, subreddit, posts_handle, comments_handle):
    coverage = {"subreddit": subreddit, "pages": 0, "posts": 0, "comments": 0,
                "unresolved_stubs": 0, "oldest_post_utc": None,
                "newest_post_utc": None, "end_reason": None}
    after = None
    seen_pages, seen_posts = set(), set()
    while True:
        params = {"limit": 100}
        if after:
            params["after"] = after
        page = client.get(f"/r/{subreddit}/new", params)
        coverage["pages"] += 1
        for thing in listing_items(page):
            if thing.get("kind") != "t3":
                continue
            item = thing["data"]
            if item["id"] in seen_posts:
                continue
            seen_posts.add(item["id"])
            post, counts = collect_post(client, subreddit, item,
                                        posts_handle, comments_handle)
            coverage["posts"] += 1
            coverage["comments"] += counts["comments"]
            coverage["unresolved_stubs"] += counts["unresolved_stubs"]
            created = post["created_utc"]
            if isinstance(created, (int, float)):
                old, new = coverage["oldest_post_utc"], coverage["newest_post_utc"]
                coverage["oldest_post_utc"] = min(old, created) if old else created
                coverage["newest_post_utc"] = max(new, created) if new else created
        next_after = page["data"].get("after")
        if not next_after:
            coverage["end_reason"] = "Reddit returned no next listing page"
            return coverage
        if next_after in seen_pages:
            coverage["end_reason"] = "Repeated pagination cursor"
            return coverage
        seen_pages.add(next_after)
        after = next_after


def read_subreddits(path):
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_]+", name):
            raise ValueError(f"Invalid subreddit name: {name}")
        if name.lower() not in {existing.lower() for existing in names}:
            names.append(name)
    if not names:
        raise ValueError("No subreddits provided")
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subreddits-file", type=Path,
                        default=Path(__file__).with_name("subreddits.txt"))
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="New output directory; existing data are never overwritten")
    parser.add_argument("--approved-access", action="store_true",
                        help="Confirm that Reddit approved this use before running")
    args = parser.parse_args()
    try:
        subreddits = read_subreddits(args.subreddits_file)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    output_dir = args.output_dir.expanduser().resolve()
    if output_dir.exists():
        parser.error("Output directory already exists")
    if not args.approved_access:
        parser.error("Reddit approval is required before API access")
    names = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")
    if any(not os.environ.get(name) for name in names):
        parser.error("Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT")
    client = RedditClient(*(os.environ[name] for name in names))
    output_dir.mkdir(parents=True)
    report = {"started_utc": datetime.now(timezone.utc).isoformat(),
              "subreddits": []}
    try:
        with (output_dir / "posts.jsonl").open("w", encoding="utf-8") as posts, \
             (output_dir / "comments.jsonl").open("w", encoding="utf-8") as comments:
            for subreddit in subreddits:
                result = collect_subreddit(client, subreddit, posts, comments)
                report["subreddits"].append(result)
                print(json.dumps(result), file=sys.stderr)
    except (RuntimeError, KeyError, TypeError, ValueError) as error:
        report["error"] = str(error)
        print(f"Collection stopped: {error}", file=sys.stderr)
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (output_dir / "coverage.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 1 if "error" in report else 0


if __name__ == "__main__":
    raise SystemExit(main())
