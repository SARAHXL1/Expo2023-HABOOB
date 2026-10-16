/* ===========================================================================
   منطق لوحة العرض — القسم 8 من المتطلبات.
   UI-01 تحديث كل ثانيتين بلا إعادة تحميل · UI-02 بلا إنترنت ·
   UI-03 الحالة بالكلمة واللون · UI-06 رسالة عند انقطاع الخادم ·
   UI-07 وضع العرض · UI-08 اختيار العقدة.
   =========================================================================== */

'use strict';

const $ = id => document.getElementById(id);

const State = {
  meta: null,
  node: null,
  paused: false,
  present: false,
  histMinutes: 15,
  lastOk: 0,
  failures: 0,
  sim: { running: false },
  latest: null,
  mode: null,
};

/* ----------------------------------------------------------- أدوات مساعدة */

async function api(path, options) {
  const res = await fetch(path, Object.assign({ cache: 'no-store' }, options || {}));
  if (!res.ok && res.status >= 500) throw new Error('HTTP ' + res.status);
  return res.json();
}

function relTime(seconds) {
  if (seconds === null || seconds === undefined) return '—';
  const s = Math.max(0, Math.round(seconds));
  if (s < 2) return 'الآن';
  if (s < 60) return 'منذ ' + s + ' ثانية';
  const m = Math.floor(s / 60);
  if (m < 60) return 'منذ ' + m + ' دقيقة';
  const h = Math.floor(m / 60);
  return 'منذ ' + h + ' ساعة';
}

function duration(seconds) {
  if (seconds === null || seconds === undefined) return '—';
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  if (h) return h + ' س ' + m + ' د';
  if (m) return m + ' د ' + x + ' ث';
  return x + ' ث';
}

function num(x, digits) {
  if (x === null || x === undefined || Number.isNaN(x)) return null;
  return Number(x).toFixed(digits === undefined ? 1 : digits);
}

function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* وحدة كل حقل، من جدول المدى في الخادم */
function unitOf(field) {
  const r = State.meta && State.meta.ranges[field];
  return r ? r.unit : '';
}
function labelOf(field) {
  const r = State.meta && State.meta.ranges[field];
  return r ? r.label : field;
}
function digitsOf(field) {
  if (field === 'lux' || field === 'rssi') return 0;
  if (field === 'wind_v') return 3;
  if (field === 'rh_pct') return 0;
  return 1;
}

/* ------------------------------------------- مفتاح الوضع (عتاد حقيقي / محاكاة) */

function renderMode(info) {
  const m = info.mode;
  const changed = State.mode !== m;
  State.mode = m;

  $('modeLive').className = m === 'live' ? 'active' : '';
  $('modeSim').className = m === 'sim' ? 'active' : '';

  const bar = $('modeBar');
  bar.className = 'modebar ' + m;
  $('modeIcon').textContent = m === 'live' ? '🔌' : '🧪';

  if (m === 'live') {
    $('modeTitle').textContent = 'وضع العتاد الحقيقي';
    $('modeSub').textContent = info.node_count
      ? 'تُعرض العقد الموصولة فعلًا عبر الواي فاي أو USB. المحاكاة متوقفة.'
      : 'لم تصل أي رسالة من عقدة بعد. كل القطع تظهر «غير متصل» حتى تصل أول رسالة.';
  } else {
    $('modeTitle').textContent = 'وضع المحاكاة';
    $('modeSub').textContent = info.simulation_running
      ? 'بيانات وهمية بلا أي عتاد — لاختبار اللوحة والعرض.'
      : 'المحاكاة متوقفة. شغّلها من قسم «أدوات» أسفل الصفحة.';
  }

  // قسم أدوات المحاكاة لا معنى له في وضع العتاد
  const simTools = $('simToolGroup');
  if (simTools) simTools.style.display = (m === 'sim') ? '' : 'none';

  if (changed) { State.node = null; }
}

