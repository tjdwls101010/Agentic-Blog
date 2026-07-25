# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
