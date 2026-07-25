# Security and Privacy

Agentic Blog is an anonymous, read-only client for Naver Blog's public surface. It is not an authentication, publishing, moderation, or account-management tool. This page explains its boundaries; [CLI Reference](CLI-Reference.md) and [Output Schema](Output-Schema.md) describe what it can write locally.

## Anonymous public-only boundary

The client sends HTTPS reads to the measured public endpoints with endpoint-specific `Referer` and ordinary desktop/mobile user-agent headers. It has no login flow, credentials, password input, OAuth token, cookie jar, browser automation, profile selection, session storage, or browser-state import. It does not attempt to bypass a private, buddy-only, deleted, suspended, blocked, or otherwise unavailable target.

A successful listing visibility value is source metadata, not authority to fetch restricted content. Some unavailable-state signatures cannot be safely distinguished without authenticated or private observations. The client only maps signatures it has conservatively measured; it does not invent a more specific reason from an ambiguous response. Treat exit code 5 as “not available to this anonymous reader” unless the error itself provides a measured reason.

## Pacing and request budgets

Every `ReadClient` request is subject to a non-bypassable minimum pause of **0.5 seconds**. A smaller library-provided pause is raised to that floor. A client also has a bounded request budget of **100 requests by default**. These limits prevent accidental bulk collection and reduce load on Naver; they do not guarantee permission, availability, or immunity from throttling.

Keep queries narrow, use `--limit`, and stop rather than retrying aggressively. When the local budget is exhausted, collection stops with `max_requests` and writes records already obtained. HTTP 429 maps to exit code 3; it is not a signal to evade or rotate identity. See [FAQ: budgets](FAQ-and-Troubleshooting.md#why-did-a-command-stop-at-max_requests).

## Local output and raw data

Read results are written locally, outside the working directory by default, under the platform user-data directory's `agentic-blog/output` path. `AGENTIC_BLOG_DATA_DIR` and `--data-dir` can redirect that base path; `--output` can select any path. Directory creation and file permissions follow the local operating system.

Output may contain public personal data: names, blog IDs, profile and media URLs, post text, comments, comment-author IDs, and timestamps. Treat result files as sensitive local data:

- Store them only where access is appropriate; do not upload or commit them by default.
- Apply retention and deletion practices suitable for the collection purpose.
- Avoid sharing full files when an aggregate or redacted excerpt is sufficient.
- Respect context, copyright, terms, and applicable privacy/data-protection obligations.

`--raw` is an explicit opt-in on selected listing/profile commands. It preserves an upstream object outside the stable normalized contract and can include additional public fields. It is not enabled by default. Do not use raw output for routine collection, and do not assume it has been redacted. `post` and `topics` do not support `--raw`.

## Diagnostics and redaction

Diagnostic handling is designed to avoid exposing unnecessary source detail. Project error diagnostics are bounded to 240 characters and remove query strings from `pstatic.net` CDN URLs before surfacing them. This protection is deliberately narrow: diagnostics and every other URL must still be treated as untrusted, potentially identifying data. Do not paste failing URLs, raw response bodies, signed media URLs, output paths containing sensitive identifiers, or live payloads into issues, chat, fixtures, or logs.

The CLI's normal successful summary intentionally reports only count, date range, stop reason, and the output path. Control characters in that displayed path are escaped, though the underlying filename is not changed. For a parsing or availability failure, record the command shape, exit code, and minimal non-sensitive structural evidence needed to reproduce it; omit target identities and response content. A parser drift is exit code 4, not an invitation to collect live captures.

## Fixtures and development evidence

Repository fixtures are synthetic only. Do not persist live responses, real profile data, real posts, comments, identifiers, URLs, cookies, request headers, or other personally identifying captures in tests, examples, issues, or commits. Use fabricated values and example domains when testing parsers or schema behavior.

This rule is especially important for comments and public-neighbour data: public availability does not make copying it into a development repository appropriate. Test structural behavior with synthetic inputs, and keep live observation ephemeral and minimal.

## Responsible use

Use the project only for legitimate, proportionate reading of anonymously accessible public information. Do not use it to evade access controls, infer private relationships, repeatedly probe unavailable accounts, collect at scale, harass people, or make decisions about people from incomplete data. Do not represent the tool's output as authoritative, complete, authenticated, or published by Naver or a blog owner.

Naver can change endpoints, visibility, and response formats. Results are a point-in-time best-effort observation, not a durable archive. Review the project's [DISCLAIMER](../../DISCLAIMER.md) and [SECURITY policy](../../SECURITY.md) alongside this guidance when handling a vulnerability or reporting security-sensitive behavior.
