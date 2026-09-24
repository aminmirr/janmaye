#!/usr/bin/env python3
"""
Publish a book's podcast audio to GitHub Releases and refresh manifest.json.

Usage:
    python build_site.py                 # list books, pick one
    python build_site.py tukey           # any distinct part of the folder name
    python build_site.py --all           # every book under BOOKS_ROOT
    python build_site.py --no-shrink     # never transcode, even a 256k original
    python build_site.py X --upload-only # upload + manifest only; no prompts, no commit
    python build_site.py --categories    # rename or merge a category across all books
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
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

BOOKS_ROOT = Path.home() / "Downloads" / "notebookLM"
SITE_DIR = Path(__file__).resolve().parent
MANIFEST = SITE_DIR / "manifest.json"
# Audio hosting stays on the original repo forever, independent of wherever
# this script (and the site's own files) live — rebranding the site must
# never re-upload or move any existing episode's audio.
AUDIO_REPO = "aminmirr/book-podcasts"
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
                       capture_output=True, text=True)
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
    subprocess.run(
        ["gh", "release", "create", tag, "--repo", repo, "--title", title,
         "--notes", f"Podcast audio for {title}"],
        capture_output=True, text=True,
    )

    all_paths = [p for ps in files.values() for p in ps]
    base = f"https://github.com/{repo}/releases/download/{tag}"

    def push(path: Path) -> None:
        r = subprocess.run(
            ["gh", "release", "upload", tag, "--repo", repo, "--clobber", str(path)],
            capture_output=True, text=True,
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
        e.setdefault("categories", [])          # up to 3 strings
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


def pick_cover(current: str) -> str:
    """Numbered list of covers/ so the path never has to be typed. Also takes a
    pasted https:// URL or any path containing a slash."""
    files = list_covers()
    print("    (drop the image in covers/ first, then pick a number — or paste a URL)")
    for i, f in enumerate(files, 1):
        print(f"    [{i}] {f}")
    raw = input(f"  Cover{f' [{current}]' if current else ''}: ").strip()
    if raw.isdigit() and 1 <= int(raw) <= len(files):
        return f"covers/{files[int(raw) - 1]}"
    return raw if "/" in raw else ""


MAX_CATEGORIES = 3          # what the site renders per book


def category_counts(meta: dict) -> dict[str, int]:
    """Every category in use, and how many books use it.

    There is no separate vocabulary file: the list *is* what books have. A category
    exists while some book carries it and disappears when the last one drops it, so
    it can never drift out of step with what the site actually shows.
    """
    counts: dict[str, int] = {}
    for entry in meta.values():
        for cat in entry.get("categories") or []:
            counts[cat] = counts.get(cat, 0) + 1
    return dict(sorted(counts.items()))


def parse_categories(raw: str, known: list[str]) -> list[str]:
    """Numbers pick from the list, anything else is a new name, and both can be mixed.

    A typed name that already exists resolves to it whatever the casing, so "business"
    never appears alongside "Business" — case drift is most of how the current mess
    happened.
    """
    chosen: list[str] = []
    lookup = {k.lower(): k for k in known}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if part.isdigit() and 1 <= int(part) <= len(known):
            pick = known[int(part) - 1]
        else:
            pick = lookup.get(part.lower(), part)
        if pick not in chosen:
            chosen.append(pick)
    return chosen[:MAX_CATEGORIES]


def ask_categories(current: list[str], meta: dict) -> list[str]:
    """Show what's in use with its usage count, then take numbers and/or new names.

    The counts are the whole mechanism: seeing "Business (3)" beside "Data (1)" is what
    makes an established name the easy choice. Nothing forbids a new one.
    """
    counts = category_counts(meta)
    known = list(counts)
    if known:
        print("\n  Categories — pick numbers, or type a new name")
        half = (len(known) + 1) // 2
        for i in range(half):
            left = f"[{i+1}] {known[i]} ({counts[known[i]]})"
            j = i + half
            right = f"[{j+1}] {known[j]} ({counts[known[j]]})" if j < len(known) else ""
            print(f"  {left:<28}{right}")
    shown = f" [{', '.join(current)}]" if current else ""
    raw = input(f"  Choose (max {MAX_CATEGORIES}){shown}: ").strip()
    return parse_categories(raw, known) if raw else current


def manage_categories() -> None:
    """Rename a category everywhere. Renaming onto an existing name merges them —
    the same operation, so there is no separate merge command."""
    meta = json.loads(META.read_text())
    while True:
        counts = category_counts(meta)
        known = list(counts)
        if not known:
            print("  No categories in use yet.")
            return
        print("\n  Categories in use")
        for i, cat in enumerate(known, 1):
            print(f"  [{i:>2}] {cat} ({counts[cat]})")
        raw = input("\n  Rename which? (number, q to finish): ").strip().lower()
        if raw in ("q", ""):
            return
        if not raw.isdigit() or not 1 <= int(raw) <= len(known):
            print("  Not a valid choice.")
            continue
        old = known[int(raw) - 1]
        new = input(f"  New name for {old!r} (an existing name merges them): ").strip()
        if not new or new == old:
            continue
        new = {k.lower(): k for k in known}.get(new.lower(), new)
        touched = rename_category(meta, old, new)
        META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
        verb = "merged into" if new in known else "renamed to"
        print(f"  → {old} {verb} {new} in {len(touched)} book(s): "
              f"{', '.join(t[:28] for t in touched) or '—'}")


def rename_category(meta: dict, old: str, new: str) -> list[str]:
    """Apply the rename in place; returns the slugs changed. De-duplicates, since a
    book holding both names must end up with one."""
    touched = []
    for slug, entry in meta.items():
        cats = entry.get("categories") or []
        if old not in cats:
            continue
        renamed = []
        for c in cats:
            c = new if c == old else c
            if c not in renamed:
                renamed.append(c)
        entry["categories"] = renamed
        touched.append(slug)
    return touched


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
    e["cover"] = cover
    e["categories"] = parse_categories(categories_raw, list(category_counts(meta)))
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
        manage_categories()
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
    by_slug.update(published)
    manifest["books"] = sorted(by_slug.values(), key=lambda b: b["title"])
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
