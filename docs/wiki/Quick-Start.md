# Quick Start

Agentic Blog reads public Naver Blog content anonymously and writes structured
results to files. It is read-only. It does not log in, use a session or cookie
jar, control a browser, or publish anything.

Install the project first as described in [Installation](Installation.md).

## 1. Search public posts

Start with a public search and choose an explicit output path:

```bash
agentic-blog search "서울 카페" --limit 10 --output seoul-cafes.json
```

The command writes a JSON array to `seoul-cafes.json` and prints a one-line
summary to stderr. Retrieved records are not printed to stdout. A zero-result
search is successful and reports `no_matches` in that summary.

Only publicly readable content is available. A private, neighbour-only,
deleted, or suspended target cannot be read anonymously and is reported as an
unavailable target instead of triggering authentication.

## 2. Follow a result into a blog and its posts

Inspect the saved search result, take a returned `blog_id`, and use that value
with the next primitive:

```bash
agentic-blog blog BLOG_ID --output blog.json
agentic-blog posts BLOG_ID --category 0 --limit 20 --output posts.json
```

`blog` returns the public profile and category tree. `posts` lists public posts
from that blog; category `0` means all categories. For an in-blog text search,
use `--query` instead of `--category`:

```bash
agentic-blog posts BLOG_ID --query "커피" --limit 10 --output blog-search.json
```

This is deliberate chaining: save each response, inspect its identifiers, and
pass the relevant identifier to the next focused command. There is no batch
crawl command.

## 3. Read one public post

Use either a supported Naver Blog post URL or the blog id and log number from a
saved result:

```bash
agentic-blog post "https://blog.naver.com/BLOG_ID/LOG_NO" --output post.json
agentic-blog post BLOG_ID LOG_NO --no-comments --output post-without-comments.json
```

By default, `post` retrieves the body and full comment thread. `--no-comments`
skips comment requests. `--comment-sort new` or `--comment-sort favorite`
selects the comment order, and `--comment-limit N` caps returned comments.

## 4. Explore topics and public neighbours

The public topic tree supplies `directory_seq` values for topic listings:

```bash
agentic-blog topics --output topics.json
agentic-blog topic DIRECTORY_SEQ --limit 20 --output topic-posts.json
agentic-blog buddies BLOG_ID --limit 20 --output buddies.json
```

Use `topic DIRECTORY_SEQ --top` for a topic's top-post listing rather than its
chronological listing. `buddies` returns only a blog's public neighbours.

## Result formats and bounds

Read commands write UTF-8 JSON by default. Use `--format ndjson` when one JSON
object per line is better for downstream processing:

```bash
agentic-blog search "서울 카페" --limit 10 --format ndjson --output seoul-cafes.ndjson
```

`--limit N` applies to `search`, `posts`, `buddies`, and `topic`; it must be
non-negative. `blog`, `post`, and `topics` have fixed result shapes and do not
accept it. Search posts can also use server-side date bounds:

```bash
agentic-blog search "서울 카페" --type post --sort date \
  --since 2026-01-01 --until 2026-06-30 --limit 20 --output cafes-2026.json
```

For the complete path, pacing, request-budget, and environment-variable facts,
see [Configuration](Configuration.md).
