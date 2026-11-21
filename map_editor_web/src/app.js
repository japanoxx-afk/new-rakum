(function () {
  'use strict';
  const R = window.RKM;
  const $ = (id) => document.getElementById(id);
  const cv = $('cv'), ctx = cv.getContext('2d'), mm = $('minimap'), mctx = mm.getContext('2d');

  // ------------------------------------------------------------------ state
  const S = {
    map: null, name: 'New Map', fileHandle: null, dirHandle: null, dirty: false,
    tool: 'brush', brush: 1, brushSize: 3, shape: 'circle', shapeDrag: null, tileSel: 10, startSel: 0, decoSel: 0, subSel: 0, res: 'gold',
    cam: { x: 0, y: 0, z: 0.5 }, grid: false, cellGrid: false, marks: false,
    hover: null, sel: null, drag: null, painting: false,
    gfx: { fdb: null, idx: null, tilesets: {} },   // tilesets[ts] = {img:[], avg:[]}
    undo: [], redo: [], act: null,
  };
  const FALLBACK = ['#3b6f8f', '#7a5a35', '#5d8a3a', '#8a8a80', '#4f5a2a', '#9a7a4a', '#3d4426', '#b0905a', '#2f5f80'];

  function toast(msg, ms) { const t = $('toast'); t.textContent = msg; t.style.display = 'block'; clearTimeout(t._h); t._h = setTimeout(() => t.style.display = 'none', ms || 2500); }
  function setDirty(v) { S.dirty = v; document.title = (v ? '* ' : '') + (S.map ? S.name + ' - ' : '') + '라크무 맵 에디터'; }

  // ----------------------------------------------------------- data (FDB)
  async function attachDataFiles(fdbFile, idxFile) {
    const idx = new Uint8Array(await idxFile.arrayBuffer());
    if (R.idxFind(idx, 'DATA\\TILE\\EAST.JTL') < 0) throw new Error('Data000.IDX에서 타일 정보를 찾지 못했습니다');
    S.gfx.fdb = fdbFile; S.gfx.idx = idx; S.gfx.tilesets = {};
    $('dataLbl').textContent = '그래픽 연결됨'; $('dataLbl').style.color = 'var(--acc2)';
    if (S.map) await ensureTileset(S.map.tileset);
    buildPalette(); draw(); drawMinimap();
  }
  async function readEntry(name) {
    const off = R.idxFind(S.gfx.idx, name);
    if (off < 0) throw new Error(name + ' 없음');
    const head = new Uint8Array(await S.gfx.fdb.slice(off, off + 4).arrayBuffer());
    const size = R.u32(head, 0);
    return await S.gfx.fdb.slice(off + 4, off + 4 + size).arrayBuffer();
  }
  // extend each diamond row by 2px on both sides so neighbouring tiles overlap (hides seams when scaled)
  function bleed(px) {
    for (let y = 0; y < 128; y++) {
      const k = y < 64 ? y : 127 - y, w = 2 + 4 * k, x0 = (256 - w) >> 1, x1 = x0 + w - 1, row = y * 1024;
      for (let e = 1; e <= 2; e++) {
        if (x0 - e >= 0) { const d = row + (x0 - e) * 4, s = row + x0 * 4; px[d] = px[s]; px[d + 1] = px[s + 1]; px[d + 2] = px[s + 2]; px[d + 3] = 255; }
        if (x1 + e < 256) { const d = row + (x1 + e) * 4, s = row + x1 * 4; px[d] = px[s]; px[d + 1] = px[s + 1]; px[d + 2] = px[s + 2]; px[d + 3] = 255; }
      }
    }
  }
  // tiles shipped next to the editor (tiles/<NAME>.js, extracted from the game's Data000.FDB)
  function loadBundled(ts) {
    return new Promise((ok) => {
      const info = R.TILESETS[ts]; if (!info) return ok(false);
      const done = () => {
        const url = window.__rkmTiles && window.__rkmTiles[ts]; if (!url) return ok(false);
        const img = new Image();
        img.onload = () => {
          const set = { img: [], avg: [], small: [] };
          for (let k = 0; k < 200; k++) {
            const c = document.createElement('canvas'); c.width = 256; c.height = 128; const g = c.getContext('2d');
            g.drawImage(img, (k % 20) * 256, Math.floor(k / 20) * 128, 256, 128, 0, 0, 256, 128);
            const sm = document.createElement('canvas'); sm.width = 64; sm.height = 32; const sg = sm.getContext('2d'); sg.imageSmoothingQuality = 'high'; sg.drawImage(c, 0, 0, 64, 32);
            const px = sg.getImageData(0, 0, 64, 32).data; let r = 0, gg = 0, b = 0, n = 0;
            for (let i = 0; i < px.length; i += 4) if (px[i + 3] > 200) { r += px[i]; gg += px[i + 1]; b += px[i + 2]; n++; }
            set.img[k] = c; set.small[k] = sm; set.avg[k] = 'rgb(' + [r / n | 0, gg / n | 0, b / n | 0].join(',') + ')';
          }
          S.gfx.tilesets[ts] = set; ok(true);
        };
        img.onerror = () => ok(false); img.src = url;
      };
      if (window.__rkmTiles && window.__rkmTiles[ts]) return done();
      const sc = document.createElement('script'); sc.src = 'tiles/' + info.file + '.js';
      sc.onload = done; sc.onerror = () => ok(false); document.head.appendChild(sc);
    });
  }
  // object/bridge sprites (tiles/<NAME>_OBJ.js): trees, decorations, well, gold mine, bridges, ramps, waterfalls
  S.spr = {};
  function loadSprites(ts) {
    return new Promise((ok) => {
      if (S.spr[ts]) return ok(true);
      const info = R.TILESETS[ts]; if (!info) return ok(false);
      const done = () => {
        const d = window.__rkmSprites && window.__rkmSprites[ts]; if (!d) return ok(false);
        const img = new Image(); img.onload = () => { S.spr[ts] = { img, meta: d.meta }; ok(true); }; img.onerror = () => ok(false); img.src = d.img;
      };
      if (window.__rkmSprites && window.__rkmSprites[ts]) return done();
      const sc = document.createElement('script'); sc.src = 'tiles/' + info.file + '_OBJ.js'; sc.onload = done; sc.onerror = () => ok(false); document.head.appendChild(sc);
    });
  }
  // world px of an object's cell (top-left). Bridges/ramps use their template anchor; everything else the game cell grid.
  function objPos(o) { return o.kind === R.KIND.SUB ? [o.x * 32, o.y * 32] : [R.cellX(o.x), R.cellY(o.y)]; }
  // sprite + draw position for an object (world px of top-left), or null
  function spriteOf(o, ts) {
    const sp = S.spr[ts == null ? S.map.tileset : ts]; if (!sp) return null;
    const [x, y] = objPos(o);
    if (o.kind === R.KIND.SUB) { const e = sp.meta.sub[o.id]; return e ? { e, img: sp.img, x, y } : null; }
    const e = sp.meta.obj[o.id]; return e ? { e, img: sp.img, x: x + e.ox, y: y + e.oy } : null;
  }
  function thumb(o, w, h) {
    const c = document.createElement('canvas'); c.width = w * 2; c.height = h * 2; const g = c.getContext('2d');
    const s = spriteOf(o); if (!s) return c;
    const k = Math.min(c.width / s.e.w, c.height / s.e.h, 2);
    g.drawImage(s.img, s.e.x, s.e.y, s.e.w, s.e.h, (c.width - s.e.w * k) / 2, (c.height - s.e.h * k) / 2, s.e.w * k, s.e.h * k);
    return c;
  }
  async function ensureTileset(ts) {
    if (!(await loadSprites(ts))) toast('오브젝트 그림(tiles\\' + R.TILESETS[ts].file + '_OBJ.js)을 불러오지 못했습니다. tiles 폴더를 확인하세요.', 6000);
    if (S.gfx.tilesets[ts]) return;
    if (!S.gfx.fdb) {
      $('stMsg').textContent = '타일 그래픽 불러오는 중…';
      const ok = await loadBundled(ts); $('stMsg').textContent = '';
      if (ok) { $('dataLbl').textContent = '타일 그래픽 내장됨'; $('dataLbl').style.color = 'var(--acc2)'; }
      else { $('dataLbl').textContent = '그래픽 없음 — tiles 폴더가 에디터 옆에 있어야 합니다'; $('dataLbl').style.color = 'var(--bad)'; }
      return;
    }
    const info = R.TILESETS[ts]; if (!info) return;
    $('stMsg').textContent = info.name + ' 타일 불러오는 중…';
    const buf = await readEntry('DATA\\TILE\\' + info.file + '.JTL');
    const ji = R.jtlInfo(buf), n = Math.min(200, ji.count * 2);
    const set = { img: new Array(n), avg: new Array(n), small: new Array(n) };
    const id = new ImageData(256, 128);
    for (let k = 0; k < n; k++) {
      id.data.fill(0);
      const r = R.decodeTile(buf, ji, k, id.data);
      bleed(id.data);
      const c = document.createElement('canvas'); c.width = 256; c.height = 128; c.getContext('2d').putImageData(id, 0, 0);
      const s = document.createElement('canvas'); s.width = 64; s.height = 32; const sc = s.getContext('2d'); sc.imageSmoothingQuality = 'high'; sc.drawImage(c, 0, 0, 64, 32);
      set.img[k] = c; set.small[k] = s; set.avg[k] = 'rgb(' + r.avg.join(',') + ')';
    }
    S.gfx.tilesets[ts] = set;
    $('stMsg').textContent = '';
  }

  // folder connection (File System Access API)
  const IDB = {
    db() { return new Promise((ok, no) => { const r = indexedDB.open('rhakmu-editor', 1); r.onupgradeneeded = () => r.result.createObjectStore('kv'); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); }); },
    async get(k) { const db = await this.db(); return new Promise(ok => { const r = db.transaction('kv').objectStore('kv').get(k); r.onsuccess = () => ok(r.result); r.onerror = () => ok(null); }); },
    async set(k, v) { const db = await this.db(); return new Promise(ok => { const t = db.transaction('kv', 'readwrite'); t.objectStore('kv').put(v, k); t.oncomplete = ok; t.onerror = ok; }); },
  };
  async function subDir(h, name) { for await (const [n, e] of h.entries()) if (n.toLowerCase() === name.toLowerCase() && e.kind === 'directory') return e; return null; }
  async function subFile(h, name) { for await (const [n, e] of h.entries()) if (n.toLowerCase() === name.toLowerCase() && e.kind === 'file') return e; return null; }
  async function useFolder(dir) {
    let data = await subDir(dir, 'Data');
    if (!data) { if (await subFile(dir, 'Data000.FDB')) data = dir; else throw new Error('선택한 폴더에 Data 폴더가 없습니다. RhakMu 설치 폴더를 선택하세요.'); }
    const fdb = await subFile(data, 'Data000.FDB'), idx = await subFile(data, 'Data000.IDX');
    if (!fdb || !idx) throw new Error('Data000.FDB / Data000.IDX를 찾지 못했습니다');
    S.dirHandle = dir; S.mapsDir = await subDir(data, 'Maps');
    await attachDataFiles(await fdb.getFile(), await idx.getFile());
    await IDB.set('dir', dir);
    listMaps();
  }
  async function listMaps() {
    const box = $('maplist'); box.innerHTML = '';
    if (!S.mapsDir) return;
    const names = [];
    for await (const [n, e] of S.mapsDir.entries()) if (e.kind === 'file' && /\.rkm$/i.test(n)) names.push([n, e]);
    names.sort((a, b) => a[0].localeCompare(b[0]));
    const h = document.createElement('div'); h.style.color = 'var(--acc)'; h.style.cursor = 'default'; h.textContent = 'Data\\Maps (' + names.length + '개)'; box.appendChild(h);
    for (const [n, e] of names) { const d = document.createElement('div'); d.textContent = n; d.onclick = async () => { await openFromHandle(e); }; box.appendChild(d); }
  }
  async function pickFolder() {
    if (!window.showDirectoryPicker) { toast('이 브라우저는 폴더 연결을 지원하지 않습니다. Chrome/Edge를 쓰거나 파일 선택을 이용하세요.', 4000); return; }
    try { const d = await window.showDirectoryPicker({ id: 'rhakmu', mode: 'readwrite' }); await useFolder(d); toast('라크무 폴더 연결됨'); }
    catch (e) { if (e.name !== 'AbortError') { console.error(e); toast('폴더 연결 실패: ' + e.message + ' → "FDB/IDX 파일 선택"을 이용하세요', 5000); } }
  }
  async function reconnect() {
    const d = await IDB.get('dir'); if (!d) return;
    try { if ((await d.requestPermission({ mode: 'readwrite' })) !== 'granted') return; await useFolder(d); toast('라크무 폴더 다시 연결됨'); } catch (e) { toast('다시 연결 실패: ' + e.message, 4000); }
  }
  function pickDataFiles() { $('fileData').value = ''; $('fileData').click(); }
  $('fileData').onchange = async (ev) => {
    const fs = [...ev.target.files];
    const fdb = fs.find(f => /\.fdb$/i.test(f.name)), idx = fs.find(f => /\.idx$/i.test(f.name));
    if (!fdb || !idx) { toast('Data000.FDB와 Data000.IDX를 함께 선택하세요 (Ctrl+클릭)', 4000); return; }
    try { await attachDataFiles(fdb, idx); toast('그래픽 연결됨'); } catch (e) { toast(e.message, 4000); }
  };

  // ------------------------------------------------------- local helper server
  // When started with "맵에디터 실행.bat", a small local server lets us list/open/save Data\Maps directly.
  const SRV = { on: false, folder: '' };
  async function srvInit() {
    if (!/^https?:/.test(location.protocol)) return false;
    try { const r = await fetch('/api/ping', { cache: 'no-store' }); if (!r.ok) return false; } catch (e) { return false; }
    SRV.on = true; $('gMaps').style.display = ''; $('modeLbl').textContent = 'Data\\Maps 자동 연결됨'; $('modeLbl').style.color = 'var(--acc2)';
    await srvList();
    const want = new URLSearchParams(location.search).get('open');   // 런처 '맵 미리보기'에서 연 경우
    if (want) { history.replaceState(null, '', location.pathname); await srvOpen(want); }
    return true;
  }
  async function srvList() {
    try {
      const j = await (await fetch('/api/maps', { cache: 'no-store' })).json();
      SRV.folder = j.folder; $('mapsFolder').textContent = j.maps.length + '개';
      const box = $('srvMaps'); box.innerHTML = '';
      j.maps.sort((a, b) => a.name.localeCompare(b.name)).forEach(it => {
        const d = document.createElement('div'); d.textContent = it.name; if (it.name === S.srvName) d.className = 'cur';
        d.onclick = () => srvOpen(it.name); box.appendChild(d);
      });
    } catch (e) { toast('맵 목록을 읽지 못했습니다: ' + e.message, 4000); }
  }
  async function srvOpen(name) {
    if (S.dirty && !confirm('저장하지 않은 변경 내용이 있습니다. 계속할까요?')) return;
    try {
      const r = await fetch('/api/map?name=' + encodeURIComponent(name), { cache: 'no-store' }); if (!r.ok) throw new Error(r.status);
      await loadMapBytes(new Uint8Array(await r.arrayBuffer()), name.split('\\').pop(), null);
      S.srvName = name; srvList();
    } catch (e) { toast('열기 실패: ' + e.message, 4000); }
  }
  async function srvSave(bytes, as) {
    let name = S.srvName && !as ? S.srvName : fileName();
    if (S.srvName && !as) { const dir = S.srvName.includes('\\') ? S.srvName.slice(0, S.srvName.lastIndexOf('\\') + 1) : ''; name = dir + fileName(); }
    if (as) { const n = prompt('저장할 파일 이름 (Data\\Maps 기준, 예: [4]My Map.rkm)', name); if (!n) return true; name = /\.rkm$/i.test(n) ? n : n + '.rkm'; }
    const r = await fetch('/api/map?name=' + encodeURIComponent(name), { method: 'PUT', body: bytes });
    if (!r.ok) { const t = await r.text(); toast('Data\\Maps에 저장 실패: ' + t + ' → 다운로드로 저장합니다. (쓰기 권한이 없으면 "맵에디터 실행.bat"을 관리자 권한으로 실행)', 7000); return false; }
    S.srvName = name; setDirty(false); toast('저장됨: Data\\Maps\\' + name); srvList(); return true;
  }

  // ------------------------------------------------------------- map io
  async function loadMapBytes(bytes, name, handle) {
    const m = R.parseRKM(bytes);
    S.map = m; S.name = name.replace(/\.rkm$/i, '').replace(/^\[\d\]/, ''); S.fileHandle = handle || null; S.srvName = null;
    S.undo = []; S.redo = []; S.sel = null;
    $('welcome').style.display = 'none';
    await ensureTileset(m.tileset);
    rebuildToolButtons(); buildPalette(); centerView(); setDirty(false); updateStatusMap(); draw(); drawMinimap();
    toast(m.repaired ? name + ' 열림 — 이전 버전 에디터의 헤더 오류를 자동 복구했습니다. 저장하면 고쳐집니다.' : name + ' 열림', m.repaired ? 6000 : 2500);
    if (m.repaired) setDirty(true);
  }
  async function openFromHandle(h) {
    try { const f = await h.getFile(); await loadMapBytes(new Uint8Array(await f.arrayBuffer()), f.name, h); } catch (e) { console.error(e); toast('열기 실패: ' + e.message, 4000); }
  }
  async function openMap() {
    if (SRV.on) { $('gMaps').classList.remove('closed'); $('gMaps').scrollIntoView(); toast('오른쪽 [맵 목록]에서 맵을 클릭하세요'); return; }
    if (S.dirty && !confirm('저장하지 않은 변경 내용이 있습니다. 계속할까요?')) return;
    if (window.showOpenFilePicker) {
      try {
        const opts = { types: [{ description: '라크무 맵', accept: { 'application/octet-stream': ['.rkm'] } }] };
        if (S.mapsDir) opts.startIn = S.mapsDir;
        const [h] = await window.showOpenFilePicker(opts); await openFromHandle(h); return;
      } catch (e) { if (e.name === 'AbortError') return; }
    }
    $('fileRkm').value = ''; $('fileRkm').click();
  }
  $('fileRkm').onchange = async (ev) => { const f = ev.target.files[0]; if (!f) return; try { await loadMapBytes(new Uint8Array(await f.arrayBuffer()), f.name, null); } catch (e) { toast('열기 실패: ' + e.message, 4000); } };

  function fileName() { return '[' + S.map.maxPlayers + ']' + S.name + '.rkm'; }
  function validate() {
    const m = S.map, w = [];
    const out = (x, y) => x < 4 || y < 4 || x >= m.W - 4 || y >= m.H - 4;
    m.players.forEach((p, i) => { if (out(p.x, p.y)) w.push('P' + (i + 1) + ' 시작 위치가 플레이 영역(점선) 밖'); else if (R.startProblems(m, p.x, p.y)) w.push('P' + (i + 1) + ' 시작 위치에 물/절벽이 있어 본진이 물 위나 절벽에 지어집니다 (빨간 사각형)'); });
    const rw = m.objects.filter(o => o.kind === R.KIND.RES && R.cellWater(m, o.x, o.y)).length; if (rw) w.push('자원 ' + rw + '개가 물 위에 있음');
    if (m.objects.some(o => o.kind === R.KIND.SUB && o.id >= R.SUB_MOD_FROM)) w.push('상하대칭 언덕 입구를 사용했습니다. 이 맵으로 게임하는 모든 PC에 상하대칭 모드(RhakMu\\Data\\tile 폴더)가 설치되어 있어야 합니다');
    const ro = m.objects.filter(o => o.kind === R.KIND.RES && out(o.x, o.y)).length; if (ro) w.push('자원 ' + ro + '개가 플레이 영역(점선) 밖');
    if (!m.objects.some(o => o.kind === R.KIND.RES)) w.push('자원(금광/우물)이 없음');
    return w;
  }
  async function save(as) {
    if (!S.map) return;
    const warn = validate(); if (warn.length && !confirm('확인 필요:\n- ' + warn.join('\n- ') + '\n\n그래도 저장할까요?')) return;
    const bytes = R.serializeRKM(S.map);
    try { R.parseRKM(bytes); } catch (e) { alert('저장 데이터 검증 실패: ' + e.message); return; }
    if (SRV.on) { try { if (await srvSave(bytes, as)) return; } catch (e) { toast('저장 실패: ' + e.message, 4000); } }
    let h = as ? null : S.fileHandle;
    if (h && h.name !== fileName() && !as) {
      // player count changed -> name prefix changed: save under the new name in the same folder
      if (S.mapsDir) { try { h = await S.mapsDir.getFileHandle(fileName(), { create: true }); } catch (e) { h = null; } } else h = null;
    }
    if (!h && window.showSaveFilePicker) {
      try {
        const opts = { suggestedName: fileName(), types: [{ description: '라크무 맵', accept: { 'application/octet-stream': ['.rkm'] } }] };
        if (S.mapsDir) opts.startIn = S.mapsDir;
        h = await window.showSaveFilePicker(opts);
      } catch (e) { if (e.name === 'AbortError') return; h = null; }
    }
    if (h) {
      try { const w = await h.createWritable(); await w.write(bytes); await w.close(); S.fileHandle = h; setDirty(false); toast('저장됨: ' + h.name); if (S.mapsDir) listMaps(); return; }
      catch (e) { console.error(e); toast('직접 저장 실패(' + e.message + ') → 다운로드로 저장합니다', 4000); }
    }
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([bytes])); a.download = fileName(); a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    setDirty(false); toast('다운로드됨: ' + fileName() + ' → RhakMu\\Data\\Maps 폴더에 넣으세요', 5000);
  }

  // --------------------------------------------------------------- undo
  function beginAct() { S.act = { tiles: new Map(), verts: new Map(), objs: null, pls: null }; }
  function snapObjs() { return S.map.objects.map(o => ({ ...o, raw: o.raw.slice() })); }
  function snapPls() { return S.map.players.map(p => ({ ...p, raw: p.raw.slice() })); }
  function noteObjs() { if (S.act && !S.act.objs) S.act.objs = snapObjs(); }
  function notePls() { if (S.act && !S.act.pls) S.act.pls = snapPls(); }
  function noteTile(k, before) { if (S.act && !S.act.tiles.has(k)) S.act.tiles.set(k, before); }
  function noteVert(i, before) { if (S.act && !S.act.verts.has(i)) S.act.verts.set(i, before); }
  function endAct() {
    const a = S.act; S.act = null; if (!a) return;
    const m = S.map;
    const rec = { tiles: [], verts: [], objs: null, pls: null };
    for (const [k, b] of a.tiles) rec.tiles.push([k, b, [m.tIdx[k], m.tA[k], m.tB[k], m.tC[k]]]);
    for (const [i, b] of a.verts) rec.verts.push([i, b, m.vert[i]]);
    if (a.objs) rec.objs = [a.objs, snapObjs()];
    if (a.pls) rec.pls = [a.pls, snapPls()];
    if (!rec.tiles.length && !rec.verts.length && !rec.objs && !rec.pls) return;
    S.undo.push(rec); if (S.undo.length > 300) S.undo.shift(); S.redo = []; setDirty(true); updateStatusMap();
  }
  function applyRec(rec, dir) {
    const m = S.map, j = dir < 0 ? 1 : 2;
    for (const t of rec.tiles) { const v = t[j]; m.tIdx[t[0]] = v[0]; m.tA[t[0]] = v[1]; m.tB[t[0]] = v[2]; m.tC[t[0]] = v[3]; }
    for (const v of rec.verts) m.vert[v[0]] = v[j];
    if (rec.objs) m.objects = (dir < 0 ? rec.objs[0] : rec.objs[1]).map(o => ({ ...o, raw: o.raw.slice() }));
    if (rec.pls) m.players = (dir < 0 ? rec.pls[0] : rec.pls[1]).map(p => ({ ...p, raw: p.raw.slice() }));
    S.sel = null; setDirty(true); updateStatusMap(); draw(); drawMinimap();
  }
  function undo() { const r = S.undo.pop(); if (!r) return; applyRec(r, -1); S.redo.push(r); }
  function redo() { const r = S.redo.pop(); if (!r) return; applyRec(r, 1); S.undo.push(r); }

  // -------------------------------------------------------------- geometry
  function worldSize() { const m = S.map; return { w: m.cw * 256, h: m.ch * 64 }; }
  function s2w(sx, sy) { return { x: (sx - cv.width / 2) / S.cam.z + S.cam.x, y: (sy - cv.height / 2) / S.cam.z + S.cam.y }; }
  function w2s(wx, wy) { return { x: (wx - S.cam.x) * S.cam.z + cv.width / 2, y: (wy - S.cam.y) * S.cam.z + cv.height / 2 }; }
  function tileAt(wx, wy) {
    const m = S.map, y0 = Math.floor(wy / 64);
    let best = null, bd = 9;
    for (let y = y0 - 1; y <= y0 + 2; y++) {
      if (y < 0 || y >= m.ch) continue;
      const off = (y & 1) * 128, x0 = Math.round((wx - off) / 256);
      for (let x = x0 - 1; x <= x0 + 1; x++) {
        if (x < 0 || x >= m.cw) continue;
        const cx = x * 256 + off, cy = y * 64, d = Math.abs(wx - cx) / 128 + Math.abs(wy - cy) / 64;
        if (d < bd) { bd = d; best = [x, y]; }
      }
    }
    return best;
  }
  function vertexAt(wx, wy) {
    const u0 = Math.round(wx / 128), v0 = Math.round(wy / 64); let best = null, bd = 9;
    for (let u = u0 - 1; u <= u0 + 1; u++) for (let v = v0 - 1; v <= v0 + 1; v++) {
      if (((u + v) & 1) === 0) continue;
      const d = Math.abs(wx - u * 128) / 128 + Math.abs(wy - v * 64) / 64; if (d < bd) { bd = d; best = [u, v]; }
    }
    return best;
  }

  // ---------------------------------------------------------------- drawing
  let raf = 0;
  function draw() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; render(); }); }
  function resize() {
    const r = $('view').getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr); cv.style.width = r.width + 'px'; cv.style.height = r.height + 'px';
    S.dpr = dpr; draw();
  }
  function drawDiamond(c, cx, cy, hw, hh) { c.beginPath(); c.moveTo(cx, cy - hh); c.lineTo(cx + hw, cy); c.lineTo(cx, cy + hh); c.lineTo(cx - hw, cy); c.closePath(); }
  function render() {
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#000'; ctx.fillRect(0, 0, cv.width, cv.height);
    const m = S.map; if (!m) return;
    const z = S.cam.z, set = S.gfx.tilesets[m.tileset];
    $('zoomLbl').textContent = Math.round(z * 100) + '%';
    ctx.setTransform(z, 0, 0, z, cv.width / 2 - S.cam.x * z, cv.height / 2 - S.cam.y * z);
    ctx.imageSmoothingEnabled = z < 1;
    const tl = s2w(0, 0), br = s2w(cv.width, cv.height);
    const y0 = Math.max(0, Math.floor(tl.y / 64) - 1), y1 = Math.min(m.ch - 1, Math.ceil(br.y / 64) + 1);
    const x0 = Math.max(0, Math.floor((tl.x - 128) / 256)), x1 = Math.min(m.cw - 1, Math.ceil((br.x + 128) / 256));
    const useSmall = z <= 0.26;
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
      const i = y * m.cw + x, cx = x * 256 + (y & 1) * 128, cy = y * 64, k = m.tIdx[i];
      if (set && set.img[k]) ctx.drawImage(useSmall ? set.small[k] : set.img[k], cx - 128, cy - 64, 256, 128);
      else {
        const c = R.cornersOf(m.tA[i], m.tB[i]);
        const tri = (ax, ay, bx, by, col) => { ctx.fillStyle = FALLBACK[col] || '#555'; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(ax, ay); ctx.lineTo(bx, by); ctx.closePath(); ctx.fill(); };
        tri(cx, cy - 64, cx + 128, cy, c.N); tri(cx + 128, cy, cx, cy + 64, c.E); tri(cx, cy + 64, cx - 128, cy, c.S); tri(cx - 128, cy, cx, cy - 64, c.W);
      }
    }
    if (S.grid) {
      ctx.strokeStyle = 'rgba(255,255,255,.18)'; ctx.lineWidth = 1 / z;
      for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) { drawDiamond(ctx, x * 256 + (y & 1) * 128, y * 64, 128, 64); ctx.stroke(); }
    }
    if (S.cellGrid && z >= 0.2) {
      ctx.strokeStyle = 'rgba(120,200,255,.16)'; ctx.lineWidth = 1 / z; ctx.beginPath();
      const [a0, b0] = R.worldCell(tl.x, tl.y), [a1, b1] = R.worldCell(br.x, br.y);
      const cx0 = Math.max(0, a0), cx1 = Math.min(m.W, a1 + 1), cy0 = Math.max(0, b0), cy1 = Math.min(m.H, b1 + 1);
      for (let x = cx0; x <= cx1; x++) { ctx.moveTo(R.cellX(x), R.cellY(cy0)); ctx.lineTo(R.cellX(x), R.cellY(cy1)); }
      for (let y = cy0; y <= cy1; y++) { ctx.moveTo(R.cellX(cx0), R.cellY(y)); ctx.lineTo(R.cellX(cx1), R.cellY(y)); }
      ctx.stroke();
    }
    if ($('lyMapEdge').checked) {
      ctx.strokeStyle = 'rgba(255,200,80,.7)'; ctx.lineWidth = 2 / z; ctx.strokeRect(R.cellX(0), R.cellY(0), m.W * 32, m.H * 32);
      ctx.setLineDash([12 / z, 8 / z]); ctx.strokeStyle = 'rgba(255,255,255,.45)'; ctx.strokeRect(R.cellX(4), R.cellY(4), (m.W - 8) * 32, (m.H - 8) * 32); ctx.setLineDash([]);
    }
    if (S.marks) {
      ctx.lineWidth = 2 / z; ctx.font = (14 / Math.max(z, .3)) + 'px sans-serif';
      for (const k of m.marks) { const px = k.x * 32, py = k.y * 32; ctx.strokeStyle = '#0ff'; ctx.beginPath(); ctx.moveTo(px - 10, py); ctx.lineTo(px + 10, py); ctx.moveTo(px, py - 10); ctx.lineTo(px, py + 10); ctx.stroke(); ctx.fillStyle = '#0ff'; ctx.fillText(String(k.t), px + 6, py - 6); }
    }
    if ($('lyObj').checked) {
      const subs = m.objects.filter(o => o.kind === R.KIND.SUB), rest = m.objects.filter(o => o.kind !== R.KIND.SUB).sort((a, b) => a.y - b.y);
      for (const o of subs) drawObject(ctx, o, z, o === S.sel);
      for (const o of rest) drawObject(ctx, o, z, o === S.sel);
    }
    if ($('lyStart').checked) m.players.forEach((p, i) => drawStart(ctx, p, i, z, S.sel === p));
    drawCursor(z);
  }
  function drawObject(c, o, z, sel) {
    const sp = spriteOf(o), [ox, oy] = objPos(o);
    if (sp) {
      c.drawImage(sp.img, sp.e.x, sp.e.y, sp.e.w, sp.e.h, sp.x, sp.y, sp.e.w, sp.e.h);
      if (o.kind === R.KIND.RES && z > 0.3) { c.fillStyle = '#fff'; c.strokeStyle = '#000'; c.lineWidth = 3; c.font = 'bold 15px sans-serif'; c.textAlign = 'center'; c.strokeText(String(o.val), ox + 16, oy + 44); c.fillText(String(o.val), ox + 16, oy + 44); c.textAlign = 'start'; }
      if (sel) { c.strokeStyle = '#fff'; c.setLineDash([6 / z, 4 / z]); c.lineWidth = 2 / z; c.strokeRect(sp.x, sp.y, sp.e.w, sp.e.h); c.setLineDash([]); }
      return;
    }
    const px = ox + 16, py = oy + 16;
    c.save(); c.translate(px, py);
    if (o.kind === R.KIND.RES) {
      const ids = R.resourceIds(S.map.tileset), gold = o.id === ids.gold;
      c.fillStyle = gold ? '#f2c230' : '#3aa0ff'; c.strokeStyle = '#000'; c.lineWidth = 3;
      if (gold) { drawDiamond(c, 0, 0, 56, 30); c.fill(); c.stroke(); } else { c.beginPath(); c.ellipse(0, 0, 40, 22, 0, 0, Math.PI * 2); c.fill(); c.stroke(); }
      c.fillStyle = '#000'; c.font = 'bold 22px sans-serif'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText(gold ? '금' : '물', 0, 1);
      if (z > 0.3) { c.fillStyle = '#fff'; c.font = '16px sans-serif'; c.fillText(String(o.val), 0, 40); }
    } else if (o.kind === R.KIND.DECO) {
      const d = R.decorList(S.map.tileset).find(x => x.id === o.id), tree = d && d.name.startsWith('나무');
      if (tree) { c.fillStyle = '#4a2e14'; c.fillRect(-4, -4, 8, 22); c.fillStyle = '#2f7a2a'; c.strokeStyle = '#0a2a08'; c.lineWidth = 2; c.beginPath(); c.arc(0, -18, 22, 0, Math.PI * 2); c.fill(); c.stroke(); }
      else { c.fillStyle = '#9a8460'; c.strokeStyle = '#2a2010'; c.lineWidth = 2; c.beginPath(); c.moveTo(-18, 10); c.lineTo(-10, -16); c.lineTo(12, -18); c.lineTo(20, 10); c.closePath(); c.fill(); c.stroke(); }
      if (z > 0.45) { c.fillStyle = '#fff'; c.font = '12px sans-serif'; c.textAlign = 'center'; c.fillText(d ? d.name : '#' + o.id, 0, 28); }
    } else if (o.kind === R.KIND.SUB) {
      c.fillStyle = 'rgba(220,80,220,.75)'; c.strokeStyle = '#300030'; c.lineWidth = 3;
      drawDiamond(c, 0, 0, 64, 32); c.fill(); c.stroke();
      c.fillStyle = '#fff'; c.font = 'bold 14px sans-serif'; c.textAlign = 'center'; c.textBaseline = 'middle';
      c.fillText(R.SUBTERRAIN[o.id] || ('보조' + o.id), 0, 0);
    } else { c.fillStyle = '#fff'; c.fillRect(-8, -8, 16, 16); }
    if (sel) { c.strokeStyle = '#fff'; c.setLineDash([6, 4]); c.lineWidth = 2 / z; c.strokeRect(-48, -40, 96, 80); c.setLineDash([]); }
    c.restore();
  }
  function drawStart(c, p, i, z, sel) {
    const px = R.cellX(p.x) + 16, py = R.cellY(p.y) + 16, col = (R.COLORS[p.team] || R.COLORS[i % 8])[1];
    const bad = R.startProblems(S.map, p.x, p.y), r = R.START_R;
    c.save(); c.fillStyle = bad ? 'rgba(255,40,30,.35)' : 'rgba(80,255,80,.12)'; c.strokeStyle = bad ? '#ff4030' : 'rgba(120,255,120,.6)'; c.lineWidth = 2 / z;
    c.fillRect(R.cellX(p.x - r), R.cellY(p.y - r), (2 * r + 1) * 32, (2 * r + 1) * 32); c.strokeRect(R.cellX(p.x - r), R.cellY(p.y - r), (2 * r + 1) * 32, (2 * r + 1) * 32);
    if (bad) { c.fillStyle = '#ff6050'; c.font = 'bold ' + (15 / Math.max(z, .35)) + 'px sans-serif'; c.textAlign = 'center'; c.fillText('본진 건설 불가 (물/절벽)', px, R.cellY(p.y - r) - 8 / Math.max(z, .35)); }
    c.restore();
    c.save(); c.translate(px, py);
    c.lineWidth = 6; c.strokeStyle = '#000'; c.beginPath(); c.ellipse(0, 0, 70, 36, 0, 0, Math.PI * 2); c.stroke();
    c.lineWidth = 4; c.strokeStyle = col; c.stroke();
    c.fillStyle = col; c.font = 'bold 30px sans-serif'; c.textAlign = 'center'; c.textBaseline = 'middle';
    c.strokeStyle = '#000'; c.lineWidth = 5; c.strokeText('P' + (i + 1), 0, 0); c.fillText('P' + (i + 1), 0, 0);
    if (z > 0.3) { c.font = '15px sans-serif'; c.fillStyle = '#fff'; c.fillText(R.RACES[p.race] || '?', 0, 50); }
    if (sel) { c.strokeStyle = '#fff'; c.setLineDash([6, 4]); c.lineWidth = 2 / z; c.strokeRect(-80, -46, 160, 92); c.setLineDash([]); }
    c.restore();
  }
  function drawCursor(z) {
    const h = S.hover; if (!h || !S.map) return;
    ctx.lineWidth = 2 / z;
    if (S.tool === 'brush') {
      let shape;
      if (S.shapeDrag) {
        const g = S.shapeDrag;
        shape = S.shape === 'rect' ? { type: 'rect', x0: g.x0, y0: g.y0, x1: g.x1, y1: g.y1 } : { type: 'line', pts: [{ x: g.x0, y: g.y0 }, { x: g.x1, y: g.y1 }], size: paintSize() };
        ctx.strokeStyle = '#fff'; ctx.setLineDash([10 / z, 6 / z]);
        if (S.shape === 'rect') ctx.strokeRect(Math.min(g.x0, g.x1), Math.min(g.y0, g.y1), Math.abs(g.x1 - g.x0), Math.abs(g.y1 - g.y0));
        else { ctx.beginPath(); ctx.moveTo(g.x0, g.y0); ctx.lineTo(g.x1, g.y1); ctx.stroke(); }
        ctx.setLineDash([]);
      } else {
        const v = vertexAt(h.x, h.y); if (!v) return;
        shape = { type: S.shape === 'square' ? 'square' : 'circle', u: v[0], v: v[1], size: paintSize() };
      }
      const list = R.shapeVerts(S.map, shape);
      ctx.fillStyle = FALLBACK[paintBrush()]; ctx.globalAlpha = .55;
      for (const [A, B] of list) { const [u, vv] = R.fromAB(A, B); drawDiamond(ctx, u * 128, vv * 64, 64, 32); ctx.fill(); }
      ctx.globalAlpha = 1;
    } else if (S.tool === 'ramp') {
      const r = R.suggestRamp(S.map, h.x, h.y);
      if (r.error || r.near) { ctx.fillStyle = 'rgba(255,60,40,.35)'; drawDiamond(ctx, h.x, h.y, 255, 128); ctx.fill(); }
      else { const sp = spriteOf({ kind: R.KIND.SUB, id: r.id, x: r.x, y: r.y }); if (sp) { ctx.globalAlpha = .75; ctx.drawImage(sp.img, sp.e.x, sp.e.y, sp.e.w, sp.e.h, sp.x, sp.y, sp.e.w, sp.e.h); ctx.globalAlpha = 1; } }
      ctx.fillStyle = (r.error || r.near) ? '#ff8070' : '#a0ff90'; ctx.font = 'bold ' + (16 / Math.max(z, .35)) + 'px sans-serif'; ctx.textAlign = 'center';
      ctx.fillText(r.error ? '언덕 가장자리가 아님' : r.near ? '다른 입구와 너무 가까움' : R.SUBTERRAIN[r.id], h.x, h.y - 140); ctx.textAlign = 'start';
    } else if (S.tool === 'tile' || S.tool === 'pick') {
      const t = tileAt(h.x, h.y); if (!t) return; ctx.strokeStyle = '#ffd040'; drawDiamond(ctx, t[0] * 256 + (t[1] & 1) * 128, t[1] * 64, 128, 64); ctx.stroke();
      if (S.tool === 'tile') { const set = S.gfx.tilesets[S.map.tileset]; if (set && set.img[S.tileSel]) { ctx.globalAlpha = .6; ctx.drawImage(set.img[S.tileSel], t[0] * 256 + (t[1] & 1) * 128 - 128, t[1] * 64 - 64); ctx.globalAlpha = 1; } }
    } else if (['res', 'deco', 'sub'].includes(S.tool)) {
      const [x, y] = placeCell(h.x, h.y), ids = R.resourceIds(S.map.tileset);
      const o = S.tool === 'res' ? { kind: R.KIND.RES, id: S.res === 'gold' ? ids.gold : ids.well, x, y } : S.tool === 'deco' ? { kind: R.KIND.DECO, id: S.decoSel, x, y } : { kind: R.KIND.SUB, id: S.subSel, x, y };
      let bad = null, plan = null;
      if (o.kind === R.KIND.SUB && isBridge(o.id)) { plan = R.planBridge(S.map, o.id, h.x, h.y); if (plan.error) { bad = plan.error; plan = null; } else { o.x = plan.x; o.y = plan.y; } }
      else if (o.kind === R.KIND.SUB) { const r = subCheck(o.id, h.x, h.y); if (r.a) { o.x = r.a.x; o.y = r.a.y; } bad = r.error || null; }
      const sp = spriteOf(o);
      if (plan && plan.changes.length) { // terrain the click will reshape: blue = becomes water, yellow = becomes ground
        for (const [A, B, T] of plan.changes) { const [u, v] = R.fromAB(A, B); ctx.fillStyle = T === 0 ? 'rgba(60,140,255,.55)' : 'rgba(255,210,60,.55)'; drawDiamond(ctx, u * 128, v * 64, 64, 32); ctx.fill(); }
        const msg = plan.run[0] + plan.run[1] ? '양쪽 땅까지 ' + (plan.run[0] + plan.run[1]) + '줄 메움' : '물·땅 모양 맞춤';
        ctx.fillStyle = '#ffe070'; ctx.font = 'bold ' + (16 / Math.max(z, .35)) + 'px sans-serif'; ctx.textAlign = 'center'; ctx.fillText(msg, h.x, h.y - 190 - 8 / Math.max(z, .35)); ctx.textAlign = 'start';
      }
      if (bad) {
        ctx.fillStyle = 'rgba(255,50,40,.35)'; const [w2, h2] = R.SUB_SIZE[o.id]; drawDiamond(ctx, h.x, h.y, w2 / 2, h2 / 2); ctx.fill();
        ctx.fillStyle = '#ff8070'; ctx.font = 'bold ' + (16 / Math.max(z, .35)) + 'px sans-serif'; ctx.textAlign = 'center'; ctx.fillText(bad, h.x, h.y - h2 / 2 - 8 / Math.max(z, .35)); ctx.textAlign = 'start';
      } else if (sp) { ctx.globalAlpha = .7; ctx.drawImage(sp.img, sp.e.x, sp.e.y, sp.e.w, sp.e.h, sp.x, sp.y, sp.e.w, sp.e.h); ctx.globalAlpha = 1; ctx.setLineDash([8 / z, 6 / z]); ctx.strokeStyle = '#ffe070'; ctx.strokeRect(sp.x, sp.y, sp.e.w, sp.e.h); ctx.setLineDash([]); }
      if (o.kind !== R.KIND.SUB) { ctx.strokeStyle = '#fff'; ctx.strokeRect(R.cellX(x), R.cellY(y), 32, 32); }
    } else if (['start'].includes(S.tool)) {
      const [x, y] = R.worldCell(h.x, h.y); ctx.strokeStyle = '#fff'; ctx.strokeRect(R.cellX(x), R.cellY(y), 32, 32);
    }
  }

  // ---------------------------------------------------------------- minimap
  function mmGeom() {
    // the minimap shows the game map (cells 0..W, 0..H)
    const m = S.map, ws = { w: m.W * 32, h: m.H * 32 }, s = Math.min(mm.width / ws.w, mm.height / ws.h);
    return { s, ox: (mm.width - ws.w * s) / 2 - R.cellX(0) * s, oy: (mm.height - ws.h * s) / 2 - R.cellY(0) * s };
  }
  let mmCache = null, mmT = 0;
  function drawMinimap(full) {
    clearTimeout(mmT); mmT = setTimeout(() => { mmCache = null; paintMinimap(); }, full ? 0 : 120);
  }
  function paintMinimap() {
    const m = S.map; mctx.fillStyle = '#000'; mctx.fillRect(0, 0, mm.width, mm.height); if (!m) return;
    const g = mmGeom(), set = S.gfx.tilesets[m.tileset];
    if (!mmCache) {
      mmCache = document.createElement('canvas'); mmCache.width = mm.width; mmCache.height = mm.height; const c = mmCache.getContext('2d');
      c.save(); c.translate(g.ox, g.oy); c.scale(g.s, g.s); c.beginPath(); c.rect(R.cellX(0), R.cellY(0), m.W * 32, m.H * 32); c.clip();
      for (let y = 0; y < m.ch; y++) for (let x = 0; x < m.cw; x++) {
        const i = y * m.cw + x, cx = x * 256 + (y & 1) * 128, cy = y * 64;
        c.fillStyle = set ? set.avg[m.tIdx[i]] : FALLBACK[m.tC[i]] || '#444';
        drawDiamond(c, cx, cy, 130, 66); c.fill();
      }
      for (const o of m.objects) { const [x, y] = objPos(o); c.fillStyle = o.kind === R.KIND.RES ? '#ffe040' : o.kind === R.KIND.SUB ? '#e050e0' : '#1a5a12'; c.fillRect(x - 40, y - 40, 112, 112); }
      c.restore();
    }
    mctx.drawImage(mmCache, 0, 0);
    m.players.forEach((p, i) => { mctx.fillStyle = (R.COLORS[p.team] || R.COLORS[i % 8])[1]; mctx.strokeStyle = '#000'; const X = g.ox + (R.cellX(p.x) + 16) * g.s, Y = g.oy + (R.cellY(p.y) + 16) * g.s; mctx.fillRect(X - 3, Y - 3, 7, 7); mctx.strokeRect(X - 3, Y - 3, 7, 7); });
    const tl = s2w(0, 0), br = s2w(cv.width, cv.height);
    mctx.strokeStyle = '#fff'; mctx.lineWidth = 1; mctx.strokeRect(g.ox + tl.x * g.s, g.oy + tl.y * g.s, (br.x - tl.x) * g.s, (br.y - tl.y) * g.s);
  }
  function mmMove(ev) {
    if (!S.map) return; const r = mm.getBoundingClientRect(), g = mmGeom();
    const x = (ev.clientX - r.left) * mm.width / r.width, y = (ev.clientY - r.top) * mm.height / r.height;
    S.cam.x = (x - g.ox) / g.s; S.cam.y = (y - g.oy) / g.s; draw(); paintMinimap();
  }
  mm.addEventListener('mousedown', (e) => { mmMove(e); const mv = (ev) => mmMove(ev), up = () => { removeEventListener('mousemove', mv); removeEventListener('mouseup', up); }; addEventListener('mousemove', mv); addEventListener('mouseup', up); });

  // ----------------------------------------------------------------- editing
  // 크기 0 = '벽': 언덕류는 꼭대기 없이 둘레의 절벽(경계) 브러시만 칠해 가장 얇은 벽을 만든다.
  // 언덕(5)·고지대 땅의 경계는 2층 절벽(4), 높은 언덕(7)·고지대 물(8)의 경계는 3층 절벽(6).
  const WALL_BAND = { 5: 4, 7: 6, 8: 6 };
  function paintBrush() { return S.brushSize === 0 && WALL_BAND[S.brush] != null ? WALL_BAND[S.brush] : S.brush; }
  function paintSize() { return Math.max(1, S.brushSize); }
  function applyShape(shape) {
    const m = S.map, list = R.shapeVerts(m, shape); if (!list.length) return;
    const brush = paintBrush();
    let ch = R.paintVerts(m, list, brush);
    ch = ch.concat(R.smoothDiagonals(m, ch, brush, S.brushSize === 0));
    for (const [i, b] of ch) noteVert(i, b);
    const verts = ch.map(c => c[0]);
    for (const [A, B] of list) for (let dA = -1; dA <= 1; dA++) for (let dB = -1; dB <= 1; dB++) { const [u, vv] = R.fromAB(A + dA, B + dB); const i = R.vIndex(m, u, vv); if (i >= 0) verts.push(i); }
    for (const [k, before] of R.retileAround(m, verts, false)) noteTile(k, before);
    draw(); drawMinimap();
  }
  function paintAt(wx, wy) {
    const v = vertexAt(wx, wy); if (!v) return;
    applyShape({ type: S.shape === 'square' ? 'square' : 'circle', u: v[0], v: v[1], size: paintSize() });
  }
  function placeRamp(wx, wy) {
    const m = S.map, r = R.suggestRamp(m, wx, wy);
    if (r.error) { toast(r.error, 3500); return; }
    if (r.near) { toast('다른 언덕 입구·다리와 너무 가깝습니다 (' + R.SUB_SPACING + '칸 이상 떨어뜨리세요)', 3500); return; }
    noteObjs();
    const o = { kind: R.KIND.SUB, id: r.id, sub: 0xcd, x: r.x, y: r.y, val: 0xcccccccc, raw: newObjRaw(R.KIND.SUB) };
    m.objects.push(o); subTerrain(o); S.sel = o; showSel(); draw(); drawMinimap();
    toast(R.SUBTERRAIN[r.id] + ' 배치됨', 2500);
  }
  function stampTile(wx, wy) {
    const m = S.map, t = tileAt(wx, wy); if (!t) return; const k = t[1] * m.cw + t[0];
    const def = R.TILE_DEF[S.tileSel]; if (!def) { toast('이 타일은 지형표에 없는 타일입니다'); return; }
    if (m.tIdx[k] === S.tileSel) return;
    noteTile(k, [m.tIdx[k], m.tA[k], m.tB[k], m.tC[k]]);
    const [a, b] = def, row = R.TRANS[a]; let pc = 0; for (let i = 0; i < 4; i++) if (b & (1 << i)) pc++;
    m.tIdx[k] = S.tileSel; m.tA[k] = a; m.tB[k] = b; m.tC[k] = pc >= 2 ? row[1] : row[2];
    // keep vertex model in sync with the stamped tile's corners
    const c = R.cornersOf(a, b), u = 2 * t[0] + (t[1] & 1);
    for (const [uu, vv, ty] of [[u, t[1] - 1, c.N], [u + 1, t[1], c.E], [u, t[1] + 1, c.S], [u - 1, t[1], c.W]]) { const i = R.vIndex(m, uu, vv); if (i >= 0 && m.vert[i] !== ty) { noteVert(i, m.vert[i]); m.vert[i] = ty; } }
    draw(); drawMinimap();
  }
  function pickTile(wx, wy) { const m = S.map, t = tileAt(wx, wy); if (!t) return; S.tileSel = m.tIdx[t[1] * m.cw + t[0]]; setTool('tile'); buildPalette(); }
  function newObjRaw(kind) {
    const r = new Uint8Array(20); r.fill(0xcc);
    r[0] = kind === R.KIND.SUB ? 0xcd : 0; r[1] = 0; r[2] = kind; r[3] = 0xcc; r[5] = 0; r[6] = 0xcd; r[7] = 0xcc; return r;
  }
  // cell for a new object under the cursor; bridges/ramps are anchored at their top-left, so centre them on the cursor
  function placeCell(wx, wy, subId) {
    if (S.tool === 'sub' || subId != null) {
      const sp = S.spr[S.map.tileset], e = sp && sp.meta.sub[subId != null ? subId : S.subSel];
      if (e) return [Math.round((wx - e.w / 2) / 32), Math.round((wy - e.h / 2) / 32)];
    }
    return R.worldCell(wx, wy);
  }
  function subCheck(id, wx, wy, ignore) {
    const a = R.findSubAnchor(S.map, id, wx, wy, ignore);
    if (!a) return { error: id <= 1 ? '다리는 물 위, 양쪽이 땅에 닿는 곳에만 놓을 수 있습니다' : id >= 6 ? '폭포는 고지대 물 가장자리 절벽에만 놓을 수 있습니다' : '언덕 입구는 맞는 높이의 언덕 가장자리(절벽)에 붙여야 놓을 수 있습니다' };
    if (a.near) return { error: '다른 언덕 입구·다리와 너무 가깝습니다 (' + R.SUB_SPACING + '칸 이상 떨어뜨리세요)', a };
    return { a };
  }
  function subTerrain(o) { vertsChanged(R.applySubTerrain(S.map, o.id, o.x, o.y)); }
  // record changed vertices for undo and retile the tiles around them
  function vertsChanged(ch) {
    const m = S.map; if (!ch.length) return;
    for (const [i, b] of ch) noteVert(i, b);
    const verts = ch.map(c => c[0]);
    for (const [i] of ch) { const u = (i % m.VW) - 1, v = Math.floor(i / m.VW) - 1; for (const [du, dv] of [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, -1], [1, -1], [-1, 1]]) { const j = R.vIndex(m, u + du, v + dv); if (j >= 0) verts.push(j); } }
    for (const [k, before] of R.retileAround(m, verts, false)) noteTile(k, before);
  }
  const isBridge = id => id === 0 || id === 1;
  // one click on water: reshape the channel/banks to the bridge template and fill ground to both shores
  function placeBridge(wx, wy) {
    const m = S.map, p = R.planBridge(m, S.subSel, wx, wy); if (p.error) { toast(p.error, 3500); return; }
    noteObjs(); vertsChanged(R.applyBridgePlan(m, p));
    const o = { kind: R.KIND.SUB, id: p.id, sub: 0xcd, x: p.x, y: p.y, val: 0xcccccccc, raw: newObjRaw(R.KIND.SUB) };
    m.objects.push(o); S.sel = o; showSel(); draw(); drawMinimap();
    toast(R.SUBTERRAIN[p.id] + ' 배치됨' + (p.run[0] + p.run[1] ? ' (양쪽 땅까지 ' + (p.run[0] + p.run[1]) + '줄 메움)' : ''), 2500);
  }
  function placeObject(wx, wy) {
    if (S.tool === 'sub' && isBridge(S.subSel)) { placeBridge(wx, wy); return; }
    if (S.tool === 'sub') {
      const r = subCheck(S.subSel, wx, wy); if (r.error) { toast(r.error, 3000); return; }
      noteObjs(); const o = { kind: R.KIND.SUB, id: S.subSel, sub: 0xcd, x: r.a.x, y: r.a.y, val: 0xcccccccc, raw: newObjRaw(R.KIND.SUB) };
      S.map.objects.push(o); subTerrain(o); S.sel = o; showSel(); draw(); drawMinimap(); return;
    }
    const m = S.map, [x, y] = placeCell(wx, wy);
    if (x < -20 || y < -20 || x >= m.W || y >= m.H) return;
    const X = Math.max(0, x), Y = Math.max(0, y);
    noteObjs();
    let o;
    if (S.tool === 'res') {
      const ids = R.resourceIds(m.tileset), gold = S.res === 'gold';
      o = { kind: R.KIND.RES, id: gold ? ids.gold : ids.well, sub: gold ? 1 : 0, x: X, y: Y, val: +$('resAmount').value || 0 };
    } else if (S.tool === 'deco') o = { kind: R.KIND.DECO, id: S.decoSel, sub: 0xcd, x: X, y: Y, val: 0xcccccccc };
    else o = { kind: R.KIND.SUB, id: S.subSel, sub: 0xcd, x: X, y: Y, val: 0xcccccccc };
    o.raw = newObjRaw(o.kind); m.objects.push(o); S.sel = o; showSel(); draw(); drawMinimap();
  }
  function hitObject(wx, wy) {
    const m = S.map; let best = null, bd = 1e9;
    if ($('lyStart').checked) m.players.forEach((p) => { const d = Math.hypot(wx - (R.cellX(p.x) + 16), (wy - (R.cellY(p.y) + 16)) * 2); if (d < 80 && d < bd) { bd = d; best = p; } });
    if ($('lyObj').checked) for (const o of m.objects) {
      const sp = spriteOf(o), [ox, oy] = objPos(o); let d;
      if (sp) {
        if (wx < sp.x || wy < sp.y || wx > sp.x + sp.e.w || wy > sp.y + sp.e.h) continue;
        d = Math.hypot(wx - (ox + 16), wy - (oy + 16)) * (o.kind === R.KIND.SUB ? 3 : 1); if (d < bd) { bd = d; best = o; }
      } else { d = Math.hypot(wx - (ox + 16), (wy - (oy + 16)) * 1.6); if (d < 60 && d < bd) { bd = d; best = o; } }
    }
    return best;
  }
  function deleteSel() {
    const m = S.map; if (!S.sel || !m.objects.includes(S.sel)) return;
    beginAct(); noteObjs(); m.objects.splice(m.objects.indexOf(S.sel), 1); endAct(); S.sel = null; showSel(); draw(); drawMinimap();
  }
  function showSel() {
    const el = $('selInfo'), o = S.sel, m = S.map;
    if (!o) { el.innerHTML = '오브젝트를 클릭해 선택, 드래그로 이동, <span class="kbd">Del</span>로 삭제'; return; }
    if (m.players.includes(o)) { el.innerHTML = '<b>P' + (m.players.indexOf(o) + 1) + ' 시작 위치</b> (' + o.x + ', ' + o.y + ') · 종족 ' + (R.RACES[o.race] || '?'); return; }
    let name = '#' + o.id;
    if (o.kind === R.KIND.RES) name = o.id === R.resourceIds(m.tileset).gold ? '금광' : '우물';
    else if (o.kind === R.KIND.DECO) { const d = R.decorList(m.tileset).find(x => x.id === o.id); name = d ? d.name : name; }
    else if (o.kind === R.KIND.SUB) name = R.SUBTERRAIN[o.id] || name;
    el.innerHTML = '<b>' + name + '</b> (' + o.x + ', ' + o.y + ')' + (o.kind === R.KIND.RES ? ' 매장량 <input type="number" id="selVal" value="' + o.val + '" step="500" style="width:80px">' : '') + ' <button id="selDel">삭제</button>';
    const v = $('selVal'); if (v) v.onchange = () => { beginAct(); noteObjs(); o.val = Math.max(0, +v.value | 0); endAct(); draw(); };
    $('selDel').onclick = deleteSel;
  }

  // ------------------------------------------------------------------ mouse
  let panDrag = null;
  cv.addEventListener('contextmenu', e => e.preventDefault());
  cv.addEventListener('mousedown', (e) => {
    if (!S.map) return;
    const dpr = S.dpr || 1, w = s2w(e.offsetX * dpr, e.offsetY * dpr);
    if (e.button === 1 || e.button === 2 || S.tool === 'pan' || S.space) { panDrag = { sx: e.clientX, sy: e.clientY, cx: S.cam.x, cy: S.cam.y }; return; }
    if (e.button !== 0) return;
    beginAct();
    switch (S.tool) {
      case 'brush':
        if (S.shape === 'rect' || S.shape === 'line') { S.shapeDrag = { x0: w.x, y0: w.y, x1: w.x, y1: w.y }; }
        else { S.painting = true; paintAt(w.x, w.y); }
        break;
      case 'ramp': placeRamp(w.x, w.y); break;
      case 'tile': S.painting = true; stampTile(w.x, w.y); break;
      case 'pick': pickTile(w.x, w.y); break;
      case 'start': {
        const p = S.map.players[S.startSel]; if (!p) break; notePls();
        const [cx, cy] = R.worldCell(w.x, w.y);
        let x = Math.min(S.map.W - 1, Math.max(0, cx)), y = Math.min(S.map.H - 1, Math.max(0, cy));
        if (R.startProblems(S.map, x, y)) { const n = R.nearestStart(S.map, x, y); if (n) { [x, y] = n; toast('물/절벽을 피해 본진을 지을 수 있는 가장 가까운 곳으로 옮겼습니다'); } else toast('근처에 본진을 지을 평지가 없습니다', 3500); }
        p.x = x; p.y = y; S.sel = p; showSel(); draw(); drawMinimap(); break;
      }
      case 'res': case 'deco': case 'sub': placeObject(w.x, w.y); break;
      case 'erase': { const o = hitObject(w.x, w.y); if (o && S.map.objects.includes(o)) { noteObjs(); S.map.objects.splice(S.map.objects.indexOf(o), 1); draw(); drawMinimap(); } S.painting = true; break; }
      case 'select': {
        const o = hitObject(w.x, w.y); S.sel = o; showSel(); draw();
        if (o) { if (S.map.players.includes(o)) notePls(); else noteObjs(); S.drag = { o, dx: o.x * 32 - w.x, dy: o.y * 32 - w.y }; }
        break;
      }
    }
  });
  addEventListener('mousemove', (e) => {
    if (panDrag) { S.cam.x = panDrag.cx - (e.clientX - panDrag.sx) / S.cam.z * (S.dpr || 1); S.cam.y = panDrag.cy - (e.clientY - panDrag.sy) / S.cam.z * (S.dpr || 1); draw(); paintMinimap(); return; }
    if (!S.map || e.target !== cv) { if (S.hover && e.target !== cv) { S.hover = null; draw(); } if (!S.drag && !S.painting) return; }
    const r = cv.getBoundingClientRect(), dpr = S.dpr || 1, w = s2w((e.clientX - r.left) * dpr, (e.clientY - r.top) * dpr);
    S.hover = w; updateStatus(w);
    if (S.painting) { if (S.tool === 'brush') paintAt(w.x, w.y); else if (S.tool === 'tile') stampTile(w.x, w.y); else if (S.tool === 'erase') { const o = hitObject(w.x, w.y); if (o && S.map.objects.includes(o)) { noteObjs(); S.map.objects.splice(S.map.objects.indexOf(o), 1); drawMinimap(); } } }
    if (S.shapeDrag) { S.shapeDrag.x1 = w.x; S.shapeDrag.y1 = w.y; }
    if (S.drag && S.drag.o.kind === R.KIND.SUB) {
      const o = S.drag.o, [w2, h2] = R.SUB_SIZE[o.id], cx = w.x + S.drag.dx + w2 / 2, cy = w.y + S.drag.dy + h2 / 2;
      const r = subCheck(o.id, cx, cy, o); if (r.a && !r.error) { o.x = r.a.x; o.y = r.a.y; showSel(); drawMinimap(); }
    } else if (S.drag) { const o = S.drag.o; o.x = Math.max(0, Math.min(S.map.W - 1, Math.round((w.x + S.drag.dx) / 32))); o.y = Math.max(0, Math.min(S.map.H - 1, Math.round((w.y + S.drag.dy) / 32))); showSel(); drawMinimap(); }
    draw();
  });
  addEventListener('mouseup', () => {
    if (panDrag) { panDrag = null; return; }
    if (S.shapeDrag && S.map) {
      const g = S.shapeDrag; S.shapeDrag = null;
      if (S.shape === 'rect') applyShape({ type: 'rect', x0: g.x0, y0: g.y0, x1: g.x1, y1: g.y1 });
      else applyShape({ type: 'line', pts: [{ x: g.x0, y: g.y0 }, { x: g.x1, y: g.y1 }], size: paintSize() });
    }
    if (S.drag && S.drag.o.kind === R.KIND.SUB) { subTerrain(S.drag.o); draw(); drawMinimap(); }
    if (S.act) endAct(); S.painting = false; S.drag = null; });
  cv.addEventListener('wheel', (e) => {
    if (!S.map) return; e.preventDefault();
    const dpr = S.dpr || 1, before = s2w(e.offsetX * dpr, e.offsetY * dpr);
    S.cam.z = Math.min(2, Math.max(0.05, S.cam.z * (e.deltaY < 0 ? 1.2 : 1 / 1.2)));
    const after = s2w(e.offsetX * dpr, e.offsetY * dpr); S.cam.x += before.x - after.x; S.cam.y += before.y - after.y;
    $('zoomLbl').textContent = Math.round(S.cam.z * 100) + '%'; draw(); paintMinimap();
  }, { passive: false });
  function zoom(f) { if (!S.map) return; S.cam.z = Math.min(2, Math.max(0.05, S.cam.z * f)); $('zoomLbl').textContent = Math.round(S.cam.z * 100) + '%'; draw(); paintMinimap(); }

  addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || document.querySelector('dialog[open]')) return;
    const k = e.key.toLowerCase();
    if (e.ctrlKey && k === 'z') { e.preventDefault(); undo(); }
    else if (e.ctrlKey && (k === 'y' || (e.shiftKey && k === 'z'))) { e.preventDefault(); redo(); }
    else if (e.ctrlKey && k === 's') { e.preventDefault(); save(e.shiftKey); }
    else if (e.ctrlKey && k === 'o') { e.preventDefault(); openMap(); }
    else if (e.ctrlKey && k === 'n') { e.preventDefault(); showNew(); }
    else if (k === 'delete' || k === 'backspace') { deleteSel(); }
    else if (k === '+' || k === '=') zoom(1.25); else if (k === '-') zoom(0.8);
    else if (k === 'g') { S.grid = !S.grid; $('bGrid').classList.toggle('on', S.grid); draw(); }
    else if (k === ' ') { S.space = true; cv.style.cursor = 'grab'; e.preventDefault(); }
    else if (['arrowleft', 'arrowright', 'arrowup', 'arrowdown'].includes(k) && S.map) {
      const d = 300 / S.cam.z; if (k === 'arrowleft') S.cam.x -= d; if (k === 'arrowright') S.cam.x += d; if (k === 'arrowup') S.cam.y -= d; if (k === 'arrowdown') S.cam.y += d; e.preventDefault(); draw(); paintMinimap();
    } else if (k >= '1' && k <= '9' && !e.ctrlKey) { setBrush(+k - 1); }
    else if (k === 'escape') { S.sel = null; showSel(); draw(); }
  });
  addEventListener('keyup', (e) => { if (e.key === ' ') { S.space = false; cv.style.cursor = 'crosshair'; } });

  // ------------------------------------------------------------------ status
  function updateStatusMap() { const m = S.map; $('stMap').textContent = m ? fileName() + ' · ' + R.TILESETS[m.tileset].name + ' · ' + m.W + '×' + m.H + ' · 오브젝트 ' + m.objects.length : '-'; }
  function updateStatus(w) {
    const m = S.map; if (!m) return;
    $('stCell').textContent = R.worldCell(w.x, w.y).join(', ');
    const t = tileAt(w.x, w.y);
    if (t) {
      const i = t[1] * m.cw + t[0], c = R.cornersOf(m.tA[i], m.tB[i]), b = R.TILESETS[m.tileset].brushes;
      $('stTile').textContent = '(' + t[0] + ',' + t[1] + ') #' + m.tIdx[i] + ' ' + (R.TRANS[m.tA[i]] || ['?'])[0] + ' m' + m.tB[i];
      const uniq = [...new Set([c.N, c.E, c.S, c.W])].map(x => b[x]); $('stTerr').textContent = uniq.join(' / ');
    }
  }

  // ------------------------------------------------------------------- tools UI
  function setTool(t) {
    S.tool = t;
    document.querySelectorAll('[data-tool]').forEach(b => b.classList.toggle('on', b.dataset.tool === t && (t !== 'res' || b.dataset.res === S.res)));
    document.querySelectorAll('#brushBtns button, #easyBtns button').forEach(b => b.classList.toggle('on', t === 'brush' && +b.dataset.b === S.brush));
    document.querySelectorAll('#shapeBtns button').forEach(b => b.classList.toggle('on', b.dataset.shape === S.shape));
    document.querySelectorAll('#startBtns button').forEach(b => b.classList.toggle('on', t === 'start' && +b.dataset.p === S.startSel));
    document.querySelectorAll('#decoBtns button').forEach(b => b.classList.toggle('on', t === 'deco' && +b.dataset.id === S.decoSel));
    document.querySelectorAll('#subBtns button').forEach(b => b.classList.toggle('on', t === 'sub' && +b.dataset.id === S.subSel));
    cv.style.cursor = t === 'pan' ? 'grab' : 'crosshair'; draw();
  }
  function setBrush(b) { if (!S.map || b > 8) return; S.brush = b; setTool('brush'); }
  const EASY = [[0, '물 · 강'], [1, '평지'], [2, '풀밭'], [3, '돌 바닥'], [5, '언덕 (1단)'], [7, '높은 언덕 (2단)'], [8, '고지대 물']];
  function buildEasy() {
    const m = S.map, ts = m ? m.tileset : 1, names = R.TILESETS[ts].brushes, set = m && S.gfx.tilesets[ts], box = $('easyBtns'); box.innerHTML = '';
    for (const [b, label] of EASY) {
      const bt = document.createElement('button'); bt.dataset.b = b;
      const c = document.createElement('canvas'); c.width = 64; c.height = 32; const g = c.getContext('2d');
      const r = R.recordFor(b, b, b, b), k = r ? R.tilesFor(r.a, r.b)[0] : -1;
      if (set && set.small[k]) g.drawImage(set.small[k], 0, 0); else { g.fillStyle = FALLBACK[b]; g.beginPath(); g.moveTo(32, 0); g.lineTo(64, 16); g.lineTo(32, 32); g.lineTo(0, 16); g.fill(); }
      if (b >= 5) { g.fillStyle = '#fff'; g.font = 'bold 12px sans-serif'; g.fillText(b === 5 ? '▲' : b === 7 ? '▲▲' : '▲~', 4, 20); }
      bt.appendChild(c); const t = document.createElement('span'); t.innerHTML = label + '<small>' + names[b] + '</small>'; bt.appendChild(t);
      bt.onclick = () => setBrush(b); box.appendChild(bt);
    }
    setTool(S.tool);
  }
  function rebuildToolButtons() {
    const m = S.map, ts = m ? m.tileset : 1, names = R.TILESETS[ts].brushes;
    buildEasy();
    const bb = $('brushBtns'); bb.innerHTML = '';
    names.forEach((n, i) => { const b = document.createElement('button'); b.dataset.b = i; b.innerHTML = '<span class="swatch" style="background:' + FALLBACK[i] + '"></span>' + (i + 1) + '. ' + n; b.onclick = () => setBrush(i); bb.appendChild(b); });
    const sb = $('startBtns'); sb.innerHTML = '';
    (m ? m.players : []).forEach((p, i) => { const b = document.createElement('button'); b.dataset.p = i; b.innerHTML = '<span class="swatch" style="background:' + (R.COLORS[p.team] || R.COLORS[i])[1] + '"></span>P' + (i + 1); b.onclick = () => { S.startSel = i; setTool('start'); }; sb.appendChild(b); });
    const mk = (box, o, label, on) => { const b = document.createElement('button'); b.appendChild(thumb(o, 72, 48)); const t = document.createElement('span'); t.textContent = label; b.appendChild(t); b.onclick = on; box.appendChild(b); return b; };
    const db = $('decoBtns'); db.innerHTML = '';
    if (m) R.decorList(ts).forEach(d => { mk(db, { kind: R.KIND.DECO, id: d.id, x: 0, y: 0 }, d.name, () => { S.decoSel = d.id; setTool('deco'); }).dataset.id = d.id; });
    const ub = $('subBtns'); ub.innerHTML = '';
    if (m) R.SUBTERRAIN.forEach((n, i) => { mk(ub, { kind: R.KIND.SUB, id: i, x: 0, y: 0 }, n, () => { S.subSel = i; setTool('sub'); }).dataset.id = i; });
    const rb = $('resBtns'); rb.innerHTML = '';
    if (m) { const ids = R.resourceIds(ts);
      const g = mk(rb, { kind: R.KIND.RES, id: ids.gold, x: 0, y: 0 }, '금광', () => { S.res = 'gold'; $('resAmount').value = 5000; setTool('res'); }); g.dataset.tool = 'res'; g.dataset.res = 'gold';
      const w = mk(rb, { kind: R.KIND.RES, id: ids.well, x: 0, y: 0 }, '우물 (물)', () => { S.res = 'well'; $('resAmount').value = 3000; setTool('res'); }); w.dataset.tool = 'res'; w.dataset.res = 'well'; }
    setTool(S.tool); updateStatusMap();
  }
  function buildPalette() {
    if ($('easyBtns')) buildEasy();
    const box = $('palette'); box.innerHTML = '';
    const set = S.map && S.gfx.tilesets[S.map.tileset];
    const info = (k) => { const d = R.TILE_DEF[k]; return d ? R.TRANS[d[0]][0] + ' / 마스크 ' + d[1] : '지형표 밖 타일'; };
    $('tileInfo').textContent = '선택 타일: #' + S.tileSel + ' (' + info(S.tileSel) + ')';
    for (let k = 0; k < 200; k++) {
      if (!(k in R.TILE_DEF)) continue;
      const c = document.createElement('canvas'); c.width = 64; c.height = 32; c.title = '#' + k + ' ' + info(k);
      const g = c.getContext('2d');
      if (set && set.small[k]) g.drawImage(set.small[k], 0, 0);
      else { const [a, b] = R.TILE_DEF[k], cr = R.cornersOf(a, b); [['N', 32, 0], ['E', 64, 16], ['S', 32, 32], ['W', 0, 16]].forEach(([n, x, y]) => { g.fillStyle = FALLBACK[cr[n]]; g.beginPath(); g.moveTo(32, 16); g.lineTo(x, y); g.lineTo(n === 'N' ? 64 : n === 'E' ? 32 : n === 'S' ? 0 : 32, n === 'N' ? 16 : n === 'E' ? 32 : n === 'S' ? 16 : 0); g.fill(); }); g.fillStyle = '#fff'; g.font = '10px sans-serif'; g.fillText(k, 2, 10); }
      if (k === S.tileSel) c.className = 'sel';
      c.onclick = () => { S.tileSel = k; setTool('tile'); buildPalette(); };
      box.appendChild(c);
    }
  }
  document.querySelectorAll('[data-tool]').forEach(b => b.onclick = () => { if (b.dataset.res) S.res = b.dataset.res; if (b.dataset.res) $('resAmount').value = b.dataset.res === 'gold' ? 5000 : 3000; setTool(b.dataset.tool); });
  document.querySelectorAll('#shapeBtns button').forEach(b => b.onclick = () => { S.shape = b.dataset.shape; if (S.tool !== 'brush') S.tool = 'brush'; setTool('brush'); });
  $('brushSize').oninput = (e) => { S.brushSize = +e.target.value; $('brushSizeLbl').textContent = S.brushSize || '벽'; draw(); };
  document.querySelectorAll('.grp>h3').forEach(h => h.onclick = () => h.parentElement.classList.toggle('closed'));
  ['lyObj', 'lyStart', 'lyMapEdge'].forEach(id => $(id).onchange = () => draw());

  // ---------------------------------------------------------------- dialogs
  function fillTs(sel) { sel.innerHTML = ''; R.TILESETS.forEach((t, i) => { const o = document.createElement('option'); o.value = i; o.textContent = i + ' · ' + t.name + ' (' + t.file + ')'; sel.appendChild(o); }); }
  function showNew() {
    if (S.dirty && !confirm('저장하지 않은 변경 내용이 있습니다. 계속할까요?')) return;
    fillTs($('nTs')); $('nTs').value = 1;
    const fillBase = () => { const s = $('nBase'); const v = s.value; s.innerHTML = ''; R.TILESETS[+$('nTs').value].brushes.forEach((n, i) => { const o = document.createElement('option'); o.value = i; o.textContent = (i + 1) + '. ' + n; s.appendChild(o); }); s.value = v || 1; };
    $('nTs').onchange = fillBase; fillBase(); $('nBase').value = 1;
    $('nSize').onchange = () => { const c = $('nSize').value === 'custom'; $('nW').style.display = $('nH').style.display = c ? '' : 'none'; };
    $('dlgNew').showModal();
  }
  $('nOk').onclick = async () => {
    let W, H; if ($('nSize').value === 'custom') { W = Math.max(40, Math.min(256, Math.round(+$('nW').value / 8) * 8)); H = Math.max(40, Math.min(256, Math.round(+$('nH').value / 2) * 2)); } else[W, H] = $('nSize').value.split('x').map(Number);
    const m = R.newMap({ W, H, tileset: +$('nTs').value, players: +$('nPl').value, base: +$('nBase').value });
    $('dlgNew').close();
    S.map = m; S.name = ($('nName').value || 'New Map').replace(/[\\/:*?"<>|]/g, ''); S.fileHandle = null; S.srvName = null; S.undo = []; S.redo = []; S.sel = null;
    $('welcome').style.display = 'none';
    await ensureTileset(m.tileset); rebuildToolButtons(); buildPalette(); centerView(); setDirty(true); draw(); drawMinimap(true);
  };
  function showPlayers() {
    const m = S.map; if (!m) return;
    const t = $('plTable');
    let h = '<tr><th></th><th>종족</th><th>색/팀 번호</th><th>X</th><th>Y</th><th>자원 1</th><th>자원 2</th><th>자원 3</th><th>플래그</th></tr>';
    m.players.forEach((p, i) => {
      h += '<tr data-i="' + i + '"><td>P' + (i + 1) + '</td><td><select data-f="race">' + R.RACES.map((r, k) => '<option value="' + k + '"' + (k === p.race ? ' selected' : '') + '>' + r + '</option>').join('') + '</select></td>' +
        '<td><select data-f="team">' + R.COLORS.map((c, k) => '<option value="' + k + '"' + (k === p.team ? ' selected' : '') + '>' + k + ' · ' + c[0] + '</option>').join('') + '</select></td>' +
        ['x', 'y', 'gold', 'water', 'res3'].map(f => '<td><input type="number" data-f="' + f + '" value="' + p[f] + '"></td>').join('') +
        '<td><input type="number" data-f="flags" value="' + p.flags + '" min="0" max="255" style="width:52px"></td></tr>';
    });
    t.innerHTML = h;
    t.querySelectorAll('[data-f]').forEach(el => el.onchange = () => {
      const p = m.players[+el.closest('tr').dataset.i], f = el.dataset.f; beginAct(); notePls(); p[f] = Math.max(0, +el.value | 0);
      if (f === 'x') p.x = Math.min(p.x, m.W - 1); if (f === 'y') p.y = Math.min(p.y, m.H - 1);
      if (f === 'flags') p.flags &= 255; endAct(); rebuildToolButtons(); draw(); drawMinimap();
    });
    $('dlgPlayers').showModal();
  }
  function showTeams() {
    const m = S.map; if (!m) return; const b = $('teamBody'); b.innerHTML = '';
    m.teams.forEach((t, i) => { const r = document.createElement('div'); r.className = 'row'; r.innerHTML = '<label>팀 ' + (i + 1) + '</label>'; const inp = document.createElement('input'); inp.value = t.name; inp.maxLength = 31; inp.style.width = '220px'; inp.onchange = () => { t.name = inp.value.replace(/[^\x20-\x7e]/g, ''); inp.value = t.name; t._dirty = true; setDirty(true); }; r.appendChild(inp); b.appendChild(r); });
    const n = document.createElement('div'); n.className = 'hint'; n.textContent = '팀 이름은 영문/숫자만 저장됩니다 (원본 형식).'; b.appendChild(n);
    $('dlgTeams').showModal();
  }
  function showProps() {
    const m = S.map; if (!m) return; fillTs($('pTs'));
    $('pName').value = S.name; $('pTs').value = m.tileset; $('pW').value = m.W; $('pH').value = m.H; $('pPl').value = m.maxPlayers; $('dlgProps').showModal();
  }
  $('pOk').onclick = async () => {
    const m = S.map; S.name = ($('pName').value || S.name).replace(/[\\/:*?"<>|]/g, '');
    const ts = +$('pTs').value, W = Math.max(40, Math.min(256, Math.round(+$('pW').value / 8) * 8)), H = Math.max(40, Math.min(256, Math.round(+$('pH').value / 2) * 2)), np = +$('pPl').value;
    if (ts !== m.tileset) {
      // remap decoration/resource ids to the new tileset's numbering
      const oi = R.resourceIds(m.tileset), ni = R.resourceIds(ts), nd = R.decorList(ts).length;
      m.objects = m.objects.filter(o => {
        if (o.kind === R.KIND.RES) { o.id = o.id === oi.gold ? ni.gold : ni.well; return true; }
        if (o.kind === R.KIND.DECO) return o.id < nd; return true;
      });
      m.tileset = ts;
    }
    if (W !== m.W || H !== m.H) resizeMap(m, W, H);
    if (np !== m.maxPlayers) {
      while (m.players.length < np) {
        const i = m.players.length, raw = new Uint8Array(24); raw[0] = i; raw[1] = 0x20;
        const ang = (i / np) * Math.PI * 2 + 0.4;
        m.players.push({ raw, flags: 0x20, race: i % 3, team: i, x: Math.round(m.W / 2 + Math.cos(ang) * m.W * 0.35), y: Math.round(m.H / 2 + Math.sin(ang) * m.H * 0.35), gold: 300, water: 500, res3: 50 });
      }
      m.players.length = np; m.maxPlayers = np;
    }
    $('dlgProps').close(); S.undo = []; S.redo = [];
    await ensureTileset(m.tileset); rebuildToolButtons(); buildPalette(); setDirty(true); draw(); drawMinimap(true);
  };
  function resizeMap(m, W, H) {
    const cw = Math.ceil(W / 8), ch = H >> 1, old = { cw: m.cw, ch: m.ch, tIdx: m.tIdx, tA: m.tA, tB: m.tB, tC: m.tC };
    const n = cw * ch; m.tIdx = new Uint16Array(n); m.tA = new Uint8Array(n); m.tB = new Uint8Array(n); m.tC = new Uint8Array(n);
    const fill = R.recordFor(1, 1, 1, 1);
    for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) {
      const k = y * cw + x;
      if (x < old.cw && y < old.ch) { const o = y * old.cw + x; m.tIdx[k] = old.tIdx[o]; m.tA[k] = old.tA[o]; m.tB[k] = old.tB[o]; m.tC[k] = old.tC[o]; }
      else { m.tA[k] = fill.a; m.tB[k] = 15; m.tC[k] = 1; m.tIdx[k] = R.tilesFor(fill.a, 15)[(x * 7 + y * 3) % 10]; }
    }
    m.W = W; m.H = H; m.cw = cw; m.ch = ch; m.s3tail = new Uint8Array(0);
    R.initVerts(m);
    m.objects = m.objects.filter(o => o.x < W && o.y < H);
    m.players.forEach(p => { p.x = Math.min(p.x, W - 1); p.y = Math.min(p.y, H - 1); });
  }
  function centerView() {
    const m = S.map, r = $('view').getBoundingClientRect(), dpr = S.dpr || 1;
    S.cam.z = Math.max(0.05, Math.min(0.5, Math.min(r.width * dpr / (m.W * 32), r.height * dpr / (m.H * 32)) * 0.95));
    S.cam.x = R.cellX(m.W / 2); S.cam.y = R.cellY(m.H / 2); $('zoomLbl').textContent = Math.round(S.cam.z * 100) + '%';
  }

  // ------------------------------------------------------------------- wiring
  $('bFixStarts').onclick = () => {
    const m = S.map; if (!m) return; beginAct(); notePls(); let moved = 0, fail = 0;
    m.players.forEach(p => { if (R.startProblems(m, p.x, p.y)) { const n = R.nearestStart(m, p.x, p.y); if (n) { p.x = n[0]; p.y = n[1]; moved++; } else fail++; } });
    endAct(); draw(); drawMinimap(); toast(moved ? moved + '명 시작 위치를 평지로 옮겼습니다' + (fail ? ' (' + fail + '명은 실패)' : '') : fail ? '평지를 찾지 못했습니다' : '모든 시작 위치가 정상입니다', 3500);
  };
  $('bNew').onclick = showNew; $('wNew').onclick = showNew;
  $('bOpen').onclick = openMap; $('wOpen').onclick = openMap;
  $('bSave').onclick = () => save(false); $('bSaveAs').onclick = () => save(true);
  $('bUndo').onclick = undo; $('bRedo').onclick = redo;
  $('bPlayers').onclick = showPlayers; $('bTeams').onclick = showTeams; $('bProps').onclick = showProps;
  $('bZoomIn').onclick = () => zoom(1.25); $('bZoomOut').onclick = () => zoom(0.8);
  $('bGrid').onclick = () => { S.grid = !S.grid; $('bGrid').classList.toggle('on', S.grid); draw(); };
  $('bCellGrid').onclick = () => { S.cellGrid = !S.cellGrid; $('bCellGrid').classList.toggle('on', S.cellGrid); draw(); };
  $('bMarks').onclick = () => { S.marks = !S.marks; $('bMarks').classList.toggle('on', S.marks); draw(); };
  $('wFolder').onclick = pickFolder; $('wFiles').onclick = pickDataFiles; $('wReconnect').onclick = reconnect;
  addEventListener('resize', resize);
  addEventListener('beforeunload', (e) => { if (S.dirty) { e.preventDefault(); e.returnValue = ''; } });
  (async () => { try { if (window.indexedDB && await IDB.get('dir')) $('wReconnect').style.display = ''; } catch (e) { } })();
  $('bRefreshMaps').onclick = srvList;
  async function startBlank() {
    const m = R.newMap({ W: 136, H: 136, tileset: 0, players: 4, base: 1 });
    S.map = m; S.name = 'New Map'; S.fileHandle = null; S.srvName = null; S.undo = []; S.redo = []; S.sel = null;
    await ensureTileset(m.tileset); rebuildToolButtons(); buildPalette(); centerView(); setDirty(false); draw(); drawMinimap(true);
  }
  resize(); rebuildToolButtons(); setTool('brush');
  (async () => {
    await startBlank();
    const srv = await srvInit();
    if (!srv) { $('modeLbl').textContent = '맵 폴더 자동 연결 안 됨 (맵에디터 실행.bat로 열면 자동 연결)'; }
    if (!S.srvName) toast('새 평지 맵(136×136, 4인, 늪지)으로 시작했습니다. 크기·타일셋은 [새 맵]/[맵 속성]에서 바꿀 수 있습니다.', 4500);
  })();
  window.__editor = { S, R, loadMapBytes, attachDataFiles, render, paintAt, save };
})();
