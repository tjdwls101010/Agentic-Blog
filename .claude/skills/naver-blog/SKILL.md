---
name: Naver Blog retrieval
description: Read Naver Blog (네이버 블로그) with the agentic-blog CLI — search posts, blogs, people, and 태그, filter reviews down to self-declared 내돈내산 posts, open a blog's category tree, list or search one blog's own posts, read a post's full body and its comment thread, browse the directory's topics, and walk the neighbour (이웃) graph — then chain those to answer multi-hop questions. Use whenever the user wants something off Naver Blog, however they phrase it: "네이버 블로그에서 X 찾아줘", "이 블로그 글 읽어줘", "X 후기 좀 모아줘", "이 블로거가 X에 대해 뭐라고 썼어?", "이 사람 주변에선 무슨 얘기해?", "요즘 블로그에서 뭐가 인기야?", or when they hand over a blog.naver.com or m.blog.naver.com URL. Also use when the user wants Korean first-hand opinion — 후기, 리뷰, 방문기, 내돈내산 — about a product, place, restaurant, or trip and has not named a source, because Naver Blog is where that lives. NOT for other blog platforms: Tistory, Velog, brunch, Medium, WordPress, Substack. NOT for other Naver services — 카페, 지식iN, 뉴스, 포스트, 쇼핑, 플레이스 are different products with no tool here. NOT for developing, testing, or releasing the agentic-blog package itself, which is ordinary repo work.
allowed-tools: Bash(agentic-blog:*), Bash(uv:*), Bash(pipx:*), Bash(curl:*), Read
---

# Naver Blog retrieval

`agentic-blog` reads Naver Blog's own public endpoints — no login, no browser, millisecond
requests. It is deliberately a set of single-target primitives with **no `crawl` command**.

**The CLI retrieves. You navigate.** Deciding which blog to open next, which commenter is worth
following, and when you have enough is not a gap in the tool; it is the job this skill exists to
do.

## Step 1 — get the tool, and get a current one

```bash
agentic-blog --version
curl -s https://pypi.org/simple/agentic-blog/ \
  | grep -oE 'agentic[_-]blog-[0-9]+\.[0-9]+\.[0-9]+' | sed 's/.*-//' | sort -V | tail -1
```

Read the installed version from `--version`, not from `catalog` — `--version` has existed in every
release, so it still answers on the old installs this check exists to catch.

Read PyPI's version from the **simple index**, as above, not from `pypi.org/pypi/agentic-blog/json`:
the two propagate independently and either can lag the other by minutes around a release.

**Being behind matters more here than the version dance usually implies.** Unlike its sibling
packages, this one tracks no rotating server tokens, so there is no drip of "upgrade or be broken"
releases — but its fixes are *parser* fixes, and a parser fix is the difference between a command
working and a command dying. In 0.1.0, `posts` failed on 21 of 30 real blogs. If the installed
version is behind, say so in one line and upgrade before starting the user's actual work:

```bash
uv tool install --upgrade --no-cache agentic-blog     # or: pipx upgrade agentic-blog
```

Check once, at the start. The installed version cannot change under you unless you change it.

If it isn't installed at all, `uv tool install agentic-blog` or `pipx install agentic-blog`. A repo
checkout and the installed CLI are different things — the one on PATH is the one that counts.

## Step 2 — there is no setup

No `login`, no `setup`, no `status`, no browser, no account, no API key, no cookie. Install and
read.

This is worth stating because the sibling scrapers all open with an authentication dance, so the
reflex is to go looking for the equivalent here and burn turns finding nothing. There is nothing.
Every read is anonymous, which is also why nothing here can see 이웃공개 content (see the last
section).

## Step 3 — ask the CLI what it can do

```bash
agentic-blog catalog     # every command, its real flags, types, defaults, and the exit-code table
agentic-blog schema      # the field list for Post, Blog, Topic, Comment, Media
```

Both are generated from the code, so they describe the version you actually have. This file
deliberately does not restate them: a command table copied into prose silently describes the wrong
version the moment the package updates, and you would trust the copy over the truth. **Anything you
need in order to *call* a command comes from the catalog.** What follows is only what the catalog
cannot carry — how to decide what to call, and how to read what comes back.

If a command is rejected as an `invalid choice`, that is an out-of-date install, not a missing
feature. Go back to Step 1 rather than working around it.

## Reading the output

Every read command writes its results to a **file** and prints one summary line to **stderr**.
Nothing useful goes to stdout.

```bash
agentic-blog search "제주도 3박4일 후기" --limit 5 --output /tmp/blog-search.json
# stderr: 5 posts, range 2026-06-08T07:47:00+00:00..2026-07-16T09:22:00+00:00,
#         stop reason: limit_reached. Saved to /tmp/blog-search.json
```

