# Security Policy

## Supported version

Security fixes target the current `0.1.x` development line. Use the latest available source or distribution before reporting a suspected issue when doing so is safe.

## Reporting a vulnerability

Do **not** include credentials, cookies, session files, browser profiles, real Naver content, raw HTTP captures, or other personal data in a public issue.

1. Use the repository's [private vulnerability reporting page](https://github.com/tjdwls101010/Agentic-Blog/security/advisories/new) when it is available.
2. Describe the affected version, command or library surface, a minimal synthetic reproduction, expected and observed behaviour, impact, and any mitigation you have identified.
3. If private reporting is unavailable, open a minimal [GitHub issue](https://github.com/tjdwls101010/Agentic-Blog/issues) requesting a private reporting channel. Do not publish exploit details or sensitive artifacts in that issue.

Reports are reviewed on a best-effort basis. A report will be acknowledged when it can be triaged; do not rely on the project for a particular response time or a paid support channel.

## In scope

Examples of useful reports include:

- unintended transmission, persistence, or disclosure of data;
- an output-path, diagnostic, parser, or dependency issue with a credible security impact;
- requests made to an unintended host or a way to bypass the client's public-only boundary;
- a regression that introduces login, credential, cookie, session, browser-state, or browser-automation handling;
- an issue that defeats the mandatory request pacing or per-run request budget; and
- a supply-chain or release-integrity issue affecting published artifacts.

The package is intentionally anonymous and read-only. Bugs that make private, neighbour-only, deleted, suspended, or otherwise unavailable content appear accessible are in scope even when the affected content itself must not be shared in the report.

## Safe reproduction rules

Use synthetic identifiers and invented content whenever possible. Do not test against accounts you do not control, attempt to bypass authentication or access controls, sustain high request rates, or collect a real person's content to demonstrate impact. Stop as soon as you have enough evidence. Keep reproduction output local and remove it after triage.

Committed tests and fixtures must be synthetic and PII-free. Never commit live captures, personal names or content, real output files, API keys, credentials, cookies, session data, browser profiles, or raw request/response dumps. Live tests, when explicitly enabled by a maintainer, must assert shapes and invariants rather than real content.

## Disclosure and fixes

Please allow maintainers reasonable time to investigate and prepare a fix before public disclosure. Maintainers may request a reduced synthetic reproduction, classify an issue as out of scope, or coordinate a disclosure timeline. Security fixes should include focused regression coverage using synthetic data and must preserve the public-only, no-authentication design.

For general development guidance, see [CONTRIBUTING.md](CONTRIBUTING.md). Responsible-use limits are stated in [DISCLAIMER.md](DISCLAIMER.md).
