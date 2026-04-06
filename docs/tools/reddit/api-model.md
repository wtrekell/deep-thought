# PRAW SDK Model Reference

Source: [PRAW 7.7.1 documentation](https://praw.readthedocs.io/en/stable/)

PRAW dynamically provides attributes from the Reddit API. Attributes are subject to change on Reddit's end. The tables below reflect typical attributes as of PRAW 7.7.1.

---

## Submission

[Documentation](https://praw.readthedocs.io/en/stable/code_overview/models/submission.html)

### Attributes

| Attribute                | Type            | Description                                                   |
| ------------------------ | --------------- | ------------------------------------------------------------- |
| `id`                     | `str`           | ID of the submission                                          |
| `title`                  | `str`           | The title of the submission                                   |
| `selftext`               | `str`           | The submission's selftext — empty string if a link post       |
| `author`                 | `Redditor`      | Instance of Redditor                                          |
| `score`                  | `int`           | The number of upvotes for the submission                      |
| `upvote_ratio`           | `float`         | The percentage of upvotes from all votes                      |
| `num_comments`           | `int`           | The number of comments on the submission                      |
| `url`                    | `str`           | The URL the submission links to, or the permalink if selfpost |
| `permalink`              | `str`           | A permalink for the submission                                |
| `name`                   | `str`           | Fullname of the submission                                    |
| `created_utc`            | `int`           | Time the submission was created, in Unix Time                 |
| `subreddit`              | `Subreddit`     | Instance of Subreddit                                         |
| `comments`               | `CommentForest` | Instance of CommentForest                                     |
| `link_flair_text`        | `str \| None`   | The link flair's text content, or None if not flaired         |
| `link_flair_template_id` | `str`           | The link flair's ID                                           |
| `author_flair_text`      | `str \| None`   | The text content of the author's flair, or None               |
| `is_self`                | `bool`          | Whether the submission is a selfpost (text-only)              |
| `is_original_content`    | `bool`          | Whether set as original content                               |
| `over_18`                | `bool`          | Whether marked as NSFW                                        |
| `spoiler`                | `bool`          | Whether marked as a spoiler                                   |
| `stickied`               | `bool`          | Whether the submission is stickied                            |
| `locked`                 | `bool`          | Whether the submission has been locked                        |
| `distinguished`          | `bool`          | Whether the submission is distinguished                       |
| `edited`                 | `bool`          | Whether the submission has been edited                        |
| `clicked`                | `bool`          | Whether clicked by the client                                 |
| `saved`                  | `bool`          | Whether the submission is saved                               |
| `poll_data`              | `PollData`      | Poll submission data (if applicable)                          |

### Key Methods

| Method                                     | Description                             |
| ------------------------------------------ | --------------------------------------- |
| `reply()`                                  | Post a comment reply                    |
| `crosspost()`                              | Create a crosspost in another subreddit |
| `edit()`                                   | Modify submission body                  |
| `delete()`                                 | Remove the submission                   |
| `hide()` / `unhide()`                      | Hide/restore from user's feed           |
| `save()` / `unsave()`                      | Bookmark/unbookmark the submission      |
| `upvote()` / `downvote()` / `clear_vote()` | Vote controls                           |
| `duplicates()`                             | Find duplicate submissions              |
| `report()`                                 | Report to moderators                    |

---

## Comment

[Documentation](https://praw.readthedocs.io/en/stable/code_overview/models/comment.html)

### Attributes

| Attribute       | Type            | Description                                                      |
| --------------- | --------------- | ---------------------------------------------------------------- |
| `id`            | `str`           | The ID of the comment                                            |
| `body`          | `str`           | The body of the comment, as Markdown                             |
| `body_html`     | `str`           | The body of the comment, as HTML                                 |
| `author`        | `Redditor`      | Instance of Redditor                                             |
| `score`         | `int`           | The number of upvotes for the comment                            |
| `created_utc`   | `int`           | Time the comment was created, in Unix Time                       |
| `parent_id`     | `str`           | ID of parent comment (`t1_` prefix) or submission (`t3_` prefix) |
| `link_id`       | `str`           | Submission ID the comment belongs to, prefixed with `t3_`        |
| `permalink`     | `str`           | URL path to the comment                                          |
| `replies`       | `CommentForest` | Instance of CommentForest                                        |
| `submission`    | `Submission`    | The submission containing this comment                           |
| `subreddit`     | `Subreddit`     | Instance of Subreddit                                            |
| `subreddit_id`  | `str`           | ID of the subreddit containing the comment                       |
| `is_submitter`  | `bool`          | Whether the comment author is also the submission author         |
| `distinguished` | `bool`          | Whether the comment is distinguished                             |
| `edited`        | `bool`          | Whether the comment has been edited                              |
| `stickied`      | `bool`          | Whether the comment is stickied                                  |
| `saved`         | `bool`          | Whether the comment is saved                                     |

### Key Methods

| Method                                     | Description                               |
| ------------------------------------------ | ----------------------------------------- |
| `reply()`                                  | Create a response to the comment          |
| `edit()`                                   | Modify the comment text                   |
| `delete()`                                 | Remove the comment                        |
| `parent()`                                 | Retrieve the parent comment or submission |
| `refresh()`                                | Update comment data from server           |
| `save()` / `unsave()`                      | Bookmark/unbookmark the comment           |
| `upvote()` / `downvote()` / `clear_vote()` | Vote controls                             |
| `report()`                                 | Flag for moderator review                 |

---

## Subreddit

[Documentation](https://praw.readthedocs.io/en/stable/code_overview/models/subreddit.html)

### Attributes

| Attribute               | Type   | Description                                             |
| ----------------------- | ------ | ------------------------------------------------------- |
| `id`                    | `str`  | ID of the subreddit                                     |
| `display_name`          | `str`  | Name of the subreddit                                   |
| `name`                  | `str`  | Fullname of the subreddit                               |
| `description`           | `str`  | Subreddit description, in Markdown                      |
| `description_html`      | `str`  | Subreddit description, in HTML                          |
| `public_description`    | `str`  | Description shown in searches and community access page |
| `subscribers`           | `int`  | Count of subscribers                                    |
| `created_utc`           | `int`  | Time the subreddit was created, in Unix Time            |
| `over18`                | `bool` | Whether the subreddit is NSFW                           |
| `spoilers_enabled`      | `bool` | Whether the spoiler tag feature is enabled              |
| `can_assign_link_flair` | `bool` | Whether users can assign their own link flair           |
| `can_assign_user_flair` | `bool` | Whether users can assign their own user flair           |
| `user_is_banned`        | `bool` | Whether the authenticated user is banned                |
| `user_is_moderator`     | `bool` | Whether the authenticated user is a moderator           |
| `user_is_subscriber`    | `bool` | Whether the authenticated user is subscribed            |

### Key Listing Methods

| Method     | Description                                    |
| ---------- | ---------------------------------------------- |
| `hot()`    | Listings sorted by hot                         |
| `new()`    | Listings sorted by new                         |
| `top()`    | Listings sorted by top (accepts `time_filter`) |
| `rising()` | Listings sorted by rising                      |
| `search()` | Search submissions in the subreddit            |
