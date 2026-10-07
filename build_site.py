#!/usr/bin/env python3
"""
Publish a book's podcast audio to GitHub Releases and refresh manifest.json.

Usage:
    python build_site.py                 # list books, pick one
    python build_site.py tukey           # any distinct part of the folder name
    python build_site.py --all           # every book under BOOKS_ROOT
    python build_site.py --no-shrink     # never transcode, even a 256k original
    python build_site.py X --upload-only # upload + manifest only; no prompts, no commit
    python build_site.py --categories    # list the categories (numbers, names, usage)
    python build_site.py X --force-upload # re-send every asset, ignoring what's there

Files are transcoded to 64k mono AAC only if they aren't already small — audio the
generator produced is left untouched, so publishing twice never degrades it.

Each language also gets a zip of its episodes, uploaded as one more release asset,
which is what the site's "download all" button points at.

Audio (GBs) goes to Releases (one release per book, tag=book-<slug>); the repo
only holds index.html + manifest.json. Idempotent: re-running re-uploads with
--clobber and rewrites the book's manifest entry. Owner/repo come from the git
remote, so the asset URLs are always correct.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BOOKS_ROOT = Path.home() / "Downloads" / "notebookLM"
SITE_DIR = Path(__file__).resolve().parent
MANIFEST = SITE_DIR / "manifest.json"
# Audio hosting stays on the original repo forever, independent of wherever
# this script (and the site's own files) live — rebranding the site must
# never re-upload or move any existing episode's audio.
AUDIO_REPO = "aminmirr/book-podcasts"
# Every repo this script touches is aminmirr's — but `gh`'s "active account" is a
# single global switch on this machine, shared with whatever else is using `gh`
# (a Claude session in another editor, a different terminal). A `gh release ...`
# call here has no `--repo`-scoped identity of its own; it just runs as whichever
# account `gh` currently has active, silently. When that's the wrong account,
# GitHub answers "release not found" / a 404 on the upload URL for a release that
# exists — indistinguishable from a real missing release in this script's own
# output, and it looked exactly like a fresh corrupt-file incident before the
# cause was traced to this (2026-09-28, two books stuck "ready to upload").
# GH_TOKEN overrides gh's stored session for one subprocess call without touching
# the shared global switch, the same fix already applied to this account's git
# remotes (see book_podcast's CLAUDE.md / this incident's session notes).
_GH_ACCOUNT = "aminmirr"


def _gh_env() -> dict:
    env = os.environ.copy()
    try:
        token = subprocess.run(["gh", "auth", "token", "-u", _GH_ACCOUNT],
                               capture_output=True, text=True, check=True).stdout.strip()
        if token:
            env["GH_TOKEN"] = token
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass   # fall back to whatever account gh already has active, rather than fail outright
    return env
# Shared with the book_podcast generator repo and check_translations.py's --register —
# a book can be researched before it's even been fed to the generator.
TRANSLATION_RESEARCH_FILE = BOOKS_ROOT / "_translation_research.json"
LANGS = ("English", "Persian")
LANG_CODE = {"English": "en", "Persian": "fa"}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def owner_repo() -> str:
    return AUDIO_REPO


def episode_title(filename: str) -> str:
    stem = re.sub(r"_(en|fa)$", "", Path(filename).stem)
    if stem == "whole_book":
        return "Full-book overview"
    stem = re.sub(r"^\d+-", "", stem)          # drop merge-order prefix "03-"
    stem = re.sub(r"^\d+(½)?-?", "", stem)      # drop leftover chapter number
    return stem.replace("-", " ").strip() or filename


def all_books() -> list[str]:
    """Folder names under BOOKS_ROOT that have audio."""
    return sorted(p.name for p in BOOKS_ROOT.iterdir() if (p / "output_podcast").is_dir())


def published_slugs() -> set[str]:
    try:
        return {b["slug"] for b in json.loads(MANIFEST.read_text())["books"]}
    except (json.JSONDecodeError, KeyError, OSError):
        return set()


def resolve(name: str, books: list[str]) -> str:
    """Exact folder name, or any distinct case-insensitive substring of one.
    Never guesses: an ambiguous or unknown name exits instead of creating an
    empty release under a typo'd tag."""
    if name in books:
        return name
    hits = [b for b in books if name.lower() in b.lower()]
    if len(hits) == 1:
        return hits[0]
    listing = "\n  ".join(hits or books)
    problem = "matches several books" if hits else "matches no book"
    sys.exit(f"{name!r} {problem}:\n  {listing}")