Then `Read` that file. Always pass `--output` with a path you chose; without it the file lands
under the platform data directory with a name you would then have to hunt for.

The payload is a **bare JSON array** — not `{"items": [...]}`. Single-target reads (`post`, `blog`)
still return a one-element list. Post bodies run to tens of KB, so `Read` with an offset and limit
rather than swallowing one whole; decide what you need before you fetch it.

`--raw` and `--no-redact` are for debugging the scraper itself and will not get you more of a post:
`--raw` attaches the unparsed upstream object, and `--no-redact` only stops *diagnostic messages*
from being truncated. Neither adds content, so reaching for one to see more of a post is a wasted
call.

## `brief` is not `body`

Listing commands — `search`, `posts`, `topic` — populate **`brief`**, which is Naver's own
truncated teaser, and leave **`body`** null. Only `post` fetches the real text.

This is the failure most likely to make this skill worse than useless, and it is silent: `brief`
reads like prose, so a summary built from it is fluent, confident, and describes a teaser rather
than the post. Nothing in the output announces the substitution. If you are about to characterize
what someone wrote, you need `body`, which means you need a `post` call.

## What the numbers and flags actually mean

- **`comment_count` is the discussion's true size; `comments[]` is only what this call fetched.**
  A post with `comment_count: 35` under `--comment-limit 3` gives you three comments. Reporting the
  array's length as the number of comments understates it silently, by however much your own flag
  cut off.
- **`visibility` arrives on listings, never on a single `post` read.** A post fetched directly
  carries no visibility signal at all, so its absence there is evidence of nothing.
- **`created_at` can be null on a `post` read even though the post obviously has a date.** Naver
  labels recent posts relatively — "7시간 전", "어제" — and a rounded interval is not a timestamp,
  so the CLI reports nothing rather than inventing precision. The listing surfaces carry an exact
  time for the same post, so `search` or `posts` is where to get it when you need it.
- **`captured_at` is when *you* scraped.** Sorting or deduplicating by it produces an ordering that
  means nothing.
- **`Blog.buddy_count` counts only the neighbours the blog *discloses*.** Naver keeps a second,
  usually much larger total that it shows nobody but the owner — one measured blog publishes 0 of
  its 1,908. So `buddy_count: 0` means "this blog does not publish its neighbour list", not "this
  person has no neighbours", and it will agree with what `buddies` returns rather than contradict
  it. Treating it as reach or popularity will be wrong by an order of magnitude on most blogs.

## Navigating

Two questions place any command: **what handle do you already hold**, and **how narrow is what it
returns**. Prefer the command whose handle you have, and among those the narrowest — that is the
whole of the routing logic.

The handles that make chaining possible:

- a post's `blog_id` → `blog`, `posts`, `buddies`
- a post's `blog_id` + `log_no` → `post` (a `log_no` alone is not a post reference; ids are unique
  per blog, not globally, so always carry the blog id with it)
- a comment's **`author_blog_id`** → that commenter's own blog. This is the edge from a post into
  the community around it, and nothing in the schema advertises it as one.
- a `Topic`'s `seq` → `topic`

Worked chains, with the judgment that matters at each hop:

**"X 후기 찾아줘"** — `search --type post`, then `post` the two or three most promising. The
judgment is which ones are worth spending a read on, not how many results to collect.

**`--type post` vs `--type tag`** — these index different things, so the choice is about what kind
of match you want. Post search reads the whole text, so it finds anything that *mentions* X, with
the recall and the false positives that implies. Tags are what the author chose to file the post
under: fewer results, but each one is a post someone considered to be *about* X. When a broad search
drowns in passing mentions, the tag axis is the sharper instrument; when a topic is niche enough
that few people tag it, it is the wrong one. Neither dominates, and nothing stops you trying both.

**"이 블로거 어떤 사람이야?"** — `blog` first. The **category tree is the best single summary of a
Naver blog**: its shape and per-category post counts describe what someone actually writes about
faster and more completely than reading their posts does. Reading posts first is the expensive way
to learn what one call already told you.

**"이 블로그에서 X에 대해 쓴 글"** — `posts --query`. Pulling the whole post list and filtering it
yourself burns the request budget on the question users ask most often.

**"이 글 반응 어때?"** — `post` returns body and comment tree in one call. The thread is frequently
more informative than the post, and replies nest inside each comment's `replies[]`.

