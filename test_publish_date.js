/* byNewest and publishedLabel, pulled straight out of index.html so they can't drift.
   Run: node test_publish_date.js */
const assert = require("assert");
const fs = require("fs");
const html = fs.readFileSync(__dirname + "/index.html", "utf8");

const grab = (start, end) => {
  const i = html.indexOf(start);
  assert.ok(i > 0, "not found in index.html: " + start);
  return html.slice(i, html.indexOf(end, i) + end.length);
};
const byNewest = eval(`(${grab("const byNewest =", ";").replace(/^const byNewest =/, "").slice(0, -1)})`);
const publishedLabel = eval(`(${grab("const publishedLabel =", "\n};").replace(/^const publishedLabel =/, "").slice(0, -1)})`);

// newest first; undated sink to the bottom
const sorted = [{ s: "old", published_at: "2026-07-25T19:00:00Z" },
                { s: "none" },
                { s: "new", published_at: "2026-10-04T07:55:56Z" },
                { s: "mid", published_at: "2026-09-12T12:40:16Z" }].sort(byNewest).map(b => b.s);
assert.deepStrictEqual(sorted, ["new", "mid", "old", "none"]);

// Persian calendar: 2026-10-04 is 12 Mehr 1405
const fa = publishedLabel("2026-10-04T07:55:56Z", "fa");
assert.ok(fa.includes("مهر") && fa.includes("۱۴۰۵") && fa.includes("۱۲"), fa);
// the date is read in UTC, so a late-evening UTC time can't slip to the next day
assert.ok(publishedLabel("2026-10-04T23:59:00Z", "fa").includes("۱۲"));
assert.ok(/4 Oct 2026/.test(publishedLabel("2026-10-04T07:55:56Z", "en")));
assert.strictEqual(publishedLabel("", "fa"), "");
assert.strictEqual(publishedLabel(undefined, "en"), "");
assert.strictEqual(publishedLabel("not a date", "fa"), "");
console.log("ok");
