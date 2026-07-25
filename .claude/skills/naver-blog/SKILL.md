---
name: Naver Blog retrieval
description: Read Naver Blog (네이버 블로그) with the agentic-blog CLI — search posts, blogs, people, and 태그, filter reviews down to self-declared 내돈내산 posts, open a blog's category tree, list or search one blog's own posts by text or by 태그, read a post's full body with its tags and its comment thread, browse the directory's topics, and walk the neighbour (이웃) graph — then chain those to answer multi-hop questions. Use whenever the user wants something off Naver Blog, however they phrase it: "네이버 블로그에서 X 찾아줘", "이 블로그 글 읽어줘", "X 후기 좀 모아줘", "이 블로거가 X에 대해 뭐라고 썼어?", "이 사람 주변에선 무슨 얘기해?", "요즘 블로그에서 뭐가 인기야?", or when they hand over a blog.naver.com or m.blog.naver.com URL. Also use when the user wants Korean first-hand opinion — 후기, 리뷰, 방문기, 내돈내산 — about a product, place, restaurant, or trip and has not named a source, because Naver Blog is where that lives. NOT for other blog platforms: Tistory, Velog, brunch, Medium, WordPress, Substack. NOT for other Naver services — 카페, 지식iN, 뉴스, 포스트, 쇼핑, 플레이스 are different products with no tool here. NOT for developing, testing, or releasing the agentic-blog package itself, which is ordinary repo work.
allowed-tools: Bash(agentic-blog:*), Bash(uv:*), Bash(pipx:*), Bash(curl:*), Read
---

# Naver Blog retrieval

`agentic-blog` reads Naver Blog's own public endpoints — no login, no browser. It is deliberately a
set of single-target primitives with **no `crawl` command**.

**The CLI retrieves. You navigate.** Deciding which blog to open next, which commenter is worth
following, and when you have enough is not a gap in the tool; it is the job this skill exists to
do.

## There is no setup, and that is the whole of it

No `login`, no `setup`, no `status`, no browser, no account, no API key, no cookie. Install and read.
Worth stating only because the reflex on a scraper is to go hunting for the authentication step and
burn turns finding nothing. Every read is anonymous, which is also why nothing here can see
이웃공개 content (last section).

What does need a moment, once, before the user's actual work:

```bash
agentic-blog --version
curl -s https://pypi.org/simple/agentic-blog/ \
  | grep -oE 'agentic[_-]blog-[0-9]+\.[0-9]+\.[0-9]+' | sed 's/.*-//' | sort -V | tail -1
```

Read the installed version from `--version` rather than `catalog`, because `--version` still answers
on the ancient installs this check exists to catch, and read PyPI's from the **simple index** rather
than the JSON API, because the two lag each other around a release.

**Being behind matters more here than a version check usually implies.** Nothing in this package
tracks rotating server tokens, so there is no drip of upgrade-or-die releases — but its fixes are
*parser* fixes, and a parser fix is the difference between a command working and a command dying. In
0.1.0, `posts` failed on 21 of 30 real blogs. So if the installed version is behind, say so in one
line and upgrade rather than working around whatever it does:

```bash
uv tool install --upgrade --no-cache agentic-blog     # or: pipx upgrade agentic-blog
```

If it isn't installed at all, `uv tool install agentic-blog` or `pipx install agentic-blog`. A repo
checkout is not an install — the one on PATH is the one that counts.

## Ask the CLI what it can do

```bash
agentic-blog catalog     # every command, its real flags, types, defaults, and the exit-code table
agentic-blog schema      # the field list for Post, Blog, Topic, Comment, Media
```

Both are generated from the code, so they describe the version you actually have. This file
deliberately does not restate them: a command table copied into prose silently describes the wrong
version the moment the package updates, and you would trust the copy over the truth. **Anything you
need in order to *call* a command comes from the catalog.** What follows is only what the catalog
cannot carry — how to decide what to call, and how to read what comes back.

An `invalid choice` rejection means the installed CLI does not have that subcommand. Check it against
`catalog` before concluding anything: if the command exists there, you mistyped it; if it does not
and you expected it to, the install is old, which is the version check above rather than something
to route around.

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
  It counts replies too, while the array holds top-level comments with their replies nested inside
  them — so `len(comments)` is smaller than `comment_count` on almost every post that has any
  discussion at all, before any flag of yours gets involved. A bound applies to the top-level
  threads, not to the total: `comment_count: 35` under a limit of 3 gives you three threads, however
  many replies hang off them. Reporting the array's length as the number of comments understates it
  silently, twice over.
