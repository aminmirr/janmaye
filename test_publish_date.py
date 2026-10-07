"""stamp_published() and sort_books(): a book's date is when it FIRST went up.
Run: python3 test_publish_date.py"""
import importlib.util
from pathlib import Path

s = importlib.util.spec_from_file_location("bs", Path(__file__).with_name("build_site.py"))
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)

# a new book gets "now"; a re-publish keeps the original date
fresh = {"new": {"title": "New"}, "old": {"title": "Old"}}
m.stamp_published(fresh, {"old": {"published_at": "2026-07-25T19:00:00Z"}}, now="2026-10-07T00:00:00Z")
assert fresh["new"]["published_at"] == "2026-10-07T00:00:00Z", fresh
assert fresh["old"]["published_at"] == "2026-07-25T19:00:00Z", fresh

# an existing entry with no date (pre-feature) gets stamped rather than left blank
fresh = {"x": {"title": "X"}}
m.stamp_published(fresh, {"x": {"title": "X"}}, now="2026-10-07T00:00:00Z")
assert fresh["x"]["published_at"] == "2026-10-07T00:00:00Z"

# no `now` given: a real UTC timestamp
fresh = {"x": {"title": "X"}}
m.stamp_published(fresh, {})
assert fresh["x"]["published_at"].endswith("Z") and len(fresh["x"]["published_at"]) == 20

# newest first, undated last, ties alphabetical
books = [{"title": "B", "published_at": "2026-09-01T00:00:00Z"},
         {"title": "None"},
         {"title": "A", "published_at": "2026-09-01T00:00:00Z"},
         {"title": "New", "published_at": "2026-10-01T00:00:00Z"}]
assert [b["title"] for b in m.sort_books(books)] == ["New", "A", "B", "None"]
print("ok")