async function setMode(m) {
  if (m === State.mode) return;
  $('modeTitle').textContent = 'جارٍ التبديل…';
  try {
    const info = await api('/api/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: m }),
    });
    State.node = null;
    renderMode(info);
    await tick();
    await tickSlow();
  } catch (e) {
    $('modeTitle').textContent = 'تعذر تبديل الوضع';
  }
}

/* ------------------------------------------------------------ 1. شريط العقدة */

function renderNodebar(d) {
  const online = !!d.online;
  if (d.skeleton) {
    $('nodeDot').className = 'dot off';
    $('nodeName').textContent = 'لا توجد عقدة';
    $('lastSeen').textContent = 'بانتظار أول رسالة';
    $('lastSeen').style.color = 'var(--not-found)';
    ['transport', 'rssiVal', 'powerVal', 'uptime', 'fw', 'msgCount']
      .forEach(id => { $(id).textContent = '—'; });
    $('batteryItem').style.display = 'none';
    for (const b of $('rssiBars').children) b.className = '';
    $('batFill').style.width = '0%';
    $('batFill').className = 'fill';
    return;
  }
  $('nodeDot').className = 'dot ' + (online ? 'on' : 'off');
  $('nodeName').textContent = d.node_name || d.node_id || '—';
  $('lastSeen').textContent = online ? relTime(d.age_s)
                                     : 'غير متصلة (' + relTime(d.age_s) + ')';
  $('lastSeen').style.color = online ? '' : 'var(--not-found)';

  const tr = { wifi: 'واي فاي', usb: 'USB', sim: 'محاكاة', test: 'اختبار' };
  $('transport').textContent = tr[d.transport] || d.transport || '—';

  // قوة الإشارة بأعمدة
  const rssi = d.wifi && d.wifi.rssi;
  const bars = $('rssiBars').children;
  let level = 0;
  if (rssi !== null && rssi !== undefined) {
    level = rssi >= -55 ? 4 : rssi >= -65 ? 3 : rssi >= -75 ? 2 : rssi >= -85 ? 1 : 0;
  }
  for (let i = 0; i < 4; i++) bars[i].className = i < level ? 'f' : '';
  $('rssiVal').textContent = (rssi === null || rssi === undefined)
    ? '—' : Math.round(rssi) + ' dBm';

  // مصدر الطاقة (الإصدار 2: التغذية من USB، ودائرة البطارية مؤجلة)
  const src = { usb: 'USB', battery: 'بطارية', solar: 'شمسي' };
  $('powerVal').textContent = src[d.power_source] || d.power_source || '—';

  // بطاقة البطارية تعود تلقائيًا إن وصلت قراءة جهد
  const pct = d.derived && d.derived.battery_pct;
  const bv = d.values && d.values.bat_v;
  const hasBattery = bv !== null && bv !== undefined;
  $('batteryItem').style.display = hasBattery ? '' : 'none';
  if (hasBattery) {
    const fill = $('batFill');
    fill.style.width = (pct === null || pct === undefined ? 0 : pct) + '%';
    fill.className = 'fill' + (bv < 3.1 ? ' crit' : bv < 3.4 ? ' low' : '');
    $('batVal').textContent =
      (pct === null ? '' : Math.round(pct) + '٪ · ') + num(bv, 2) + ' V';
  }

  $('uptime').textContent = duration(d.uptime_s);
  $('fw').textContent = d.fw || '—';
  $('msgCount').textContent = d.msg_count === undefined ? '—' : d.msg_count;
}

/* ------------------------------------------------------ 2. بطاقة UTCI الكبيرة */

