# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-07-25

### Fixed

- Blogs whose id is all digits can be read. Naver issues such ids — `8892050` answers on `category-list`, `post-list`, `public-buddies`, and in-blog search, and its posts render at `m.blog.naver.com/8892050/{logNo}` — but the identifier validator rejected the shape as though it could only be a mistyped numeric `blogNo`. Since these blogs appear in ordinary search results, the tool could return a post and then refuse to open it. Found by an end-to-end session that hit exactly that wall while collecting reviews.

## [0.2.0] - 2026-07-25

### Added

- `search --self-purchased` keeps only posts whose author labelled them 내돈내산 — bought with their own money. It narrows hard: one measured query went from 1,178,608 posts to 3,397, an entirely different result set. It is the blogger's own declaration and not a verification, so it narrows the pool of reviews rather than cleaning it; absence of the label means very little, since most honest posts never carry one.
- `search --type tag` searches the tags authors filed their posts under, rather than the full text. Fewer results than `--type post`, but each is a post someone considered to be *about* the term instead of one that merely mentions it. Tag results carry a leaner card — `blog_no`, `blog_name`, and `category_name` are null, because Naver's tag index does not supply them — but every handle needed to chain onward is present.

### Changed

- `search --type post` now reads Naver's mobile search API. It returns the same posts in the same order — verified identical for the top 20 across four queries — while filling `blog_no`, `category_name`, `comment_count`, `like_count`, and `thumbnail_url`, which the previous source did not supply and which therefore came back null. No field was added, removed, or retyped. `--type blog` and `--type id` deliberately stay on the section API: its blog index is a different and larger corpus (15,441 results against 5,611 for one query) and the mobile blog card carries no description, so moving them would have silently emptied `Blog.description`.
- `posts --query` now uses Naver's in-blog search API instead of scraping the PC search page. Pages carry 20 posts instead of 10 and arrive already populated, so the second request that used to be needed to fill each result is gone — the same answer now costs fewer requests. This also removes the last place where a Naver template change could break a whole command rather than one field. As a result the same five fields listed above are populated here too, and `--query` now accepts `--raw`, which it previously rejected because there was no upstream object to hand back.

### Fixed

- `Blog.post_count` and `Blog.buddy_count` are populated. Both were documented in the output schema and both were null in every output of every command since the first release: no `Blog` constructor ever assigned them, although the response validator had been checking the upstream values all along and discarding them. `buddy_count` reports the neighbours a blog **publicly discloses**, which is what `buddies` can actually enumerate; Naver keeps a second and usually far larger total visible only to the blog's owner, so `0` here means "publishes no neighbour list" rather than "has no neighbours".
- `posts`, `blog`, and `posts --query` no longer abort on posts whose teaser ends mid-emoji. Naver truncates `briefContents` at a fixed length, and when the cut falls between the two halves of an emoji it ships the first half alone. An unpaired surrogate has no UTF-8 encoding, so writing the results raised `UnicodeEncodeError` and killed the command instead of degrading one field. Found by the pre-release sweep on 3 of 30 blogs; present in every release before this one.

### Added (repository)

- A `naver-blog` Claude Code skill at `.claude/skills/naver-blog/`, so Claude can chain the CLI's single-target primitives into multi-hop answers. Not part of the PyPI distribution.

## [0.1.2] - 2026-07-25

### Fixed

- `posts --notices` now reports each notice's comment count. Notice cards spell the field `commentCount` where every other listing uses `commentCnt`, so a number Naver does supply was being dropped.
- A notice's `visibility` is now read from the field the notice card actually carries (`postOpenType`) rather than inferred from the absence of the flags other listings use. The reported value is unchanged for every notice observed — 61 across 21 blogs, all public — but it is now grounded in the response instead of falling out of three missing fields, so an unobserved non-public notice is reported as unknown rather than confidently as public.

## [0.1.1] - 2026-07-25

### Fixed

- `posts` no longer fails on blogs that contain videos. Naver reports a video thumbnail's play length as a number, which the response validator rejected; 21 of 30 sampled blogs were affected.
- `posts --notices` no longer fails on blogs that have pinned notices. The notice surface is a distinct upstream shape that names its blog with `blogId`, and it was being validated as though it were an ordinary post listing; 14 of 30 sampled blogs were affected.
- `post` now reports `created_at`. Single-post reads previously always returned a null publication time. Naver labels recent posts relatively instead ("7시간 전"), and those are still reported as no publish time rather than converted, because a rounded interval is not a timestamp — the listing surfaces expose an exact time for the same post.
- Post dates from `posts --query` are no longer nine hours early. Timestamps rendered in a page are Korean wall-clock time and were being serialized as though they were UTC. All three surfaces that report a post's time — `search`, `posts --query`, and `post` — now agree.
- Post bodies no longer contain `SE-TEXT` editor markers. SmartEditor ONE brackets its text blocks with HTML comments, which were being read as though they were the author's own writing; 12 of 30 sampled posts were affected.
- `post` no longer fails on comments whose attached images carry their address in an alternate field.

### Changed

- The synthetic notice-listing fixture now mirrors the shape Naver actually returns. The previous fixture encoded an assumption that the live API never satisfies, which is why the notice defect above shipped.

## [0.1.0] - 2026-07-25

### Added

- Anonymous, read-only Naver Blog CLI with focused `search`, `blog`, `posts`, `post`, `buddies`, `topics`, and `topic` primitives.
- Offline `catalog` and generated output `schema` commands.
- JSON and NDJSON file output with UTF-8 Korean text preservation, platform data-directory defaults, and explicit output paths.
- Public post-body extraction to lightweight Markdown with media metadata and optional full public comment retrieval.
- Public blog category trees, in-blog post search, public buddy lists, and Naver topic discovery.
- Typed failures and documented exit codes for usage failures, blocking or throttling, response drift, and unavailable anonymous targets.
- A mandatory 0.5-second inter-request floor and per-run request budget.
- Offline, synthetic-fixture test policy; fixture PII checks; live checks restricted to opt-in shape and invariant assertions.
- Release documentation, security reporting guidance, contribution guidance, and responsible-use disclaimer.

### Security

- The runtime is deliberately anonymous: no login flow, account, credential store, cookie jar, session file, browser state, browser dependency, or access-control bypass is included.
- Diagnostic and fixture guidance requires synthetic, PII-free committed data and prohibits real captures and personal session material.
