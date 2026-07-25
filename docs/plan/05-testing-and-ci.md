# Testing, Packaging & CI

Mirror `agentic-x` / `agentic-threads`, minus everything that existed to police the browser
boundary — there is no browser here, so `test_no_scrapling_import.py` and the base-wheel
"Scrapling is absent" smoke assertion have no analogue and must not be ported.

## pyproject.toml

The repo already has a `0.0.1` placeholder. Amend it to:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agentic-blog"
version = "0.1.0"                      # bump per release; gated vs tag
requires-python = ">=3.11"             # raised from the committed >=3.9 (D10)
license = "MIT"
dependencies = [
    "httpx>=0.27",
    "platformdirs>=4.0",
    "lxml>=5.0",
]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.8", "pre-commit>=3.8", "build>=1.2", "jsonschema>=4.0"]

[project.scripts]
agentic-blog = "agentic_blog.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/agentic_blog"]

[tool.ruff]
line-length = 100
target-version = "py311"
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[project.urls]
Homepage  = "https://github.com/tjdwls101010/Agentic-Blog"
Issues    = "https://github.com/tjdwls101010/Agentic-Blog/issues"
Changelog = "https://github.com/tjdwls101010/Agentic-Blog/blob/main/CHANGELOG.md"
```

**There is no `[browser]` extra.** Three runtime dependencies is the whole tree — the smallest of
the family, and that is a feature worth protecting in review.

`jsonschema` is a declared dev dependency so the schema-validation test actually runs in CI rather
than being `importorskip`'d away.

## Tests (`tests/`) — offline, fixture-driven; no network in CI

- `conftest.py`: `load_fixture` returns a fixture file's bytes/JSON.
- `tests/fixtures/*.json` and `*.html`: **hand-authored synthetic, PII-free** skeletons with fake
  blog ids (`synthetic_alice`), fake numeric ids, and invented Korean text. Cover:
  `search_post`, `search_blog`, `search_id`, `category_list`, `post_list`, `notice_post_list`,
  `popular_post_list`, `public_buddies`, `comments_info`, `cbox_list`, `directory_list`,
  `directory_post_list`, plus `post_se_one.html`, `post_legacy.html`, `post_search_list.html`, and
  an `unavailable` variant per family. Un-ignored in `.gitignore` by **exact name**, never a
  wildcard. Real captures live in gitignored `scratch/` and are never committed.

Test files, all offline with mock transports:

- `test_identifiers.py` — every accepted spelling of a blog and post reference (bare id, both
  hosts, `PostView.naver` query form, two-argument form), plus rejection of a bare `logNo` with no
  blog id, and rejection of non-Naver hosts.
- `test_endpoints.py` — every parameter builder: exact query strings, the three non-derivable
  constants (`CBOX_POOL`, the `_201_` `objectId` shape, `POST_LIST_MAX_ITEM_COUNT`), per-host
  header sets including the mandatory `Referer`, and **an explicit assertion that `itemCount`
  is clamped to 30** rather than passed through.
- `test_client.py` — the `)]}',` XSSI strip (including a response that does *not* carry it),
  mandatory first-and-every-request pacing, the request budget, envelope-level error mapping for
  all three envelope shapes (`isSuccess:false`, cbox `success:false`, HTTP non-2xx), and sanitised
  transport failures.
- `test_parse.py` — every anchored JSON envelope path, empty/null branches, `totalCount: 0`
  handling (**it must not be treated as "no results"**), separator-category filtering, and exact
  drift diagnostics.
- `test_body.py` — the SmartEditor ONE component walk (text, image with caption, quotation,
  link card, horizontal rule, place map), the legacy `div.post_ct` fallback, lazy-image
  `data-lazy-src` handling, Markdown escaping of literal `[`/`]`/`>` in post text, and
  `BodyParseError` when neither container is present. Plus the `PostSearchList.naver` logNo
  extraction.
- `test_model.py` — normalisation of all three timestamp formats, `<strong class="search_keyword">`
  stripping, id-as-string serialisation, visibility-flag mapping, `raw` opt-in, schema/`to_dict`
  parity, complete field descriptions, generated JSON Schema validity, and fixture-derived model
  validation with `jsonschema`.
- `test_retrieve.py` — pagination to exhaustion via short-page detection, `--limit` composition,
  request budgets, deduplication, comment-tree flattening/nesting, and the `stop_reason` vocabulary.
- `test_cli.py` — parser/handler/catalog synchronisation, every help and flag surface, the
  mutually-exclusive flag pairs (`--query` vs `--category`, `--query` vs `--sort popular`), offline
  catalog and JSON Schema output, the documented exit-code mapping, stdout/stderr contracts, and
  UTF-8 output-file naming with a Korean identifier.
- `test_redact.py` and `test_fixture_pii.py` — recursive redaction, `pstatic.net` signed-URL
  handling, bounded/cyclic input, and committed-fixture scanning.

**One regression test earns its own line because it guards a silent-failure trap** (D8): asserting
that in-blog search is *not* implemented by passing a search term to `post-list`. That call returns
HTTP 200 with the full unfiltered list — it looks like a working search and is not one. The test
should assert the `posts --query` path calls `PostSearchList.naver`.

- `tests/live/` (opt-in, gated behind `AGENTIC_BLOG_LIVE=1`, **never in CI**): real requests
  against public blogs; asserts **shapes and invariants, never content** (no PII).
  Env: `AGENTIC_BLOG_LIVE_BLOG`, `AGENTIC_BLOG_LIVE_QUERY`.

## CI (`.github/workflows/ci.yml`) — Python 3.11 and 3.12

- `lint-and-test`: explicit include matrix — `ubuntu-latest`/3.11, `ubuntu-latest`/3.12,
  `macos-latest`/3.12. Install pinned `requirements-dev.lock` + `pip install -e . --no-deps`;
  run `ruff check .`, `ruff format --check .`, `python scripts/check_fixtures_pii.py`, `pytest`.
- `build-and-smoke`: on `macos-latest` and `ubuntu-latest` with Python 3.12 — build an sdist from
  the checkout, derive a wheel from that sdist with `pip wheel --no-deps`, install it into a clean
  venv **with its three real dependencies**, then smoke-test `agentic-blog --version`, `--help`,
  `catalog`, `schema`, and `schema --json` offline. The sdist-first path verifies
  source-distribution completeness; the offline smoke verifies that the meta commands need no
  network.

`lxml` ships manylinux and macOS wheels for 3.11/3.12, so no build toolchain is needed on any CI
leg. If a future Python release lands before `lxml` publishes wheels for it, that leg will try to
compile — pin the matrix rather than letting it silently start building from source.

## Publishing (`.github/workflows/publish.yml`) — already working, two hardening items

The pipeline is **already configured and proven**: repo `tjdwls101010/Agentic-Blog`, workflow
`publish.yml`, environment `pypi`, Trusted Publishing (OIDC), and `agentic-blog 0.0.1` was
published this way. **Keep the filename and the environment name** — the PyPI publisher is
registered against both.

Two changes to bring it to the sibling standard:

1. **Pin `pypa/gh-action-pypi-publish` to a commit SHA**, not the floating `@release/v1`. A
   floating tag on the action that holds your OIDC identity is the one place in this repo where a
   supply-chain move would go unnoticed.
2. **Add the version gate.** `scripts/check_tag_version.py` must run in the `build` job and verify
   tag == `pyproject.toml` version == `__init__.__version__`, all three. The current workflow will
   happily publish a tag that disagrees with the package.

Trigger stays `on: release: published` — a GitHub Release, not a bare tag push.

## pre-commit + scripts

- `.pre-commit-config.yaml`: `ruff --fix` + `ruff-format`, plus a local hook running
  `scripts/check_fixtures_pii.py` on `tests/fixtures/*`.
- `scripts/check_tag_version.py` — the three-way gate, stdlib `tomllib` (available because of D10).
- `scripts/check_fixtures_pii.py` — coarse allowlist scan over committed fixtures: `pstatic.net`
  CDN hosts, emails, phone numbers, Korean personal-name-shaped strings, and high-entropy tokens.
  Structural only; **human review is the real control.**
- `scripts/record_fixture.py` — dev tool to capture real responses into gitignored `scratch/`.
- `.gitignore`: `scratch/`, `*.raw.json`, `*.raw.html`, `output/`, `.venv/`, plus the general
  Python set. Fixtures un-ignored by exact name.

## A note on PII discipline for this project specifically

The siblings' PII rules are inherited wholesale (D13), but the risk profile here is **higher**, not
lower, despite the data being public and login-free. Naver blogs routinely carry real names, faces,
workplaces, children, and home neighbourhoods, and `buddies` + `posts` + comment authors compose
into a social graph with almost no effort. Two consequences for testing:

- **Fixtures must be invented, not minimised captures.** Redacting a real capture is not enough;
  Korean nicknames and post titles are themselves identifying. Write synthetic Korean text.
- **`tests/live/` must never assert on content.** Shapes, types, counts, and invariants only. A
  live test that asserts a real post's title bakes a stranger's data into the repo forever.
