/* =========================================================================
   هبوب — live.js
   زر «مصدر البيانات»: الأعمدة الافتراضية (بيانات العرض) ↔ عمود الاختبار (العقدة الحقيقية).
   يُحمَّل بعد السكربت الرئيسي في index.html، ويستخدم متغيراته العامة:
   S, T, t, A, L, render, soft, toast, actions, GEO, CX, CY.

   قاعدة واحدة: في وضع عمود الاختبار لا يظهر إلا ما أرسله الخادم، والقيمة الغائبة «—».
   ========================================================================= */

const LIVE = {
  source: 'demo',          // 'demo' = الأعمدة الافتراضية · 'test' = عمود الاختبار
  timer: null,
  demo: null,              // نسخة من بيانات العرض تُستعاد عند الرجوع
  last: null,              // آخر رد من /api/platform/live
  hist: null,              // منحنى WBGT لآخر 15 دقيقة
  error: null,
  refreshMs: 2000,
  routes: ['overview', 'map', 'zone', 'alerts', 'sensors', 'account', 'settings'],
  readIds: new Set(),      // تنبيهات علّمها المشغل مقروءة (تبقى بين التحديثات)
  alertMem: {},            // ذاكرة التنبيهات: وقت أول رصد، وما زال قائمًا أم زال
  fc: null, fcAt: 0, fcErr: null,   // توقع Open-Meteo من /api/forecast
  decision: null,          // آخر قرار «تفعيل الآن» في هذه الجلسة
};
const SRC_KEY = 'haboob.source';
const canLive = location.protocol !== 'file:';   // الملف المفتوح مباشرة لا يصل للخادم
const hhmm = (ts) => new Date(ts * 1000).toTimeString().slice(0, 5);
// العمود الذي تأخذ المنطقة قيمها منه: أول عمود حقيقي، وإلا أول عمود (القاعدة نفسها في platform_view.py)
const mainPole = (poles) => (poles || []).find(p => !p.simulated) || (poles || [])[0];

Object.assign(T, {
  srcDemo: ['الأعمدة الافتراضية', 'Default poles'],
  srcTest: ['عمود الاختبار', 'Test pole'],
  srcLabel: ['مصدر البيانات', 'Data source'],
  liveTag: ['بيانات حية', 'Live data'],
  srvSim: ['محاكاة', 'Simulation'],
  srvLive: ['عتاد حقيقي', 'Hardware'],
});

/* ---------- زر التبديل في الشريط العلوي ---------- */
function srcToggle() {
  const on = LIVE.source === 'test';
  const srv = LIVE.last ? (LIVE.last.server_mode === 'live' ? t('srvLive') : t('srvSim')) : '';
  const state = on
    ? (LIVE.error ? `<span class="demo-tag" style="background:var(--crit-soft,#F9E1DE);color:var(--crit)">${LIVE.error}</span>`
                  : `<span class="demo-tag" style="background:var(--ok-soft,#E3F1EA);color:var(--ok)">${t('liveTag')}${srv ? ' · ' + srv : ''}</span>`)
    : `<span class="demo-tag">${t('demo')}</span>`;
  return `<div class="lang" role="group" aria-label="${t('srcLabel')}" title="${t('srcLabel')}">
      <button class="${on ? '' : 'on'}" data-act="source" data-k="demo">${t('srcDemo')}</button>
      <button class="${on ? 'on' : ''}" data-act="source" data-k="test" ${canLive ? '' : 'disabled'}>${t('srcTest')}</button>
    </div>${state}`;
}

// إعادة رسم هادئة: تحديث الخادم كل 2 ث لا يعيد تشغيل حركة ظهور الصفحة (وإلا يومض المحتوى)
function quietSoft() { S._quiet = true; try { soft(); } finally { S._quiet = false; } }

/* ---------- التبديل ---------- */
function snapshotDemo() {
  const keys = ['zones', 'sensors', 'alerts', 'events', 'devices', 'tasks', 'log', 'devLog', 'selZone', 'clock'];
  LIVE.demo = {};
  keys.forEach(k => { LIVE.demo[k] = S[k] instanceof Date ? new Date(S[k]) : JSON.parse(JSON.stringify(S[k])); });
}
function restoreDemo() {
  if (!LIVE.demo) return;
  Object.keys(LIVE.demo).forEach(k => { S[k] = LIVE.demo[k]; });
  LIVE.demo = null;
}

