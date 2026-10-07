"""ask_meta() writes what you type and skips books already filled in.

Runs against a COPY of books.meta.json — never the live file.
Run: python3 test_ask_meta.py
"""
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path

s = importlib.util.spec_from_file_location("bs", Path(__file__).with_name("build_site.py"))
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)

BOOK = "Show-your-work"
SLUG = m.slugify(BOOK)


def run(meta_entry: dict, keys: str) -> dict:
    """Point META at a temp copy, type `keys`, return the resulting entry."""
    tmp = Path(tempfile.mkdtemp()) / "books.meta.json"
    tmp.write_text(json.dumps({SLUG: meta_entry}))
    m.META = tmp
    sys.stdin = io.StringIO(keys)
    sys.stdin.isatty = lambda: True
    m.ask_meta([BOOK])
    return json.loads(tmp.read_text())[SLUG]


blank = {"title_en": "Show your work", "title_fa": "", "author": "", "cover": "",
         "categories": []}

# 1. Typed answers land in the file; a cover number resolves to its covers/ path.
covers = sorted(p.name for p in (m.SITE_DIR / "covers").iterdir()
                if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"))
assert "README.md" not in covers, "only images are offered as covers"
e = run(blank, "Show Your Work!\nکارت را نشان بده\nAustin Kleon\n1\ncreativity, productivity-career, philosophy, psychology\n")
assert e["title_en"] == "Show Your Work!", e
assert e["title_fa"] == "کارت را نشان بده", e
assert e["author"] == "Austin Kleon", e
assert e["cover"] == f"covers/{covers[0]}", e
assert e["categories"] == ["creativity", "productivity-career", "philosophy"], "capped at 3"

# 2. Enter keeps the existing value instead of blanking it.
e = run({**blank, "author": "Austin Kleon"}, "\n\n\n\n\n")
assert e["title_en"] == "Show your work" and e["author"] == "Austin Kleon", e
assert e["cover"] == "", e

# 3. A pasted URL is taken as-is; a bare word that isn't a number is ignored.
e = run(blank, "\n\n\nhttps://example.com/c.jpg\n\n")
assert e["cover"] == "https://example.com/c.jpg", e
e = run(blank, "\n\n\nnonsense\n\n")
assert e["cover"] == "", e

# 4. A book that already has author + cover is never asked about (empty stdin would
#    raise EOFError if it prompted).
sys.stdin = io.StringIO("")
sys.stdin.isatty = lambda: True
e = run({**blank, "author": "A", "cover": "covers/x.jpg"}, "")
assert e["author"] == "A" and e["cover"] == "covers/x.jpg"

# 5. Non-interactive (cron, piped) never prompts.
tmp = Path(tempfile.mkdtemp()) / "books.meta.json"
tmp.write_text(json.dumps({SLUG: blank}))
m.META = tmp
sys.stdin = io.StringIO("")
sys.stdin.isatty = lambda: False
m.ask_meta([BOOK])
assert json.loads(tmp.read_text())[SLUG] == blank

# 6. clean_cover_path() strips accidental wrapping quotes and whitespace —
# a books.meta.json entry hand-edited to "'covers/x.jpg'" instead of
# "covers/x.jpg" is exactly the mistake this guards against.
for raw, want in (
    ("'covers/x.jpg'", "covers/x.jpg"),
    ('"covers/x.jpg"', "covers/x.jpg"),
    ("  covers/x.jpg  ", "covers/x.jpg"),
    ("'  covers/x.jpg  '", "covers/x.jpg"),
    ("'\"covers/x.jpg\"'", "covers/x.jpg"),      # both quote styles, nested
    ("https://example.com/x.jpg", "https://example.com/x.jpg"),  # untouched
    ("", ""),
):
    assert m.clean_cover_path(raw) == want, (raw, m.clean_cover_path(raw))

# 7. The interactive prompt cleans the same way — a value typed or pasted with
# stray quotes into pick_cover() never reaches the saved file quoted.
e = run(blank, "\n\n\n'covers/typo-with-quotes.jpg'\n\n")
assert e["cover"] == "covers/typo-with-quotes.jpg", e

print("ok")
