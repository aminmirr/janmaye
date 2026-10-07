/* Lock-screen / headset controls (Media Session), pulled straight out of index.html
   and run against a fake navigator. Run: node test_media_session.js */
const assert = require("assert");
const fs = require("fs");
const html = fs.readFileSync(__dirname + "/index.html", "utf8");
const a = html.indexOf("/* ---------------- lock-screen / headset controls");
const b = html.indexOf("/* ---------------- end media session ---------------- */");
assert.ok(a > 0 && b > a, "media session block not found");
const src = html.slice(a, b);

function setup({ withApi = true } = {}) {
  const handlers = {};
  const listeners = {};
  const mediaSession = { metadata: null, playbackState: "none", positionState: null,
    setActionHandler(act, fn) { if (act === "bogus") throw new TypeError("unsupported"); handlers[act] = fn; },
    setPositionState(s) { this.positionState = s; } };
  const env = {
    navigator: withApi ? { mediaSession } : {},
    MediaMetadata: class { constructor(o) { Object.assign(this, o); } },
    location: { href: "https://aminmirr.github.io/janmaye/" },
    URL,
    META: { bk: { cover: "covers/x.jpg", author: "Some Author" } },
    cleanCoverPath: r => r,
    queue: [{ slug: "bk", label: "فصل ۱", book: "A Book" }, { slug: "bk", label: "فصل ۲", book: "A Book" }],
    qi: 0, loads: [], stops: 0, fails: 0,
    audio: { duration: 100, currentTime: 20, paused: true, playbackRate: 1.5, plays: 0,
      play() { this.paused = false; this.plays++; return Promise.resolve(); }, pause() { this.paused = true; },
      addEventListener(ev, fn) { (listeners[ev] ||= []).push(fn); } },
  };
  const f = new Function("env", `
    const {navigator,MediaMetadata,location,URL,META,cleanCoverPath,audio}=env;
    const cur=()=>env.queue[env.qi];
    const fail=()=>{env.fails++};
    const stopPlayer=()=>{env.stops++};
    const load=a=>env.loads.push([env.qi,a]);
    const queue=env.queue; let qi=0;
    ${src.replace(/\bqi\b/g, "env.qi")}
    return {msTrack,msPosition,msState,msClear,MS};`);
  return { env, handlers, listeners, mediaSession, api: f(env) };
}

// ── metadata and previous/next availability ───────────────────────────────────
let t = setup();
t.api.msTrack(t.env.queue[0]);
assert.strictEqual(t.mediaSession.metadata.title, "فصل ۱");
assert.strictEqual(t.mediaSession.metadata.album, "A Book");
assert.strictEqual(t.mediaSession.metadata.artist, "Some Author");
assert.strictEqual(t.mediaSession.metadata.artwork[0].src, "https://aminmirr.github.io/janmaye/covers/x.jpg", "cover is an absolute URL");
assert.strictEqual(t.handlers.previoustrack, null, "first episode: no previous button");
assert.strictEqual(typeof t.handlers.nexttrack, "function");
t.env.qi = 1; t.api.msTrack(t.env.queue[1]);
assert.strictEqual(typeof t.handlers.previoustrack, "function");
assert.strictEqual(t.handlers.nexttrack, null, "last episode: no next button");
t.handlers.previoustrack();
assert.deepStrictEqual(t.env.loads.pop(), [0, true], "previous goes back one and plays");

// a book with no cover and no author still gets valid metadata
t = setup(); t.env.META.bk = {};
t.api.msTrack(t.env.queue[0]);
assert.deepStrictEqual(t.mediaSession.metadata.artwork, []);
assert.strictEqual(t.mediaSession.metadata.artist, "");

// ── transport ─────────────────────────────────────────────────────────────────
t = setup();
t.handlers.play(); assert.strictEqual(t.env.audio.plays, 1);
t.handlers.pause(); assert.strictEqual(t.env.audio.paused, true);
t.handlers.seekbackward({}); assert.strictEqual(t.env.audio.currentTime, 5, "default 15 s");
t.handlers.seekbackward({ seekOffset: 99 }); assert.strictEqual(t.env.audio.currentTime, 0, "never below 0");
t.handlers.seekforward({ seekOffset: 30 }); assert.strictEqual(t.env.audio.currentTime, 30, "honours the OS offset");
t.handlers.seekforward(); assert.strictEqual(t.env.audio.currentTime, 45);
t.handlers.seekto({ seekTime: 70 }); assert.strictEqual(t.env.audio.currentTime, 70);
t.handlers.seekto({ seekTime: 999 }); assert.strictEqual(t.env.audio.currentTime, 100, "clamped to the end");
t.handlers.stop(); assert.strictEqual(t.env.stops, 1);

// ── position + state ──────────────────────────────────────────────────────────
t = setup();
t.api.msPosition();
assert.deepStrictEqual(t.mediaSession.positionState, { duration: 100, playbackRate: 1.5, position: 20 });
t.env.audio.duration = NaN; t.mediaSession.positionState = null; t.api.msPosition();
assert.strictEqual(t.mediaSession.positionState, null, "no duration yet: nothing reported");
t.env.audio.duration = Infinity; t.api.msPosition();
assert.strictEqual(t.mediaSession.positionState, null, "a stream with no end: nothing reported");
assert.ok(["loadedmetadata", "seeked", "ratechange", "play", "pause"].every(e => t.listeners[e]), "re-reported when it changes");

t.env.audio.paused = false; t.api.msState(); assert.strictEqual(t.mediaSession.playbackState, "playing");
t.env.audio.paused = true;  t.api.msState(); assert.strictEqual(t.mediaSession.playbackState, "paused");
t.env.qi = -1;              t.api.msState(); assert.strictEqual(t.mediaSession.playbackState, "none", "nothing loaded");
t.env.qi = 0; t.api.msTrack(t.env.queue[0]); t.api.msClear();
assert.strictEqual(t.mediaSession.metadata, null); assert.strictEqual(t.mediaSession.playbackState, "none");

// ── a browser without the API changes nothing ─────────────────────────────────
t = setup({ withApi: false });
assert.strictEqual(t.api.MS, null);
t.api.msTrack(t.env.queue[0]); t.api.msPosition(); t.api.msState(); t.api.msClear();   // must not throw

// an action the browser rejects must not break the rest
t = setup();
t.mediaSession.setActionHandler("play", () => {});
t.api.msTrack(t.env.queue[0]);
console.log("ok");