function renderUtci(d) {
  const der = d.derived || {};
  const card = $('utciCard');
  const band = der.stress_key;

  card.className = 'utci-card' + (band ? ' b-' + band : '');

  if (der.utci_c === null || der.utci_c === undefined) {
    const why = d.skeleton
      ? 'لم تصل أي رسالة من العقدة بعد. وصّل العقدة أو شغّل جسر USB.'
      : (der.utci_unavailable_reason || 'بانتظار البيانات…');
    $('utciBody').innerHTML =
      '<div class="value" style="font-size:52px">—</div>' +
      '<div class="na">' + esc(why) + '</div>';
  } else {
    $('utciBody').innerHTML =
      '<div class="value">' + num(der.utci_c, 1) + '<span class="unit">°م</span></div>' +
      '<div class="category">' + esc(der.stress_category || '') + '</div>';
  }

  $('mrtVal').innerHTML = der.mrt_c === null || der.mrt_c === undefined
    ? '—' : num(der.mrt_c, 1) + ' <span style="font-size:15px">°م</span>';
  const mb = $('mrtBadge');
  if (der.mrt_assumed) {
    mb.style.display = '';
    mb.title = 'الكرة الحرارية مؤجلة، فـ MRT مفترضة مساوية لحرارة الهواء.';
  } else {
    mb.style.display = 'none';
  }
  $('v10Val').innerHTML = der.v10_ms === null || der.v10_ms === undefined
    ? '—' : num(der.v10_ms, 2) + ' <span style="font-size:15px">م/ث</span>';

  const wc = $('windClamped');
  if (der.wind_clamped) {
    wc.style.display = '';
    wc.firstElementChild.title = (der.notes || []).join(' ');
  } else {
    wc.style.display = 'none';
  }
}

/* ------------------------------------------------- 3. شبكة بطاقات القطع (8.2) */

function renderCards(d) {
  const order = State.meta.sensors.map(s => s.id);
  const html = order.map(id => {
    const s = d.sensors[id];
    if (!s) return '';
    const statusAr = State.meta.status_ar[s.status] || s.status;
    const bad = ['not_found', 'read_error', 'out_of_range', 'stale'].includes(s.status);

    let vals = '';
    const fields = Object.keys(s.values || {});
    if (fields.length) {
      vals = fields.map(f => {
        const raw = s.values[f];
        const shown = raw === null || raw === undefined
          ? '<span class="v none">—</span>'
          : '<span class="v">' + num(raw, digitsOf(f)) +
            '<span class="u">' + esc(unitOf(f)) + '</span></span>';
        return '<div class="kv"><span class="k">' + esc(labelOf(f)) + '</span>' + shown + '</div>';
      }).join('');
    } else {
      const note = s.status === 'assumed' ? 'لا ترسل قراءة' :
                   s.status === 'ok' ? 'تعمل، بلا قيمة مباشرة' : '';
      vals = '<div class="kv"><span class="v none" style="font-size:17px">' +
             esc(note) + '</span></div>';
    }

    // أرقام إضافية مفيدة على البطاقة
    let extra = '';
    if (id === 'ds18b20' && s.extra && s.extra.count !== undefined)
      extra = 'عدد المجسات: ' + esc(s.extra.count);
    if (id === 'anemometer' && s.extra && s.extra.samples !== undefined)
      extra = 'عينات: ' + esc(s.extra.samples);

    const help = (bad && s.help)
      ? '<div class="help">💡 ' + esc(s.help) + '</div>' : '';

    return '' +
      '<div class="card s-' + s.status + '">' +
        '<div class="head">' +
          '<div><div class="name">' + esc(s.ar) + '</div>' +
          '<div class="tech">' + esc(s.tech) + '</div></div>' +
          '<span class="badge s-' + s.status + '">' + esc(statusAr) + '</span>' +
        '</div>' +
        '<div class="values">' + vals + '</div>' +
        help +
        '<div class="foot"><span>' + esc(s.port) + '</span>' +
        '<span>' + (extra ? esc(extra) + ' · ' : '') + relTime(s.age_s) + '</span></div>' +
      '</div>';
  }).join('');
  $('cards').innerHTML = html;
}

/* ------------------------------------------------------------- 4. التنبيهات */

