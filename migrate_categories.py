#!/usr/bin/env python3
"""One-off (2026-10-08): move every published book from the old free-typed category
names to subgenre ids from categories.json. Safe to re-run. A book not listed here is
left alone and reported — new books pick from the list at publish time instead."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# title_en (as in books.meta.json) -> subgenre ids, first = primary
ASSIGN = {
    "Moving the Needle with Lean OKRs": ["management-leadership", "strategy-performance"],
    "Key Performance Indicators": ["strategy-performance", "management-leadership"],
    "good to great": ["management-leadership", "strategy-performance"],
    "Lean Analytic": ["startups-entrepreneurship", "data-science-analytics"],
    "Naked Statistics": ["statistics-mathematics"],
    "Exploratory Data Analysis": ["statistics-mathematics", "data-science-analytics"],
    "Introductory Econometrics for Finance": ["finance-investing", "statistics-mathematics"],
    "Die with Zero": ["personal-finance", "life-design"],
    "The Constitution of Liberty": ["political-theory", "economics"],
    "The Narrow Corridor": ["democracy-authoritarianism", "economics"],
    "Autocracy Inc  The Dictators Who Want to Run the World": ["democracy-authoritarianism"],
    "The Open Society and Its Enemies": ["political-theory", "philosophy"],
    "The Psychology of Totalitarianism": ["democracy-authoritarianism", "psychology"],
    "Honeybee Democracy": ["nature-life-sciences"],
    "FOOD": ["food-health"],
    "Thinking in Systems": ["systems-complexity", "thinking-decisions"],
    "Cloud Native Database": ["databases-data-systems"],
    "Designing Data Intensive Applications": ["databases-data-systems", "software-engineering"],
    "Database Anonymization": ["privacy-security", "databases-data-systems"],
    "Learning Domain-Driven Design": ["software-engineering"],
    "Show Your Work!": ["creativity", "productivity-career"],
}


def main() -> int:
    meta_file = HERE / "books.meta.json"
    meta = json.loads(meta_file.read_text())
    valid = {s["id"] for g in json.loads((HERE / "categories.json").read_text())["groups"]
             for s in g["subs"]}
    bad = {t: [i for i in ids if i not in valid] for t, ids in ASSIGN.items()
           if any(i not in valid for i in ids)}
    if bad:
        sys.exit(f"ids not in categories.json: {bad}")
    by_title = {e.get("title_en"): e for e in meta.values()}
    missing = [t for t in ASSIGN if t not in by_title]
    for title, ids in ASSIGN.items():
        if title in by_title:
            by_title[title]["categories"] = ids
    left = [e["title_en"] for e in meta.values() if e.get("title_en") not in ASSIGN]
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(f"updated {len(ASSIGN) - len(missing)} book(s)")
    if missing:
        print(f"  no such title in books.meta.json: {missing}")
    if left:
        print(f"  left alone (not in the mapping): {left}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
