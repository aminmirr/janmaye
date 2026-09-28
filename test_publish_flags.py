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
                   "covers/x.jpg", "Creativity,Career")
e = json.loads(tmp.read_text())[SLUG]
assert e["title_en"] == "Show Your Work!", e
assert e["title_fa"] == "کارت را نشان بده", e
assert e["author"] == "Austin Kleon", e
assert e["cover"] == "covers/x.jpg", e
assert e["categories"] == ["Creativity", "Career"], e

# 1b. A --cover flag with stray wrapping quotes (typed into the dashboard's
# publish wizard, or passed by hand) is cleaned the same way pick_cover() is —
# this is the path that actually produced the incident: the wizard's Input
# widget sends whatever was typed straight through as a flag, unedited.
tmp = with_meta(blank)
m.apply_meta_flags(BOOK, "T", "", "A", "'covers/typo with quotes.jpg'", "")
e = json.loads(tmp.read_text())[SLUG]
assert e["cover"] == "covers/typo with quotes.jpg", e

# 2. An empty categories string clears them, same as choosing none interactively.
tmp = with_meta({**blank, "categories": ["Old"]})
m.apply_meta_flags(BOOK, "T", "", "A", "", "")
e = json.loads(tmp.read_text())[SLUG]
assert e["categories"] == [], e

# 3. Numbers resolve against the site's existing categories, same as ask_categories().
tmp = with_meta(blank)
other_slug = "other-book"
meta = json.loads(tmp.read_text())
meta[other_slug] = {**blank, "categories": ["Business", "Data"]}
tmp.write_text(json.dumps(meta))
m.apply_meta_flags(BOOK, "T", "", "A", "", "1,New")
e = json.loads(tmp.read_text())[SLUG]
assert e["categories"] == ["Business", "New"], e

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