- **`visibility` arrives on listings, never on a single `post` read.** A post fetched directly
  carries no visibility signal at all, so its absence there is evidence of nothing.
- **`created_at` can be null on a `post` read even though the post obviously has a date.** Naver
  labels recent posts relatively — "7시간 전", "어제" — and a rounded interval is not a timestamp,
  so the CLI reports nothing rather than inventing precision. The listing surfaces carry an exact
  time for the same post, so `search` or `posts` is where to get it when you need it.
- **`captured_at` is when *you* scraped.** Sorting or deduplicating by it produces an ordering that
  means nothing.
- **`tags: null` and `tags: []` are different answers.** Null means nothing fetched them — every
  listing, and a `post` read whose budget ran out before the extra request. An empty list is the
  measured answer that this post carries no tags, which happens: 80 of 82 sampled posts had at least
  one, so a couple in thirty genuinely have none. An empty `tags` on a `post` read is a fact about
  the post; a null one is a fact about your call.
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
- a post's **`tags`** → a tag search anywhere on Naver, or the same tag inside this one blog. Only a
  `post` read fills these in; every listing leaves them null. See "Following a tag" below.
- a `Topic`'s `seq` → `topic`

### Choosing the axis, not just the command

Most of these surfaces offer more than one axis, and the wrong axis wastes a read rather than
failing it — so the choice is worth making deliberately rather than defaulting.

**Whole text vs tags.** These index different things. Post search reads the body, so it finds
anything that *mentions* X, with the recall and the false positives that implies. Tags are what the
author chose to file the post under: fewer results, but each is a post someone considered to be
*about* X. When a broad search drowns in passing mentions, the tag axis is the sharper instrument;
when a topic is niche enough that few people tag it, it is the wrong one. Neither dominates, and
nothing stops you trying both.

**Finding a blog vs resolving an id.** Blog search matches blogs by subject and name — the right
call for "제주 여행 블로그 추천해줘", where you do not know who you are looking for. Id search
resolves a specific account, and it is also how you turn a nickname or a half-remembered handle into
a real `blog_id` you can then chain from. Reaching for blog search when the user already named
someone spends a request ranking strangers.

**Relevance vs recency.** Relevance ordering is the default and the right one when topical precision
matters. Date ordering is what "요즘", "최근", "올해" actually ask for, and it is also the honest
choice when the user wants a picture of current opinion rather than the best-matching post of the
last decade — a highly-ranked review from 2019 answers a different question than it appears to.
Server-side date bounds narrow harder than either ordering does, and unlike `--limit` they move the
thousand-result ceiling instead of running into it.

**Inside one blog, four surfaces answer four different questions.** In-blog text search for "what
has this person written about X"; the same for a tag, when you want what they *filed* under X rather
than what they mentioned; a category, when the category tree already handed you the right handle,
which is cheaper and cleaner than searching; popularity, for what this blog's own readers actually
read; notices, for the pinned post — which is where bloggers put their disclosure statements, their
standing rules, and their self-description, so it is unusually informative for its size.

**How much of a thread.** The full thread is the default and is usually right, because it is one
call. Bound it when the post is famous enough that the thread is enormous, and skip comments
entirely when the question is only about what the author wrote — that is a real request saved.
Favourite ordering surfaces the comments other readers endorsed, which is the better read of
*reception*; newest-first, the default, over-weights whoever arrived most recently.

### Worked chains

**"X 후기 찾아줘"** — search, then read the bodies of the ones worth a read. Which those are is the
judgment: topical directness over keyword presence, a spread of authors rather than three posts from
the same blog, dates that match what was asked, and a visible reason to trust the account. Collecting
more results is the cheap substitute for choosing among them.

**"이 블로거 어떤 사람이야?"** — `blog` first. The category tree and its per-category post counts
describe what someone writes *about* faster than reading posts does, and in one call. It says nothing
about voice, stance, or whether they still post, so sample posts when the question is one of those
rather than one of subject.

**"이 글 반응 어때?"** — one `post` call returns body and comment tree together. Replies nest inside
each comment's `replies[]`, and the thread is often the more informative half.

**"이 사람 주변 사람들은 무슨 얘기해?"** — `buddies`, then read a few. An empty `buddies` result is
ordinary, not an error: plenty of blogs expose no public neighbour list, and the honest report is
"this blog doesn't publish one." Neighbours who all write the same thing are one source, not five.

