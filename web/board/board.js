// ECMWF/GFS天気図ボード（画用紙版）
// 複数の図を並べ、マウスで移動・拡大縮小し、キーで時間を前後させる。
// 各図（パネル）は「図種 + 表示範囲」を持つ。表示範囲が null なら全体の表示範囲に揃う（既定）。
// 同じ図種を別の表示範囲で複数並べる（広さ違い）ことも、配置を名前を付けて登録することもできる。
// 画像規則: output/{model}/{init}/{region}/{chart}_{ft:03d}.png、一覧は output/manifest.json（相対パス。静的サイトでも動く）
// 各図（パネル）は「モデル + 図種 + 表示範囲」を持ち、モデル・範囲が null なら全体の指定に揃う。ECMWFとGFSの同時比較もできる。
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const IMG_W = 950, IMG_H = 760, TITLE_H = 22;           // 元画像のサイズと見出し帯の高さ
  const MIN_W = IMG_W * 0.25, MAX_W = IMG_W * 2;          // 0.25〜2倍（元アプリと同じ）
  const OUT = "../output/";                                  // 画像・manifest（このページは board/ 配下）
  const API = "../api/";                                     // 更新API（ローカルサーバーのみ）
  const LS_KEY = "nwpBoard.v1";                            // 配置の自動保存
  const LS_PRESETS = "nwpBoard.presets.v1";                // 登録した配置
  const pad = (n) => String(n).padStart(2, "0");

  // 並び順（高層→地上）。整列すると左上が最も高い高度、右下が地上(surf)になる。未知の図は末尾
  const ORDER = ["jet300", "z500", "t500", "t700", "ept850", "t850", "t975", "t925", "tenki", "surf"];
  const DEFAULT_ON = ["jet300", "z500", "t700", "t850", "t925", "surf"];
  const REGION_DEFAULT = "japan";
  // 上部メニューとパネル見出し用の短い名前
  const SHORT = { surf: "地上降水", tenki: "天気", t975: "975", t925: "925", t850: "850", ept850: "850EPT",
                  t700: "700", t500: "500気温", z500: "500高度", jet300: "300" };
  const RSHORT = { japan: "日本周辺", okinawa: "沖縄周辺", asia: "東アジア", japan3: "日本域0.125°", okinawa3: "南西域0.125°" };
  const RORDER = ["japan", "okinawa", "asia", "japan3", "okinawa3"];

  // items: パネルの一覧。{id, chart, region(null=全体に揃う), model(null=全体に揃う), primary, on, x, y, w, z}
  //   primary=true: 上部メニューのON/OFFで操作する基本パネル。false: 広さ違いで増やした複製（✕で削除）
  const S = { m: null, model: null, init: null, region: null, ft: 0, items: [], zTop: 1, seq: 0, active: null, timer: null };
  const els = {}; // id → {root, img, nodata, name, sel, wantUrl}

  const imgUrl = (model, init, region, chart, ft) => `${OUT}${model}/${init}/${region}/${chart}_${String(ft).padStart(3, "0")}.png`;
  const parseInit = (s) => new Date(Date.UTC(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8), +s.slice(8, 10)));
  const fmt = (d, off, tz) => {
    const t = new Date(d.getTime() + off * 3600e3);
    return `${t.getUTCMonth() + 1}/${pad(t.getUTCDate())}(${"日月火水木金土"[t.getUTCDay()]}) ${pad(t.getUTCHours())}時${tz}`;
  };
  const modelKeys = () => Object.keys(S.m.models || {});
  const entry = (model, init) => (((S.m.models[model] || {}).inits) || []).find((i) => i.init === init);
  const regionMap = (model) => (entry(model, S.init) || {}).regions || {};      // 現在の初期値での {region: {chart: [ft]}}
  const allInits = () => [...new Set(modelKeys().flatMap((m) => S.m.models[m].inits.map((i) => i.init)))].sort().reverse();
  const rank = (arr, v) => { const i = arr.indexOf(v); return i < 0 ? 99 : i; };
  const regionsOf = () => [...new Set(modelKeys().flatMap((m) => Object.keys(regionMap(m))))]
    .sort((a, b) => rank(RORDER, a) - rank(RORDER, b));
  const chartsOf = () => [...new Set(modelKeys().flatMap((m) => Object.values(regionMap(m)).flatMap((r) => Object.keys(r))))]
    .sort((a, b) => rank(ORDER, a) - rank(ORDER, b));
  const getItem = (id) => S.items.find((i) => i.id === id);
  const effRegion = (it) => it.region || S.region;
  const effModel = (it) => it.model || S.model;
  const has = (model, region, chart) => !!((regionMap(model)[region] || {})[chart]);
  const availFts = (it) => ((regionMap(effModel(it))[effRegion(it)] || {})[it.chart]) || [];
  // 予報時間 ft がその図に無いとき（刻みの粗い範囲）は、直前の予報時間、無ければ最小のものを使う
  const pickFt = (list, ft) => {
    if (list.includes(ft)) return ft;
    const before = list.filter((f) => f <= ft);
    return before.length ? Math.max(...before) : Math.min(...list);
  };
  const visible = () => S.items.filter((i) => i.on);

  // 表示中の図のFTの和集合（無ければ全図）
  function fts() {
    const set = new Set();
    for (const it of visible()) availFts(it).forEach((f) => set.add(f));
    if (!set.size) for (const m of modelKeys()) for (const r of Object.values(regionMap(m))) for (const a of Object.values(r)) a.forEach((f) => set.add(f));
    return [...set].sort((a, b) => a - b);
  }

  function toast(msg) {
    const t = $("toast");
    t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { t.hidden = true; }, 2200);
  }

  const barH = () => (document.body.classList.contains("nobar") ? 0 : $("bar").offsetHeight);
  function fitBoard() { $("board").style.top = barH() + "px"; }

  // ---------- 保存・復元
  const save = () => localStorage.setItem(LS_KEY, JSON.stringify(
    { items: S.items, model: S.model, region: S.region, init: S.init, ft: S.ft, seq: S.seq }));
  function load() { try { return JSON.parse(localStorage.getItem(LS_KEY)) || {}; } catch (e) { return {}; } }
  const loadPresets = () => { try { return JSON.parse(localStorage.getItem(LS_PRESETS)) || {}; } catch (e) { return {}; } };

  // ---------- パネルの作成・配置
  function newItem(chart, o) {
    return Object.assign({ id: "p" + (++S.seq), chart, region: null, model: null, primary: true, on: true,
                           x: 0, y: 0, w: 450, z: ++S.zTop }, o || {});
  }
  // 全ての図種に基本パネルが1つあるようにする（上部メニューのON/OFF用）
  function ensurePrimaries() {
    for (const c of chartsOf()) {
      if (!S.items.some((i) => i.primary && i.chart === c)) S.items.push(newItem(c, { on: false }));
    }
  }
  const sortedVisible = () => visible().sort((a, b) =>
    rank(ORDER, a.chart) - rank(ORDER, b.chart) ||
    (b.primary - a.primary) ||
    rank(RORDER, effRegion(a)) - rank(RORDER, effRegion(b)) ||
    rank(modelKeys(), effModel(a)) - rank(modelKeys(), effModel(b)) || a.id.localeCompare(b.id));

  function fillRegionSel(sel) {
    sel.innerHTML = "";
    const o0 = document.createElement("option");
    o0.value = ""; o0.textContent = "範囲:全体";  // 既定は全体の表示範囲に揃う
    sel.appendChild(o0);
    for (const r of regionsOf()) {
      const o = document.createElement("option");
      o.value = r; o.textContent = RSHORT[r] || r;
      sel.appendChild(o);
    }
  }

  function fillModelSel(sel) {
    sel.innerHTML = "";
    const o0 = document.createElement("option");
    o0.value = ""; o0.textContent = "モデル:全体";
    sel.appendChild(o0);
    for (const k of modelKeys()) {
      const o = document.createElement("option");
      o.value = k; o.textContent = S.m.models[k].label;
      sel.appendChild(o);
    }
    sel.hidden = modelKeys().length < 2;   // モデルが1つだけなら出さない
  }

  function ensureEl(it) {
    if (els[it.id]) return els[it.id];
    const root = document.createElement("div");
    root.className = "panel";
    root.innerHTML =
      `<div class="title"><span class="left"><span class="name"></span><select class="rsel" title="この図の表示範囲"></select><select class="msel" title="この図のモデル"></select></span>` +
      `<span class="btns"><span class="dup" title="別の表示範囲で複製（広さ違い）">⧉</span><span class="x" title="閉じる">✕</span></span></div>` +
      `<div class="body"><img alt=""><div class="nodata" hidden>この図・範囲の画像なし</div><div class="grip" title="ドラッグで大きさ変更"></div></div>`;
    $("board").appendChild(root);
    const e = { root, img: root.querySelector("img"), nodata: root.querySelector(".nodata"),
                name: root.querySelector(".name"), sel: root.querySelector(".rsel"), msel: root.querySelector(".msel"), wantUrl: "" };
    fillRegionSel(e.sel);
    fillModelSel(e.msel);
    els[it.id] = e;
    wirePanel(it.id, e);
    return e;
  }

  function applyGeom(it) {
    const e = els[it.id];
    if (!e) return;
    e.root.style.display = it.on ? "" : "none";
    e.root.style.left = it.x + "px";
    e.root.style.top = it.y + "px";
    e.root.style.width = it.w + "px";
    e.root.style.zIndex = it.z;
    e.root.classList.toggle("variant", !it.primary);
  }

  function activate(id) {
    S.active = id;
    for (const k in els) els[k].root.classList.toggle("active", k === id);
    const it = getItem(id);
    if (it) { it.z = ++S.zTop; applyGeom(it); }
  }

  function wirePanel(id, e) {
    // 移動（タイトル帯をドラッグ。範囲選択などの操作部品は除く）
    e.root.querySelector(".title").addEventListener("pointerdown", (ev) => {
      if (ev.target.closest(".btns") || ev.target.tagName === "SELECT") return;
      const it = getItem(id); if (!it) return;
      activate(id);
      const sx = ev.clientX, sy = ev.clientY, ox = it.x, oy = it.y;
      const mv = (m) => { it.x = Math.max(0, ox + m.clientX - sx); it.y = Math.max(0, oy + m.clientY - sy); applyGeom(it); };
      const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); save(); };
      addEventListener("pointermove", mv); addEventListener("pointerup", up);
      ev.preventDefault();
    });
    // 大きさ変更（右下をドラッグ。縦横比は元画像のまま）
    e.root.querySelector(".grip").addEventListener("pointerdown", (ev) => {
      const it = getItem(id); if (!it) return;
      activate(id);
      const sx = ev.clientX, sy = ev.clientY, ow = it.w;
      const mv = (m) => {
        const dw = Math.max(m.clientX - sx, (m.clientY - sy) * IMG_W / IMG_H);
        it.w = Math.min(MAX_W, Math.max(MIN_W, ow + dw));
        applyGeom(it);
      };
      const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); save(); };
      addEventListener("pointermove", mv); addEventListener("pointerup", up);
      ev.preventDefault(); ev.stopPropagation();
    });
    e.root.addEventListener("pointerdown", () => activate(id));
    // ホイールで拡大縮小（カーソル位置を基準にする）
    e.root.addEventListener("wheel", (ev) => {
      const it = getItem(id); if (!it) return;
      ev.preventDefault();
      const r = e.root.getBoundingClientRect();
      const k = ev.deltaY < 0 ? 1.1 : 1 / 1.1;
      const nw = Math.min(MAX_W, Math.max(MIN_W, it.w * k));
      const f = nw / it.w;
      it.x = Math.max(0, it.x + (ev.clientX - r.left) * (1 - f)); // タイトル帯が画面外に出ないよう0以上
      it.y = Math.max(0, it.y + (ev.clientY - r.top) * (1 - f));
      it.w = nw;
      applyGeom(it); save();
    }, { passive: false });
    // この図の表示範囲
    e.sel.addEventListener("change", () => {
      const it = getItem(id); if (!it) return;
      it.region = e.sel.value || null;
      renderItem(it); refreshLabel(); save();
    });
    e.msel.addEventListener("change", () => {
      const it = getItem(id); if (!it) return;
      it.model = e.msel.value || null;
      renderItem(it); refreshLabel(); save();
    });
    e.root.querySelector(".dup").onclick = () => addVariantFor(getItem(id));
    e.root.querySelector(".x").onclick = () => {
      const it = getItem(id); if (!it) return;
      if (it.primary) { it.on = false; applyGeom(it); buildToggles(); }
      else { removeItem(it); }
      save();
    };
  }

  function removeItem(it) {
    if (els[it.id]) { els[it.id].root.remove(); delete els[it.id]; }
    S.items = S.items.filter((i) => i !== it);
    if (S.active === it.id) S.active = null;
  }

  // 画像の差し替え（読み込み完了まで古い画像を残してちらつきを防ぐ）
  function renderItem(it) {
    const e = ensureEl(it);
    applyGeom(it);
    e.sel.value = it.region || "";
    e.msel.value = it.model || "";
    const list = availFts(it);
    const base = SHORT[it.chart] || it.chart;
    if (!list.length) { e.nodata.hidden = false; e.name.textContent = base; return; }
    const ft = pickFt(list, S.ft);
    e.name.textContent = ft === S.ft ? base : `${base} (FT${ft}h)`;
    e.nodata.hidden = true;
    if (!it.on) return;
    const url = imgUrl(effModel(it), S.init, effRegion(it), it.chart, ft);
    e.wantUrl = url;
    const im = new Image();
    im.onload = () => { if (e.wantUrl === url) e.img.src = url; };
    im.src = url;
  }

  // 画面に出ているモデルの出典を、画面左下に表示する（データ提供元の出典明記）
  function refreshCredit() {
    const used = [...new Set(visible().map(effModel))];
    $("credit").textContent = "データ: " + used.map((m) => (S.m.models[m] || {}).credit).filter(Boolean).join(" / ");
  }

  function refreshLabel() {
    const d = parseInit(S.init);
    $("dateLabel").textContent = `${fmt(d, S.ft, "UTC")} (${fmt(d, S.ft + 9, "JST")}) ｜ 初期値 ${pad(d.getUTCHours())}UTC ＋${S.ft}h`;
  }

  function refresh() {
    for (const it of S.items) renderItem(it);
    refreshLabel();
    refreshCredit();
    prefetch();
    save();
  }

  // 前後のFTを先読み（↑↓での閲覧を軽くする）
  function prefetch() {
    const f = fts(), i = f.indexOf(S.ft);
    for (const ft of [f[i + 1], f[i - 1]]) {
      if (ft === undefined) continue;
      for (const it of visible()) {
        const l = availFts(it);
        if (l.length) new Image().src = imgUrl(effModel(it), S.init, effRegion(it), it.chart, pickFt(l, ft));
      }
    }
  }

  // ---------- 配置
  function tile() {
    const on = sortedVisible();
    if (!on.length) return;
    const W = innerWidth, H = innerHeight - barH();
    let best = null;
    for (let cols = 1; cols <= on.length; cols++) {
      const rows = Math.ceil(on.length / cols);
      const w = Math.min(W / cols, ((H / rows) - TITLE_H) * IMG_W / IMG_H) - 4;
      if (!best || w > best.w) best = { cols, w };
    }
    const w = Math.min(MAX_W, Math.max(MIN_W, Math.floor(best.w)));
    on.forEach((it, i) => {
      it.w = w;
      it.x = (i % best.cols) * (w + 4) + 2;
      it.y = Math.floor(i / best.cols) * (w * IMG_H / IMG_W + TITLE_H + 4) + 2;
      it.z = ++S.zTop;
      applyGeom(it);
    });
    save();
  }

  // 初期化: 既定の図（全て全体の表示範囲に揃う）を高層→地上の順で敷き詰める
  function resetLayout() {
    for (const k of Object.keys(els)) { els[k].root.remove(); delete els[k]; }
    S.items = [];
    for (const c of chartsOf()) S.items.push(newItem(c, { on: DEFAULT_ON.includes(c) }));
    buildToggles(); refresh(); tile();
  }

  // ---------- 広さ違い
  // 1枚の図を、まだ並んでいない別の表示範囲で複製する
  function addVariantFor(it) {
    if (!it) return;
    const shown = new Set(visible().filter((i) => i.chart === it.chart).map(effRegion));
    const next = regionsOf().find((r) => !shown.has(r) && has(effModel(it), r, it.chart));
    if (!next) { toast("この図は、全ての表示範囲で既に並んでいます"); return; }
    const v = newItem(it.chart, { region: next, model: it.model, primary: false, x: it.x + 30, y: it.y + 30, w: it.w });
    S.items.push(v);
    renderItem(v); activate(v.id); save();
  }

  // 選択中の図を、他の全ての表示範囲でも並べて整列する
  function addAllVariants() {
    const it = getItem(S.active) || sortedVisible()[0];
    if (!it) { toast("先に図を選択（クリック）してください"); return; }
    const shown = new Set(visible().filter((i) => i.chart === it.chart && effModel(i) === effModel(it)).map(effRegion));
    let n = 0;
    for (const r of regionsOf()) {
      if (shown.has(r) || !has(effModel(it), r, it.chart)) continue;
      S.items.push(newItem(it.chart, { region: r, model: it.model, primary: false, w: it.w }));
      n++;
    }
    if (!n) { toast("この図は、全ての表示範囲で既に並んでいます"); return; }
    refresh(); tile();
    toast(`${SHORT[it.chart] || it.chart} を ${n} 範囲ぶん追加しました`);
  }

  // 選択中の図を、他のモデルでも（同じ表示範囲で）並べて整列する＝モデル比較
  function addAllModels() {
    const it = getItem(S.active) || sortedVisible()[0];
    if (!it) { toast("先に図を選択（クリック）してください"); return; }
    const region = effRegion(it);
    const shown = new Set(visible().filter((i) => i.chart === it.chart && effRegion(i) === region).map(effModel));
    let n = 0;
    for (const m of modelKeys()) {
      if (shown.has(m) || !has(m, region, it.chart)) continue;
      S.items.push(newItem(it.chart, { region: it.region, model: m, primary: false, w: it.w }));
      n++;
    }
    if (!n) { toast("この図は、全てのモデルで既に並んでいます（またはデータがありません）"); return; }
    refresh(); tile();
    toast(`${SHORT[it.chart] || it.chart} を ${n} モデルぶん追加しました`);
  }

  // ---------- 登録した配置
  function buildPresetSel(selected) {
    const sel = $("presetSel");
    const p = loadPresets();
    sel.innerHTML = "";
    const o0 = document.createElement("option");
    o0.value = ""; o0.textContent = Object.keys(p).length ? "（選択して呼び出し）" : "（登録なし）";
    sel.appendChild(o0);
    for (const name of Object.keys(p)) {
      const o = document.createElement("option");
      o.value = name; o.textContent = name;
      sel.appendChild(o);
    }
    sel.value = selected && p[selected] ? selected : "";
  }

  function savePreset() {
    const name = $("presetName").value.trim();
    if (!name) { toast("登録名を入力してください"); return; }
    const p = loadPresets();
    const existed = !!p[name];
    p[name] = { items: JSON.parse(JSON.stringify(S.items)), model: S.model, region: S.region, savedAt: Date.now() };
    localStorage.setItem(LS_PRESETS, JSON.stringify(p));
    buildPresetSel(name);
    toast(existed ? `「${name}」を上書き登録しました` : `「${name}」を登録しました`);
  }

  function applyPreset(name) {
    const pr = loadPresets()[name];
    if (!pr) return;
    for (const k of Object.keys(els)) { els[k].root.remove(); delete els[k]; }
    S.items = JSON.parse(JSON.stringify(pr.items));
    S.seq = Math.max(S.seq, ...S.items.map((i) => +String(i.id).slice(1) || 0));
    S.zTop = Math.max(1, ...S.items.map((i) => i.z || 1));
    if (pr.model && modelKeys().includes(pr.model)) { S.model = pr.model; $("modelSel").value = S.model; }
    if (pr.region && regionsOf().includes(pr.region)) { S.region = pr.region; $("regionSel").value = S.region; }
    ensurePrimaries();
    fixFt(); buildToggles(); refresh();
    $("presetName").value = name;
    toast(`「${name}」を呼び出しました`);
  }

  function deletePreset() {
    const name = $("presetSel").value;
    if (!name) { toast("削除する登録を選択してください"); return; }
    const p = loadPresets();
    delete p[name];
    localStorage.setItem(LS_PRESETS, JSON.stringify(p));
    buildPresetSel();
    toast(`「${name}」を削除しました`);
  }

  // ---------- UI
  function buildToggles() {
    const box = $("chartToggles");
    box.innerHTML = "";
    for (const c of chartsOf()) {
      const prim = S.items.find((i) => i.primary && i.chart === c);
      const b = document.createElement("button");
      b.textContent = SHORT[c] || (S.m.charts[c] || c);
      b.title = S.m.charts[c] || c;
      b.className = prim && prim.on ? "on" : "";
      b.onclick = () => {
        let p = S.items.find((i) => i.primary && i.chart === c);
        if (!p) { p = newItem(c, { on: false }); S.items.push(p); }
        p.on = !p.on;
        if (p.on) { renderItem(p); activate(p.id); }
        applyGeom(p); buildToggles(); save();
      };
      box.appendChild(b);
    }
  }

  function buildSelects() {
    const sm = $("modelSel");
    sm.innerHTML = "";
    for (const k of modelKeys()) {
      const o = document.createElement("option");
      o.value = k; o.textContent = S.m.models[k].label;
      sm.appendChild(o);
    }
    sm.value = S.model;
    sm.onchange = () => { S.model = sm.value; fixFt(); rebuildRegionSelects(); refresh(); };
    buildInitOptions();
    rebuildRegionSelects();
  }

  // 初期値は全モデルの和集合。どのモデルにあるかを併記する（モデルによって最新の初期値が違うため）
  function buildInitOptions() {
    const si = $("initSel");
    si.innerHTML = "";
    for (const init of allInits()) {
      const o = document.createElement("option");
      const who = modelKeys().filter((m) => entry(m, init)).map((m) => S.m.models[m].label.split(" ")[0]).join("/");
      o.value = init; o.textContent = `${fmt(parseInit(init), 0, "UTC")} 初期値 [${who}]`;
      si.appendChild(o);
    }
    si.value = S.init;
    si.onchange = () => { S.init = si.value; fixFt(); rebuildRegionSelects(); refresh(); };
  }

  function rebuildRegionSelects() {
    const sr = $("regionSel");
    sr.innerHTML = "";
    for (const r of regionsOf()) {
      const o = document.createElement("option");
      o.value = r; o.textContent = S.m.regions[r] || r;
      sr.appendChild(o);
    }
    if (!regionsOf().includes(S.region)) S.region = regionsOf().includes(REGION_DEFAULT) ? REGION_DEFAULT : regionsOf()[0];
    sr.value = S.region;
    sr.onchange = () => { S.region = sr.value; fixFt(); refresh(); };
    for (const k in els) {
      const v = els[k].sel.value, w = els[k].msel.value;
      fillRegionSel(els[k].sel); els[k].sel.value = v;
      fillModelSel(els[k].msel); els[k].msel.value = w;
    }
  }

  function fixFt() {
    const f = fts();
    if (f.length && !f.includes(S.ft)) S.ft = f.reduce((a, b) => (Math.abs(b - S.ft) < Math.abs(a - S.ft) ? b : a));
  }

  // ---------- 時間操作
  function stepFt(d) { // d=+1: 予報時間を進める（端で止まる）
    const f = fts(), i = f.indexOf(S.ft) + d;
    if (i >= 0 && i < f.length) { S.ft = f[i]; refresh(); }
  }
  function setFt(ft) { S.ft = ft; fixFt(); refresh(); }
  // 初期時刻を前後へ。keepValid=true なら予報有効時刻を固定（FTを逆方向に補正）
  function stepInit(d, keepValid) {
    const list = allInits().slice().reverse(); // 昇順（古→新）
    const j = list.indexOf(S.init) + d;
    if (j < 0 || j >= list.length) return;
    const dh = (parseInit(list[j]) - parseInit(S.init)) / 3600e3;
    S.init = list[j];
    if (keepValid) S.ft = Math.max(0, S.ft - dh);
    $("initSel").value = S.init;
    rebuildRegionSelects(); fixFt(); refresh();
  }
  function play() {
    if (S.timer) { stop(); return; }
    $("btnPlay").textContent = "⏸";
    S.timer = setInterval(() => {
      const f = fts(), i = f.indexOf(S.ft);
      S.ft = f[(i + 1) % f.length]; refresh();
    }, 700);
  }
  function stop() { if (S.timer) { clearInterval(S.timer); S.timer = null; } $("btnPlay").textContent = "▶"; }

  addEventListener("keydown", (e) => {
    if (["SELECT", "INPUT", "TEXTAREA"].includes(e.target.tagName)) return;
    const k = e.key;
    if (k === "ArrowUp") { e.ctrlKey ? setFt(Math.max(...fts())) : stepFt(+1); }
    else if (k === "ArrowDown") { e.ctrlKey ? setFt(Math.min(...fts())) : stepFt(-1); }
    else if (k === "ArrowRight") stepInit(+1, e.ctrlKey);
    else if (k === "ArrowLeft") stepInit(-1, e.ctrlKey);
    else if (k === "p" || k === "P") play();
    else if (k === "s" || k === "S") stop();
    else if (k === "t" || k === "T") tile();
    else if (k === "i" || k === "I") resetLayout();
    else if (k === "d" || k === "D") { document.body.classList.toggle("nobar"); fitBoard(); }
    else if (k === "h" || k === "H") $("help").hidden = !$("help").hidden;
    else if (k === "b" || k === "B") { const it = getItem(S.active); if (it) { it.z = 0; applyGeom(it); } }
    else return;
    e.preventDefault();
    if (k.startsWith("Arrow")) stop(); // 矢印キーで再生停止（元アプリと同様）
  });

  $("btnTile").onclick = tile;
  $("btnVariants").onclick = addAllVariants;
  $("btnModels").onclick = addAllModels;
  $("btnPlay").onclick = play;
  $("btnReset").onclick = resetLayout;
  $("btnHelp").onclick = () => { $("help").hidden = !$("help").hidden; };
  $("btnHelpClose").onclick = () => { $("help").hidden = true; };
  $("btnPresetSave").onclick = savePreset;
  $("btnPresetDel").onclick = deletePreset;
  $("presetSel").onchange = () => { if ($("presetSel").value) applyPreset($("presetSel").value); };
  $("presetName").addEventListener("keydown", (e) => { if (e.key === "Enter") savePreset(); });
  addEventListener("resize", fitBoard);
  new ResizeObserver(fitBoard).observe($("bar")); // 折り返しでメニューの高さが変わっても画用紙の開始位置を合わせる

  // ---------- 起動
  async function boot() {
    try { S.m = await (await fetch(OUT + "manifest.json", { cache: "no-store" })).json(); }
    catch (e) { $("dateLabel").textContent = "manifest.json を読めません（update_latest.py を先に実行）"; return; }
    if (!modelKeys().length) { $("dateLabel").textContent = "天気図がありません（update_latest.py を実行）"; return; }
    const sv = load();
    S.model = modelKeys().includes(sv.model) ? sv.model : modelKeys()[0];
    const inits = allInits();
    S.init = inits.includes(sv.init) ? sv.init : (S.m.models[S.model].inits[0] || {}).init || inits[0];
    const regs = regionsOf();
    S.region = regs.includes(sv.region) ? sv.region : (regs.includes(REGION_DEFAULT) ? REGION_DEFAULT : regs[0]);
    S.ft = sv.ft || 0;
    S.seq = sv.seq || 0;
    const fresh = !Array.isArray(sv.items) || !sv.items.length;
    S.items = fresh ? [] : sv.items;
    S.zTop = Math.max(1, ...S.items.map((i) => i.z || 1));
    if (fresh) for (const c of chartsOf()) S.items.push(newItem(c, { on: DEFAULT_ON.includes(c) }));
    ensurePrimaries();
    fixFt();
    buildSelects(); buildToggles(); buildPresetSel();
    fitBoard();
    refresh();
    if (fresh) tile();
  }

  // ---------- 最新データの取得（サーバーの /api/update を呼ぶ）
  async function reloadManifest() {
    if (!S.m) { location.reload(); return; }
    const m = await (await fetch(OUT + "manifest.json", { cache: "no-store" })).json();
    if (!Object.keys(m.models || {}).length) return;
    const prevNewest = allInits()[0];
    S.m = m;
    if (!m.models[S.model]) S.model = modelKeys()[0];
    const newest = allInits()[0];
    if (newest !== prevNewest || !allInits().includes(S.init)) S.init = newest; // 新しい初期値が増えたら切り替える
    ensurePrimaries();
    fixFt(); buildSelects(); buildToggles(); refresh();
  }

  async function pollUpdate() {
    let j;
    try { j = await (await fetch(API + "status")).json(); } catch (e) {
      // 更新APIが無い（公開用の静的サイト）場合はボタンごと隠す
      $("btnUpdate").hidden = true; $("updateMsg").hidden = true; return;
    }
    const last = (j.log && j.log.length) ? j.log[j.log.length - 1] : "";
    if (j.running) {
      $("btnUpdate").disabled = true;
      $("updateMsg").textContent = "更新中… " + last;
      setTimeout(pollUpdate, 3000);
    } else {
      $("btnUpdate").disabled = false;
      if (j.rc === null || j.rc === undefined) { $("updateMsg").textContent = ""; return; }
      $("updateMsg").textContent = j.rc === 0 ? "更新完了" : "更新に失敗（logs/update_ui.log）";
      if (j.rc === 0) reloadManifest();
    }
  }

  $("btnUpdate").onclick = async () => {
    $("btnUpdate").disabled = true;
    $("updateMsg").textContent = "更新を開始しています…";
    try { await fetch(API + "update", { method: "POST" }); } catch (e) { $("updateMsg").textContent = "開始できません"; $("btnUpdate").disabled = false; return; }
    pollUpdate();
  };

  boot().then(pollUpdate);
})();