function renderAlerts(d) {
  const list = d.alerts || [];
  if (!list.length) {
    $('alerts').innerHTML = '<div class="alerts-empty">✓ لا توجد تنبيهات. كل القطع ضمن المتوقع.</div>';
    return;
  }
  $('alerts').innerHTML = list.map(a =>
    '<div class="alert ' + esc(a.severity) + '">' +
      '<span class="code">' + esc(a.code) + '</span>' +
      '<span><span class="txt">' + esc(a.text) + '</span>' +
      (a.hint ? '<div class="hint">' + esc(a.hint) + '</div>' : '') + '</span>' +
    '</div>').join('');
}

/* --------------------------------------------------------- 5. الرسوم الصغيرة */

const CHART_DEFS = [
  { key: 'ta_c',    title: 'حرارة الهواء',  unit: '°م',  color: '#38bdf8', digits: 1 },
  { key: 'rh_pct',  title: 'الرطوبة',       unit: '%',   color: '#22d3ee', digits: 0 },
  { key: 'utci_c',  title: 'UTCI',          unit: '°م',  color: '#ef4444', digits: 1 },
  { key: 'wind_ms', title: 'سرعة الرياح',   unit: 'م/ث', color: '#4ade80', digits: 2 },
  { key: 'wind_v',  title: 'جهد الموتور',   unit: 'V',   color: '#facc15', digits: 3 },
];

function buildCharts() {
  $('charts').innerHTML = CHART_DEFS.map(c =>
    '<div class="chart">' +
      '<div class="ch-head"><span class="ch-title">' + c.title + '</span>' +
      '<span class="ch-now" id="now_' + c.key + '">—</span></div>' +
      '<canvas id="cv_' + c.key + '"></canvas>' +
      '<div class="ch-foot"><span>' + c.unit + '</span><span id="mm_' + c.key + '"></span></div>' +
    '</div>').join('');
}

function renderCharts(series) {
  const ts = series.t || [];
  for (const c of CHART_DEFS) {
    const ys = series[c.key] || [];
    Charts.line($('cv_' + c.key), ts, ys, c.color);
    const valid = ys.filter(y => y !== null && y !== undefined && !Number.isNaN(y));
    const last = valid.length ? valid[valid.length - 1] : null;
    $('now_' + c.key).textContent = last === null ? '—' : Number(last).toFixed(c.digits);
    $('now_' + c.key).style.color = last === null ? 'var(--text-faint)' : c.color;
    $('mm_' + c.key).textContent = valid.length
      ? 'الأدنى ' + Math.min(...valid).toFixed(c.digits) +
        ' · الأعلى ' + Math.max(...valid).toFixed(c.digits)
      : '';
  }
}

/* ------------------------------------------------------------ 6. التشخيص */

function renderDiag(d) {
  const items = [
    ['عناوين I2C المكتشفة', (d.i2c_found || []).join('، ') || '—'],
    ['مصدر MRT', d.derived && d.derived.mrt_assumed
      ? 'مفترضة (تساوي حرارة الهواء)' : 'من الكرة الحرارية'],
    ['مصدر الطاقة', d.power_source || '—'],
    ['الذاكرة الحرة', d.heap_free ? Math.round(d.heap_free / 1024) + ' KB' : '—'],
    ['سبب آخر إعادة تشغيل', d.reset_reason || '—'],
    ['عنوان IP للعقدة', (d.wifi && d.wifi.ip) || '—'],
    ['فترة الإرسال', d.send_interval_s ? d.send_interval_s + ' ث' : '—'],
    ['إصدار عقد البيانات', d.schema ?? '—'],
    ['وقت القياس', d.ts ? new Date(d.ts * 1000).toLocaleString('ar-SA') : '—'],
    ['ساعة العقدة', d.ts_replaced ? 'غير مضبوطة (استُخدم وقت الاستلام)' : 'مضبوطة'],
    ['معاملات المعايرة', d.node_settings
      ? 'K=' + d.node_settings.wind_k + ' · B=' + d.node_settings.wind_b +
        ' · ارتفاع ' + d.node_settings.wind_height_m + ' م'
      : '—'],
  ];
  $('diagGrid').innerHTML = items.map(([k, v]) =>
    '<div class="diag-item"><div class="k">' + esc(k) + '</div>' +
    '<div class="v">' + esc(v) + '</div></div>').join('');
}

