// 断面図・エマグラムの自由選択（ローカルサーバーの /api/custom を呼ぶ）（Vanilla JS）
(() => {
  const $ = (id) => document.getElementById(id);
  const OUT = "output/";
  // 入力欄の候補（公開の固定断面・固定地点と同じ。おおよその位置）
  const PRESET_X = [["南北 130E", 45, 130, 25, 130], ["南北 140E", 45, 140, 25, 140],
                    ["東西 35N", 35, 120, 35, 150], ["東西 30N", 30, 120, 30, 150], ["東シナ海→日本海", 30, 125, 40, 135]];
  const PRESET_E = [["稚内", 45.42, 141.68], ["館野", 36.06, 140.13], ["潮岬", 33.45, 135.76],
                    ["福岡", 33.58, 130.38], ["那覇", 26.21, 127.69], ["石垣島", 24.34, 124.16], ["札幌", 43.06, 141.33]];
  let manifest = null;
  const kind = () => document.querySelector("input[name=kind]:checked").value;

  function buildPresets() {
    const box = $("presets");
    box.innerHTML = "";
    if (kind() === "xsection") {
      for (const [n, a, b, c, d] of PRESET_X) {
        const bt = document.createElement("button"); bt.textContent = n;
        bt.onclick = () => { $("lat1").value = a; $("lon1").value = b; $("lat2").value = c; $("lon2").value = d; drawMap(); };
        box.appendChild(bt);
      }
    } else {
      for (const [n, la, lo] of PRESET_E) {
        const bt = document.createElement("button"); bt.textContent = n;
        bt.onclick = () => { $("lat").value = la; $("lon").value = lo; drawMap(); };
        box.appendChild(bt);
      }
    }
  }
  function applyKind() {
    $("rowX").hidden = kind() !== "xsection";
    $("rowOpt").hidden = kind() !== "xsection";                       // 表示要素の選択は断面だけ
    $("rowE").hidden = kind() !== "emagram";
    buildPresets(); clickStep = 0; mapHint(); drawMap();
  }
  function buildInit() {
    const sel = $("init");
    sel.innerHTML = "";
    const m = manifest && manifest.models[$("model").value];
    for (const i of ((m && m.inits) || [])) {
      const s = i.init;
      sel.add(new Option(`${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)} ${s.slice(8)}Z`, s));
    }
  }
  // ---------- 地図（Canvas・外部のタイルは使わない）。クリックで断面の始点・終点／エマグラムの地点を指定する
  const EXTS = { ea: { lon0: 100, lon1: 180, lat0: 0, lat1: 70 }, nh: { lon0: 0, lon1: 360, lat0: -15, lat1: 90 } };
  let coast = null, clickStep = 0;                                    // clickStep: 次にクリックするのが始点(0)か終点(1)か
  const cv = $("map");
  const ext = () => EXTS[$("ext").value];
  const val = (id) => parseFloat($(id).value);
  function sizeCanvas() {
    const e = ext(), w = cv.clientWidth || 800, dpr = window.devicePixelRatio || 1;
    const h = Math.round(w * (e.lat1 - e.lat0) / (e.lon1 - e.lon0) * ($("ext").value === "nh" ? 0.5 : 1));   // 北半球は縦を圧縮して表示
    cv.width = w * dpr; cv.height = h * dpr; cv.style.height = h + "px";
    cv.getContext("2d").setTransform(dpr, 0, 0, dpr, 0, 0);
    return { w, h };
  }
  const toXY = (lon, lat, w, h) => { const e = ext(); return [((((lon - e.lon0) % 360) + 360) % 360) / (e.lon1 - e.lon0) * w, (e.lat1 - lat) / (e.lat1 - e.lat0) * h]; };
  function drawMap() {
    const { w, h } = sizeCanvas(), c = cv.getContext("2d"), e = ext();
    c.clearRect(0, 0, w, h);
    c.strokeStyle = "rgba(0,0,0,.18)"; c.lineWidth = 1; c.fillStyle = "#667"; c.font = "10px sans-serif";
    const gstep = $("ext").value === "nh" ? 30 : 10;
    for (let lo = Math.ceil(e.lon0 / gstep) * gstep; lo <= e.lon1; lo += gstep) { const [x] = toXY(lo, 0, w, h); c.beginPath(); c.moveTo(x, 0); c.lineTo(x, h); c.stroke(); c.fillText(lo + "E", x + 2, h - 3); }
    for (let la = Math.ceil(e.lat0 / 10) * 10; la <= e.lat1; la += 10) { const [, y] = toXY(0, la, w, h); c.beginPath(); c.moveTo(0, y); c.lineTo(w, y); c.stroke(); c.fillText(la + "N", 2, y - 2); }
    if (coast) {
      c.strokeStyle = "#333"; c.lineWidth = 0.8;
      for (const l of coast) {
        c.beginPath();
        let px = null;
        for (let i = 0; i < l.length; i += 2) {
          const [x, y] = toXY(l[i], l[i + 1], w, h);
          if (px === null || Math.abs(x - px) > w / 2) c.moveTo(x, y); else c.lineTo(x, y);   // 端をまたぐ線は切る
          px = x;
        }
        c.stroke();
      }
    }
    // 公開サイトの固定断面・固定地点（参考）
    c.strokeStyle = "rgba(26,79,208,.35)"; c.setLineDash([4, 3]);
    for (const [, a, b, cc, d] of PRESET_X.slice(0, 2)) { const p = toXY(b, a, w, h), q = toXY(d, cc, w, h); c.beginPath(); c.moveTo(...p); c.lineTo(...q); c.stroke(); }
    c.setLineDash([]); c.fillStyle = "rgba(26,79,208,.45)";
    for (const [, la, lo] of PRESET_E.slice(0, 5)) { const [x, y] = toXY(lo, la, w, h); c.fillRect(x - 2, y - 2, 4, 4); }
    // 現在の指定
    c.strokeStyle = "#d02020"; c.fillStyle = "#d02020"; c.lineWidth = 2;
    if (kind() === "xsection") {
      const v = ["lat1", "lon1", "lat2", "lon2"].map(val);
      if (v.every(isFinite)) {
        const p = toXY(v[1], v[0], w, h), q = toXY(v[3], v[2], w, h);
        c.beginPath(); c.moveTo(...p); c.lineTo(...q); c.stroke();
        c.beginPath(); c.arc(p[0], p[1], 5, 0, 7); c.fill();                       // 始点は大きい丸
        c.beginPath(); c.arc(q[0], q[1], 3, 0, 7); c.fill();
      }
    } else {
      const la = val("lat"), lo = val("lon");
      if (isFinite(la) && isFinite(lo)) { const [x, y] = toXY(lo, la, w, h); c.beginPath(); c.arc(x, y, 5, 0, 7); c.fill(); }
    }
  }
  function mapHint() {
    $("mapHint").textContent = kind() === "xsection"
      ? "地図を2回クリック＝始点→終点（大きい丸が始点）。青の点線・点は公開サイトの固定断面・固定地点。"
      : "地図をクリックすると、その地点のエマグラムを作れます。";
  }
  cv.addEventListener("click", (ev) => {
    const r = cv.getBoundingClientRect(), e = ext();
    const lon = e.lon0 + (ev.clientX - r.left) / r.width * (e.lon1 - e.lon0);
    const lat = e.lat1 - (ev.clientY - r.top) / r.height * (e.lat1 - e.lat0);
    const f = (x) => (Math.round(x * 10) / 10).toString();
    if (kind() === "xsection") {
      if (clickStep === 0) { $("lat1").value = f(lat); $("lon1").value = f(lon); $("lat2").value = f(lat); $("lon2").value = f(lon); }
      else { $("lat2").value = f(lat); $("lon2").value = f(lon); }
      clickStep = 1 - clickStep;
    } else { $("lat").value = f(lat); $("lon").value = f(lon); }
    drawMap();
  });
  cv.addEventListener("mousemove", (ev) => {
    const r = cv.getBoundingClientRect(), e = ext();
    $("mapInfo").textContent = `${(e.lat1 - (ev.clientY - r.top) / r.height * (e.lat1 - e.lat0)).toFixed(1)}N ${(e.lon0 + (ev.clientX - r.left) / r.width * (e.lon1 - e.lon0)).toFixed(1)}E`;
  });
  $("ext").onchange = drawMap;
  window.addEventListener("resize", drawMap);
  for (const id of ["lat1", "lon1", "lat2", "lon2", "lat", "lon"]) $(id).addEventListener("input", drawMap);
  fetch("coast.json").then((r) => r.json()).then((j) => { coast = j.lines; drawMap(); }).catch(() => drawMap());

  async function boot() {
    try { manifest = await (await fetch(OUT + "manifest.json", { cache: "no-store" })).json(); } catch (e) {
      $("msg").textContent = "manifest.json を読めません。先に作図してください"; $("msg").className = "err"; return;
    }
    for (const [k, v] of Object.entries(manifest.models || {})) if (!v.analysis) $("model").add(new Option(v.label || k, k));   // 再解析（JRA-55）は対象外
    $("model").onchange = buildInit;
    buildInit();
    for (const r of document.querySelectorAll("input[name=kind]")) r.onchange = applyKind;
    applyKind();
  }

  // ディスク使用量（ローカルサーバーの /api/disk）。上限を超えた項目は赤で出す
  const fmtB = (b) => (b >= 1024 ** 3 ? (b / 1024 ** 3).toFixed(2) + "GB" : Math.round(b / 1024 ** 2) + "MB");
  async function showDisk() {
    try {
      const j = await (await fetch("api/disk", { cache: "no-store" })).json();
      const parts = j.items.filter((i) => i.key === "grib" || i.key === "custom").map((i) =>
        `<span class="${i.level === "over" ? "warn" : ""}">${i.label} ${fmtB(i.size)} / 上限 ${fmtB(i.limit)}</span>`);
      parts.push(`<span class="${j.free_level === "ok" ? "" : "warn"}">ディスクの空き ${fmtB(j.free)}${j.free_level === "min" ? "（少ないため新しい取得を止めています）" : ""}</span>`);
      $("disk").innerHTML = "ディスク: " + parts.join(" ／ ") + "（上限を超えると古いものから自動で削除します）";
    } catch (e) { $("disk").textContent = ""; }
  }
  showDisk();

  // ---------- 作図結果の履歴（直近10件）。サーバーが output/custom/ の画像ファイルから作る一覧を読む
  // （ブラウザの保存には頼らない。別のブラウザでも、サイトデータを消しても同じ）
  const MAX_HIST = 10;
  let LOCAL = true;                                    // ローカルサーバーか（公開サイトでは閲覧だけ）
  // 公開サイトでも、Render の断面図API（nwp_xsection_api）が設定されていれば、断面図を作れる（config.js の NWP_XSECTION_API）。
  // 作図は認証なし（回数制限あり）・公開サイトへの掲載だけ合言葉が要る。エマグラムは対象外。
  const REMOTE = String(window.NWP_XSECTION_API || "").replace(/\/+$/, "");
  let REMOTE_MODE = false;
  async function detectLocal() {
    try { const j = await (await fetch("api/custom/list", { cache: "no-store" })).json(); LOCAL = Array.isArray(j.items); } catch (e) { LOCAL = false; }
    if (!LOCAL && REMOTE) { REMOTE_MODE = true; setupRemote(); }
    else if (!LOCAL) {                                  // 公開サイト: 作者が公開した図を見るだけ（新しく作ることはできない）
      $("form").hidden = true; $("disk").hidden = true;
      $("intro").textContent = "作者が公開した断面図・エマグラムです（公開サイトでは新しく作ることはできません）。下のボタンで選んでください。";
    }
  }
  async function getHist() {
    const url = LOCAL ? "api/custom/list" : "output/custom/list.json";
    try { const j = await (await fetch(url, { cache: "no-store" })).json(); return Array.isArray(j.items) ? j.items : []; }
    catch (e) { return []; }
  }
  // 登録した日時（公開した時刻 pub）。無い項目（以前の公開分・ローカルからの公開分）は作図した時刻 ts を「作図」として出す。ブラウザの時刻帯で表示する
  const pad2 = (n) => String(n).padStart(2, "0");
  const fmtTs = (sec) => { const d = new Date(sec * 1000); return (d.getMonth() + 1) + "/" + d.getDate() + " " + pad2(d.getHours()) + ":" + pad2(d.getMinutes()); };
  const stampText = (c) => (c.pub ? "　登録 " + fmtTs(c.pub) : c.ts ? "　作図 " + fmtTs(c.ts) : "");
  const histText = (c) => `${c.label}（${c.model} ${c.initText} ＋${c.ft}h）` + stampText(c) + (c.published ? "【公開中】" : "");
  // 結果の画像を出す。ローカルでは「公開サイトに載せる／外す」も出す
  function showResult(c) {
    if (REMOTE_MODE) return showRemoteResult(c, true);               // 一覧（公開サイトの list.json）の図はすべて公開済み
    const base = c.url.split("/").pop();
    const link = `./#${c.mk ? `model=${c.mk}&init=${c.ik}&` : ""}${c.mk ? `ft=${c.ft}&` : ""}fig=1&region2=custom&chart2=${encodeURIComponent(base)}`;
    $("result").innerHTML = (LOCAL
      ? `<p><a href="${link}" target="_blank" rel="noopener">通常版の左の図と並べて見る（通常版を開く）</a>` +
        `<span class="note">　通常版の「別の図を並べる」で、右の図を選び直せます</span></p><p id="pubRow"><button id="btnPub">${c.published ? "公開から外す" : "公開サイトに載せる"}</button> ` +
        `<span class="note" id="pubMsg">${c.published ? "公開中です（公開サイトの「保存された断面図・エマグラム」で、誰でも見られます）"
          : "公開サイトに載せると、誰でも見られます（直近10件まで。古いものから外れます）"}</span></p>` : "") +
      `<img alt="${histText(c)}" src="${c.url}">`;
    if (LOCAL) wirePub(c);
  }

  // 公開サイトに載せる／外す。誤操作を防ぐため、2回押して確定する（1回目で表示が変わり、5秒以内にもう一度押す）
  function wirePub(c) {
    const b = $("btnPub"), msg = $("pubMsg"), label = b.textContent;
    b.onclick = async () => {
      if (!b.dataset.armed) {
        b.dataset.armed = "1";
        b.textContent = c.published ? "本当に外す（もう一度押す）" : "本当に公開する（もう一度押す）";
        setTimeout(() => { if (b.dataset.armed) { delete b.dataset.armed; b.textContent = label; } }, 5000);
        return;
      }
      b.disabled = true;
      msg.textContent = "公開サイトへ反映しています…（数十秒かかります）";
      try {
        const r = await fetch("api/custom/" + (c.published ? "unpublish" : "publish"), {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ names: [c.url.split("/").pop()] }) });
        const j = await r.json();
        if (!r.ok) { msg.textContent = j.error || "反映できません"; b.disabled = false; delete b.dataset.armed; b.textContent = label; return; }
        await renderHist();
        showResult((j.items || []).find((x) => x.url === c.url) || { ...c, published: !c.published });
        $("pubMsg").textContent = (c.published ? "公開から外しました" : "公開しました（公開サイトへの反映に1〜2分かかります）") + "。";
      } catch (e) { msg.textContent = "反映できません（ローカルサーバーを確認してください）"; b.disabled = false; delete b.dataset.armed; b.textContent = label; }
    };
  }
  async function renderHist() {
    const h = await getHist(), box = $("hist");
    box.innerHTML = "";
    if (!h.length) return;
    const t = document.createElement("div"); t.className = "note";
    t.textContent = LOCAL ? `最近の作図（直近${MAX_HIST}件・保存した画像ファイルから表示）` : "公開されている断面図・エマグラム";
    box.appendChild(t);
    for (const c of h) {
      const b = document.createElement("button");
      b.textContent = histText(c);
      b.title = "この結果を表示する";
      b.onclick = () => showResult(c);
      box.appendChild(b);
    }
  }
  detectLocal().then(renderHist);

  $("go").onclick = async () => {
    if (REMOTE_MODE) return goRemote();
    const q = new URLSearchParams({ kind: kind(), model: $("model").value, init: $("init").value, ft: $("ft").value });
    for (const id of kind() === "xsection" ? ["lat1", "lon1", "lat2", "lon2"] : ["lat", "lon"]) q.set(id, $(id).value);
    if (kind() === "xsection") {                                       // 断面の表示要素（色塗り・等値線・風矢羽）
      q.set("shade", document.querySelector("input[name=shade]:checked").value);
      q.set("contours", [...document.querySelectorAll("input[name=cont]:checked")].map((e) => e.value).join(","));
      q.set("barbs", document.querySelector("input[name=barbs]:checked").value);
    }
    $("go").disabled = true; $("msg").className = ""; $("msg").textContent = "作図中…（データ取得が入ると1分ほどかかります）";
    try {
      const r = await fetch("api/custom?" + q);
      const j = await r.json();
      if (!r.ok) { $("msg").textContent = j.error || "作図できません"; $("msg").className = "err"; }
      else {
        $("msg").textContent = "完了";
        await renderHist();                        // サーバーの一覧（画像ファイル）を読み直す。いま作った画像が先頭に来る
        const cur = (await getHist()).find((x) => x.url === j.url);
        if (cur) showResult(cur); else $("result").innerHTML = `<img alt="" src="${j.url}">`;
      }
    } catch (e) { $("msg").textContent = "サーバーに接続できません（ローカルサーバーで開いてください）"; $("msg").className = "err"; }
    $("go").disabled = false;
    showDisk();
  };

  // ---------- 公開サイトから Render の断面図APIで作る（REMOTE_MODE）
  const KEY_STORE = "nwpXsectionKey";
  const getKey = () => { try { return localStorage.getItem(KEY_STORE) || ""; } catch (e) { return ""; } };
  const setKey = (v) => { try { v ? localStorage.setItem(KEY_STORE, v) : localStorage.removeItem(KEY_STORE); } catch (e) { /* 保存できなくても使える */ } };
  const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function setupRemote() {
    $("disk").hidden = true;
    const em = document.querySelector("input[name=kind][value=emagram]");
    if (em) em.closest("label").hidden = true;                                // エマグラムは対象外
    $("rowKey").hidden = false;
    $("pass").value = getKey();
    $("pass").onchange = () => setKey($("pass").value.trim());
    $("intro").innerHTML = "断面図を、サーバー（Render）でその場で作れます。<b>作図に合言葉は要りません</b>（1時間に8回まで）。" +
      "初回や久しぶりのときはサーバーの起動に<b>1分ほど</b>、データの取得を含めて<b>1〜2分</b>かかります。" +
      "作った図を<b>公開サイトに載せる</b>ときだけ、渡された合言葉が要ります。下の一覧は、公開されている図です。";
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function remoteJson(path, opt) {
    const r = await fetch(REMOTE + path, opt);
    let j = {};
    try { j = await r.json(); } catch (e) { /* JSON でない応答 */ }
    return { r, j };
  }

  async function goRemote() {
    const q = new URLSearchParams({ model: $("model").value, init: $("init").value, ft: $("ft").value });
    for (const id of ["lat1", "lon1", "lat2", "lon2"]) q.set(id, $(id).value);
    q.set("shade", document.querySelector("input[name=shade]:checked").value);
    q.set("contours", [...document.querySelectorAll("input[name=cont]:checked")].map((e) => e.value).join(","));
    q.set("barbs", document.querySelector("input[name=barbs]:checked").value);
    const fail = (t) => { $("msg").textContent = t; $("msg").className = "err"; $("go").disabled = false; };
    $("go").disabled = true; $("msg").className = ""; $("msg").textContent = "サーバーに接続しています…（久しぶりのときは起動に1分ほどかかります）";
    try {
      let { r, j } = await remoteJson("/api/xsection?" + q);
      if (!r.ok && r.status !== 202) return fail(j.error || `作図できません（HTTP ${r.status}）`);
      const t0 = Date.now();
      while (j.state === "queued" || j.state === "running") {
        $("msg").textContent = (j.state === "queued" && j.position ? `順番待ちです（前に${j.position}件）` : "作図中です（データ取得が入ると1〜2分かかります）") +
          `…${Math.round((Date.now() - t0) / 1000)}秒`;
        await sleep(3000);
        if (Date.now() - t0 > 12 * 60 * 1000) return fail("時間がかかりすぎています。しばらくしてからもう一度試してください");
        ({ r, j } = await remoteJson("/api/job/" + encodeURIComponent(j.job)));
        if (!r.ok) return fail(j.error || `状態を確認できません（HTTP ${r.status}）`);
      }
      if (j.state === "error") return fail(j.error || "作図できません");
      $("msg").textContent = "完了";
      showRemoteResult({ ...j, url: REMOTE + j.url }, false);
    } catch (e) { return fail("サーバーに接続できません（しばらくしてからもう一度試してください）"); }
    $("go").disabled = false;
  }

  // 結果の画像と、公開サイトに載せる／外すボタン。published: 公開サイトに載っているか
  function showRemoteResult(c, published) {
    const name = c.name || c.url.split("/").pop();
    const src = c.url;                                                         // 作ったばかりの図は API の絶対URL・一覧の図は相対URL
    $("result").innerHTML =
      `<p id="pubRow"><button id="btnPub">${published ? "公開から外す" : "公開サイトに載せる"}</button> ` +
      `<span class="note" id="pubMsg">${published ? "公開中です（誰でも見られます）。外すには合言葉が要ります。"
        : "公開サイトに載せると誰でも見られます（直近10件まで）。合言葉が要ります。作図結果は、しばらくすると API 側から消えます。"}</span></p>` +
      `<img alt="${esc(c.label)}" src="${esc(src)}">` +
      (c.legal ? `<p class="note">${esc(c.legal)}</p>` : "");
    wireRemotePub(name, published);
  }

  function wireRemotePub(name, published) {
    const b = $("btnPub"), msg = $("pubMsg"), label = b.textContent;
    b.onclick = async () => {
      const key = ($("pass").value || "").trim();
      if (!key) { msg.textContent = "合言葉を入力してください（上の「合言葉」欄）"; return; }
      if (!b.dataset.armed) {                                                  // 誤操作を防ぐため2回押して確定する（5秒以内）
        b.dataset.armed = "1";
        b.textContent = published ? "本当に外す（もう一度押す）" : "本当に公開する（もう一度押す）";
        setTimeout(() => { if (b.dataset.armed) { delete b.dataset.armed; b.textContent = label; } }, 5000);
        return;
      }
      b.disabled = true; msg.textContent = "公開サイトへ反映しています…（数十秒かかります）";
      const undo = (t) => { msg.textContent = t; b.disabled = false; delete b.dataset.armed; b.textContent = label; };
      try {
        const { r, j } = await remoteJson(published ? "/api/unpublish" : "/api/publish", {
          method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + key }, body: JSON.stringify({ name }) });
        if (!r.ok) return undo(j.error || `反映できません（HTTP ${r.status}）`);
        setKey(key);                                                           // 合っていた合言葉は、この端末に覚えておく
        b.hidden = true;
        msg.textContent = (published ? "公開から外しました" : "公開しました") + "。公開サイトへの反映に1〜2分かかります（下の一覧は、そのあと再読み込みすると変わります）。";
      } catch (e) { undo("反映できません（しばらくしてからもう一度試してください）"); }
    };
  }

  boot();
})();