function setSource(src) {
  if (src === LIVE.source) return;
  if (src === 'test' && !canLive) { toast(A('شغّل الموقع من الخادم لعرض عمود الاختبار', 'Open the site from the server to use the test pole')); return; }
  if (src === 'test') {
    snapshotDemo();
    LIVE.source = 'test';
    // المنطقة والعمود يبدآن فارغين حتى يصل أول رد، فلا تظهر بيانات وهمية لحظة التبديل
    S.zones = [emptyZone()]; S.sensors = []; S.alerts = []; S.events = [];
    S.devices = S.devices.filter(d => d.zone === 'Z'); S.tasks = []; S.log = []; S.devLog = [];
    S.selZone = 'Z'; S.clock = new Date();
    pull();
    LIVE.timer = setInterval(pull, LIVE.refreshMs);
  } else {
    clearInterval(LIVE.timer); LIVE.timer = null;
    LIVE.source = 'demo'; LIVE.last = null; LIVE.error = null; LIVE.hist = null;
    LIVE.alertMem = {}; LIVE.fc = null; LIVE.fcAt = 0; LIVE.fcErr = null; LIVE.decision = null;
    restoreDemo();
  }
  try { localStorage.setItem(SRC_KEY, LIVE.source); } catch (e) { /* التخزين غير متاح */ }
  if (!LIVE.routes.includes(S.route)) { go('overview'); return; }
  if (S.route === 'zone') { go('zone/' + S.selZone); return; }
  soft();
}

/* ---------- تحويل رد الخادم إلى بيانات المنصة ---------- */
function emptyZone() {
  return { id: 'Z', name: { ar: 'منطقة الاختبار', en: 'Test zone' }, live: true,
           temp: null, hum: null, wind: null, solar: null, wbgt: null, flag: null,
           visitors: null, mitigated: false };
}

/* تنبيهات الخادم + ذاكرة: وقت أول رصد، وما زال قائمًا يُعلَّم «تمت المعالجة» عند زواله */
function mergeAlerts(list, zoneId) {
  const now = hhmm(Date.now() / 1000), cur = new Set();
  list.forEach(a => {
    cur.add(a.id);
    const old = LIVE.alertMem[a.id];
    LIVE.alertMem[a.id] = Object.assign({ zone: zoneId, live: true }, a,
      { time: old ? old.time : now, sent: old ? old.sent : now, status: 'active' });
  });
  Object.values(LIVE.alertMem).forEach(a => { if (!cur.has(a.id) && a.status === 'active') a.status = 'resolved'; });
  const all = Object.values(LIVE.alertMem);
  all.filter(a => a.status === 'resolved').slice(0, -15).forEach(a => { delete LIVE.alertMem[a.id]; });   // لا يتضخم السجل
  return Object.values(LIVE.alertMem).map(a => Object.assign({}, a, { read: a.status === 'resolved' || LIVE.readIds.has(a.id) }));
}

function applyLive(d) {
  const z = Object.assign(emptyZone(), d.zone || {});
  S.zones = [z];
  S.sensors = (d.poles || []).map(p => ({
    id: p.id, zone: p.zone, k: p.k || 0,
    temp: p.temp, hum: p.hum, wind: p.wind, solar: p.solar,
    wbgt: p.wbgt, flag: p.flag,
    batt: p.batt, power: p.power, status: p.status,
    last: Math.round(p.last_s || 0), live: true, simulated: p.simulated,
  }));
  S.alerts = mergeAlerts(d.alerts || [], z.id);
  // قرار «تفعيل الآن»: يبقى ظاهرًا ما دام محرك advice يرى تدخلًا مطلوبًا
  const a = z.advice;
  if (LIVE.decision && a && a.action !== 'intervene') LIVE.decision = null;
  z.mitigated = !!(LIVE.decision && a && a.action === 'intervene');
  z.decision = LIVE.decision;
  z.recent = d.decisions || [];
  if (LIVE.hist) { z.series = LIVE.hist.series; z.seriesLabels = LIVE.hist.labels; }
  S.selZone = z.id;
}

