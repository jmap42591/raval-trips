"use strict";
const $ = (s) => document.querySelector(s);
let R = null;                 // latest report from the server
let monthKey = null;          // selected month in the report tab

// ---------- helpers ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (x, d = 1) => (x == null ? "—" : x.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
const cur = () => (R && R.settings.currency) || "€";
const money = (x) => (x == null ? "—" : num(x, 2) + " " + cur());
const date = (ts) => new Date(ts * 1000).toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const hm = (ts) => new Date(ts * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
const dur = (sec) => { const m = Math.round(sec / 60); return m < 60 ? m + " min" : Math.floor(m / 60) + " h " + String(m % 60).padStart(2, "0"); };
const tile = (k, v, unit) => `<div class="tile"><div class="k">${esc(k)}</div><div class="v">${v}${unit ? ` <small>${esc(unit)}</small>` : ""}</div></div>`;

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json", "X-Raval-Trips": "1" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  return r.json();
}

// ---------- tabs ----------
document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === name));
  try { localStorage.setItem("tab", name); } catch (e) { /* ignore */ }
}

// ---------- current cycle ----------
function tripCard(t, i, inProgress, isLast) {
  const when = t.end - t.start >= 60 ? `${date(t.start)} → ${hm(t.end)}` : date(t.end);
  const batt = t.used_pct == null ? "—" : `${Math.round(t.soc_start)}% → ${Math.round(t.soc_end)}% (−${Math.round(t.used_pct)}%)`;
  return `<div class="trip">
    <div class="km">${num(t.km)} <small>km</small></div>
    <div><div class="when">Trip ${i} · ${esc(when)} ${isLast && inProgress ? '<span class="badge">in progress</span>' : ""}</div>
    <div class="meta"><span>⏱ ~${dur(t.duration)}</span><span>🔋 ${batt}</span><span>⚡ <b>${t.kwh == null ? "—" : num(t.kwh) + " kWh"}</b></span><span>💶 <b>${money(t.cost)}</b></span><span>📈 ${t.kwh_100 == null ? "—" : num(t.kwh_100) + " kWh/100 km"}</span></div></div>
  </div>`;
}

function renderCycle() {
  const el = $("#cycle");
  const c = R.current;
  if (!c) {
    el.innerHTML = onboarding();
    bindConnect(el);
    return;
  }
  const s = c.summary;
  const since = c.last_charge ? `${date(c.last_charge.ts)} · ${Math.round(c.last_charge.soc)}%` : "—";
  let h = `<h2>Since the last charge</h2><div class="note">Last charge finished: <b>${esc(since)}</b>. Trips are split when readings are more than ${R.settings.gap_minutes} min apart, and the cycle closes at the next charge. Cost at ${num(R.settings.price_kwh, 2)} ${esc(cur())}/kWh.</div>`;
  h += `<div class="grid">${tile("Trips", s.trips)}${tile("Distance", num(s.km), "km")}${tile("Energy", num(s.kwh), "kWh")}${tile("Cost", money(s.cost))}${tile("Average", num(s.kwh_100), "kWh/100 km")}${tile("Driving time", dur(s.duration))}</div>`;
  h += `<h2>Trips</h2>`;
  const n = c.trips.length;
  h += c.trips.map((t, i) => tripCard(t, i + 1, c.in_progress, i === n - 1)).join("");
  h += `<h2>Previous charge cycles</h2>`;
  if (!R.cycles.length) h += `<div class="empty">No earlier cycles yet.</div>`;
  else {
    h += `<div class="scroll"><table><tr><th>Period</th><th>Trips</th><th>km</th><th>kWh</th><th>Cost</th><th>kWh/100 km</th></tr>` +
      R.cycles.map((x) => `<tr><td>${date(x.summary.start)} → ${date(x.summary.end)}</td><td>${x.summary.trips}</td><td>${num(x.summary.km, 0)}</td><td>${num(x.summary.kwh)}</td><td>${money(x.summary.cost)}</td><td>${num(x.summary.kwh_100)}</td></tr>`).join("") + `</table></div>`;
  }
  el.innerHTML = h;
}

