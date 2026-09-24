# جان‌مایه (Janmaye)

A static site listing AI-generated podcast summaries of books (English + Persian),
made with [NotebookLM](https://notebooklm.google.com/).

**Live:** https://aminmirr.github.io/janmaye/ · GitHub Pages off `main`.

Formerly `book-podcasts`. That repo still exists — it's kept alive permanently
as the audio host (see the Audio row below) and, at its own GitHub Pages
address, a static handoff page pointing here. Nothing about the rebrand moved
or re-uploaded any existing episode.

Each book has one **whole-book** episode (standalone overview) plus one episode
**per chapter**. Two languages per book where available.

## How it's put together

| Layer | Where | Notes |
|-------|-------|-------|
| Site | `index.html` (single file, no build step) | Reads `manifest.json` + `books.meta.json` at load |
| Audio | **GitHub Releases on `aminmirr/book-podcasts`** (one release per book, tag `book-<slug>`) — see `AUDIO_REPO` in `build_site.py` | 64k mono AAC; never enters git; hosted separately from this repo on purpose |
| Generated data | `manifest.json` | episodes, URLs, **durations** — do not hand-edit |
| Editable data | `books.meta.json` | titles, author, cover, notes, categories, chapter titles |
| Covers | `covers/*` | referenced from `books.meta.json` |
| Logo | `logo.png` (master) → `icon.png`, `og.png` | favicon + social preview; regenerate the two from the master, don't edit them |
| Likes + suggestions | **Supabase** (anon key + RLS) | see below |

## Publish / update audio

```bash
python build_site.py                       # list books, pick one
python build_site.py tukey                 # any distinct part of the folder name
python build_site.py --all                 # every book with audio
```

Drop the cover image in `covers/` first. After uploading, the script asks for the
book's titles (EN/FA), author, cover (pick from a numbered list of `covers/`, or paste
a URL) and up to 3 categories, writes them into `books.meta.json`, then offers to
commit and push. It only asks about books that don't already have an author and a
cover, so republishing is silent. Everything else — chapter titles, notes — stays a
file edit.

`build_site.py` transcodes each `.m4a` to 64k mono AAC (~4× smaller than NotebookLM's
256k stereo, transparent for speech), reads durations via `ffprobe`, uploads them as
Release assets with a progress bar, and rewrites the book's `manifest.json` entry.
Requires `ffmpeg`. It also **seeds** `books.meta.json` with a stub for any new book
(never overwriting existing edits).

Files that are already ~64k mono upload untouched, so republishing never re-encodes
good audio (`--no-shrink` forces that for every file). Book names are matched loosely
— `tukey` finds `Exploratory-Data-Analysis--John-W-Tukey` — but never guessed: an
ambiguous or unknown name exits instead of creating an empty release under a typo.

### Download-all zips

Publishing also builds one zip per language (`<slug>-en.zip`, `<slug>-fa.zip`),
uploads it as another release asset, and records its URL, size and file count under
`zips` in the manifest. The site turns that into a **Download all · 74 MB** link next
to the chapter count; a book with no `zips` entry simply doesn't show one, so books
published before this existed keep working until their next publish.

`ZIP_STORED`, not deflate — m4a is already compressed, so deflating would burn CPU
to save nothing (measured overhead: ~1 KB on a 74 MB bundle). Entries are nested
under the book's folder name so unzipping makes a directory instead of spraying
loose files.

One zip per language rather than one per book: total storage is identical, since
each episode appears in exactly one zip, but a Persian listener doesn't download the
English half. It also means the button always matches the language on screen.

## Editing book details — `books.meta.json`

`manifest.json` is generated (overwritten on every publish); `books.meta.json` is
**yours** and is never overwritten. Keyed by book slug:

```json
"show-your-work": {
  "title_en": "Show Your Work!",              // English title (shown bold)
  "title_fa": "کارت را نشان بده",              // Persian title
  "author":   "Austin Kleon",
  "cover":    "covers/show-your-work.jpg",     // repo path OR full https:// URL
  "note_en":  "One-line description",
  "note_fa":  "توضیح کوتاه",
  "categories": ["Creativity", "Career"],      // up to 3; clickable filters on the site
  "chapters": {                                 // per-chapter title overrides (EN/FA)
    "00-A-New-Way-of-Operating": { "title_en": "A New Way of Operating", "title_fa": "" }
  }
}
```

Edit, `git commit && git push`, done. `build_site.py` uses `setdefault` everywhere,
so it only **adds** missing keys — your edits always survive a republish.

- **Chapter titles:** keyed by chapter key (the filename minus `_en`/`_fa`), shared by
  both languages. English is pre-filled from filenames; add `title_fa` for Persian.
- **Covers:** drop an image in `covers/` and point `cover` at it, or use any `https://`
  URL. Missing/broken images just render without a cover.
- **Categories:** ≤3 per book. They become clickable chips that filter the list.

## Links

Two kinds, both permanent.

**The audio file itself** — a GitHub Release asset, playable and downloadable with no
site involved. Every URL is already in `manifest.json`:

```
https://github.com/aminmirr/book-podcasts/releases/download/book-<slug>/<file>.m4a
```

**A place on the site** — hash links, handled by `openFromHash()`:

| Link | Opens |
|---|---|
| `…/#show-your-work` | that book, scrolled into view |
| `…/#show-your-work/full` | its whole-book episode, loaded in the player |
| `…/#show-your-work/04-8-Learn-to-Take-a-Punch` | that chapter, with the table of contents opened |

The share button in the player copies the link for whatever is playing.

Chapters are keyed by **chapter key**, not by number. Numbering is per-language — a
book with 6 English and 3 Persian episodes numbers the same chapter differently — and
shifts whenever a missing episode is generated, so `#slug/3` would rot. The key is the
asset filename minus `_en`/`_fa`, the same key `books.meta.json` uses, so one link
lands on the same chapter in either language. A key with no episode in the current
language falls back to opening the book.

Deep links load the episode but never autoplay.

## Search

The box above the category chips filters the list as you type, matching book titles
(EN + FA), author, note, categories and **chapter titles**. A book matched only by a
chapter opens its chapter list, so you can see why it matched. `/` focuses the box,
Escape clears it. It composes with the category chips (both must match).

Queries are folded before comparing, or Persian search quietly fails: the zero-width
non-joiner in words like `خلاصه‌های` means a typed space would never match, and Arabic
`ي`/`ك` look identical to Persian `ی`/`ک` on most keyboards. `node test_search.js`
covers this.

Note that Persian search only finds what exists — as of now every `title_fa` and
`note_fa` in `books.meta.json` is empty, so there is no Persian book text to match.
The publish prompt asks for those.

## Site features

- Reading-room design (Newsreader serif + Vazirmatn, one amber/verdigris accent),
  bilingual EN/FA with RTL, per-chapter **spine** sized by listening length.
- Per-book **like / dislike** and a **suggest a book** flow (GitHub issue *or*
  anonymous Supabase form).
- **Mobile player** (≤680px): a custom expanded/collapsed player that opens expanded
  when you play something and auto-collapses when you scroll or interact elsewhere.
  Desktop keeps the compact bottom bar. Both have 15s skip + playback speed.

## Likes & suggestions (Supabase)

Static sites can't store data, so votes/suggestions use a Supabase project via its
**anon public key** (safe to ship in the browser — gated by Row-Level Security).

- Config lives in `index.html` (`SB_URL`, `SB_KEY`).
- Tables: `votes` (one row per `slug`+browser `voter`, value ±1; anon can read/insert/
  update, **not delete**) and `suggestions` (anon can **insert only** — visitors cannot
  read others' suggestions; you read them in the Supabase dashboard → Table Editor).
- The `service_role` key is **never** used here and must stay secret.

Reading incoming suggestions: Supabase dashboard → **Table Editor → `suggestions`**.