/* منحنى WBGT الفعلي لآخر 15 دقيقة من /api/history (حتى 30 نقطة) */
async function pullHistory(nodeId) {
  if (!nodeId) { LIVE.hist = null; return; }
  const r = await fetch('/api/history?minutes=15&node=' + encodeURIComponent(nodeId), { cache: 'no-store' });
  const h = (await r.json()).series || {};
  const pts = (h.t || []).map((t, i) => [t, (h.wbgt_c || [])[i]]).filter(p => p[1] != null);
  const step = Math.max(1, Math.ceil(pts.length / 30));
  const s = pts.filter((_, i) => i % step === 0 || i === pts.length - 1);
  LIVE.hist = {
    series: s.map(p => p[1]),
    labels: s.map((p, i) => (i % 5 === 0 || i === s.length - 1) ? hhmm(p[0]) : ''),
  };
}

/* توقع WBGT للساعات القادمة من /api/forecast (Open-Meteo): كل 10 دقائق، وعمود الاختبار فقط */
async function pullForecast() {
  if (Date.now() - LIVE.fcAt < 600000 && (LIVE.fc || LIVE.fcErr)) return;
  LIVE.fcAt = Date.now();
  try {
    const r = await fetch('/api/forecast', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const f = await r.json();
    if (LIVE.source !== 'test') return;
    LIVE.fc = f.available ? f : null;
    LIVE.fcErr = f.available ? null : (f.reason || A('التوقع غير متاح', 'Forecast unavailable'));
  } catch (e) {
    LIVE.fc = null; LIVE.fcErr = A('تعذر جلب التوقع من الخادم', 'Could not fetch the forecast from the server');
  }
}
function liveForecast() {
  const f = LIVE.fc;
  if (!f || !f.available) return null;
  const rows = (f.hours || []).filter(h => h.wbgt != null);
  if (!rows.length) return null;
  const note = A('توقع الطقس من Open-Meteo للموقع، وWBGT محسوب بدالة Liljegren نفسها. لا يعتمد على قراءات العمود.',
                 'Weather forecast from Open-Meteo for the site, with WBGT from the same Liljegren function. Not based on the pole’s readings.')
             + (f.stale ? ' ' + A('(نتيجة محفوظة: تعذر التحديث)', '(cached: refresh failed)') : '');
  return { hours: rows.map(h => h.time.slice(11, 13)), data: rows.map(h => h.wbgt), note };
}

async function pull() {
  if (LIVE.source !== 'test') return;
  try {
    const r = await fetch('/api/platform/live', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    if (LIVE.source !== 'test') return;               // بُدّل الوضع أثناء الطلب
    LIVE.last = d; LIVE.error = null;
    const main = mainPole(d.poles);
    try { await pullHistory(main && main.node_id); } catch (e) { LIVE.hist = null; }
    applyLive(d);
    pullForecast().then(() => { if (S.authed && S.route === 'overview' && !document.querySelector('.modal-bg')) quietSoft(); });
  } catch (e) {
    LIVE.error = A('تعذر الاتصال بالخادم', 'Server unreachable');
    S.sensors.forEach(p => { p.status = 'offline'; });
  }
  S.clock = new Date();
  if (S.authed && !document.querySelector('.modal-bg')) quietSoft();   // لا نعيد الرسم فوق نافذة مفتوحة
}

/* ---------- التفسير والتوصية من الخادم بدل القيم التوضيحية ---------- */
const SYS_TITLE = {
  shading: { ar: 'تفعيل التظليل', en: 'Activate shading' },
  fans: { ar: 'تشغيل المراوح', en: 'Start fans' },
  'shading+coolingSys': { ar: 'تفعيل التظليل + التبريد فورًا', en: 'Shading + cooling now' },
};
const _factorsDemo = factorsFor;
factorsFor = function (z) {
  if (!z.live) return _factorsDemo(z);
  const e = z.explain || {};
  return [
    { k: 'fSolar', v: Math.max(0, e.radiation || 0), c: 'var(--heat)' },
    { k: 'fWind', v: Math.max(0, e.low_wind || 0), c: 'var(--cau)' },
  ];
};
const _recDemo = recFor;
recFor = function (z) {
  if (!z.live) return _recDemo(z);
  const a = z.advice;
  if (!a || a.action !== 'intervene' || z.mitigated) return null;
  const e = z.explain || {};
  return {
    sys: a.systems,
    title: SYS_TITLE[a.systems.join('+')] || SYS_TITLE.shading,
    why: {
      ar: `الإشعاع يرفع WBGT بمقدار ${e.radiation}°، وضعف الرياح بمقدار ${e.low_wind}°. الرقم محسوب بإعادة حساب WBGT بعد إزالة كل عامل.`,
      en: `Radiation adds ${e.radiation}° to WBGT and low wind adds ${e.low_wind}°, from re-computing WBGT without each factor.`,
    },
    drop: a.drop_c, conf: null, water: null, time: null,   // لا نسبة ثقة ولا زمن ولا مياه: الخادم لا يحسبها
  };
};

/* ---------- التقييم النصي بالقواعد (AI/heat_analysis + AI/recommendation_engine) ----------
   منفصل عن توصية advice الرقمية أعلاه: advice تحسب الأثر بإعادة حساب WBGT،
   وهذا تقييم بقواعد وعتبات ثابتة يشرح العوامل ويصف الإجراء. */
const FACTOR_AR = {
  'High Solar Radiation': ['إشعاع شمسي مرتفع', 'High solar radiation'],
  'Low Wind Speed': ['رياح ضعيفة', 'Low wind speed'],
  'High Air Temperature': ['حرارة هواء مرتفعة', 'High air temperature'],
  'High Humidity': ['رطوبة مرتفعة', 'High humidity'],
};
const RULE_PRIO = { low: ['b-ok', 'منخفضة', 'Low'], medium: ['b-cau', 'متوسطة', 'Medium'], high: ['b-heat', 'عالية', 'High'], critical: ['b-crit', 'حرجة', 'Critical'] };
function liveInsight(z) {
  const r = z.recommendation, an = z.analysis;
  if (!r) return '';
  const p = RULE_PRIO[r.priority] || RULE_PRIO.medium;
  const fac = ((an && an.factors) || []).map(f => {
    const n = FACTOR_AR[f.factor];
    return `<span class="badge b-neutral" title="${f.reason}">${n ? A(n[0], n[1]) : f.factor} · <span class="num">${f.value}</span></span>`;
  }).join(' ');
  return `<div class="card" style="margin-bottom:18px"><div class="card-head"><div><h3>${A('تقييم هبوب بالقواعد', 'Haboob rule-based assessment')}</h3>
    <p>${A('قواعد وعتبات ثابتة تشرح العوامل وتصف الإجراء؛ الأثر الرقمي في بطاقة التوصية من إعادة حساب WBGT.', 'Fixed rules and thresholds that explain the factors and describe the action; the numeric effect is in the recommendation card.')}</p></div>
    <span class="badge ${p[0]}">${A('الأولوية', 'Priority')}: ${A(p[1], p[2])}</span></div>
    <div style="padding:4px 20px 18px"><b style="font-size:15px">${r.title}</b>
      <div class="sm muted" style="margin-top:4px">${r.reason}</div>
      <div class="sm" style="margin-top:6px"><span class="faint">${A('الأثر المقصود', 'Intended effect')}:</span> ${r.expected_effect}</div>
      ${fac ? `<div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">${fac}</div>` : `<div class="faint sm" style="margin-top:10px">${A('لا عوامل ظاهرة بحسب القواعد.', 'No contributing factors flagged by the rules.')}</div>`}
    </div></div>`;
}

/* ---------- «تفعيل الآن» في عمود الاختبار: يسجّل القرار ويعرض الأثر المتوقع من advice ---------- */
const FLAG_BADGE = { white: 'ok', green: 'cau', yellow: 'heat', red: 'heat', black: 'crit' };
const flagBadge = f => f ? stBadge(FLAG_BADGE[f]) + ` <span class="faint sm">${t('cat' + FLAGS.indexOf(f))}</span>` : '—';
const sysNames = list => list.map(k => t(k)).join(' + ');

const _openActivate = openActivate;
openActivate = function (zid) {
  const z = Z(zid);
  if (!z || !z.live) return _openActivate(zid);
  const rec = recFor(z), a = z.advice;
  if (!rec || !a) return;
  const CMD = { shading: A('تفعيل التظليل في المنطقة', 'Activate zone shading'), coolingSys: A('تشغيل وحدة التبريد في المنطقة', 'Start the zone cooling unit'), fans: A('تشغيل المراوح في المنطقة', 'Start the zone fans') };   // بلا نسب مختلقة (نسخة العرض تذكر 80%)
  const cmds = a.systems.map(s => CMD[s] || s);
  modal(`${mHead(t('approveTitle') + ' — ' + zn(zid), L(z.name))}
  <div class="modal-b"><p class="muted">${A('سيُسجَّل قرارك في الخادم. عمود الاختبار لا يشغّل أجهزة فعلية، فتأتي القراءة بعد التنفيذ من الحساس: إن ظلّلته فعلًا يظهر الانخفاض في الرسالة التالية.',
      'Your decision is recorded on the server. The test pole does not drive real devices, so the reading afterwards comes from the sensor: if you actually shade it, the drop appears in the next message.')}</p>
    <ul class="steps-list" style="margin-top:14px">${cmds.map(k => `<li><span class="st"></span>${k}</li>`).join('')}</ul>
    <div class="compare" style="margin-top:16px"><div><div class="faint sm">WBGT ${A('الآن', 'now')}</div><div class="num" style="font-size:24px;font-weight:600;color:var(--${stOf(z.wbgt)})">${fx(z.wbgt, 1)}°</div></div>
      <div class="best"><div class="faint sm">${A('المتوقع بعد التنفيذ (محسوب)', 'Expected after action (computed)')}</div><div class="num" style="font-size:24px;font-weight:600;color:var(--brand)">${fx(a.after_c, 1)}°</div></div></div>
  </div>
  <div class="modal-f"><button class="btn btn-text" data-act="mclose">${t('cancel')}</button><button class="btn btn-primary" data-act="doActivate" data-id="${zid}">${A('تسجيل القرار', 'Record decision')}</button></div>`);
};

const _doActivate = doActivate;
doActivate = function (zid) {
  const z = Z(zid);
  if (!z || !z.live) return _doActivate(zid);
  const a = z.advice, pole = mainPole(LIVE.last && LIVE.last.poles);
  if (!a || a.action !== 'intervene') { closeModal(); return; }
  LIVE.decision = { at: Date.now(), systems: a.systems, from_c: z.wbgt, from_flag: z.flag, expected_c: a.after_c, expected_flag: a.after_flag };
  z.mitigated = true; z.decision = LIVE.decision;
  // نسخة على الخادم؛ تعذّرها لا يمنع العرض لكنه يُذكر في الرسالة
  fetch('/api/platform/decision', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: pole && pole.node_id, pole_id: pole && pole.id, zone: zid, systems: a.systems,
      wbgt_c: z.wbgt, flag: z.flag, expected_c: a.after_c, expected_flag: a.after_flag }) })
    .then(r => { if (!r.ok) throw new Error(); pull(); })
    .catch(() => toast(A('تعذر حفظ القرار على الخادم؛ سُجّل في هذه الجلسة فقط', 'Could not save the decision on the server; kept for this session only')));
  logAdd({ ar: `${sysNames(a.systems)} — ${zn(zid)}`, en: `${sysNames(a.systems)} — Zone ${zid}` },
         { ar: `قرار مسجّل · WBGT ${fx(z.wbgt, 1)}° ← المتوقع ${fx(a.after_c, 1)}°`, en: `Decision recorded · WBGT ${fx(z.wbgt, 1)}° → expected ${fx(a.after_c, 1)}°` });
  modal(`<div class="modal-b" style="text-align:center;padding-top:30px"><div class="success-mark">${I.check}</div><h2>${A('تم تسجيل القرار', 'Decision recorded')}</h2>
    <p class="muted" style="margin-top:6px">${A('الأثر المتوقع محسوب بمحرك التوصية. القراءة الفعلية تبقى من الحساس.', 'The expected effect is computed by the advice engine. The actual reading stays with the sensor.')}</p>
    <div style="display:flex;justify-content:center;align-items:center;gap:14px;margin:20px 0 6px">${flagBadge(z.flag)}<span class="faint">${LANG === 'ar' ? '←' : '→'}</span>${flagBadge(a.after_flag)}</div>
    <div class="num faint">WBGT ${fx(z.wbgt, 1)}° ${LANG === 'ar' ? '←' : '→'} <b style="color:var(--${stOf(a.after_c)})">${fx(a.after_c, 1)}°</b> <span class="sm">(${A('متوقع', 'expected')})</span></div></div>
    <div class="modal-f" style="justify-content:center"><button class="btn btn-ghost" data-act="mclose">${t('stayHere')}</button><button class="btn btn-primary" data-act="toOverviewFlash" data-id="${zid}">${t('backOverview')}</button></div>`);
  soft();
};

/* بطاقة «القرار مسجّل» في صفحة المنطقة */
function liveDoneText(z) {
  const d = z.decision;
  return d ? A(`سُجّل قرار تفعيل ${sysNames(d.systems)}. الأثر المتوقع محسوب، أما الرقم الحالي فهو قراءة الحساس.`,
               `A decision to activate ${sysNames(d.systems)} is recorded. The expected effect is computed; the number shown is the live sensor reading.`)
           : A('تم تسجيل القرار.', 'Decision recorded.');
}
function liveDoneBlock(z) {
  const d = z.decision || {};
  return `<div class="impact"><div><b class="num" style="color:var(--ok)">${fx(d.from_c, 1)}° → ${fx(d.expected_c, 1)}°</b><span>${A('متوقع (محسوب)', 'Expected (computed)')}</span></div>
    <div><b>${flagBadge(d.expected_flag)}</b><span style="display:block;margin-top:4px">${A('العلم المتوقع', 'Expected flag')}</span></div>
    <div><b class="num" style="color:var(--${stOf(z.wbgt)})">${fx(z.wbgt, 1)}°</b><span style="display:block;margin-top:4px">${A('قراءة الحساس الآن', 'Sensor reading now')}</span></div></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn btn-dark" data-act="goto" data-to="overview">${t('backOverview')}</button><button class="btn btn-text" data-act="liveUndo">${A('إلغاء القرار', 'Withdraw decision')}</button></div>`;
}
actions.liveUndo = () => { LIVE.decision = null; const z = Z(S.selZone); if (z) { z.mitigated = false; z.decision = null; } soft(); };

/* ---------- ربط الزر وحماية الصفحات ---------- */
actions.source = d => setSource(d.k);

// منطقة الاختبار Z تُرسم دائرة في وسط الخريطة (المعرّفات A إلى X محجوزة لمناطق العرض)
GEO.Z = { type: 'c', r: 92, mid: [CX, CY], ang: 0 };

// حالة «مقروء» تبقى بين تحديثات الخادم الدورية (كل 2 ث)
const _markRead = markRead;
markRead = function (id) { _markRead(id); if (LIVE.source === 'test') LIVE.readIds.add(id); };
const _readAll = actions.readAll;
actions.readAll = function () { if (LIVE.source === 'test') S.alerts.forEach(a => { if (a.status === 'active') LIVE.readIds.add(a.id); }); _readAll(); };

// تنبيه حي: الحراري يفتح قرار «تفعيل الآن»، وتنبيه القطع يفتح شبكة المستشعرات (لا مهام صيانة في عمود الاختبار)
const _alertdo = actions.alertdo;
actions.alertdo = function (d) {
  const a = S.alerts.find(x => x.id === d.id);
  if (!a || !a.live) return _alertdo(d);
  markRead(a.id); S.menu = null;
  if (a.iv === 'auto') { const z = Z(a.zone); if (z && recFor(z)) { soft(); openActivate(a.zone); } else go('zone/' + a.zone); return; }
  go('sensors');
};

// الصفحات التي لا تملك بيانات حية تعود إلى النظرة العامة في وضع الاختبار
const _routeLive = route;
route = function () {
  if (LIVE.source === 'test' && S.authed) {
    const r = location.hash.replace(/^#\/?/, '').split('/')[0];
    if (r && !LIVE.routes.includes(r) && r !== 'zones' && r !== 'events') {
      toast(A('هذه الصفحة تعمل على بيانات العرض فقط', 'This page uses demo data only'));
      history.replaceState(null, '', '#/overview');
    }
  }
  _routeLive();
};

// استعادة آخر اختيار، أو ?source=test في الرابط ليوم العرض
(function initSource() {
  let want = new URLSearchParams(location.search).get('source');
  if (!want) { try { want = localStorage.getItem(SRC_KEY); } catch (e) { want = null; } }
  if (want === 'test' && canLive) setSource('test');
})();