def pick(books: list[str]) -> list[str]:
    """No argument given: number the books and ask. Marks the ones already on the site."""
    if not sys.stdin.isatty():
        sys.exit(__doc__)
    done = published_slugs()
    print(f"\nBooks in {BOOKS_ROOT}:\n")
    for i, b in enumerate(books, 1):
        mark = "  (on the site)" if slugify(b) in done else ""
        print(f"  [{i}] {b}{mark}")
    while True:
        raw = input("\nPublish which? (number, 'a' for all, q to quit): ").strip().lower()
        if raw in ("q", ""):
            sys.exit(0)
        if raw == "a":
            return books
        if raw.isdigit() and 1 <= int(raw) <= len(books):
            return [books[int(raw) - 1]]
        print("  Not a valid choice.")


def bar(done: int, total: int, label: str = "") -> None:
    """One-line progress bar; counts finished files, so it steps per file, not per byte."""
    filled = round(20 * done / max(total, 1))
    print(f"\r  [{'#' * filled}{'.' * (20 - filled)}] {done}/{total}  {label[:38]:<38}",
          end="\n" if done == total else "", flush=True)


def already_small(path: Path) -> bool:
    """True if this is already ~64k mono (the generator's own output). Re-encoding it
    would only lose quality, so the transcode is skipped per file rather than per run."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=channels,bit_rate", "-of", "default=noprint_wrappers=1", str(path)],
        capture_output=True, text=True,
    ).stdout
    info = dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)
    try:
        return int(info["channels"]) == 1 and int(info["bit_rate"]) <= 80_000
    except (KeyError, ValueError):
        return False


def shrink(src: Path, dst_dir: Path) -> Path:
    """Transcode to 64k mono AAC (transparent for speech, ~4x smaller). Keeps the
    filename so the release asset name / URL stays stable."""
    dst = dst_dir / src.name
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-movflags", "+faststart", str(dst)],
        check=True,
    )
    return dst


def make_zip(paths: list[Path], dst: Path, folder: str) -> Path:
    """Bundle one language's episodes for a single 'download the whole book' click.

    ZIP_STORED, not DEFLATE: m4a is already compressed, so deflating spends CPU to
    save nothing. Entries are nested under `folder` so unzipping makes a directory
    instead of spraying loose files."""
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_STORED) as z:
        for p in paths:
            z.write(p, arcname=f"{folder}/{p.name}")
    return dst


def duration_secs(path: Path) -> int | None:
    """Audio length in whole seconds via ffprobe (feeds the site's chapter spine)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True,
        )
        return round(float(out.stdout.strip()))
    except (ValueError, OSError):
        return None


def audio_files(book_dir: Path, lang: str) -> list[Path]:
    d = book_dir / "output_podcast" / lang
    if not d.is_dir():
        return []
    # whole_book first, then numeric order
    return sorted(d.glob("*.m4a"), key=lambda p: (not p.stem.startswith("whole_book"), p.name))


def release_assets(tag: str, repo: str) -> dict[str, int]:
    """What the release already holds: asset name → byte size.

    Empty on any failure — a missing release, no network, unreadable JSON — which
    falls back to uploading everything. Skipping is the optimisation, so any doubt
    resolves toward doing the work.
    """
    r = subprocess.run(["gh", "release", "view", tag, "--repo", repo, "--json", "assets"],
                       capture_output=True, text=True, env=_gh_env())
    if r.returncode:
        return {}
    try:
        return {a["name"]: a["size"] for a in json.loads(r.stdout).get("assets") or []}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def to_upload(paths: list[Path], have: dict[str, int],
              force: bool = False) -> list[Path]:
    """Which of these still need sending.

    Size is the only comparison GitHub offers without downloading each asset, so two
    different files of identical byte length would read as the same. For 64k AAC of
    differing speech that does not happen; --force-upload is the way out if it ever
    does, or if an asset is truncated.
    """
    if force:
        return list(paths)
    return [p for p in paths if have.get(p.name) != p.stat().st_size]


def stamp_published(fresh: dict, existing: dict, now: str | None = None) -> None:
    """Give each freshly published entry its `published_at`: the date it FIRST went
    up. A re-publish or top-up keeps the original — it is when the book appeared on
    the site, not when it was last touched. Mutates `fresh`."""
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for slug, entry in fresh.items():
        entry["published_at"] = (existing.get(slug) or {}).get("published_at") or now