async function refreshErrors() {
  try {
    const r = await api('/api/errors');
    const list = r.errors || [];
    if (!list.length) {
      $('errList').innerHTML = '<div class="muted">لا توجد رسائل مرفوضة.</div>';
      return;
    }
    $('errList').innerHTML = list.map(e =>
      '<div class="err-item"><div>' + esc(e.reason) + '</div>' +
      '<div class="when">' + new Date(e.rx_ts * 1000).toLocaleTimeString('ar-SA') +
      ' · المصدر: ' + esc(e.source) + '</div>' +
      (e.body ? '<div class="body">' + esc(e.body.slice(0, 300)) + '</div>' : '') +
      '</div>').join('');
  } catch (e) { /* يتولاها فحص الاتصال */ }
}

/* ------------------------------------------------------------- 7. الأدوات */

function fillCalibration(d) {
  if (document.activeElement &&
      document.activeElement.closest &&
      document.activeElement.closest('.tool-group')) return;   // لا نكتب فوق ما يكتبه المستخدم
  const n = d.node_settings || {};
  $('calK').value = n.wind_k ?? '';
  $('calB').value = n.wind_b ?? '';
  $('calVmin').value = n.wind_v_min ?? '';
  $('calH').value = n.wind_height_m ?? '';
  $('calGlobe').value = n.globe_offset_c ?? '';
}

const FAULTS = [
  { key: 'missing:dht22',     label: 'DHT22 مفقود' },
  { key: 'missing:mlx90614',  label: 'MLX90614 مفقود' },
  { key: 'missing:ads1115',   label: 'ADS1115 مفقود' },
  { key: 'missing:mlx90614',  label: 'MLX90614 مفقود' },
  { key: 'missing:veml7700',  label: 'VEML7700 مفقود' },
  { key: 'error:dht22',       label: 'DHT22 قراءة خاطئة' },
  { key: 'error:veml7700',    label: 'VEML7700 قراءة خاطئة' },
  { key: 'out_range:veml7700', label: 'إضاءة خارج المدى' },
  { key: 'out_range:anemometer', label: 'رياح خارج المدى' },
  { key: 'wind_zero',         label: 'جهد الموتور صفر (CK-02)' },
  { key: 'wind_neg',          label: 'جهد الموتور سالب (CK-03)' },
  { key: 'lux_zero',          label: 'إضاءة صفر (CK-04)' },
  { key: 'tg_jump',           label: 'قفز حرارة الكرة (CK-05)' },
  { key: 'reboot',            label: 'إعادة تشغيل متكررة (CK-06)' },
  { key: 'offline',           label: 'انقطاع العقدة' },
];

function buildFaultGrid() {
  $('faultGrid').innerHTML = FAULTS.map(f =>
    '<label class="chk"><input type="checkbox" data-fault="' + f.key + '">' +
    esc(f.label) + '</label>').join('');
}

function collectFaults() {
  const out = {};
  document.querySelectorAll('#faultGrid input[type=checkbox]').forEach(cb => {
    if (!cb.checked) return;
    const [kind, sensor] = cb.dataset.fault.split(':');
    if (sensor) { (out[kind] = out[kind] || []).push(sensor); }
    else { out[kind] = true; }
  });
  return out;
}

function renderSim(st) {
  State.sim = st;
  $('simToggle').textContent = st.running ? '⏹ إيقاف المحاكاة' : '▶ تشغيل المحاكاة';
  $('simToggle').className = st.running ? 'on' : '';
  $('simStatus').textContent = st.running
    ? 'تعمل · ' + st.sent + ' رسالة · كل ' + st.interval_s + ' ثانية · العقد: ' + st.nodes.join('، ')
    : 'متوقفة';
}

/* ------------------------------------------------------- حلقة التحديث (UI-01) */

function setServerOnline(ok) {
  if (ok) {
    State.failures = 0;
    $('offlineBanner').classList.remove('show');
  } else {
    State.failures++;
    if (State.failures >= 2) $('offlineBanner').classList.add('show');
  }
}