// ---------- monthly report ----------
function renderMonth() {
  const el = $("#month");
  if (!R.months.length) { el.innerHTML = `<div class="empty">The monthly report appears after your first trips are recorded.</div>`; return; }
  if (!monthKey || !R.months.some((m) => m.key === monthKey)) monthKey = R.months[0].key;
  const m = R.months.find((x) => x.key === monthKey);
  const s = m.summary;
  let h = `<div class="row2"><div><label>Month</label><select id="monthSel">${R.months.map((x) => `<option value="${x.key}" ${x.key === monthKey ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></div><div></div></div>`;
  h += `<h2>${esc(m.name)}</h2><div class="note">Cost = energy used on each trip × ${num(R.settings.price_kwh, 2)} ${esc(cur())}/kWh.</div>`;
  h += `<div class="grid">${tile("Trips", s.trips)}${tile("Charges", s.charges)}${tile("Distance", num(s.km, 0), "km")}${tile("Energy", num(s.kwh), "kWh")}${tile("Cost", money(s.cost))}${tile("Average ≈", num(s.kwh_100), "kWh/100 km")}</div>`;
  const vals = m.trips.map((t) => t.kwh_100).filter((v) => v != null);
  if (vals.length > 1) {
    const mx = Math.max(...vals, 1);
    h += `<h2>Consumption per trip (kWh/100 km)</h2><div class="bars">${vals.map((v) => `<div style="height:${Math.max(4, (v / mx) * 100)}%" title="${num(v)} kWh/100 km"></div>`).join("")}</div>`;
  }
  h += `<h2>Trips this month</h2><div class="scroll"><table><tr><th>Date</th><th>km</th><th>kWh</th><th>Cost</th><th>kWh/100 km</th></tr>`;
  h += m.trips.map((t) => `<tr><td>${date(t.start)}</td><td>${num(t.km)}</td><td>${num(t.kwh)}</td><td>${money(t.cost)}</td><td>${num(t.kwh_100)}</td></tr>`).join("");
  h += `<tr class="total"><td>Total</td><td>${num(s.km)}</td><td>${num(s.kwh)}</td><td>${money(s.cost)}</td><td>≈ ${num(s.kwh_100)}</td></tr></table></div>`;
  h += `<div class="note">${s.trips} trips · ${s.charges} charges (≈ ${num(s.charged_kwh)} kWh put into the battery).</div>`;
  h += `<h2>All months</h2><div class="scroll"><table><tr><th>Month</th><th>Trips</th><th>Charges</th><th>km</th><th>kWh</th><th>Cost</th><th>kWh/100 km</th></tr>`;
  h += R.months.map((x) => `<tr><td>${esc(x.name)}</td><td>${x.summary.trips}</td><td>${x.summary.charges}</td><td>${num(x.summary.km, 0)}</td><td>${num(x.summary.kwh)}</td><td>${money(x.summary.cost)}</td><td>${num(x.summary.kwh_100)}</td></tr>`).join("");
  const t = R.totals;
  h += `<tr class="total"><td>Total</td><td>${t.trips}</td><td>${t.charges}</td><td>${num(t.km, 0)}</td><td>${num(t.kwh)}</td><td>${money(t.cost)}</td><td>≈ ${num(t.kwh_100)}</td></tr></table></div>`;
  h += `<p><a href="/api/export/trips.csv"><button class="ghost">Download trips (CSV)</button></a> <a href="/api/export/charges.csv"><button class="ghost">Download charges (CSV)</button></a></p>`;
  el.innerHTML = h;
  $("#monthSel").addEventListener("change", (e) => { monthKey = e.target.value; renderMonth(); });
}

// ---------- connect / settings ----------
function onboarding() {
  return `<div class="card"><h2 style="margin-top:0">Welcome 👋 Let's connect your car</h2>
  <ol class="steps">
    <li><b>On the VW portal</b> (once): sign in at <i>eu-data-act.drivesomethinggreater.com</i> with your VW ID, pair your car, and create a <b>continuous</b> data request every <b>15 minutes</b> with <b>all data clusters</b>. The first files can take a while to appear.</li>
    <li><b>Here</b>: enter the same VW ID below. Your password stays in this computer's secure vault and is only sent to VW.</li>
    <li>Wait for the first sync. Your trips appear as soon as the car has reported a drive.</li>
  </ol>${connectForm()}
  <p class="note">No account with us, no cloud: this app talks only to the VW portal and keeps the data in a local file. Prefer not to enter a password? Download the data files from the portal yourself and import them in Settings.</p></div>`;
}

function connectForm() {
  const s = R.settings;
  return `<label>VW ID e-mail</label><input id="email" type="email" value="${esc(s.email)}" autocomplete="username">
  <label>Password</label><input id="password" type="password" autocomplete="current-password">
  <label>Brand</label><select id="brand">${["CUPRA", "SEAT"].map((b) => `<option ${s.brand === b ? "selected" : ""}>${b}</option>`).join("")}</select>
  <p><button class="primary" id="connectBtn">Connect</button></p><div class="msg" id="connectMsg"></div><div id="vehiclePick"></div>`;
}

function bindConnect(root) {
  const btn = root.querySelector("#connectBtn");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const msg = root.querySelector("#connectMsg");
    msg.className = "msg"; msg.textContent = "Signing in to the portal…"; btn.disabled = true;
    const r = await api("/api/login", { email: root.querySelector("#email").value, password: root.querySelector("#password").value, brand: root.querySelector("#brand").value });
    btn.disabled = false;
    if (r.error) { msg.className = "msg err"; msg.textContent = r.error; return; }
    msg.className = "msg ok";
    msg.textContent = `Connected. Car: ${r.vehicles.map((v) => v.nickname || v.vin).join(", ")}. Syncing…`;
    await api("/api/sync", {});
    setTimeout(load, 3000);
  });
}

function renderSettings() {
  const s = R.settings, d = R.data, st = R.status;
  const first = d.first ? date(d.first) : "—", last = d.last ? date(d.last) : "—";
  let h = `<div class="card"><h2 style="margin-top:0">Your car</h2>${R.connected ? `<div class="note">Connected as <b>${esc(s.email)}</b> · VIN <b>${esc(s.vin)}</b></div>` : ""}${connectForm()}</div>`;
  h += `<div class="card"><h2 style="margin-top:0">Calculation</h2>
    <div class="row2"><div><label>Battery capacity (kWh)</label><input id="battery" type="number" step="0.1" value="${s.battery_kwh}"></div>
    <div><label>Price per kWh</label><input id="price" type="number" step="0.01" value="${s.price_kwh}"></div></div>
    <div class="row2"><div><label>Currency symbol</label><input id="currency" value="${esc(s.currency)}"></div>
    <div><label>New trip when readings are more than (min) apart</label><input id="gap" type="number" step="5" value="${s.gap_minutes}"></div></div>
    <p><button class="primary" id="saveBtn">Save</button> <span class="msg ok" id="saveMsg"></span></p>
    <div class="note">Energy = % of battery used × capacity. Charging losses are not included, so your bill will be a bit higher.</div></div>`;
  h += `<div class="card"><h2 style="margin-top:0">Data</h2>
    <div class="note">${d.readings} readings · ${d.deliveries} files processed · from ${esc(first)} to ${esc(last)}<br>
    Last sync: ${st.last_run ? date(st.last_run) : "never"}${st.last_error ? ` · <span style="color:var(--bad)">${esc(st.last_error)}</span>` : ""}</div>
    <label>Import data files (.zip) downloaded from the portal</label><input id="zipIn" type="file" accept=".zip" multiple>
    <div class="msg" id="zipMsg"></div>
    <p><button class="ghost" id="quitBtn">Quit Raval Trips</button> <span class="note">Stops the app. Open it again any time; it catches up on missed data.</span></p>
    <details><summary class="note">Sync log</summary><pre class="note">${esc((st.log || []).join("\n") || "—")}</pre></details></div>`;
  $("#settings").innerHTML = h;
  bindConnect($("#settings"));
  $("#saveBtn").addEventListener("click", async () => {
    await api("/api/settings", { battery_kwh: $("#battery").value, price_kwh: $("#price").value, currency: $("#currency").value, gap_minutes: $("#gap").value });
    $("#saveMsg").textContent = "Saved ✓";
    load();
  });
  $("#quitBtn").addEventListener("click", async () => {
    if (!confirm("Quit Raval Trips? Data is only downloaded while the app is running.")) return;
    try { await api("/api/quit", {}); } catch (e) { /* server already gone */ }
    document.body.innerHTML = '<main style="padding:60px 20px;text-align:center"><h2>Raval Trips has stopped</h2><p class="note">You can close this tab.</p></main>';
  });
  $("#zipIn").addEventListener("change", async (e) => {
    const msg = $("#zipMsg"); let ok = 0, bad = 0;
    for (const f of e.target.files) {
      const r = await fetch("/api/import", { method: "POST", headers: { "X-Raval-Trips": "1", "X-Filename": f.name }, body: await f.arrayBuffer() });
      (r.ok ? ok++ : bad++);
    }
    msg.className = "msg " + (bad ? "err" : "ok"); msg.textContent = `${ok} imported, ${bad} failed.`;
    load();
  });
}

// ---------- main ----------
function renderStatus() {
  const st = R.status, d = R.data;
  let t;
  if (st.running) t = "Syncing…";
  else if (!R.connected) t = "Not connected yet";
  else t = st.last_ok ? `Last sync ${date(st.last_ok)}` : (st.last_error ? "Sync problem — see Settings" : "Waiting for the first sync");
  $("#status").textContent = `${t} · ${d.readings} readings`;
}

// do not wipe what the user is typing when the page refreshes itself
const busy = (sel) => { const a = document.activeElement; return !!a && $(sel).contains(a) && /INPUT|SELECT/.test(a.tagName); };

async function load() {
  try { R = await api("/api/report"); } catch (e) { $("#status").textContent = "Cannot reach the local server"; return; }
  renderStatus();
  if (!busy("#cycle")) renderCycle();
  if (!busy("#month")) renderMonth();
  if (!busy("#settings")) renderSettings();
}

$("#syncBtn").addEventListener("click", async () => {
  $("#syncBtn").disabled = true;
  await api("/api/sync", {});
  setTimeout(() => { $("#syncBtn").disabled = false; load(); }, 4000);
});

try { showTab(localStorage.getItem("tab") || "cycle"); } catch (e) { showTab("cycle"); }
load();
setInterval(load, 60000);