def sort_books(books) -> list:
    """Newest first; a book with no date sinks below the dated ones, then by title."""
    by_title = sorted(books, key=lambda b: b["title"])
    return sorted(by_title, key=lambda b: b.get("published_at") or "", reverse=True)


def publish_book(book_name: str, repo: str, do_shrink: bool = True,
                 force: bool = False) -> dict | None:
    book_dir = BOOKS_ROOT / book_name
    files = {lang: audio_files(book_dir, lang) for lang in LANGS}
    if not any(files.values()):
        print(f"  skip {book_name}: no audio")
        return None

    slug = slugify(book_name)
    tag = f"book-{slug}"
    title = book_name.replace("-", " ")

    # create the release once (ignore "already exists")
    gh_env = _gh_env()
    subprocess.run(
        ["gh", "release", "create", tag, "--repo", repo, "--title", title,
         "--notes", f"Podcast audio for {title}"],
        capture_output=True, text=True, env=gh_env,
    )

    all_paths = [p for ps in files.values() for p in ps]
    base = f"https://github.com/{repo}/releases/download/{tag}"

    def push(path: Path) -> None:
        r = subprocess.run(
            ["gh", "release", "upload", tag, "--repo", repo, "--clobber", str(path)],
            capture_output=True, text=True, env=gh_env,
        )
        if r.returncode:
            print()
            sys.exit(f"  upload failed for {path.name}: {r.stderr.strip()}")

    with tempfile.TemporaryDirectory() as tmp:
        # Only the files that are still big get transcoded; the rest upload as-is.
        small: dict[Path, Path] = {}
        big = [p for p in all_paths if do_shrink and not already_small(p)]
        if big:
            print(f"  shrinking {len(big)} of {len(all_paths)} file(s) to 64k mono AAC ...")
            for i, p in enumerate(big, 1):
                small[p] = shrink(p, Path(tmp))
                bar(i, len(big), p.name)
        # what actually gets uploaded, still grouped by language
        up = {lang: [small.get(p, p) for p in ps] for lang, ps in files.items() if ps}
        uploads = [p for ps in up.values() for p in ps]

        # One gh call per file so the bar can advance; a single batched call gives no
        # feedback until every asset is done.
        have = release_assets(tag, repo)
        todo = to_upload(uploads, have, force)
        print(f"  uploading to release {tag} ...")
        if len(todo) < len(uploads):
            print(f"  {len(uploads) - len(todo)} of {len(uploads)} already uploaded"
                  f" — sending {len(todo)}")
        if todo:
            bar(0, len(todo))
            for i, p in enumerate(todo, 1):
                push(p)
                bar(i, len(todo), p.name)

        # One zip per language, so a listener downloads the half they actually want.
        # Storage is the same either way: each episode appears in exactly one zip.
        # An unchanged episode set makes a byte-identical archive (ZIP_STORED, same
        # files, same order), so the same size check covers zips with nothing added.
        print(f"  bundling {len(up)} zip(s) ...")
        zips = {}
        bar(0, len(up))
        for i, (lang, ps) in enumerate(up.items(), 1):
            z = make_zip(ps, Path(tmp) / f"{slug}-{LANG_CODE[lang]}.zip", book_name)
            if to_upload([z], have, force):
                push(z)
            zips[lang] = {"url": f"{base}/{z.name}", "bytes": z.stat().st_size,
                          "count": len(ps)}
            bar(i, len(up), z.name)

    episodes = {
        lang: [{"title": episode_title(p.name), "url": f"{base}/{p.name}",
                "seconds": duration_secs(p)} for p in ps]
        for lang, ps in files.items() if ps
    }
    return {"slug": slug, "title": title, "episodes": episodes, "zips": zips}


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"books": []}


META = SITE_DIR / "books.meta.json"


def chapter_key(url_or_name: str) -> str:
    """Stable per-chapter key shared by the EN and FA files (drops _en/_fa + .m4a)."""
    name = url_or_name.rsplit("/", 1)[-1]
    stem = name[:-4] if name.endswith(".m4a") else name
    return re.sub(r"_(en|fa)$", "", stem)