async function tick() {
  if (State.paused) return;
  try {
    const nodes = await api('/api/nodes');
    if (nodes.mode && nodes.mode !== State.mode) {
      // غُيّر الوضع من متصفح آخر أو من سطر الأوامر
      renderMode(await api('/api/mode'));
    }
    renderNodeOptions(nodes.nodes || []);

    const q = State.node ? ('?node=' + encodeURIComponent(State.node)) : '';
    const d = await api('/api/latest' + q);
    setServerOnline(true);

    if (!d.available) {
      $('utciCategory') && ($('utciBody').innerHTML =
        '<div class="value" style="font-size:52px">—</div>' +
        '<div class="na">' + esc(d.message || 'بانتظار أول رسالة…') + '</div>');
      return;
    }

    State.latest = d;
    State.node = d.node_id;
    renderNodebar(d);
    renderUtci(d);
    renderCards(d);
    renderAlerts(d);
    renderDiag(d);
    fillCalibration(d);
    $('rawJson').textContent = JSON.stringify(
      (processingRaw(d)), null, 2);
  } catch (e) {
    setServerOnline(false);
  }
}

/* آخر رسالة خام: الخادم يعيدها ضمن lastest عبر الحقول الأصلية */
function processingRaw(d) {
  return d.raw || {
    schema: d.schema, node_id: d.node_id, fw: d.fw, ts: d.ts,
    uptime_s: d.uptime_s, reset_reason: d.reset_reason, wifi: d.wifi,
    heap_free: d.heap_free, i2c_found: d.i2c_found,
    send_interval_s: d.send_interval_s,
    sensors: Object.fromEntries(Object.entries(d.sensors).map(([k, s]) =>
      [k, Object.assign({ status: s.status }, s.values, s.extra)])),
  };
}

async function tickSlow() {
  if (State.paused) return;
  try {
    const q = State.node ? ('?node=' + encodeURIComponent(State.node) + '&') : '?';
    const h = await api('/api/history' + q + 'minutes=' + State.histMinutes);
    renderCharts(h.series || {});
    const st = await api('/api/simulation');
    renderSim(st);
    const health = await api('/api/health');
    $('healthLine').textContent =
      'يعمل منذ ' + duration(health.uptime_s) + ' · ' +
      health.storage.readings + ' قراءة مخزنة · ' +
      health.storage.rejected + ' مرفوضة · ' +
      (health.pythermalcomfort ? 'pythermalcomfort جاهزة' : 'pythermalcomfort غير مثبّتة');
    if ($('diagPanel').open) refreshErrors();
  } catch (e) { /* يتولاها tick */ }
}

function renderNodeOptions(nodes) {
  const sel = $('nodeSelect');
  const sig = nodes.map(n => n.node_id + (n.online ? '1' : '0')).join('|');
  if (sel.dataset.sig === sig) return;
  sel.dataset.sig = sig;
  if (!nodes.length) {
    sel.innerHTML = '<option>' +
      (State.mode === 'live' ? 'لا توجد عقدة موصولة' : 'المحاكاة متوقفة') +
      '</option>';
    return;
  }
  sel.innerHTML = nodes.map(n =>
    '<option value="' + esc(n.node_id) + '"' +
    (n.node_id === State.node ? ' selected' : '') + '>' +
    (n.online ? '🟢 ' : '🔴 ') + esc(n.node_name || n.node_id) + '</option>').join('');
  if (!State.node) State.node = nodes[0].node_id;
}

/* ----------------------------------------------------------------- الإقلاع */