**"이 사람 주변 사람들은 무슨 얘기해?"** — `buddies`, then `posts` on a few. An empty `buddies`
result is ordinary, not an error: plenty of blogs expose no public neighbour list, and the honest
report is "this blog doesn't publish one."

## Is this the answer, or part of it?

The stderr line ends with a `stop_reason`, and it is the difference between a complete result and a
fragment presented as one.

- **`no_next_page` / `no_matches` / `single_target`** — genuinely the end.
- **`limit_reached`** — your own `--limit` stopped it. There is more.
- **`max_requests`** — the per-invocation request budget stopped it, not the data. The result is
  partial and reporting it as complete is simply wrong.

One more end exists that no `stop_reason` distinguishes: **Naver's search stops handing out results
after about a thousand posts per query**, however many it claims to have matched. So `no_next_page`
on a broad search means "the index stopped answering", not "you have them all", and "전부 모았다" is
never true of a popular keyword. When exhaustiveness is what the user actually wants, narrowing the
query — a date window, a tag, one blog — reaches deeper than paging ever will.

## What a chain costs

Every hop is a real request against a 0.5s floor, with a budget of 100 requests per invocation. A
three-blog sweep with comment threads is nothing; a thirty-blog sweep is a minute of wall clock and
should be announced before it starts rather than discovered afterwards.

The second half matters more than the pacing: **report the shape of what you actually did.** A
chain that sampled 5 of 60 neighbours but presents itself as "what the neighbours think" is a wrong
answer wearing a confident summary. Say which hops you took and how many you skipped.

Size every `--limit` from the question being asked. "Is this blog active" needs a handful of posts;
"what has she argued about this month" needs a date window and more.

## Sponsored content, and what `--self-purchased` does and does not promise

Naver Blog's review corpus is saturated with 협찬 / 체험단 / 광고 posts, and **Naver publishes no
`is_ad` field** — check `schema`, there is none, because Naver does not reliably expose one.

What Naver does publish is the *opposite* claim, and only when a blogger volunteers it.
`search --self-purchased` keeps posts the author labelled 내돈내산 — bought with their own money.
It is a real filter and a strong one: on one measured query it cut 1.2M posts to 3,397, an entirely
different result set. But it is **the blogger's own declaration, not Naver's verification**, and the
two failure directions are not symmetric:

- Its **presence** does not certify that nothing was sponsored. Nobody audits the claim.
- Its **absence** says almost nothing. Most honest posts never bother with the label.

So this narrows the pool; it does not clean it. Describing those results as "광고 없는 후기" claims a
guarantee that does not exist — "본인이 내돈내산이라고 밝힌 글" is the sentence that is actually true.
Judgment stays the instrument, applied to a smaller pile, and a judgment the reader cannot see is a
judgment they cannot check.

Signals worth weighing before spending a `post` call: disclosure language in the body, a category
tree that is entirely product reviews, a posting cadence too uniform to be a person's actual life.
None of these is decisive alone.

## When something fails

`catalog` prints what each exit code *means*. This is what to do — and the theme is that failures
here are informative rather than transient, so retrying the same command is rarely the fix.

- **1** — usage error or an invalid identifier. `invalid choice` specifically means an out-of-date
  install: Step 1.
- **3** — HTTP 429. Stop that line of work rather than looping. A measured 355-request serialized
  run never saw one, so a 429 is a real signal about volume, not noise.
- **4** — the response structure changed. There is no self-heal in this package: no browser to fall
  back to and no token registry to re-anchor, so the fix ships as a release. Upgrade, or tell the
  user it needs a newer version.
- **5** — the target does not exist.

**There is no exit 2.** Every sibling scraper uses it for an authentication failure, and there is
no authentication here, so a habit carried over from one of those will misread whatever it lands on.

## The honest edge

Neighbour-only (이웃공개 / 서로이웃공개) posts, deleted posts, private blogs, suspended blogs.

What is known: listings carry a `visibility` of `buddy` or `both_buddy`, and a post so marked is
very likely unreadable by an anonymous client — which this always is. That is a fact about the post,
not a malfunction, and not something to apologise for or retry.

What is **not** known: what actually happens when you try to read one. Recon spent 355 requests
across twelve Korean and English search terms hunting for a specimen of any of these four classes
and found none, so the package deliberately never mapped them. If you hit an odd failure on a post
whose listing said `buddy`, report it as what it is rather than inventing a diagnosis.

## What doesn't exist

There are **no writes**. The CLI cannot post, comment, follow, or like — don't offer. There is no
`crawl`, by design.

And keep captures out of the repo: this project **tracks `.json` test fixtures**, so `.gitignore`
will not catch a scrape saved into the working tree, and a scrape committed to a repo outlives the
question it was collected for.
