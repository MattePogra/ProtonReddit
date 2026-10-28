"""Summarize prior activity of commenters within a collected Reddit corpus."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def read_jsonl(path: Path, label: str) -> list[dict]:
    if not path.is_file():
        raise ValueError(f"Missing {label} input: {path}")
    rows = []
    ids = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        row = json.loads(line)
        item_id = row.get("id")
        if not item_id or item_id in ids:
            raise ValueError(f"Missing or duplicate {label} ID at line {line_number}")
        ids.add(item_id)
        rows.append(row)
    return rows


def summarize(posts: list[dict], comments: list[dict], target_post_id: str):
    target_posts = [post for post in posts if post["id"] == target_post_id]
    if len(target_posts) != 1:
        raise ValueError("Target post must appear exactly once in posts input")
    target_time = target_posts[0].get("created_utc")
    if not isinstance(target_time, (int, float)):
        raise ValueError("Target post has no valid creation time")
    target_counts = Counter(
        comment["author"].casefold()
        for comment in comments
        if comment.get("post_id") == target_post_id and comment.get("author")
    )
    prior_posts = Counter()
    prior_comments = Counter()
    communities = defaultdict(set)
    display_name = {}
    for kind, rows, counter in (
        ("post", posts, prior_posts), ("comment", comments, prior_comments)
    ):
        for row in rows:
            author = row.get("author")
            if not author:
                continue
            key = author.casefold()
            display_name.setdefault(key, author)
            created = row.get("created_utc")
            if key in target_counts and isinstance(created, (int, float)) and created < target_time:
                counter[key] += 1
                if row.get("subreddit"):
                    communities[key].add(row["subreddit"])
    return [
        {
            "author": display_name.get(key, key),
            "target_comments": target_counts[key],
            "prior_posts_in_corpus": prior_posts[key],
            "prior_comments_in_corpus": prior_comments[key],
            "prior_subreddits_in_corpus": ",".join(sorted(communities[key])),
        }
        for key in sorted(target_counts)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--posts", required=True, type=Path)
    parser.add_argument("--comments", required=True, type=Path)
    parser.add_argument("--target-post-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new path")
    try:
        posts = read_jsonl(args.posts, "post")
        comments = read_jsonl(args.comments, "comment")
        rows = summarize(posts, comments, args.target_post_id)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        parser.error(str(error))
    if not rows:
        parser.error("No commenters found for target post")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} author rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
