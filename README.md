# ProtonReddit

I'm building this small, non-commercial project to look at public conversations about Proton and privacy on Reddit. One question I want to explore is whether people commenting on a particular discussion had previously taken part in Proton-focused communities.

Access to the Reddit Data API is still pending, so the code is here for review only.

## What the code does

`reddit_collect.py` is the collector. Once access is approved, it can read recent posts from the communities listed in `subreddits.txt` and the comments on those posts. It saves posts, comments, and a coverage report in a new local directory. It only reads public content; it does not post, vote, or message anyone. `reddit_api.py` is a short entry point to the same collector.

`author_activity.py` works on a collection already saved locally. Given a post ID, it counts each commenter's earlier posts and comments **within that collection**. The counts are not a measure of anyone's full Reddit history. Sentiment analysis is not part of the code yet.

The collector uses Reddit's `/new` listing, which may not reach older posts. Some comment branches may also remain unavailable. The coverage report records what was retrieved and any unresolved comment branches, so missing history is not mistaken for no activity.

## Running it after approval

Set `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and a descriptive `REDDIT_USER_AGENT` in your local environment. Keep credentials and collected data out of Git. Then run:

```bash
python3 reddit_collect.py --subreddits-file subreddits.txt --output-dir /path/to/new_run --approved-access
```

To summarize earlier activity for one post in that collection:

```bash
python3 author_activity.py --posts /path/to/new_run/posts.jsonl --comments /path/to/new_run/comments.jsonl --target-post-id POST_ID --output /path/to/new_author_activity.csv
```

The `--approved-access` flag is a reminder for the person running the script; it does not verify approval. Before collecting real data, the project's scope and its process for removing deleted Reddit content still need to be settled in line with Reddit's requirements.

## Reddit documentation

- [Data API guidance](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)
- [API reference](https://www.reddit.com/dev/api/)
