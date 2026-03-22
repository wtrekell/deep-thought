# Reddit Tool — Enhancements

Future capabilities beyond the current collection-only scope.

---

## Post and Comment Authoring

Add write operations via PRAW's `Subreddit.submit()` for new threads and `Submission.reply()` / `Comment.reply()` for comments. Would require authenticated user credentials (beyond the read-only client credentials used for collection). Potential subcommands: `reddit post`, `reddit reply`.
