# ProtonReddit

Personal, non-commercial project to analyze public discussions about Proton and privacy-related issues. The intended analysis compares responses to a discussion with authors' earlier public activity in Proton-focused communities.

## Current code

`reddit_collect.py` uses application-only OAuth to read the `/new` listing of each subreddit in `subreddits.txt`, then reads visible comment trees for the returned posts, expanding `MoreComments` stubs. It writes `posts.jsonl`, `comments.jsonl`, and `coverage.json` to a **new** output directory. Post and comment IDs are unique identifiers; `author` is a public username or null when unavailable. The JSONL files allow author matching within the collected corpus. No sentiment classification is implemented yet.

`reddit_api.py` is a compatibility entry point that calls the same collector. Use `reddit_collect.py` as the access-review source.

`author_activity.py` takes a collected corpus and a target post ID. It reports one row per public commenter, counting their contributions in the **collected Proton corpus before the target post**. It checks that input post and comment IDs are unique. These are observed counts, not complete account histories or sentiment labels.

## Coverage limits

**This code does not claim to retrieve every historical post or comment.** Reddit's `/new` listing can end before the beginning of a community's history. A `MoreComments` stub can also remain unresolved. `coverage.json` records returned pages, observed date ranges, item counts, and unresolved stubs. The community list is an initial verified set, not an exhaustive registry of every Proton-related subreddit. Complete historical coverage depends on what Reddit approves and provides. No code can grant that access on its own.

## Use after Reddit approval

Set `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and `REDDIT_USER_AGENT` in the environment. Never commit credentials. The script only makes read requests and does not post, vote, or message users. Run it only after Reddit approves this use case:

```bash
python3 reddit_collect.py --subreddits-file subreddits.txt --output-dir /path/to/new_run --approved-access
```

After a collection, an author-activity summary can be generated without contacting Reddit:

```bash
python3 author_activity.py --posts /path/to/new_run/posts.jsonl --comments /path/to/new_run/comments.jsonl --target-post-id 1xg8nq9 --output /path/to/new_author_activity.csv
```

The `--approved-access` flag is an operator confirmation, not proof of approval. Collected data must not be committed. Reddit requires deletion of content and author data removed from the platform; a retention and deletion procedure must be settled before collecting real data. This repository is currently for source review, not an operational archive.

## References

- [Reddit Data API documentation](https://www.reddit.com/dev/api/)
- [Reddit OAuth2 documentation](https://github.com/reddit-archive/reddit/wiki/oauth2)
- [Reddit Data API guidance](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)
