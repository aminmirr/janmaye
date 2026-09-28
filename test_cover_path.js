/* cleanCoverPath(), pulled straight out of index.html so it can't drift.
   Run: node test_cover_path.js */
const assert = require("assert");
const fs = require("fs");

const html = fs.readFileSync(__dirname + "/index.html", "utf8");

const grab = (start, end) => {
  const i = html.indexOf(start);
  assert.ok(i > 0, "not found in index.html: " + start);
  const j = html.indexOf(end, i);
  return html.slice(i, j + end.length);
};
const src = grab("const cleanCoverPath =", ";");

const cleanCoverPath = eval(`(${src.slice(src.indexOf("=") + 1, -1)})`);

// The reported incident: a books.meta.json entry hand-edited to wrap the path
// in quotes that were never meant to be part of the value.
assert.strictEqual(
  cleanCoverPath("'covers/designing data-intensive applications.jpg'"),
  "covers/designing data-intensive applications.jpg");

assert.strictEqual(cleanCoverPath('"covers/x.jpg"'), "covers/x.jpg");
assert.strictEqual(cleanCoverPath("  covers/x.jpg  "), "covers/x.jpg");
assert.strictEqual(cleanCoverPath("'  covers/x.jpg  '"), "covers/x.jpg");
assert.strictEqual(cleanCoverPath("'\"covers/x.jpg\"'"), "covers/x.jpg"); // nested, both styles
assert.strictEqual(cleanCoverPath("https://example.com/x.jpg"), "https://example.com/x.jpg");
assert.strictEqual(cleanCoverPath(""), "");
assert.strictEqual(cleanCoverPath(null), "");
assert.strictEqual(cleanCoverPath(undefined), "");

console.log("ok");
