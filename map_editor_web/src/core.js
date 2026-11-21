/* RhakMu (라크무) map core: .rkm (J2M) parse/serialize, terrain auto-tiling, resource decoding.
 * Formats reverse-engineered from the original game data (TriggerSoft, 2003).
 */
(function (G) {
  'use strict';

  // ---------------------------------------------------------------- constants
  // DATA\STB\EDITOR\TABLE_TILESETUP.STB
  // name, Min, Max, 0TileNo, 0TileCnt, 15TileNo, 15TileCnt, TileNo, TileCnt, CrossTile, CrossTileCnt, Dir
  const TRANS = [
    ['물-땅', 0, 1, 10, 10, 0, 10, 30, 3, 42, 1, -1],
    ['땅-물', 1, 0, 0, 10, 10, 10, 30, 3, 42, 1, 1],
    ['땅-풀', 1, 2, 20, 10, 10, 10, 52, 2, 60, 1, 1],
    ['풀-땅', 2, 1, 10, 10, 20, 10, 52, 2, 60, 1, -1],
    ['땅-돌', 1, 3, 198, 2, 10, 10, 184, 1, 188, 1, -1],
    ['땅-절벽1', 1, 4, 20, 10, 10, 10, 70, 3, 82, 1, -1],
    ['돌-땅', 3, 1, 10, 10, 198, 2, 184, 1, 188, 1, 1],
    ['절벽1-땅', 4, 1, 10, 10, 20, 10, 70, 3, 82, 1, 1],
    ['2층땅-절벽1', 5, 4, 20, 10, 10, 10, 52, 2, 60, 1, 1],
    ['절벽1-2층땅', 4, 5, 10, 10, 20, 10, 52, 2, 60, 1, -1],
    ['절벽1-절벽2', 4, 6, 20, 10, 20, 10, 92, 3, 104, 1, -1],
    ['절벽2-절벽1', 6, 4, 20, 10, 20, 10, 92, 3, 104, 1, 1],
    ['3층땅-절벽2', 7, 6, 20, 10, 10, 10, 52, 2, 60, 1, 1],
    ['절벽2-3층땅', 6, 7, 10, 10, 20, 10, 52, 2, 60, 1, -1],
    ['절벽2-3층물', 6, 8, 0, 10, 20, 10, 162, 3, 174, 1, 1],
    ['3층물-절벽2', 8, 6, 20, 10, 0, 10, 162, 3, 174, 1, -1],
  ];
  // brush adjacency (99 = may touch directly, otherwise the brush that must sit in between)
  const MID = [
    [99, 99, 1, 1, 1, 1, 1, 1, 1],
    [99, 99, 99, 99, 99, 4, 4, 4, 4],
    [1, 99, 99, 1, 1, 1, 1, 1, 1],
    [1, 99, 1, 99, 1, 1, 1, 1, 1],
    [1, 99, 1, 1, 99, 99, 99, 6, 6],
    [4, 4, 4, 4, 99, 99, 4, 4, 4],
    [4, 4, 4, 4, 99, 4, 99, 99, 99],
    [6, 6, 6, 6, 6, 6, 99, 99, 6],
    [6, 6, 6, 6, 6, 6, 99, 6, 99],
  ];
  const EDGE = [3, 10, 5, 12], CORNER = [2, 1, 8, 4, 7, 14, 11, 13], DIAG = [9, 6];
  // corner bits of a tile record mask: bit set = corner is the transition's Min brush
  const BIT = { E: 1, S: 2, N: 4, W: 8 };

  const TILESETS = [
    { file: 'EAST', name: '늪지', brushes: ['늪지', '황토', '풀밭', '돌 바닥', '2층 절벽', '2층 황토', '3층 절벽', '3층 황토', '3층 늪지'] },
    { file: 'WEST', name: '설원', brushes: ['얼음물', '땅', '설원', '돌 바닥', '2층 절벽', '2층 땅', '3층 절벽', '3층 땅', '3층 얼음물'] },
    { file: 'SAVAGE', name: '유적', brushes: ['진흙땅', '황토', '대리석 바닥', '돌 바닥', '2층 성벽', '2층 황토', '3층 성벽', '3층 황토', '3층 진흙땅'] },
    { file: 'DUNGEON', name: '던전', brushes: ['용암', '동굴 바닥', '동굴 돌바닥', '구조토', '2층 절벽', '2층 돌바닥', '3층 절벽', '3층 돌바닥', '3층 용암'] },
  ];
  // DATA\STB\EDITOR\SPECIAL_OBJECT.STB : trees, decorations, well, gold mine (ids per tileset)
  const DECOR = [
    { trees: 10, decos: 10 }, // 0 늪지: well 20, gold 21
    { trees: 10, decos: 7 },  // 1 설원: well 17, gold 18
    { trees: 10, decos: 7 },  // 2 유적: well 17, gold 18
    { trees: 0, decos: 10 },  // 3 던전: well 10, gold 11
  ];
  function decorList(ts) {
    const d = DECOR[ts] || DECOR[0], out = [];
    for (let i = 0; i < d.trees; i++) out.push({ id: i, name: '나무-' + (i + 1) });
    for (let i = 0; i < d.decos; i++) out.push({ id: d.trees + i, name: '장식물-' + (i + 1) });
    return out;
  }
  function resourceIds(ts) { const d = DECOR[ts] || DECOR[0]; const w = d.trees + d.decos; return { well: w, gold: w + 1 }; }
  const SUBTERRAIN = ['왼편 다리', '오른편 다리', '왼쪽 2층 언덕 입구', '오른쪽 2층 언덕 입구', '왼쪽 3층 언덕 입구', '오른쪽 3층 언덕 입구', '왼쪽 폭포 (큰언덕)', '오른쪽 폭포 (큰언덕)',
    '왼쪽 2층 언덕 입구 (상하대칭)', '오른쪽 2층 언덕 입구 (상하대칭)', '왼쪽 3층 언덕 입구 (상하대칭)', '오른쪽 3층 언덕 입구 (상하대칭)'];
  // ids 8-11 are added by the flip mod (Data\\tile\\*.jtl / *_Bridge.brg next to the game); the original game has only 0-7
  const SUB_MOD_FROM = 8;
  const RACES = ['무휼', '아렌', '마르두크'];
  const COLORS = [['빨강', '#e02020'], ['파랑', '#2060ff'], ['주황', '#ff9020'], ['검정', '#303030'], ['하양', '#f0f0f0'], ['노랑', '#f0e020'], ['보라', '#a040e0'], ['초록', '#20c040']];
  const KIND = { SUB: 3, DECO: 5, RES: 7 };
  const SEC6_DEFAULT_B64 = '__SEC6__';

  // ------------------------------------------------------------- tile tables
  function tilesFor(a, b) {
    const r = TRANS[a]; if (!r) return [];
    const m = r[11] === 1 ? b : 15 - b, out = [];
    const rng = (s, n) => { for (let i = 0; i < n; i++) out.push(s + i); return out; };
    if (b === 0) return rng(r[3], r[4]);
    if (b === 15) return rng(r[5], r[6]);
    let i = EDGE.indexOf(m); if (i >= 0) return rng(r[7] + i * r[8], r[8]);
    i = CORNER.indexOf(m); if (i >= 0) return rng(r[9] + i * r[10], r[10]);
    i = DIAG.indexOf(m); if (i >= 0) return [r[9] + 8 * r[10] + i];
    return out;
  }
  // reverse: tile index -> [a,b] that produces it (first match), used by manual tile stamping
  const TILE_DEF = (() => {
    const def = {};
    for (let a = 0; a < TRANS.length; a++) for (let b = 0; b < 16; b++)
      for (const t of tilesFor(a, b)) if (!(t in def)) def[t] = [a, b];
    return def;
  })();
  function cornersOf(a, b) {
    const r = TRANS[a] || TRANS[0];
    return { E: b & 1 ? r[1] : r[2], S: b & 2 ? r[1] : r[2], N: b & 4 ? r[1] : r[2], W: b & 8 ? r[1] : r[2] };
  }
  function compat(p, q) { return MID[p][q] === 99; }
  // choose a transition row for a set of corner brushes; returns {a,b,c} or null
  function recordFor(E, S, N, W) {
    const ts = [E, S, N, W];
    const uniq = [...new Set(ts)];
    if (uniq.length === 1) {
      const T = uniq[0];
      let a = TRANS.findIndex(r => r[1] === T && r[11] === 1);
      if (a < 0) a = TRANS.findIndex(r => r[1] === T);
      return a < 0 ? null : { a, b: 15, c: T };
    }
    if (uniq.length !== 2) return null;
    const [p, q] = uniq;
    let a = TRANS.findIndex(r => r[1] === p && r[2] === q && r[11] === 1);
    if (a < 0) a = TRANS.findIndex(r => r[1] === q && r[2] === p && r[11] === 1);
    if (a < 0) a = TRANS.findIndex(r => (r[1] === p && r[2] === q) || (r[1] === q && r[2] === p));
    if (a < 0) return null;
    const mn = TRANS[a][1], mx = TRANS[a][2];
    const b = (E === mn ? 1 : 0) | (S === mn ? 2 : 0) | (N === mn ? 4 : 0) | (W === mn ? 8 : 0);
    let pc = 0; for (let i = 0; i < 4; i++) if (b & (1 << i)) pc++;
    return { a, b, c: pc >= 2 ? mn : mx };
  }

  // ---------------------------------------------------------------- binary io
  const u16 = (d, o) => d[o] | (d[o + 1] << 8);
  const u32 = (d, o) => (d[o] | (d[o + 1] << 8) | (d[o + 2] << 16) | (d[o + 3] << 24)) >>> 0;
  const w16 = (d, o, v) => { d[o] = v & 255; d[o + 1] = (v >> 8) & 255; };
  const w32 = (d, o, v) => { d[o] = v & 255; d[o + 1] = (v >>> 8) & 255; d[o + 2] = (v >>> 16) & 255; d[o + 3] = (v >>> 24) & 255; };

  function cp949Decode(bytes) {
    try { return new TextDecoder('euc-kr').decode(bytes); } catch (e) { return String.fromCharCode(...bytes); }
  }
  // names are ASCII in all shipped maps; non-ASCII typed by the user is stored as '?'
  function asciiBytes(s, n) {
    const out = new Uint8Array(n);
    for (let i = 0; i < Math.min(s.length, n - 1); i++) { const c = s.charCodeAt(i); out[i] = c < 128 ? c : 63; }
    return out;
  }

  // ------------------------------------------------------------------ parsing
  // File layout: "J2M\0", u32 count, u32 0, then count × (u32 id, u32 offset). Sections are read by id:
  // 0 map info, 1 teams/players, 2 tiles, 3 objects, 4 triggers, 5 settings, 6 markers, 7 tail(16 bytes)
  function parseRKM(buf) {
    const d = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
    if (d[0] !== 0x4a || d[1] !== 0x32 || d[2] !== 0x4d) throw new Error('라크무 맵 파일(J2M)이 아닙니다');
    const n = u32(d, 4), ents = [];
    for (let i = 0; i < n; i++) ents.push({ id: u32(d, 12 + i * 8), off: u32(d, 16 + i * 8) });
    const hdrEnd = 12 + n * 8;
    let raw = {}, repaired = false;
    if (ents.some(e => e.off < hdrEnd || e.off > d.length)) {
      // files written by editor v1 had a 72-byte header (wrong section-7 offset): recover them
      if (n === 8 && u32(d, 8) === 0 && u32(d, 12) === 0 && u32(d, 16) === 72) {
        const o = []; for (let i = 1; i <= 7; i++) o.push(u32(d, 8 + i * 8));
        o.push(d.length);
        for (let i = 0; i < 6; i++) raw[i] = d.slice(o[i], o[i + 1]);
        const t = d.slice(o[6]), k = u32(t, 0), ml = Math.min(t.length, 4 + k * 12);
        raw[6] = t.slice(0, ml); raw[7] = t.length - ml >= 16 ? t.slice(ml, ml + 16) : new Uint8Array(16);
        ents.forEach((e, i) => e.id = i); repaired = true;
      } else throw new Error('섹션 오프셋이 잘못된 파일입니다');
    } else {
      const sorted = ents.slice().sort((x, y) => x.off - y.off);
      sorted.forEach((e, i) => { raw[e.id] = d.slice(e.off, i + 1 < sorted.length ? sorted[i + 1].off : d.length); });
    }
    for (let i = 0; i <= 7; i++) if (!raw[i]) throw new Error('섹션 ' + i + ' 없음');
    const sec = { 1: raw[0], 2: raw[1], 3: raw[2], 4: raw[3], 5: raw[4], 6: raw[5], 7: raw[6] };
    const hdrUnk = u32(d, 8);
    const s1 = sec[1];
    const m = {
      secOrder: ents.map(e => e.id), hdrUnk, s8: raw[7], repaired,
      s1: s1.slice(),
      tileset: u32(s1, 0), W: u16(s1, 8), H: u16(s1, 10), maxPlayers: s1[13] || 2,
    };
    m.cw = Math.ceil(m.W / 8); m.ch = m.H >> 1;
    // section 2: 8 teams (id + 32 byte name) + players (24 bytes)
    const s2 = sec[2];
    m.teams = [];
    for (let i = 0; i < 8; i++) {
      const o = i * 33, nb = s2.slice(o + 1, o + 33); let z = nb.indexOf(0); if (z < 0) z = 32;
      m.teams.push({ id: s2[o], name: cp949Decode(nb.slice(0, z)), raw: s2.slice(o, o + 33) });
    }
    m.players = [];
    const np = Math.floor((s2.length - 264) / 24);
    for (let i = 0; i < np; i++) {
      const o = 264 + i * 24, r = s2.slice(o, o + 24);
      m.players.push({ raw: r, flags: r[1], race: r[2], team: r[4], x: u16(r, 6), y: u16(r, 8), gold: u32(r, 12), water: u32(r, 16), res3: u32(r, 20) });
    }
    m.s2tail = s2.slice(264 + np * 24);
    // section 3: tiles
    const s3 = sec[3], nt = Math.floor(s3.length / 5);
    if (nt !== m.cw * m.ch) { // tolerate odd sizes
      m.cw = Math.ceil(m.W / 8); m.ch = Math.floor(nt / m.cw);
    }
    m.tIdx = new Uint16Array(m.cw * m.ch); m.tA = new Uint8Array(m.cw * m.ch); m.tB = new Uint8Array(m.cw * m.ch); m.tC = new Uint8Array(m.cw * m.ch);
    for (let i = 0; i < m.cw * m.ch; i++) { m.tIdx[i] = u16(s3, i * 5); m.tA[i] = s3[i * 5 + 2]; m.tB[i] = s3[i * 5 + 3]; m.tC[i] = s3[i * 5 + 4]; }
    m.s3tail = s3.slice(m.cw * m.ch * 5);
    // section 4: objects
    const s4 = sec[4];
    m.s4lead = u32(s4, 0);
    const no = u32(s4, 4);
    m.objects = [];
    for (let i = 0; i < no; i++) {
      const r = s4.slice(8 + i * 20, 28 + i * 20);
      m.objects.push({ raw: r, kind: r[2], id: u16(r, 4), sub: r[6], x: u32(r, 8), y: u32(r, 12), val: u32(r, 16) });
    }
    m.s4tail = s4.slice(8 + no * 20);
    m.s5 = sec[5]; m.s6 = sec[6]; m.s7 = sec[7];
    // section 7: list of (x,y,type) markers (meaning not fully known, preserved)
    m.marks = [];
    if (m.s7.length >= 4) {
      const k = u32(m.s7, 0);
      if (4 + k * 12 <= m.s7.length) for (let i = 0; i < k; i++) m.marks.push({ x: u32(m.s7, 4 + i * 12), y: u32(m.s7, 8 + i * 12), t: u32(m.s7, 12 + i * 12) });
    }
    initVerts(m);
    return m;
  }

  // -------------------------------------------------------------- serializing
  function serializeRKM(m) {
    const s1 = m.s1.slice();
    w32(s1, 0, m.tileset); w16(s1, 8, m.W); w16(s1, 10, m.H); s1[13] = m.maxPlayers;
    const s2 = new Uint8Array(264 + m.players.length * 24 + m.s2tail.length);
    m.teams.forEach((t, i) => {
      const r = t.raw.slice(); r[0] = t.id;
      if (t._dirty) { r.fill(0, 1, 33); r.set(asciiBytes(t.name, 32), 1); }
      s2.set(r, i * 33);
    });
    m.players.forEach((p, i) => {
      const r = p.raw.slice();
      r[1] = p.flags; r[2] = p.race; r[4] = p.team; w16(r, 6, p.x); w16(r, 8, p.y); w32(r, 12, p.gold); w32(r, 16, p.water); w32(r, 20, p.res3);
      s2.set(r, 264 + i * 24);
    });
    s2.set(m.s2tail, 264 + m.players.length * 24);
    const nt = m.cw * m.ch, s3 = new Uint8Array(nt * 5 + m.s3tail.length);
    for (let i = 0; i < nt; i++) { w16(s3, i * 5, m.tIdx[i]); s3[i * 5 + 2] = m.tA[i]; s3[i * 5 + 3] = m.tB[i]; s3[i * 5 + 4] = m.tC[i]; }
    s3.set(m.s3tail, nt * 5);
    const s4 = new Uint8Array(8 + m.objects.length * 20 + m.s4tail.length);
    w32(s4, 0, m.s4lead); w32(s4, 4, m.objects.length);
    m.objects.forEach((o, i) => {
      const r = o.raw.slice(); r[2] = o.kind; w16(r, 4, o.id); r[6] = o.sub; w32(r, 8, o.x); w32(r, 12, o.y); w32(r, 16, o.val);
      s4.set(r, 8 + i * 20);
    });
    s4.set(m.s4tail, 8 + m.objects.length * 20);
    const order = m.secOrder || [0, 1, 2, 3, 4, 5, 6, 7];
    const body = { 0: s1, 1: s2, 2: s3, 3: s4, 4: m.s5, 5: m.s6, 6: m.s7, 7: m.s8 };
    let off = 12 + order.length * 8; const offs = {};
    for (const id of order) { offs[id] = off; off += body[id].length; }
    const out = new Uint8Array(off);
    out.set([0x4a, 0x32, 0x4d, 0]); w32(out, 4, order.length); w32(out, 8, m.hdrUnk || 0);
    order.forEach((id, i) => { w32(out, 12 + i * 8, id); w32(out, 16 + i * 8, offs[id]); });
    for (const id of order) out.set(body[id], offs[id]);
    return out;
  }

  function b64(s) { if (typeof atob === 'function') return Uint8Array.from(atob(s), c => c.charCodeAt(0)); return new Uint8Array(Buffer.from(s, 'base64')); }

  function newMap(opt) {
    const W = opt.W, H = opt.H, ts = opt.tileset, np = opt.players;
    const m = { secOrder: [0, 1, 2, 3, 4, 5, 6, 7], tileset: ts, W, H, maxPlayers: np, cw: Math.ceil(W / 8), ch: H >> 1 };
    m.s1 = new Uint8Array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, np, 0xcc, 0, 0, 0xcc, 0xcc, 0xcc]);
    m.teams = [];
    for (let i = 0; i < 8; i++) { const raw = new Uint8Array(33); raw[0] = i; raw.set(asciiBytes('Team-' + (i + 1), 32), 1); m.teams.push({ id: i, name: 'Team-' + (i + 1), raw }); }
    m.players = [];
    for (let i = 0; i < np; i++) {
      const raw = new Uint8Array(24); raw[0] = i; raw[1] = 0x20; raw[5] = 0; raw[3] = 0; raw[10] = 0; raw[11] = 0;
      const ang = (i / np) * Math.PI * 2;
      m.players.push({ raw, flags: 0x20, race: i % 3, team: i, x: Math.round(W / 2 + Math.cos(ang) * W * 0.35), y: Math.round(H / 2 + Math.sin(ang) * H * 0.35), gold: 300, water: 500, res3: 50 });
    }
    m.s2tail = new Uint8Array(0);
    const nt = m.cw * m.ch;
    m.tIdx = new Uint16Array(nt); m.tA = new Uint8Array(nt); m.tB = new Uint8Array(nt); m.tC = new Uint8Array(nt);
    m.s3tail = new Uint8Array(0);
    m.s4lead = 0; m.objects = []; m.s4tail = new Uint8Array(0);
    m.hdrUnk = 0;
    m.s5 = new Uint8Array(2); m.s6 = b64(SEC6_DEFAULT_B64); m.s7 = new Uint8Array(4); m.s8 = new Uint8Array(16); m.marks = [];
    initVerts(m, opt.base == null ? 1 : opt.base);
    for (let y = 0; y < m.ch; y++) for (let x = 0; x < m.cw; x++) retile(m, x, y, true);
    return m;
  }

  // ------------------------------------------------------------ vertex model
  // Tiles are 256x128 diamonds in a staggered layout: tile (x,y) centre = (x*256 + (y&1)*128, y*64).
  // Corners live on a lattice (u*128, v*64), u+v odd. Tile corners: N(u,y-1) E(u+1,y) S(u,y+1) W(u-1,y), u=2x+(y&1).
  function initVerts(m, fill) {
    m.VW = 2 * m.cw + 3; m.VH = m.ch + 2;
    m.vert = new Int8Array(m.VW * m.VH).fill(fill == null ? -1 : fill);
    if (fill != null) return;
    for (let y = 0; y < m.ch; y++) for (let x = 0; x < m.cw; x++) {
      const i = y * m.cw + x, c = cornersOf(m.tA[i], m.tB[i]), u = 2 * x + (y & 1);
      setV(m, u, y - 1, c.N, true); setV(m, u + 1, y, c.E, true); setV(m, u, y + 1, c.S, true); setV(m, u - 1, y, c.W, true);
    }
    for (let i = 0; i < m.vert.length; i++) if (m.vert[i] < 0) m.vert[i] = 1;
  }
  function vIndex(m, u, v) { const a = u + 1, b = v + 1; return (a < 0 || b < 0 || a >= m.VW || b >= m.VH) ? -1 : b * m.VW + a; }
  function getV(m, u, v) { const i = vIndex(m, u, v); return i < 0 ? -1 : m.vert[i]; }
  function setV(m, u, v, t, onlyIfUnset) { const i = vIndex(m, u, v); if (i < 0) return; if (onlyIfUnset && m.vert[i] >= 0) return; m.vert[i] = t; }
  function tileCorners(m, x, y) {
    const u = 2 * x + (y & 1);
    return { N: getV(m, u, y - 1), E: getV(m, u + 1, y), S: getV(m, u, y + 1), W: getV(m, u - 1, y) };
  }
  // tiles that use vertex (u,v) as a corner
  function tilesOfVertex(m, u, v) {
    const out = [];
    const add = (base, row) => { if (row < 0 || row >= m.ch) return; const b = base - (row & 1); if (b & 1) return; const x = b >> 1; if (x >= 0 && x < m.cw) out.push([x, row]); };
    add(u, v + 1); add(u, v - 1); add(u - 1, v); add(u + 1, v);
    return out;
  }
  function hash(x, y) { let h = (x * 374761393 + y * 668265263) | 0; h = (h ^ (h >>> 13)) * 1274126177; return (h ^ (h >>> 16)) >>> 0; }

  // recompute tile (x,y) from its corners. Returns true if changed.
  function retile(m, x, y, force) {
    const i = y * m.cw + x, c = tileCorners(m, x, y);
    if (c.N < 0 || c.E < 0 || c.S < 0 || c.W < 0) return false;
    const r = recordFor(c.E, c.S, c.N, c.W);
    if (!r) return false;
    const cur = cornersOf(m.tA[i], m.tB[i]);
    if (!force && cur.N === c.N && cur.E === c.E && cur.S === c.S && cur.W === c.W && tilesFor(m.tA[i], m.tB[i]).includes(m.tIdx[i])) return false;
    const list = tilesFor(r.a, r.b);
    if (!list.length) return false;
    m.tIdx[i] = list[hash(x, y) % list.length]; m.tA[i] = r.a; m.tB[i] = r.b; m.tC[i] = r.c;
    return true;
  }

  // rotated lattice coords: A=(u+v-1)/2, B=(u-v-1)/2 -> tile corners form unit squares in (A,B)
  const toAB = (u, v) => [(u + v - 1) >> 1, (u - v - 1) >> 1];
  const fromAB = (A, B) => [A + B + 1, A - B];

  // vertices (as [A,B]) covered by a brush shape
  function shapeVerts(m, shape) {
    const out = new Map(), add = (A, B) => { const [u, v] = fromAB(A, B); if (vIndex(m, u, v) >= 0) out.set(A + ',' + B, [A, B]); };
    const circle = (u, v, s) => {
      const [A0, B0] = toAB(u, v);
      if (s <= 1) { add(A0, B0); return; }
      const r = s / 2, R = Math.ceil(r);
      for (let dA = -R; dA <= R; dA++) for (let dB = -R; dB <= R; dB++) if ((dA + 0.5) * (dA + 0.5) + (dB + 0.5) * (dB + 0.5) <= r * r + 0.5) add(A0 + dA, B0 + dB);
    };
    if (shape.type === 'square') {
      const [A0, B0] = toAB(shape.u, shape.v), lo = -Math.floor((shape.size - 1) / 2), hi = Math.ceil((shape.size - 1) / 2);
      for (let dA = lo; dA <= hi; dA++) for (let dB = lo; dB <= hi; dB++) add(A0 + dA, B0 + dB);
    } else if (shape.type === 'circle') circle(shape.u, shape.v, shape.size);
    else if (shape.type === 'rect') { // screen-aligned rectangle in world pixels
      const x0 = Math.min(shape.x0, shape.x1), x1 = Math.max(shape.x0, shape.x1), y0 = Math.min(shape.y0, shape.y1), y1 = Math.max(shape.y0, shape.y1);
      for (let v = Math.floor(y0 / 64); v <= Math.ceil(y1 / 64); v++) for (let u = Math.floor(x0 / 128); u <= Math.ceil(x1 / 128); u++) {
        if (((u + v) & 1) === 0) continue; const X = u * 128, Y = v * 64;
        if (X >= x0 - 64 && X <= x1 + 64 && Y >= y0 - 32 && Y <= y1 + 32) { const [A, B] = toAB(u, v); add(A, B); }
      }
    } else if (shape.type === 'line') { // thick polyline in world pixels
      const pts = shape.pts;
      for (let i = 0; i < pts.length; i++) {
        const a = pts[i], b = pts[i + 1] || pts[i], len = Math.hypot(b.x - a.x, b.y - a.y), steps = Math.max(1, Math.ceil(len / 48));
        for (let k = 0; k <= steps; k++) {
          const x = a.x + (b.x - a.x) * k / steps, y = a.y + (b.y - a.y) * k / steps;
          const u0 = Math.round(x / 128), v0 = Math.round(y / 64); let best = null, bd = 9;
          for (let u = u0 - 1; u <= u0 + 1; u++) for (let v = v0 - 1; v <= v0 + 1; v++) { if (((u + v) & 1) === 0) continue; const dd = Math.abs(x - u * 128) / 128 + Math.abs(y - v * 64) / 64; if (dd < bd) { bd = dd; best = [u, v]; } }
          if (best) circle(best[0], best[1], shape.size);
        }
      }
    }
    return [...out.values()];
  }

  // paint brush T on the given vertex set; neighbours that cannot touch get the intermediate brush
  function paintVerts(m, list, T) {
    const fixed = new Set(), queue = [], changedV = [];
    const key = (A, B) => A + ',' + B;
    for (const [A, B] of list) {
      const [uu, vv] = fromAB(A, B), i = vIndex(m, uu, vv); if (i < 0) continue;
      if (m.vert[i] !== T) { changedV.push([i, m.vert[i]]); m.vert[i] = T; }
      fixed.add(key(A, B)); queue.push([A, B]);
    }
    let guard = 0, head = 0;
    while (head < queue.length && guard++ < 400000) {
      const [A, B] = queue[head++], [pu, pv] = fromAB(A, B), tp = getV(m, pu, pv);
      for (let dA = -1; dA <= 1; dA++) for (let dB = -1; dB <= 1; dB++) {
        if (!dA && !dB) continue;
        const nA = A + dA, nB = B + dB, k = key(nA, nB);
        if (fixed.has(k)) continue;
        const [nu, nv] = fromAB(nA, nB), ni = vIndex(m, nu, nv);
        if (ni < 0) continue;
        const tn = m.vert[ni];
        if (compat(tp, tn)) continue;
        changedV.push([ni, tn]); m.vert[ni] = MID[tp][tn]; fixed.add(k); queue.push([nA, nB]);
      }
    }
    return changedV;
  }
  // Shipped maps almost never use the diagonal masks (6/9: two opposite corners). After painting, turn such
  // checkerboard tiles into a normal edge/corner by giving the minority pair the painted brush (or the majority).
  // thin (벽 모드): 칠한 브러시 쌍(T)을 잇는 체크무늬는 반대쪽 두 꼭짓점이 아니라 하나만 칠해 모서리 타일로 만든다.
  //   왼쪽·오른쪽·위로 한 칸씩 이어 그릴 때 두 꼭짓점을 다 칠하면 2x2 덩어리가 되어 벽이 두꺼워진다.
  function smoothDiagonals(m, changed, T, thin) {
    const extra = [];
    for (let round = 0; round < 6; round++) {
      const seen = new Set(), fix = [];
      for (const [vi] of changed.concat(extra)) {
        const u = (vi % m.VW) - 1, v = Math.floor(vi / m.VW) - 1;
        for (const [x, y] of tilesOfVertex(m, u, v)) {
          const k = y * m.cw + x; if (seen.has(k)) continue; seen.add(k);
          const c = tileCorners(m, x, y);
          if (c.N === c.S && c.E === c.W && c.N !== c.E && c.N >= 0 && c.E >= 0) {
            const bu = 2 * x + (y & 1);
            const keepNS = c.N === T || (c.E !== T && HEIGHT_OF(c.N) >= HEIGHT_OF(c.E));
            const tt = keepNS ? c.N : c.E;
            const other = keepNS ? [[bu + 1, y], [bu - 1, y]] : [[bu, y - 1], [bu, y + 1]];
            fix.push([tt, thin && tt === T ? [pickThin(m, other, T)] : other]);
          }
        }
      }
      if (!fix.length) break;
      for (const [tt, vs] of fix) {
        const list = vs.map(([uu, vv]) => toAB(uu, vv));
        for (const r of paintVerts(m, list, tt)) extra.push(r);
      }
    }
    return extra;
  }
  // 벽 모드에서 체크무늬를 메울 꼭짓점 하나: 이미 같은 브러시 이웃이 더 많은 쪽 (같으면 첫째 = 아래/오른쪽)
  function pickThin(m, pair, T) {
    let best = pair[0], bn = -1;
    for (const [uu, vv] of pair) {
      let n = 0;
      for (const [du, dv] of [[0, -2], [2, 0], [0, 2], [-2, 0], [1, -1], [1, 1], [-1, 1], [-1, -1]]) if (getV(m, uu + du, vv + dv) === T) n++;
      if (n > bn) { bn = n; best = [uu, vv]; }
    }
    return best;
  }
  function HEIGHT_OF(t) { return [0, 1, 1, 1, 2, 2, 3, 3, 3][t] || 0; }
  function paint(m, u, v, T, s) { const ch = paintVerts(m, shapeVerts(m, { type: 'square', u, v, size: s }), T); return ch.concat(smoothDiagonals(m, ch, T)); }

  // terrain "level" of a brush: 0 water, 1 ground, 2 = level-2 plateau, 3 = level-3 plateau, -1 cliff band
  const LEVEL = [0, 1, 1, 1, -1, 2, -2, 3, 3];
  // buildable = flat ground of any level (not water, not cliff bands)
  const BUILDABLE = [false, true, true, true, true, true, true, true, false];
  const HEIGHT = [0, 1, 1, 1, 2, 2, 3, 3, 3];
  function tileAtWorld(m, wx, wy) {
    const y0 = Math.floor(wy / 64); let best = null, bd = 9;
    for (let y = y0 - 1; y <= y0 + 2; y++) {
      if (y < 0 || y >= m.ch) continue;
      const off = (y & 1) * 128, x0 = Math.round((wx - off) / 256);
      for (let x = x0 - 1; x <= x0 + 1; x++) {
        if (x < 0 || x >= m.cw) continue;
        const d = Math.abs(wx - (x * 256 + off)) / 128 + Math.abs(wy - y * 64) / 64;
        if (d < bd) { bd = d; best = [x, y]; }
      }
    }
    return best;
  }
  // Game cells vs. this editor's world pixels.
  // The game lays terrain record (col,row) over cells X..X+7, Y..Y+3 with X = col*8 + (row&1)*4, Y = row*2
  // (0040B580 -> 0040B6F0; bridges 0040BDD0 use the same anchor), so the tile diamond is centred on cell
  // (X+4, Y+2). Resources, decorations and start points sit at pixel (x*32, y*32) of that cell grid (00439E60).
  // This editor draws the tile diamond centred on world (X*32, Y*32), i.e. 4 cells left and 2 cells up, so a
  // record cell (x,y) is drawn at world (x*32 - 128, y*32 - 64). Bridges/ramps (kind 3) keep their own
  // shipped-map templates and are not converted.
  const CELL_OX = -128, CELL_OY = -64;
  const cellX = x => x * 32 + CELL_OX, cellY = y => y * 32 + CELL_OY;
  const worldCell = (wx, wy) => [Math.floor((wx - CELL_OX) / 32), Math.floor((wy - CELL_OY) / 32)];
  function cellBuildable(m, cx, cy) {
    if (cx < 0 || cy < 0 || cx >= m.W || cy >= m.H) return false;
    const t = tileAtWorld(m, cellX(cx) + 16, cellY(cy) + 16); if (!t) return false;
    const c = tileCorners(m, t[0], t[1]);
    return BUILDABLE[c.N] && BUILDABLE[c.E] && BUILDABLE[c.S] && BUILDABLE[c.W] &&
      HEIGHT[c.N] === HEIGHT[c.E] && HEIGHT[c.N] === HEIGHT[c.S] && HEIGHT[c.N] === HEIGHT[c.W];
  }
  function cellWater(m, cx, cy) {
    const t = tileAtWorld(m, cellX(cx) + 16, cellY(cy) + 16); if (!t) return false;
    const c = tileCorners(m, t[0], t[1]), w = x => x === 0 || x === 8;
    return w(c.N) && w(c.E) && w(c.S) && w(c.W);
  }
  // start position needs room for the main building (about 7x7 cells)
  const START_R = 3;
  function startProblems(m, x, y) {
    let bad = 0;
    for (let dy = -START_R; dy <= START_R; dy++) for (let dx = -START_R; dx <= START_R; dx++) if (!cellBuildable(m, x + dx, y + dy)) bad++;
    return bad;
  }
  // nearest position (spiral search) where the main building fits
  function nearestStart(m, x, y) {
    for (let r = 0; r < 40; r++) for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) !== r) continue;
      const X = x + dx, Y = y + dy; if (X < 4 + START_R || Y < 4 + START_R || X >= m.W - 4 - START_R || Y >= m.H - 4 - START_R) continue;
      if (!startProblems(m, X, Y)) return [X, Y];
    }
    return null;
  }
  // Bridges / hill entrances / waterfalls are anchored on the vertex lattice and need an exact terrain shape under them.
  // Templates learnt from all 24 shipped maps: [dx, dy, class] of vertices around the anchor (px).
  // class: 0 water, 1 ground (level 1), 2 level-2 plateau (incl. cliff band), 3 level-3, 4 high water
  const SUB_CLASS = [0, 1, 1, 1, 2, 2, 3, 3, 4];
  const SUB_TPL = {"0":[[-128,0,0],[-128,128,1],[-128,256,1],[-128,384,1],[0,-64,0],[0,64,0],[0,192,1],[0,320,1],[128,0,0],[128,128,0],[128,256,1],[128,384,1],[256,-64,1],[256,64,0],[256,192,0],[384,0,1],[384,128,0],[384,256,0],[512,-64,1],[512,64,1],[512,192,0],[512,320,0],[640,0,1],[640,256,0]],"1":[[-128,-64,1],[-128,64,1],[-128,192,0],[-128,320,0],[0,0,1],[0,128,0],[0,256,0],[128,-64,1],[128,64,0],[128,192,0],[256,0,0],[256,128,0],[256,256,1],[256,384,1],[384,-64,0],[384,64,0],[384,192,1],[384,320,1],[512,0,0],[512,128,1],[512,256,1],[512,384,1],[640,192,1],[640,320,1]],"2":[[-128,64,1],[-128,192,1],[-128,320,1],[0,0,2],[0,128,1],[0,256,1],[128,-64,2],[128,64,2],[128,192,1],[256,0,2],[256,128,2],[384,-64,2],[384,64,2],[384,192,2],[512,0,2],[512,128,2]],"3":[[-128,-64,2],[-128,64,2],[-128,192,2],[0,0,2],[0,128,2],[128,-64,2],[128,64,2],[128,192,1],[256,0,2],[256,128,1],[256,256,1],[384,64,1],[384,192,1],[384,320,1],[512,0,1],[512,128,1],[512,256,1]],"4":[[-128,64,2],[-128,192,2],[-128,320,2],[0,0,3],[0,128,2],[0,256,2],[128,-64,3],[128,64,3],[128,192,2],[256,0,3],[256,128,3],[384,-64,3],[384,64,3],[384,192,3],[512,128,3],[512,256,3]],"5":[[-128,-64,3],[-128,64,3],[0,0,3],[0,128,3],[128,-64,3],[128,64,3],[128,192,2],[256,0,3],[256,128,2],[256,256,2],[384,64,2],[384,192,2],[384,320,2],[512,0,2],[512,128,2],[512,256,2]],"6":[[-128,0,2],[-128,128,1],[-128,256,0],[-128,512,1],[0,-64,3],[0,64,2],[0,192,1],[0,320,0],[128,0,3],[128,128,2],[128,256,1],[128,384,0],[256,-64,4],[256,64,3],[256,192,2],[256,320,1],[256,448,0],[384,0,4],[384,128,3],[384,256,2],[384,384,1],[512,-64,4],[512,64,4],[512,192,3],[512,320,2],[512,448,1],[512,576,1],[640,0,4],[640,128,4],[640,256,3],[640,384,2],[640,512,1],[640,640,1],[768,64,4],[768,448,2]],"7":[[-128,0,4],[-128,128,4],[-128,256,3],[-128,384,2],[-128,512,1],[0,-64,4],[0,64,4],[0,192,3],[0,320,2],[0,448,1],[0,576,1],[128,0,4],[128,128,3],[128,256,2],[128,384,1],[256,-64,4],[256,64,3],[256,192,2],[256,320,1],[256,448,0],[384,0,3],[384,128,2],[384,256,1],[384,384,0],[512,-64,3],[512,64,2],[512,192,1],[512,320,0],[640,0,2],[640,128,1],[640,256,0],[768,-64,2],[768,64,1],[768,192,1],[768,320,1],[768,448,1],[768,576,1]]};
  const SUB_SIZE = [[638, 320], [638, 320], [510, 256], [510, 256], [510, 256], [510, 256], [766, 594], [766, 512], [510, 256], [510, 256], [510, 256], [510, 256]];
  for (let i = 0; i < 4; i++) SUB_TPL[8 + i] = SUB_TPL[2 + i].map(([dx, dy, c]) => [dx, 256 - dy, c]);
  const SUB_TOL = [2, 2, 1, 1, 1, 1, 4, 4, 1, 1, 1, 1];
  const SUB_SPACING = 10; // cells (closest pair in shipped maps)
  function subMismatch(m, id, ax, ay) {
    let bad = 0;
    for (const [dx, dy, c] of SUB_TPL[id]) {
      const u = (ax + dx) / 128, v = (ay + dy) / 64, t = getV(m, u, v);
      if (t < 0 || SUB_CLASS[t] !== c) bad++;
    }
    return bad;
  }
  // flipped hill entrances (8-11): make the plateau side of the template the green cliff band (brush 4)
  // so the high end of the ramp meets matching ground instead of a square patch of plateau dirt.
  function applySubTerrain(m, id, x, y) {
    const ch = [];
    if (id < SUB_MOD_FROM || !SUB_TPL[id]) return ch;
    const ax = x * 32, ay = y * 32, hi = Math.max(...SUB_TPL[id].map(t => t[2]));
    for (const [dx, dy, c] of SUB_TPL[id]) {
      if (c !== hi) continue;
      const u = (ax + dx) / 128, v = (ay + dy) / 64, i = vIndex(m, u, v);
      if (i < 0) continue;
      const t = m.vert[i], want = t === 5 ? 4 : t === 7 ? 6 : -1;
      if (want >= 0) { ch.push([i, t]); m.vert[i] = want; }
    }
    return ch;
  }
  function subSpacingOK(m, x, y, ignore) {
    return !m.objects.some(o => o !== ignore && o.kind === 3 && Math.max(Math.abs(o.x - x), Math.abs(o.y - y)) < SUB_SPACING);
  }
  // Anchor parity per object: template vertices must land on tile corners (u+v odd). In the shipped maps the
  // left bridge (0) and waterfalls (6, 7) sit on even anchors, everything else on odd ones.
  const subParity = id => { const [dx, dy] = SUB_TPL[id][0]; return 1 - ((dx / 128 + dy / 64) & 1); };
  // best lattice-aligned anchor near the cursor (cursor = sprite centre). Returns {x,y,bad,near} in cells or null.
  function findSubAnchor(m, id, wx, wy, ignore) {
    const [w, h] = SUB_SIZE[id], cx = wx - w / 2, cy = wy - h / 2, par = subParity(id);
    let best = null;
    for (let du = -3; du <= 3; du++) for (let dv = -4; dv <= 4; dv++) {
      const u = Math.round(cx / 128) + du, v = Math.round(cy / 64) + dv;
      if (((u + v) & 1) !== par) continue;
      const ax = u * 128, ay = v * 64; if (ax < 0 || ay < 0) continue;
      const bad = subMismatch(m, id, ax, ay); if (bad > SUB_TOL[id]) continue;
      const x = ax / 32, y = ay / 32, d = Math.hypot(ax - cx, (ay - cy) * 2);
      const near = !subSpacingOK(m, x, y, ignore);
      const score = d + bad * 200 + (near ? 5000 : 0);
      if (!best || score < best.score) best = { x, y, bad, near, score };
    }
    return best;
  }

  // ---- one-click bridges (0 왼편, 1 오른편)
  // A shipped bridge crosses a water channel two vertices wide with ground banks on both sides (SUB_TPL, all 40
  // bridges of the shipped maps match it within SUB_TOL). The game itself only swaps the BRG tiles in (0040BDD0),
  // so the bridge length is fixed. planBridge picks the anchor near the click, forces the template's water/ground
  // and, when the river is wider than the bridge, fills ground outward from each bank until the existing shore.
  const BRIDGE_MAX_RUN = 12;   // vertex rows of new ground per bank (about 12 tiles)
  const BRIDGE_GROUND = 1;     // 황토/땅: the only ground brush that may touch water (MID)
  function bridgeShape(m, id, ax, ay) {
    const water = [], ground = [];
    for (const [dx, dy, c] of SUB_TPL[id]) (c === 0 ? water : ground).push(toAB((ax + dx) / 128, (ay + dy) / 64));
    // axis: the banks lie on either side of the channel; id 0 crosses along B, id 1 along A
    const ax2 = id === 0 ? 1 : 0, mid = water.reduce((s, p) => s + p[ax2], 0) / water.length;
    const banks = [ground.filter(p => p[ax2] < mid), ground.filter(p => p[ax2] > mid)];
    return { water, ground, axis: ax2, banks };
  }
  function planBridgeAt(m, id, ax, ay) {
    const S = bridgeShape(m, id, ax, ay), set = new Map(), key = (A, B) => A + ',' + B;
    const cls = (A, B) => { const [u, v] = fromAB(A, B), t = getV(m, u, v); return t < 0 ? -1 : SUB_CLASS[t]; };
    const want = (A, B, T) => { const [u, v] = fromAB(A, B), t = getV(m, u, v); if (t !== T) set.set(key(A, B), [A, B, T]); };
    let wet = 0;
    for (const [A, B] of S.water) {
      const c = cls(A, B); if (c < 0) return { error: '맵 가장자리라 다리를 놓을 수 없습니다' };
      if (c >= 2) return { error: '언덕·절벽·고지대 물에는 다리를 놓을 수 없습니다' };
      if (c === 0) wet++; want(A, B, 0);
    }
    if (wet * 2 < S.water.length) return { error: '다리는 물 위를 클릭해 놓으세요' };
    for (const [A, B] of S.ground) {
      const c = cls(A, B); if (c < 0) return { error: '맵 가장자리라 다리를 놓을 수 없습니다' };
      if (c >= 2) return { error: '다리 끝이 언덕·절벽에 걸립니다' };
      if (c !== 1) want(A, B, BRIDGE_GROUND);
    }
    // causeways: walk outward from each bank along the axis, one vertex row at a time, until the shore
    const run = [];
    for (let side = 0; side < 2; side++) {
      const bank = S.banks[side], dir = side ? 1 : -1, a = S.axis, o = 1 - a;
      const edge = side ? Math.max(...bank.map(p => p[a])) : Math.min(...bank.map(p => p[a]));
      const across = [...new Set(bank.map(p => p[o]))];
      let n = 0, reached = false;
      for (let step = 1; step <= BRIDGE_MAX_RUN + 1 && !reached; step++) {
        const row = across.map(q => { const p = []; p[a] = edge + dir * step; p[o] = q; return p; });
        const cs = row.map(([A, B]) => cls(A, B));
        if (cs.some(c => c < 0)) return { error: '다리 끝에서 땅까지 가기 전에 맵 가장자리에 닿습니다' };
        if (cs.some(c => c >= 2)) return { error: '다리 끝과 땅 사이에 언덕·절벽·고지대 물이 있습니다' };
        const dry = cs.filter(c => c === 1).length;
        if (dry === row.length) { reached = true; break; }
        if (step > BRIDGE_MAX_RUN) break;
        for (const [A, B] of row) if (cls(A, B) !== 1) want(A, B, BRIDGE_GROUND);
        n = step; if (dry) reached = true;
      }
      if (!reached) return { error: '강이 너무 넓습니다. 다리 양쪽 ' + BRIDGE_MAX_RUN + '칸 안에 땅이 있어야 합니다' };
      run.push(n);
    }
    return { changes: [...set.values()], run };
  }
  // anchor + terrain plan for a bridge click: {x, y, id, changes:[[A,B,T]], run:[a,b]} or {error}
  function planBridge(m, id, wx, wy, ignore) {
    const [w, h] = SUB_SIZE[id], cx = wx - w / 2, cy = wy - h / 2, par = subParity(id);
    // the corner nearest the click must be water (otherwise the plan would dig a channel through land)
    let cu = 0, cv = 0, cd = 1e9;
    for (let u = Math.floor(wx / 128); u <= Math.floor(wx / 128) + 1; u++) for (let v = Math.floor(wy / 64); v <= Math.floor(wy / 64) + 1; v++) {
      if (!((u + v) & 1)) continue; const d = Math.abs(wx - u * 128) / 128 + Math.abs(wy - v * 64) / 64; if (d < cd) { cd = d; cu = u; cv = v; }
    }
    const t = getV(m, cu, cv); if (t < 0 || SUB_CLASS[t] !== 0) return { error: '다리는 물 위를 클릭해 놓으세요' };
    let best = null, err = null, near = false;
    for (let du = -3; du <= 3; du++) for (let dv = -4; dv <= 4; dv++) {
      const u = Math.round(cx / 128) + du, v = Math.round(cy / 64) + dv;
      if (((u + v) & 1) !== par) continue;
      const ax = u * 128, ay = v * 64; if (ax < 0 || ay < 0) continue;
      const x = ax / 32, y = ay / 32;
      if (!subSpacingOK(m, x, y, ignore)) { near = true; continue; }
      const p = planBridgeAt(m, id, ax, ay);
      if (p.error) { if (!err) err = p.error; continue; }
      const score = Math.hypot(ax - cx, (ay - cy) * 2) + p.changes.length * 40;
      if (!best || score < best.score) best = { x, y, id, changes: p.changes, run: p.run, score };
    }
    if (best) return best;
    if (near && !err) return { error: '다른 언덕 입구·다리와 너무 가깝습니다 (' + SUB_SPACING + '칸 이상 떨어뜨리세요)' };
    return { error: err || '다리는 물 위를 클릭해 놓으세요' };
  }
  // write a bridge plan into the vertex model. Returns changed vertices [[index, before]] (callers retile).
  function applyBridgePlan(m, plan) {
    const fixed = new Set(), queue = [], ch = [], key = (A, B) => A + ',' + B;
    for (const [A, B, T] of plan.changes) {
      const [u, v] = fromAB(A, B), i = vIndex(m, u, v); if (i < 0) continue;
      ch.push([i, m.vert[i]]); m.vert[i] = T;
    }
    // keep the whole template fixed while neighbours get transition brushes
    for (const [dx, dy] of SUB_TPL[plan.id]) { const [A, B] = toAB((plan.x * 32 + dx) / 128, (plan.y * 32 + dy) / 64); fixed.add(key(A, B)); queue.push([A, B]); }
    for (const [A, B] of plan.changes) { if (!fixed.has(key(A, B))) { fixed.add(key(A, B)); queue.push([A, B]); } }
    let head = 0;
    while (head < queue.length && head < 200000) {
      const [A, B] = queue[head++], [pu, pv] = fromAB(A, B), tp = getV(m, pu, pv);
      for (let dA = -1; dA <= 1; dA++) for (let dB = -1; dB <= 1; dB++) {
        const nA = A + dA, nB = B + dB, k = key(nA, nB); if (fixed.has(k)) continue;
        const [nu, nv] = fromAB(nA, nB), ni = vIndex(m, nu, nv); if (ni < 0) continue;
        const tn = m.vert[ni]; if (compat(tp, tn)) continue;
        ch.push([ni, tn]); m.vert[ni] = MID[tp][tn]; fixed.add(k); queue.push([nA, nB]);
      }
    }
    return ch;
  }
  // choose a ramp/hill object for a click near a cliff: returns {id, msg} or {error}
  function suggestRamp(m, wx, wy) {
    let best = null;
    for (const id of [2, 3, 4, 5, 8, 9, 10, 11]) {
      const a = findSubAnchor(m, id, wx, wy); if (!a) continue;
      if (!best || a.score < best.a.score) best = { id, a };
    }
    if (best) return { id: best.id, x: best.a.x, y: best.a.y, near: best.a.near };
    return { error: '여기에는 언덕 입구를 놓을 수 없습니다. 언덕(절벽) 가장자리, 아래쪽으로 내려가는 면을 클릭하세요.' };
  }
  function suggestRampOld(m, wx, wy) {
    const u0 = Math.round(wx / 128), v0 = Math.round(wy / 64), lv = { 1: [], 2: [], 3: [] };
    for (let u = u0 - 6; u <= u0 + 6; u++) for (let v = v0 - 10; v <= v0 + 10; v++) {
      if (((u + v) & 1) === 0) continue; const t = getV(m, u, v); if (t < 0 || t === 0 || t === 8) continue;
      const L = LEVEL[t]; if (L > 0) lv[L].push([u * 128 - wx, v * 64 - wy]);
    }
    const c = a => [a.reduce((s, p) => s + p[0], 0) / a.length, a.reduce((s, p) => s + p[1], 0) / a.length];
    const dmin = a => a.length ? Math.min(...a.map(p => Math.hypot(p[0], p[1] * 2))) : Infinity;
    const pairs = [[1, 2, 2], [2, 3, 4], [1, 3, 6]].filter(([a, b]) => lv[a].length && lv[b].length)
      .map(([a, b, base]) => ({ a, b, base, d: dmin(lv[a]) + dmin(lv[b]) + (base === 6 ? 300 : 0) })).sort((x, y) => x.d - y.d);
    if (!pairs.length) return { error: '근처에 높이가 다른 지형(절벽)이 없습니다. 언덕 가장자리를 클릭하세요.' };
    const p = pairs[0], lo = c(lv[p.a]), hi = c(lv[p.b]);
    return { id: p.base + (lo[0] < hi[0] ? 0 : 1) };
  }

  function retileAround(m, verts, forceAll) {
    const seen = new Set(), changed = [];
    for (const vi of verts) {
      const u = (vi % m.VW) - 1, v = Math.floor(vi / m.VW) - 1;
      for (const [x, y] of tilesOfVertex(m, u, v)) {
        const k = y * m.cw + x; if (seen.has(k)) continue; seen.add(k);
        const before = [m.tIdx[k], m.tA[k], m.tB[k], m.tC[k]];
        if (retile(m, x, y, forceAll)) changed.push([k, before]);
      }
    }
    return changed;
  }

  // ---------------------------------------------------------- data archives
  // IDX: hash table of [u32 link][u32 offset][name\0]. We look names up by byte search.
  function idxFind(idxBytes, name) {
    const pat = new TextEncoder().encode(name.toUpperCase() + '\0');
    const d = idxBytes;
    outer: for (let i = 4; i + pat.length <= d.length; i++) {
      for (let j = 0; j < pat.length; j++) if (d[i + j] !== pat[j]) continue outer;
      // must be a full name (not the tail of a longer, fragmented name)
      const prev = d[i - 1];
      if (prev >= 0x20 && prev < 0x7f && prev !== 0) { /* possible fragment, still accept if offset sane */ }
      return u32(d, i - 4);
    }
    return -1;
  }

  // JTL tileset: header (T bytes) + records of 65568 bytes: 16 hdr + 2 diamonds (16384 RGB565 px each) + 16
  const DIAMOND_ROWS = (() => {
    const r = []; for (let k = 0; k < 64; k++) { const w = 2 + 4 * k; r.push([(256 - w) >> 1, w]); }
    return r.concat(r.slice().reverse());
  })();
  function jtlInfo(buf) { const d = new Uint8Array(buf, 0, 32); return { T: u32(d, 4), count: u32(d, 16) & 0xffff, rec: 65568 }; }
  // decode tile index k (record k>>1, diamond k&1) into RGBA 256x128
  function decodeTile(buf, info, k, out) {
    const rec = k >> 1, v = k & 1, off = info.T + rec * info.rec + 16 + v * 32768;
    const px = new Uint16Array(buf.slice(off, off + 32768));
    const o = out || new Uint8ClampedArray(256 * 128 * 4);
    let p = 0, sr = 0, sg = 0, sb = 0;
    for (let y = 0; y < 128; y++) {
      const [x0, w] = DIAMOND_ROWS[y];
      for (let x = x0; x < x0 + w; x++, p++) {
        const c = px[p], q = (y * 256 + x) * 4;
        const r = ((c >> 11) & 31) * 255 / 31, g = ((c >> 5) & 63) * 255 / 63, b = (c & 31) * 255 / 31;
        o[q] = r; o[q + 1] = g; o[q + 2] = b; o[q + 3] = 255; sr += r; sg += g; sb += b;
      }
    }
    return { rgba: o, avg: [sr / p | 0, sg / p | 0, sb / p | 0] };
  }

  G.RKM = { applySubTerrain, planBridge, applyBridgePlan, BRIDGE_MAX_RUN,
    TRANS, MID, EDGE, CORNER, DIAG, TILESETS, SUBTERRAIN, RACES, COLORS, KIND, TILE_DEF,
    decorList, resourceIds, tilesFor, cornersOf, recordFor, compat,
    parseRKM, serializeRKM, newMap, initVerts, getV, setV, vIndex, tileCorners, tilesOfVertex,
    retile, retileAround, paint, paintVerts, smoothDiagonals, shapeVerts, suggestRamp, findSubAnchor, SUB_MOD_FROM, subMismatch, subSpacingOK, SUB_SIZE, SUB_SPACING, LEVEL, BUILDABLE, cellBuildable, cellWater, CELL_OX, CELL_OY, cellX, cellY, worldCell, startProblems, nearestStart, START_R, tileAtWorld, toAB, fromAB, idxFind, jtlInfo, decodeTile, u32, u16,
  };
})(typeof window !== 'undefined' ? window : globalThis);
