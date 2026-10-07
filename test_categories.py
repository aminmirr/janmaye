"""Categories come from a closed taxonomy (categories.json): groups, each with
subgenres, each with an id and English + Persian names. A book stores subgenre ids.

Free-typing produced the mess this replaced: Data alongside Data Science, lowercase
'computer science', and categories used exactly once.

Run: python3 test_categories.py
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

tax = m.load_taxonomy()
subs = m.flat_subs(tax)

# ── the shipped taxonomy is well-formed ───────────────────────────────────────

ids = [x["id"] for x in subs]
assert len(ids) == len(set(ids)), "subgenre ids are unique"
assert all(x["en"] and x["fa"] for x in subs), "every subgenre has both names"
assert all(g["en"] and g["fa"] and g["subs"] for g in tax["groups"]), "every group too, non-empty"
assert 6 <= len(tax["groups"]) <= 10, "a handful of broad groups, like the big sites"
# flat numbering follows group order and carries the group
assert subs[0]["group"] == tax["groups"][0]["id"] and subs[0]["id"] == tax["groups"][0]["subs"][0]["id"]

# ── every published book's categories exist in it (the migration's contract) ──

live = json.loads(Path(__file__).with_name("books.meta.json").read_text())
assert m.unknown_ids(live, tax) == {}, m.unknown_ids(live, tax)
assert all(1 <= len(e["categories"]) <= m.MAX_CATEGORIES for e in live.values()), \
    "every published book has 1–3 categories"

# ── parsing what you type ─────────────────────────────────────────────────────

econ = next(x for x in subs if x["id"] == "economics")
n_econ = subs.index(econ) + 1

assert m.parse_categories(str(n_econ), subs) == (["economics"], [])
assert m.parse_categories("economics", subs) == (["economics"], [])          # id
assert m.parse_categories("ECONOMICS", subs) == (["economics"], [])          # name, any casing
assert m.parse_categories("اقتصاد", subs) == (["economics"], [])             # Persian name
assert m.parse_categories(" Finance &  Investing ", subs) == (["finance-investing"], [])
# numbers, ids and names mix; order kept; no repeats
got, bad = m.parse_categories(f"{n_econ}, creativity, اقتصاد", subs)
assert got == ["economics", "creativity"] and bad == [], (got, bad)
# capped at three
got, _ = m.parse_categories("1,2,3,4,5", subs)
assert len(got) == m.MAX_CATEGORIES == 3
# the list is closed: anything else is handed back, never stored
assert m.parse_categories("Brand New, economics", subs) == (["economics"], ["Brand New"])
assert m.parse_categories("999", subs) == ([], ["999"])
assert m.parse_categories("", subs) == ([], [])

# ── stale names are reported ──────────────────────────────────────────────────

assert m.unknown_ids({"a": {"categories": ["Data Science", "economics"]}, "b": {"categories": []}}, tax) \
    == {"a": ["Data Science"]}

# ── usage counts are by id ────────────────────────────────────────────────────

assert m.category_counts({"a": {"categories": ["economics", "creativity"]},
                          "b": {"categories": ["economics"]}, "c": {}}) \
    == {"economics": 2, "creativity": 1}

# ── the prompt ────────────────────────────────────────────────────────────────

def ask(typed, current=()):
    tmp = Path(tempfile.mkdtemp()) / "books.meta.json"
    tmp.write_text("{}")
    m.META = tmp
    sys.stdin = io.StringIO(typed)
    sys.stdout, real = io.StringIO(), sys.stdout
    try:
        return m.ask_categories(list(current), {})
    finally:
        sys.stdout = real

assert ask(f"{n_econ}, creativity\n") == ["economics", "creativity"]
# Enter keeps what the book already had
assert ask("\n", current=["creativity"]) == ["creativity"]
assert ask("\n") == []
# a name that isn't on the list is refused and asked again
assert ask("Brand New\neconomics\n") == ["economics"]

print("ok")
