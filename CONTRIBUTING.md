# Contributing

Thanks for helping improve Agentic Blog. This project is a deliberately small, anonymous, read-only reader for public Naver Blog content. Contributions must preserve that boundary.

## Ground rules

- Keep changes focused and explain the user-visible reason for them.
- Use English for code, comments, documentation, CLI output, and issue discussions where practical.
- Do not add login, accounts, credentials, cookie jars, session files, browser profiles, browser automation, stealth tooling, access-control bypasses, write actions, bulk crawling, daemons, or another Naver service without an explicit project decision.
- Preserve the three runtime dependencies: `httpx`, `platformdirs`, and `lxml`. Discuss any additional runtime dependency before adding it.
- Preserve the non-bypassable 0.5-second request floor and the bounded per-run request budget.
- Do not weaken [DISCLAIMER.md](DISCLAIMER.md) or make unsupported claims about access, authentication, publication, or Naver affiliation.

All participants must follow the [Code of Conduct](CODE_OF_CONDUCT.md). Security-sensitive findings belong in [SECURITY.md](SECURITY.md), not a public issue.

## Development setup

Use Python 3.11 or newer. Create an isolated environment, install the package with development dependencies, and confirm the offline CLI surfaces:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
agentic-blog --version
agentic-blog catalog
agentic-blog schema --json
```

The `catalog` and `schema` commands must remain offline. Do not add a setup, login, status, or doctor step: the intended first-run experience is install, then read public content.

## Tests and quality checks

Tests must be offline and fixture-driven. Before opening a pull request, run the repository's configured checks:

```bash
ruff check .
ruff format --check .
python scripts/check_fixtures_pii.py
pytest
```

Changes to packaging or command-line behaviour also need an install/smoke check covering `agentic-blog --version`, `--help`, `catalog`, `schema`, and `schema --json` from the built artifact. Keep test coverage focused on observable behaviour, errors, edge values, output contracts, and privacy boundaries.

Network checks are opt-in only and must never run in CI. When a maintainer authorizes a live check, use the smallest possible public query, keep output local, assert only shapes and invariants, and delete captures afterwards. Never make live content a fixture or an assertion.

## Fixtures, logs, and privacy

Committed fixtures must be hand-authored, synthetic, and PII-free. Use invented IDs and invented Korean text; redacting a real capture is not sufficient. Do not commit any of the following:

- real posts, comments, usernames, neighbour lists, images, or raw server responses;
- credentials, API keys, cookies, session files, browser state, or account data;
- output files, diagnostic dumps, or request/response captures; or
- data that could identify, profile, or contact a real person.

Keep any temporary investigation material outside version control. If a bug requires upstream evidence, reduce it to a synthetic structural example before committing. Raw diagnostic data must be handled locally and with the same care as production personal data.

## Pull requests

1. Search existing issues and pull requests before starting work.
2. Open an issue for a behaviour change, public-surface change, or design question before investing in a broad implementation.
3. Keep a pull request narrowly scoped; include tests and documentation for changed behaviour.
4. State the commands you actually ran and any checks you could not run. Do not describe unrun checks as passing.
5. Call out any impact on anonymous/public-only access, output schemas, pacing, budgets, fixtures, or release artefacts.

Maintain backward-compatible output and exit-code behaviour unless the change explicitly documents a versioned compatibility decision. Update the generated CLI catalog/schema expectations and focused tests when command flags or models change.

## Release policy

Maintainers release only after the offline suite, fixture PII scan, formatting/lint checks, and built-artifact smoke checks pass. Live validation, when performed, is bounded, public-only, and never persisted. Version declarations, the release tag, and the published artifact must agree; publishing is a maintainer action triggered by a GitHub Release, not by a contributor branch or a bare tag.

Do not create tags, GitHub Releases, or package publications as part of ordinary development or a pull request. See [CHANGELOG.md](CHANGELOG.md) for released changes.