def seed_meta(manifest: dict) -> None:
    """Ensure books.meta.json has hand-editable stubs (book fields, up to-3 categories,
    and a per-chapter title map). Uses setdefault everywhere — it only ADDS missing
    keys and NEVER overwrites an existing value, so your edits always survive a republish."""
    meta = json.loads(META.read_text()) if META.exists() else {}
    research = (json.loads(TRANSLATION_RESEARCH_FILE.read_text())
                if TRANSLATION_RESEARCH_FILE.exists() else {})
    for b in manifest["books"]:
        e = meta.setdefault(b["slug"], {})
        e.setdefault("title_en", b["title"])
        # A book researched ahead of time (check_translations.py --register, before it
        # even had a notebook) lands here so that first publish needs no re-research.
        # Only fills what's still unset — a hand edit always wins.
        if cached := research.get(b["slug"]):
            if e.get("translated_fa") is None and cached.get("translated_fa") is not None:
                e["translated_fa"] = cached["translated_fa"]
            if not e.get("title_fa") and cached.get("title_fa"):
                e["title_fa"] = cached["title_fa"]
            if not e.get("note_fa") and cached.get("note_fa"):
                e["note_fa"] = cached["note_fa"]
        for k in ("title_fa", "author", "cover", "note_en", "note_fa"):
            e.setdefault(k, "")
        e.setdefault("translated_fa", None)      # True/False once checked; None = unknown, no badge
        e.setdefault("categories", [])          # up to 3 subgenre ids from categories.json
        chs = e.setdefault("chapters", {})       # chapter_key -> {title_en, title_fa}
        for eps in b["episodes"].values():
            for ep in eps:
                if "whole_book" in ep["url"]:
                    continue
                c = chs.setdefault(chapter_key(ep["url"]), {})
                c.setdefault("title_en", ep["title"])
                c.setdefault("title_fa", "")
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(f"books.meta.json: {len(meta)} book(s) (existing edits untouched)")


