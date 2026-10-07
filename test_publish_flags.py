"""apply_meta_flags() and push_now() are the non-interactive equivalents of
ask_meta()'s prompt loop and commit_and_push()'s git steps — the wizard's path.

Runs against a COPY of books.meta.json — never the live file.
Run: python3 test_publish_flags.py
"""
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path

s = importlib.util.spec_from_file_location("bs", Path(__file__).with_name("build_site.py"))
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)

BOOK = "Show-your-work"
SLUG = m.slugify(BOOK)

blank = {"title_en": "Show your work", "title_fa": "", "author": "", "cover": "",
         "categories": []}


def with_meta(meta_entry: dict) -> Path:
    tmp = Path(tempfile.mkdtemp()) / "books.meta.json"
    tmp.write_text(json.dumps({SLUG: meta_entry}))
    m.META = tmp
    return tmp


# 1. Every field lands exactly as given — no prompting, no "Enter keeps it".
tmp = with_meta(blank)
m.apply_meta_flags(BOOK, "Show Your Work!", "کارت را نشان بده", "Austin Kleon",
                   "covers/x.jpg", "Creativity,productivity-career")
e = json.loads(tmp.read_text())[SLUG]
assert e["title_en"] == "Show Your Work!", e
assert e["title_fa"] == "کارت را نشان بده", e
assert e["author"] == "Austin Kleon", e
assert e["cover"] == "covers/x.jpg", e
assert e["categories"] == ["creativity", "productivity-career"], e   # name and id both resolve to ids

# 1b. A --cover flag with stray wrapping quotes (typed into the dashboard's
# publish wizard, or passed by hand) is cleaned the same way pick_cover() is —
# this is the path that actually produced the incident: the wizard's Input
# widget sends whatever was typed straight through as a flag, unedited.
tmp = with_meta(blank)
m.apply_meta_flags(BOOK, "T", "", "A", "'covers/typo with quotes.jpg'", "")
e = json.loads(tmp.read_text())[SLUG]
assert e["cover"] == "covers/typo with quotes.jpg", e

# 1c. A bare filename lands as a covers/ path (the two published books that shipped
# without a cover typed it that way).
tmp = with_meta(blank)
m.apply_meta_flags(BOOK, "T", "", "A", "lean_analitycs.jpg", "")
assert json.loads(tmp.read_text())[SLUG]["cover"] == "covers/lean_analitycs.jpg"
tmp = with_meta(blank)
m.apply_meta_flags(BOOK, "T", "", "A", "https://example.com/x.jpg", "")
assert json.loads(tmp.read_text())[SLUG]["cover"] == "https://example.com/x.jpg", "URLs untouched"

# 2. An empty categories string clears them, same as choosing none interactively.
tmp = with_meta({**blank, "categories": ["creativity"]})
m.apply_meta_flags(BOOK, "T", "", "A", "", "")
e = json.loads(tmp.read_text())[SLUG]
assert e["categories"] == [], e

# 3. Numbers and Persian names resolve against the closed taxonomy, same as
# ask_categories(); the list is numbered in categories.json order.
tmp = with_meta(blank)
m.apply_meta_flags(BOOK, "T", "", "A", "", "1,خلاقیت")
e = json.loads(tmp.read_text())[SLUG]
assert e["categories"] == ["management-leadership", "creativity"], e

# 3b. A name that is not on the list stops the publish instead of being stored.
tmp = with_meta(blank)
try:
    m.apply_meta_flags(BOOK, "T", "", "A", "", "creativity,Brand New")
    raise AssertionError("an unknown category must not be accepted")
except SystemExit as exc:
    assert "Brand New" in str(exc), exc
assert json.loads(tmp.read_text())[SLUG]["categories"] == [], "nothing written on refusal"

# 4. No such book in the manifest: a no-op, not a KeyError.
tmp = with_meta(blank)
before = tmp.read_text()
m.apply_meta_flags("Nonexistent-Book", "T", "", "A", "", "")
assert tmp.read_text() == before, "must not touch the file when the book isn't in it"

# 5. push_now() runs add/commit/push in order, with no Y/n prompt.
calls = []


def fake_run(cmd, **kw):
    calls.append(cmd)
    return types.SimpleNamespace(returncode=0, stdout="", stderr="")


m.subprocess = types.SimpleNamespace(run=fake_run)
m.SITE_DIR = Path(tempfile.mkdtemp())
m.push_now([BOOK], "owner/repo")
assert len(calls) == 3, calls
assert calls[0][-3:] == ["manifest.json", "books.meta.json", "covers"], calls[0]
assert "commit" in calls[1] and f"Add {BOOK}" in calls[1], calls[1]
assert calls[2][-1] == "push", calls[2]

print("ok")
