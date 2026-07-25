# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A `naver-blog` Claude Code skill at `.claude/skills/naver-blog/`, so Claude can chain the CLI's single-target primitives into multi-hop answers. Not part of the PyPI distribution.

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