def list_covers() -> list[str]:
    """Filenames in covers/, sorted — the numbered list pick_cover() shows, and
    what a non-interactive caller (the dashboard's publish wizard) needs to
    build the same numbered picker without going through input()."""
    covers = SITE_DIR / "covers"
    return sorted(p.name for p in covers.iterdir()
                  if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")) \
        if covers.is_dir() else []


def clean_cover_path(raw: str) -> str:
    """Strip stray quote marks a cover path picked up by accident — typed into a
    prompt or the dashboard's publish wizard out of shell/JSON habit, or pasted
    from somewhere that already had them, e.g. "'covers/x.jpg'" instead of
    "covers/x.jpg". Every writer of books.meta.json's cover field funnels through
    here (pick_cover() and apply_meta_flags() below), so a mistake made once
    doesn't need re-fixing at every call site — or worse, in the file by hand.
    index.html defends the same way at render time, for whatever is already
    sitting in the file from before this existed."""
    p = _strip_quotes(raw)
    # A bare filename means a file in covers/: stored as typed it resolved to nothing.
    return f"covers/{p}" if p and "/" not in p and ":" not in p else p


def _strip_quotes(raw: str) -> str:
    return str(raw or "").strip().strip("'\"").strip()


def pick_cover(current: str) -> str:
    """Numbered list of covers/ so the path never has to be typed. Also takes a
    pasted https:// URL or any path containing a slash."""
    files = list_covers()
    print("    (drop the image in covers/ first, then pick a number — or paste a URL)")
    for i, f in enumerate(files, 1):
        print(f"    [{i}] {f}")
    raw = _strip_quotes(input(f"  Cover{f' [{current}]' if current else ''}: "))
    if raw.isdigit() and 1 <= int(raw) <= len(files):
        return f"covers/{files[int(raw) - 1]}"
    if raw in files:                       # typed a filename that is really in covers/
        return f"covers/{raw}"
    return raw if "/" in raw else ""


MAX_CATEGORIES = 3          # what the site renders per book
TAXONOMY = SITE_DIR / "categories.json"


def load_taxonomy() -> dict:
    """The closed list of categories: groups, each with subgenres, each with an id and
    an English + Persian name. A book stores subgenre ids; its groups are derived."""
    return json.loads(TAXONOMY.read_text())


def flat_subs(tax: dict) -> list[dict]:
    """Every subgenre in display order, tagged with its group — the numbering the
    prompt and the wizard both show."""
    return [{**sub, "group": g["id"], "group_en": g["en"], "group_fa": g["fa"]}
            for g in tax["groups"] for sub in g["subs"]]


def category_counts(meta: dict) -> dict[str, int]:
    """How many books carry each subgenre id (only ids in use appear)."""
    counts: dict[str, int] = {}
    for entry in meta.values():
        for cat in entry.get("categories") or []:
            counts[cat] = counts.get(cat, 0) + 1
    return counts


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def parse_categories(raw: str, subs: list[dict]) -> tuple[list[str], list[str]]:
    """(chosen ids, unrecognised words). A part may be the list number, the id, or the
    English / Persian name in any casing. The list is closed: anything else is reported
    back, never stored — free-typing is how 'Data' ended up beside 'Data Science'."""
    lookup: dict[str, str] = {}
    for sub in subs:
        for key in (sub["id"], sub["en"], sub["fa"]):
            lookup[_norm(key)] = sub["id"]
    chosen: list[str] = []
    unknown: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if part.isdigit() and 1 <= int(part) <= len(subs):
            pick = subs[int(part) - 1]["id"]
        else:
            pick = lookup.get(_norm(part))
        if pick is None:
            unknown.append(part)
        elif pick not in chosen:
            chosen.append(pick)
    return chosen[:MAX_CATEGORIES], unknown


def unknown_ids(meta: dict, tax: dict) -> dict[str, list[str]]:
    """slug -> category ids that are not in the taxonomy (e.g. a pre-redesign name)."""
    valid = {s["id"] for s in flat_subs(tax)}
    return {slug: bad for slug, e in meta.items()
            if (bad := [c for c in e.get("categories") or [] if c not in valid])}


def print_taxonomy(tax: dict, counts: dict[str, int] | None = None) -> None:
    counts = counts or {}
    n = 0
    for g in tax["groups"]:
        print(f"\n  {g['en']}  ·  {g['fa']}")
        for sub in g["subs"]:
            n += 1
            used = f" ({counts[sub['id']]})" if sub["id"] in counts else ""
            print(f"    [{n:>2}] {sub['en']}{used}")


def ask_categories(current: list[str], meta: dict) -> list[str]:
    """Show the groups with their subgenres, take numbers (or names), ask again on
    anything not on the list. Enter keeps what the book has."""
    tax = load_taxonomy()
    subs = flat_subs(tax)
    print("\n  Categories — pick numbers from the list")
    print_taxonomy(tax, category_counts(meta))
    shown = f" [{', '.join(current)}]" if current else ""
    while True:
        raw = input(f"\n  Choose (max {MAX_CATEGORIES}){shown}: ").strip()
        if not raw:
            return current
        chosen, unknown = parse_categories(raw, subs)
        if unknown:
            print(f"  Not on the list: {', '.join(unknown)}. "
                  "(Add a new one to categories.json first.)")
            continue
        return chosen


def ask_meta(names: list[str]) -> None:
    """Fill in the hand-edited fields for freshly published books. Skips a book that
    already has an author and a cover, so republishing never re-interrogates you.
    Chapter titles stay a file edit — too many to sit through a prompt for."""
    if not sys.stdin.isatty():
        return
    meta = json.loads(META.read_text())
    for name in names:
        e = meta.get(slugify(name))
        if e is None or (e.get("author") and e.get("cover")):
            continue
        print(f"\n── Book details: {name} ──   (Enter keeps what's shown)")
        for key, label in (("title_en", "English title"), ("title_fa", "Persian title"),
                           ("author", "Author")):
            cur = e.get(key, "")
            val = input(f"  {label}{f' [{cur}]' if cur else ''}: ").strip()
            if val:
                e[key] = val
        if cover := pick_cover(e.get("cover", "")):
            e["cover"] = cover
        e["categories"] = ask_categories(e.get("categories") or [], meta)
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")


def apply_meta_flags(name: str, title_en: str, title_fa: str, author: str,
                     cover: str, categories_raw: str) -> None:
    """Non-interactive equivalent of ask_meta()'s per-book prompt loop, for a
    caller (the dashboard's publish wizard) that already collected every
    answer itself and has nothing left to ask. A no-op if the book has no
    manifest entry yet — mirrors ask_meta()'s own `if e is None: continue`."""
    meta = json.loads(META.read_text())
    e = meta.get(slugify(name))
    if e is None:
        return
    e["title_en"] = title_en
    e["title_fa"] = title_fa
    e["author"] = author
    e["cover"] = clean_cover_path(cover)
    chosen, unknown = parse_categories(categories_raw, flat_subs(load_taxonomy()))
    if unknown:
        sys.exit(f"unknown categories: {', '.join(unknown)} — see `python build_site.py --categories`")
    e["categories"] = chosen
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")


def push_now(names: list[str], repo: str) -> None:
    """Non-interactive equivalent of commit_and_push()'s git steps — no Y/n,
    since a caller that already decided to push has nothing left to confirm."""
    git = ["git", "-C", str(SITE_DIR)]
    subprocess.run([*git, "add", "manifest.json", "books.meta.json", "covers"], check=True)
    r = subprocess.run([*git, "commit", "-m", f"Add {', '.join(names)}"],
                       capture_output=True, text=True)
    if r.returncode and "nothing to commit" not in r.stdout:
        sys.exit(r.stdout + r.stderr)
    subprocess.run([*git, "push"], check=True)
    print(f"\nLive in a minute: https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/")


def commit_and_push(names: list[str], repo: str) -> None:
    """Publishing only reaches the live site after a push, so offer it here."""
    if not sys.stdin.isatty():
        return
    if input("\nCommit and push to the live site? [Y/n]: ").strip().lower() in ("n", "no"):
        print("  Skipped. When ready:  git add -A && git commit -m '...' && git push")
        return
    push_now(names, repo)


def _extract_flag(args: list[str], name: str) -> tuple[list[str], str | None]:
    """Pulls a `--name=value` flag out of args, returning the remaining args and
    the value (None if the flag wasn't present). Hand-rolled to match the rest
    of main()'s flag handling, which predates argparse here."""
    prefix = f"{name}="
    value = None
    remaining = []
    for a in args:
        if a.startswith(prefix):
            value = a[len(prefix):]
        else:
            remaining.append(a)
    return remaining, value


def main() -> None:
    args = sys.argv[1:]
    do_shrink = "--no-shrink" not in args
    # --upload-only: do the slow, unattended half (transcode, upload, manifest) and
    # stop. Said explicitly rather than inferred from isatty, because the queue runs
    # this with a terminal attached and still must not prompt or commit.
    upload_only = "--upload-only" in args
    force = "--force-upload" in args
    if "--categories" in args:
        print_taxonomy(load_taxonomy(), category_counts(json.loads(META.read_text())))
        return
    # The wizard's non-interactive metadata path: every field arrives as its own
    # flag rather than through ask_meta()'s prompts. --push opts into commit_and_push's
    # git steps without its Y/n confirmation, since the wizard already asked.
    push = "--push" in args
    args = [a for a in args if a != "--push"]
    args, title_en = _extract_flag(args, "--title-en")
    args, title_fa = _extract_flag(args, "--title-fa")
    args, author = _extract_flag(args, "--author")
    args, cover = _extract_flag(args, "--cover")
    args, categories_raw = _extract_flag(args, "--categories")
    args = [a for a in args
            if a not in ("--no-shrink", "--upload-only", "--force-upload")]
    repo = owner_repo()

    books = all_books()
    if not books:
        sys.exit(f"no books with audio under {BOOKS_ROOT}")
    if args == ["--all"]:
        names = books
    elif args:
        names = [resolve(a, books) for a in args]
    else:
        names = pick(books)
    print("\nPublishing: " + ", ".join(names))

    published = {}
    for name in names:
        entry = publish_book(name, repo, do_shrink, force)
        if entry:
            published[entry["slug"]] = entry

    # Re-read immediately before writing and lay only our own books on top. An upload
    # takes minutes, and this file is rewritten whole — trusting a copy read at startup
    # means a second publish running alongside silently reverts whatever the first one
    # did. Only the books this run touched are ours to overwrite.
    manifest = load_manifest()
    by_slug = {b["slug"]: b for b in manifest["books"]}
    clobbered = [s for s in published if s in by_slug]
    stamp_published(published, by_slug)
    by_slug.update(published)
    manifest["books"] = sort_books(by_slug.values())
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {MANIFEST} ({len(manifest['books'])} book(s), "
          f"{len(published)} updated, {len(published) - len(clobbered)} new)")
    seed_meta(manifest)
    if upload_only:
        print("\n  Uploaded. Titles, author, cover and the commit are still yours:")
        print(f"  python build_site.py \"{names[0]}\"")
        return
    if title_en is not None and title_fa is not None and author is not None and cover is not None:
        apply_meta_flags(names[0], title_en, title_fa, author, cover, categories_raw or "")
        if push:
            push_now(names, repo)
        return
    ask_meta(names)
    commit_and_push(names, repo)


if __name__ == "__main__":
    main()
