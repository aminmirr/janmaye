/* The desktop bar and the two mobile layouts must keep the same controls in the same
   direction. Static checks against index.html, since there is no browser here.
   Run: node test_player_parity.js */
const assert = require("assert");
const fs = require("fs");
const html = fs.readFileSync(__dirname + "/index.html", "utf8");

const mp = html.slice(html.indexOf('<div id="mplayer"'), html.indexOf("<dialog"));
const exp = mp.slice(mp.indexOf("<!-- EXPANDED -->"), mp.indexOf("<!-- COLLAPSED -->"));
const col = mp.slice(mp.indexOf("<!-- COLLAPSED -->"));
const acts = frag => [...frag.matchAll(/data-act="(\w+)"/g)].map(m => m[1]);

// Transport order is the same RTL order in the expanded and collapsed mobile players
// (they used to mirror each other: back/forward swapped when the sheet collapsed).
const transport = frag => acts(frag).filter(a => ["prev", "back", "toggle", "fwd", "next"].includes(a));
assert.deepStrictEqual(transport(exp), ["prev", "back", "toggle", "fwd", "next"]);
assert.deepStrictEqual(transport(col), ["back", "toggle", "fwd"]);
assert.ok(transport(exp).indexOf("back") < transport(exp).indexOf("fwd"), "back precedes forward, as in the collapsed bar");

// Parity: what the desktop bar can do, the mobile sheet can too.
assert.ok(/id="plang"/.test(html) && acts(exp).includes("lang"), "language toggle on both");
assert.ok(acts(exp).includes("share") && acts(exp).includes("download") && acts(exp).includes("speed"));
assert.strictEqual((mp.match(/class="mp-scrub"/g) || []).length, 2, "both mobile progress bars are seekable");
assert.ok(/id="scrub"/.test(html));

// One seek implementation for every bar, and the timeline follows the page direction.
assert.ok(/function bindScrub\(el\)/.test(html) && /\$\$\("\.mp-scrub"\)\.forEach\(bindScrub\)/.test(html));
assert.ok(/inset-inline-start:0; height:100%; width:0; background:#f2a544/.test(html), "mobile fill starts at the inline start (right in RTL)");
assert.ok(!/class="mp-fill" style="[^"]*left:0/.test(html), "no hard-coded left:0 fill");

// Space must not be swallowed while typing.
assert.ok(/TEXTAREA\|SELECT/.test(html) && /isContentEditable/.test(html) && /!dlg\.open/.test(html));
// Closing the player saves the position first.
assert.ok(/function stopPlayer\(\)\{\s*forceRecordProgress\(false\);/.test(html));
console.log("ok");