### Following a tag

Tags are Naver Blog's own "related posts" mechanism, and they are the only edge that runs *outward
from a post's content* rather than from its author. A post you already judged good names the terms
its writer thought it was about — which are better search queries than the ones you guessed, because
a human who knows the topic chose them.

The same tag then goes two ways, and they are different questions: searched globally it finds other
people writing about the same thing; searched inside this blog it finds the rest of *this* author's
posts on it, which is how you get from one good post to the series it belongs to.

Nothing else exposes a post's tags — a listing leaves them null, and the post page's HTML does not
carry them — so this hop only exists after a real `post` read.

## Is this the answer, or part of it?

The stderr line ends with a `stop_reason`. It is the difference between a complete result and a
fragment presented as one — but it answers a narrower question than it looks like it does, and two of
the three readings that sound final have a way of being false.

- **`limit_reached`** — your own `--limit` stopped it. There is more. Unambiguous.
- **`max_requests`** — the request budget stopped it, not the data. Partial, and which *part* is
  partial depends on the command: a `post` that ends this way has a complete body and a truncated
  comment thread, so the body is still usable even though the discussion is not.
- **`no_matches`** — nothing matched. Genuinely empty.
- **`single_target`** — one target was resolved. That is *not* the same as "you have everything
  about it": a `post` reports `single_target` whether the whole thread came back, or
  `--comment-limit` cut it off, or `--no-comments` skipped it entirely. Only your own flags tell
  you which, and the output does not remind you what you asked for.
- **`no_next_page`** — the endpoint stopped paginating. On a blog or a topic that is the end. On a
  broad search it is not: **Naver stops handing out results after about a thousand posts per
  query**, however many it claims to have matched, so this means "the index stopped answering", and
  "전부 모았다" is never true of a popular keyword.

When exhaustiveness is what the user actually wants, narrowing — a date window, a tag, one blog —
reaches deeper than paging ever will, because it moves the ceiling rather than climbing to it.

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

Judgment stays the instrument, applied to a smaller pile. Signals worth weighing: disclosure language
in the body, a category tree that is entirely product reviews, a posting cadence too uniform to be a
person's actual life, a pinned notice that is a rate card. None is decisive alone, and the label and
the body can flatly disagree — a post titled 내돈내산 whose body says 수수료를 제공받습니다 is a real
shape, not a hypothetical. When you drop a post on evidence like that, say which post and which
sentence: an exclusion the reader cannot see is one they cannot check.

## When something fails

`catalog` prints what each code *means*. What it cannot tell you is that failures here are
**informative rather than transient**, so re-running the same command is almost never the fix.

- **1** — your call was wrong, not Naver. Fix the call; do not retry it.
- **3** — stop that line of work rather than looping. A measured 355-request serialized run never
  produced one, so this is a real signal about volume, not noise to wait out.
- **4** — the response shape changed, and nothing here can route around it: no browser to fall back
  to, no token registry to re-anchor, so the fix ships as a release. Upgrade, or tell the user it
  needs a newer version. Do not try to out-guess a parser.
- **5** — Naver said the target does not exist. It is specifically *not* the code for "exists but
  you cannot see it": nothing in the package maps there, so do not report a 5 as a privacy wall.

**There is no exit 2.** There is no authentication here for it to mean, so anything reading a 2 as an
auth failure is a habit from a different tool misreading this one.

## The honest edge

Neighbour-only (이웃공개 / 서로이웃공개) posts, deleted posts, private blogs, suspended blogs.

What is known: listings carry a `visibility` of `buddy` or `both_buddy`, and a post so marked is
very likely unreadable by an anonymous client — which this always is. That is a fact about the post,
not a malfunction, and not something to apologise for or retry.

What is **not** known: what actually happens when you try to read one. A long hunt for a specimen of
any of these four classes turned up none, so rather than guess a failure shape the package mapped
nothing to them — which is why no exit code means "private". If you hit an odd failure on a post
whose listing said `buddy`, report it as the odd failure it is rather than inventing a diagnosis
that happens to fit.

## What doesn't exist

There are **no writes**. The CLI cannot post, comment, follow, or like — don't offer. There is no
`crawl`, by design.

And keep captures out of the repo: this project **tracks `.json` test fixtures**, so `.gitignore`
will not catch a scrape saved into the working tree, and a scrape committed to a repo outlives the
question it was collected for.
