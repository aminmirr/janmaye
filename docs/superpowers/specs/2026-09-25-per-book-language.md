# Per-book language: Persian-only chrome, English as a listening choice

**Date:** 2026-09-25
**Component:** `index.html`

## Problem

The site currently has one global `LANG`, switched by a top-nav toggle,
that drives *everything*: chrome text, every book's chapter list/titles,
and which audio plays. That's the wrong model for this site now — it
should be a Persian site (chrome, browsing, search) that happens to carry
both English and Persian audio per book. Switching to "English" today
means the whole page becomes an English site; what's wanted is "listen to
this one book in English," independent of every other book on the page
and independent of the site's own language.

Confirmed during design: site chrome (nav, search placeholder, category
labels, footer, hero, player button labels) becomes permanently Persian.
Each **book** independently remembers whether it's being viewed/listened
to in Persian or English — its own chapter titles, its own spine, its own
audio — via a toggle on its card and a matching toggle in the player bar
(reachable while listening, since the player is fixed/sticky). Switching
one book's language never touches any other book or the page chrome.

## Design

### Global `LANG` is retired; a per-book map replaces it

```js
let bookLang = JSON.parse(localStorage.getItem("abs-book-lang") || "{}");
const getBookLang = slug => bookLang[slug] || "fa";
function setBookLang(slug, lang){
  bookLang[slug] = lang;
  localStorage.setItem("abs-book-lang", JSON.stringify(bookLang));
}
```

Persisted per book, same `abs-` prefix convention as `abs-lang`/`abs-rate`/
`abs-voter`/`abs-history`. `abs-lang` itself is retired (no longer read or
written) — existing values left in visitors' `localStorage` are harmless.

### Chrome becomes hardcoded Persian

- `T.en` dictionary deleted. `t()` returns `T.fa` unconditionally.
- `document.documentElement.lang`/`dir` fixed to `"fa"`/`"rtl"`, set once.
- The `--accent` custom property's `html[data-lang="fa"]` conditional is
  removed — saffron becomes the single, permanent accent (the old
  per-language accent switch belonged to the whole-site-toggle model this
  replaces).
- `num()` (book/episode count stats), `dur()` when used for the site-wide
  listening-time stat, `faDigits()` (mobile player clock), the mobile
  player's missing-cover placeholder text, and the suggestion form's
  submitted `lang` field all become fixed to Persian — these are chrome,
  not book content.
- The `<div class="langswitch">` nav toggle and its click handler are
  deleted entirely.

### Functions that read book content take an explicit `lang` argument

Anywhere `LANG` was read to decide *book content* (not chrome) now takes
an explicit parameter instead of reading a global — because the caller
(book-scoped code) knows which book, and therefore which `bookLang` entry,
it's rendering:

- `langKey(lang)` — was `langKey()`.
- `split(book, lang)` — was `split(book)`.
- `chTitle(slug, ep, lang)` — was `chTitle(slug, ep)`.
- `dur(secs, lang)` — was `dur(secs)` (still defaults to `"fa"` for the
  chrome call site above).
- A per-book `num` (`const bnum = n => lang==="fa" ? n.toLocaleString("fa-IR") : n.toLocaleString("en-US");`),
  scoped inside `bookEl()`, for that book's own chapter-count/numbering —
  distinct from the chrome-level `num()`.
- `mkTrack(b, kind, ep, idx, lang)` — **new required parameter**. The
  returned track object gains a `lang` field (`tr.lang`), since nothing
  can implicitly read a global anymore. Every existing consumer of a
  track's language (`recordEntry()` in the listening-history feature,
  which currently reads global `LANG` when writing a history entry) reads
  `tr.lang` instead.

### `bookEl(b)` computes its own language once, up front

```js
const bLang = getBookLang(b.slug);
```
Used for every content decision inside that function: `split(b, bLang)`,
chapter titles, the book note (`bLang==="fa" ? m.note_fa : m.note_en`),
the per-book `num`, every `mkTrack(..., bLang)` call.

### `dir="ltr"` scoping for an English-mode book

The page stays `dir="rtl"` throughout. A book currently in English needs
its own title/chapter-list block wrapped with `dir="ltr"` — English text
inside an RTL page needs this explicitly, it doesn't fall out for free.
The "no official Persian translation" badge's own text becomes fixed
Persian (it's informational chrome about the source book, not something
that should flip with a book's current listening language).

### Two toggles, one state, reusing the existing keep-your-place logic

**Book card**: a small FA/EN control (styled like the old `.langswitch`
pill, scoped to one book) near the title block. Click: `setBookLang(slug, newLang)`,
then re-run `render()` — reusing the existing keep-your-place mechanism
(the current site-wide toggle already does this on language switch; the
same ratio-preserving logic applies here, just triggered per-book instead
of site-wide). A full `render()` on a single book's toggle is intentional
reuse of already-correct machinery (TOC-open state per slug is already
preserved across re-renders via the existing `open` Set) rather than new
book-scoped DOM-patching code.

**Player bar**: the same toggle, shown for whichever book is currently
loaded (`cur()?.slug`) — this is the "while listening" control. Same
handler: `setBookLang(cur().slug, newLang)` → `render()` → the existing
ratio-preserving resume happens the same way. Desktop only for this
iteration — the mobile player is a separate, more involved surface and
isn't part of this change.

### `playHistoryEntry(entry)` follows the same per-book model

Currently checks the retired global `LANG` and does a full-site
`render()` if the entry's language differs. Becomes: if
`getBookLang(entry.slug) !== entry.lang`, call `setBookLang(entry.slug, entry.lang)`
then `render()`; otherwise skip the re-render and start the track
directly, same as today's fast path.

### Search matches both languages, always

`matchBook()` currently matches chapters using `split(b).chapters` under
whatever the (retired) global language was. With no site-wide language,
it needs to check chapter titles in **both** languages unconditionally,
independent of any book's current `bookLang` state — otherwise typing an
English title/chapter name would silently fail to find a book currently
showing its Persian chapters (or vice versa). Header-level matching
(`title_en`, `title_fa`, `note_en`, `note_fa`, categories) already checks
both language fields today and needs no change.

## What this does not change

The audio pipeline, the generator, `manifest.json`/`books.meta.json`
structure, the listening-history feature's storage shape (`HISTORY` stays
keyed by episode URL — only how its `lang` field gets populated changes,
from a global read to `tr.lang`), the mobile player's own UI beyond the
chrome-text fixes above (no mobile per-book toggle in this iteration).

## Testing

`node test_search.js` needs new cases: a book currently showing Persian
chapters must still be found by an English chapter-title search, and vice
versa. `node test_history.js` unaffected (it tests the pure functions,
which don't touch `LANG`). Manual: toggle one book to English on its
card, confirm its chapter titles/spine flip while every other book and
all chrome stays Persian; play a chapter, use the player-bar toggle,
confirm it resumes the equivalent chapter in the other language at the
same position; reload the page, confirm the book's English choice
persisted while an untouched book is still Persian.
