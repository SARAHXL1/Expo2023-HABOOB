/* ===========================================================================
   رسوم صغيرة بسيطة على canvas — القسم 8.1 / 5
   مكتوبة يدويًا بلا أي مكتبة خارجية، حتى لا تحتاج الصفحة أي ملف من الإنترنت (UI-02).
   =========================================================================== */

const Charts = (function () {

  const CSS = getComputedStyle(document.documentElement);
  function v(name, fallback) {
    const x = CSS.getPropertyValue(name);
    return (x && x.trim()) || fallback;
  }

  /**
   * يرسم خطًا زمنيًا داخل عنصر canvas.
   * @param {HTMLCanvasElement} cv
   * @param {number[]} ts    أوقات بالثواني
   * @param {Array<number|null>} ys  القيم، وقد تحوي فراغات (null)
   * @param {string} color   لون الخط
   */
  function line(cv, ts, ys, color) {
    const dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth || 300;
    const h = cv.clientHeight || 92;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
    }
    const g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);

    // النقاط الصالحة فقط
    const pts = [];
    for (let i = 0; i < ys.length; i++) {
      const y = ys[i];
      if (y === null || y === undefined || Number.isNaN(y)) continue;
      pts.push([ts[i], y]);
    }

    const padT = 10, padB = 16, padL = 6, padR = 46;
    const plotW = Math.max(10, w - padL - padR);
    const plotH = Math.max(10, h - padT - padB);

    if (pts.length === 0) {
      g.fillStyle = v('--text-faint', '#6b7f9e');
      g.font = '13px system-ui, sans-serif';
      g.textAlign = 'center';
      g.fillText('لا توجد بيانات', w / 2, h / 2 + 4);
      return;
    }

    let lo = Infinity, hi = -Infinity;
    for (const [, y] of pts) { if (y < lo) lo = y; if (y > hi) hi = y; }
    if (hi - lo < 1e-9) { hi = lo + 1; lo = lo - 1; }
    const pad = (hi - lo) * 0.14;
    lo -= pad; hi += pad;

    const t0 = pts[0][0], t1 = pts[pts.length - 1][0];
    const span = Math.max(1, t1 - t0);
    const X = t => padL + ((t - t0) / span) * plotW;
    const Y = y => padT + (1 - (y - lo) / (hi - lo)) * plotH;

    // خطوط الشبكة الأفقية + قيم المحور
    g.strokeStyle = v('--line', '#2a3c5e');
    g.lineWidth = 1;
    g.fillStyle = v('--text-faint', '#6b7f9e');
    g.font = '11px system-ui, sans-serif';
    g.textAlign = 'left';
    for (let i = 0; i <= 2; i++) {
      const val = lo + (hi - lo) * (i / 2);
      const y = Math.round(Y(val)) + 0.5;
      g.beginPath(); g.moveTo(padL, y); g.lineTo(padL + plotW, y); g.stroke();
      g.fillText(fmt(val), padL + plotW + 6, y + 4);
    }

    // تعبئة خفيفة تحت الخط
    g.beginPath();
    g.moveTo(X(pts[0][0]), Y(pts[0][1]));
    for (const [t, y] of pts) g.lineTo(X(t), Y(y));
    g.lineTo(X(pts[pts.length - 1][0]), padT + plotH);
    g.lineTo(X(pts[0][0]), padT + plotH);
    g.closePath();
    const grad = g.createLinearGradient(0, padT, 0, padT + plotH);
    grad.addColorStop(0, hexA(color, 0.26));
    grad.addColorStop(1, hexA(color, 0.0));
    g.fillStyle = grad;
    g.fill();

    // الخط
    g.beginPath();
    g.moveTo(X(pts[0][0]), Y(pts[0][1]));
    for (const [t, y] of pts) g.lineTo(X(t), Y(y));
    g.strokeStyle = color;
    g.lineWidth = 2;
    g.lineJoin = 'round';
    g.lineCap = 'round';
    g.stroke();

    // آخر نقطة
    const last = pts[pts.length - 1];
    g.beginPath();
    g.arc(X(last[0]), Y(last[1]), 3.4, 0, Math.PI * 2);
    g.fillStyle = color;
    g.fill();

    // مدى الوقت أسفل الرسم
    g.fillStyle = v('--text-faint', '#6b7f9e');
    g.textAlign = 'right';
    g.fillText(clock(t0), padL + 2, h - 3);
    g.textAlign = 'left';
    g.fillText(clock(t1), padL + plotW - 2, h - 3);
  }

  function fmt(x) {
    const a = Math.abs(x);
    if (a >= 10000) return (x / 1000).toFixed(0) + 'k';
    if (a >= 100) return x.toFixed(0);
    if (a >= 10) return x.toFixed(1);
    return x.toFixed(2);
  }

  function clock(ts) {
    const d = new Date(ts * 1000);
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  }

  function hexA(hex, a) {
    const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex.trim());
    if (!m) return 'rgba(99,102,241,' + a + ')';
    return 'rgba(' + parseInt(m[1], 16) + ',' + parseInt(m[2], 16) + ',' +
           parseInt(m[3], 16) + ',' + a + ')';
  }

  return { line, fmt };
})();