async function boot() {
  buildCharts();
  buildFaultGrid();

  try {
    State.meta = await api('/api/meta');
  } catch (e) {
    $('offlineBanner').classList.add('show');
    setTimeout(boot, 2000);
    return;
  }

  if (!State.meta.pythermalcomfort) $('libWarning').classList.add('show');

  try { renderMode(await api('/api/mode')); } catch (e) { /* يتولاها tick */ }

  const ips = State.meta.server_ips || [];
  $('serverHint').textContent = ips.length
    ? ips.map(ip => 'const char* SERVER = "http://' + ip + ':' + State.meta.port +
                    '/api/readings";').join('\n')
    : 'تعذر معرفة عنوان IP. استخدم ipconfig في ويندوز أو ifconfig في ماك.';

  const refresh = (State.meta.timing && State.meta.timing.dashboard_refresh_ms) || 2000;
  State.histMinutes = (State.meta.timing && State.meta.timing.history_minutes_default) || 15;
  $('histMinutes').value = String(State.histMinutes);
  $('histMinutesLabel').textContent = State.histMinutes;

  await tick();
  await tickSlow();
  setInterval(tick, refresh);          // UI-01
  setInterval(tickSlow, 5000);
}

/* ----------------------------------------------------------- ربط الأزرار */

$('modeLive').addEventListener('click', () => setMode('live'));
$('modeSim').addEventListener('click', () => setMode('sim'));

$('nodeSelect').addEventListener('change', e => { State.node = e.target.value; tick(); tickSlow(); });

$('pauseBtn').addEventListener('click', () => {
  State.paused = !State.paused;
  $('pauseBtn').textContent = State.paused ? '▶ استئناف التحديث' : '⏸ إيقاف التحديث';
  $('pauseBtn').className = State.paused ? 'on' : '';
  if (!State.paused) { tick(); tickSlow(); }
});

$('presentBtn').addEventListener('click', () => {
  State.present = !State.present;
  document.body.classList.toggle('present', State.present);
  $('presentBtn').textContent = State.present ? '✕ إنهاء وضع العرض' : '🔎 وضع العرض';
  $('presentBtn').className = State.present ? 'on' : '';
});

$('histMinutes').addEventListener('change', e => {
  State.histMinutes = Number(e.target.value);
  $('histMinutesLabel').textContent = State.histMinutes;
  tickSlow();
});

$('exportBtn').addEventListener('click', () => {
  const mins = Number($('exportRange').value);
  let url = '/api/export.csv?node=' + encodeURIComponent(State.node || '');
  if (mins > 0) url += '&from=' + (Date.now() / 1000 - mins * 60);
  window.location.href = url;
});

$('calSave').addEventListener('click', async () => {
  const msg = $('calMsg');
  msg.textContent = 'جارٍ الحفظ…';
  msg.className = 'muted';
  try {
    const r = await api('/api/calibration', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        node_id: State.node,
        wind_k: Number($('calK').value),
        wind_b: Number($('calB').value),
        wind_v_min: Number($('calVmin').value),
        wind_height_m: Number($('calH').value),
        globe_offset_c: Number($('calGlobe').value),
      }),
    });
    msg.textContent = r.accepted ? '✓ ' + r.message : '✕ ' + (r.error || 'تعذر الحفظ');
    msg.className = r.accepted ? 'ok-msg' : 'err-msg';
  } catch (e) {
    msg.textContent = '✕ تعذر الاتصال بالخادم.';
    msg.className = 'err-msg';
  }
  setTimeout(() => { $('calMsg').textContent = ''; }, 6000);
});

$('simToggle').addEventListener('click', async () => {
  if (State.mode === 'live') { await setMode('sim'); return; }
  const action = State.sim.running ? 'stop' : 'start';
  renderSim(await api('/api/simulation', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  }));
});

$('faultApply').addEventListener('click', async () => {
  await api('/api/simulation', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'faults', node_id: State.node, faults: collectFaults() }),
  });
});

$('faultClear').addEventListener('click', async () => {
  document.querySelectorAll('#faultGrid input').forEach(cb => { cb.checked = false; });
  await api('/api/simulation', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'faults', node_id: State.node, faults: {} }),
  });
});

$('diagPanel').addEventListener('toggle', () => { if ($('diagPanel').open) refreshErrors(); });

window.addEventListener('resize', () => {
  clearTimeout(window.__rz);
  window.__rz = setTimeout(tickSlow, 180);
});

boot();
