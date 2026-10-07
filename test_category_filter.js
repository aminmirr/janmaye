/* Taxonomy lookups and the group/subgenre filter, pulled straight out of index.html.
   Run: node test_category_filter.js */
const assert = require("assert");
const fs = require("fs");
const html = fs.readFileSync(__dirname + "/index.html", "utf8");
const i = html.indexOf("let TAX =");
assert.ok(i > 0);
const j = html.indexOf("const matchesCat =", i);
const src = html.slice(i, html.indexOf(";\n", html.indexOf("!group ||", j)) + 2);
const mod = { exports: {} };
new Function("module", src + "module.exports={setTaxonomy,catName,catGroup,matchesCat};")(mod);
const { setTaxonomy, catName, catGroup, matchesCat } = mod.exports;

const real = JSON.parse(fs.readFileSync(__dirname + "/categories.json", "utf8"));
setTaxonomy(real);

assert.strictEqual(catName("economics", "fa"), "اقتصاد");
assert.strictEqual(catName("economics", "en"), "Economics");
assert.strictEqual(catGroup("economics"), "money");
assert.strictEqual(catName("old-name", "fa"), "old-name", "unknown id shown as typed");
assert.strictEqual(catGroup("old-name"), undefined);

const book = ["political-theory", "economics"];      // two groups: society + money
assert.ok(matchesCat(book, null, null), "no filter matches everything");
assert.ok(matchesCat(book, "society", null));
assert.ok(matchesCat(book, "money", null), "a book is in every group its subgenres are in");
assert.ok(!matchesCat(book, "technology", null));
assert.ok(matchesCat(book, "money", "economics"));
assert.ok(!matchesCat(book, "money", "personal-finance"), "subgenre must be one the book has");
assert.ok(!matchesCat(book, "society", "economics"), "subgenre must sit inside the chosen group");
assert.ok(!matchesCat([], "money", null));
assert.ok(!matchesCat(["old-name"], "money", null), "stale ids belong to no group");

// the shipped file is well-formed: unique ids, both names everywhere
const ids = real.groups.flatMap(g => g.subs.map(s => s.id));
assert.strictEqual(new Set(ids).size, ids.length, "subgenre ids are unique");
real.groups.forEach(g => { assert.ok(g.id && g.en && g.fa, g.id);
  g.subs.forEach(s => assert.ok(s.id && s.en && s.fa, s.id)); });

// a missing/odd taxonomy file degrades to no categories rather than throwing
setTaxonomy(null);
assert.strictEqual(catName("economics", "fa"), "economics");
console.log("ok");
