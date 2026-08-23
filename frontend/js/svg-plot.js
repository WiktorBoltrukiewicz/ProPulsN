/* svg-plot.js — the one 2D plotting helper.
 *
 * Two callers: the live convergence chart (log Y, several series) and the
 * results Plot Creator (linear, one series). No chart library — a couple of
 * polylines and a set of ticks is all either of them needs.
 */

const NS = 'http://www.w3.org/2000/svg';

const el = (name, attrs = {}) => {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, value);
  }
  return node;
};

const isFinite_ = (v) => typeof v === 'number' && Number.isFinite(v);

/** Nice round tick values covering [lo, hi]. */
function linearTicks(lo, hi, count = 5) {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].find((m) => m * mag >= raw) * mag;
  const ticks = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + step * 1e-9; t += step) {
    ticks.push(t);
  }
  return ticks;
}

/** Decade ticks for a log axis. */
function logTicks(loExp, hiExp) {
  const ticks = [];
  for (let e = Math.ceil(loExp); e <= Math.floor(hiExp); e += 1) ticks.push(e);
  return ticks.length ? ticks : [loExp, hiExp];
}

function formatTick(value) {
  const abs = Math.abs(value);
  if (value === 0) return '0';
  if (abs >= 1e5 || abs < 1e-3) return value.toExponential(1).replace('e+', 'e');
  return String(Number(value.toPrecision(4)));
}

/**
 * Draw a chart into `svg`.
 *
 * series: [{ name, color, points: [[x, y], ...] }]
 * options: { yScale: 'linear'|'log', xLabel, yLabel, threshold, thresholdLabel }
 */
export function drawPlot(svg, series, options = {}) {
  const {
    yScale = 'linear',
    xLabel = '',
    yLabel = '',
    threshold = null,
    thresholdLabel = '',
  } = options;

  const width = svg.clientWidth || 640;
  const height = svg.clientHeight || 340;
  const pad = { top: 16, right: 18, bottom: 40, left: 62 };

  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.replaceChildren();

  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  if (plotW <= 0 || plotH <= 0) return;

  const useLog = yScale === 'log';

  // Only finite points plot; log additionally needs strictly positive Y.
  const clean = series.map((s) => ({
    ...s,
    points: (s.points || []).filter(
      ([x, y]) => isFinite_(x) && isFinite_(y) && (!useLog || y > 0),
    ),
  }));

  const all = clean.flatMap((s) => s.points);
  if (!all.length) {
    svg.append(
      el('text', {
        x: width / 2, y: height / 2,
        'text-anchor': 'middle', class: 'svg-label',
      }),
    );
    svg.lastChild.textContent = 'No data yet';
    return;
  }

  const xs = all.map((p) => p[0]);
  const ys = all.map((p) => p[1]);
  let xMin = Math.min(...xs);
  let xMax = Math.max(...xs);
  let yMin = Math.min(...ys);
  let yMax = Math.max(...ys);

  if (threshold != null && isFinite_(threshold) && (!useLog || threshold > 0)) {
    yMin = Math.min(yMin, threshold);
    yMax = Math.max(yMax, threshold);
  }
  // Degenerate ranges (a single point, or a flat line) still need a box.
  if (xMax === xMin) { xMin -= 0.5; xMax += 0.5; }
  if (yMax === yMin) {
    if (useLog) { yMin /= 10; yMax *= 10; } else { yMin -= 0.5; yMax += 0.5; }
  }

  let toY;
  let yTickValues;
  if (useLog) {
    const loE = Math.floor(Math.log10(yMin));
    const hiE = Math.ceil(Math.log10(yMax));
    toY = (v) => pad.top + plotH - ((Math.log10(v) - loE) / (hiE - loE)) * plotH;
    yTickValues = logTicks(loE, hiE).map((e) => 10 ** e);
  } else {
    const ticks = linearTicks(yMin, yMax);
    const lo = Math.min(yMin, ticks[0]);
    const hi = Math.max(yMax, ticks[ticks.length - 1]);
    toY = (v) => pad.top + plotH - ((v - lo) / (hi - lo)) * plotH;
    yTickValues = ticks;
  }
  const toX = (v) => pad.left + ((v - xMin) / (xMax - xMin)) * plotW;

  const gridColor = getComputedStyle(document.documentElement)
    .getPropertyValue('--border').trim() || '#262B31';

  // Horizontal gridlines + Y ticks
  for (const value of yTickValues) {
    const y = toY(value);
    if (y < pad.top - 1 || y > pad.top + plotH + 1) continue;
    svg.append(el('line', {
      x1: pad.left, x2: pad.left + plotW, y1: y, y2: y,
      stroke: gridColor, 'stroke-width': 1,
    }));
    const label = el('text', {
      x: pad.left - 8, y: y + 3, 'text-anchor': 'end', class: 'svg-label',
    });
    label.textContent = useLog ? `1e${Math.round(Math.log10(value))}` : formatTick(value);
    svg.append(label);
  }

  // X ticks
  for (const value of linearTicks(xMin, xMax, 6)) {
    const x = toX(value);
    if (x < pad.left - 1 || x > pad.left + plotW + 1) continue;
    svg.append(el('line', {
      x1: x, x2: x, y1: pad.top + plotH, y2: pad.top + plotH + 5,
      stroke: gridColor, 'stroke-width': 1,
    }));
    const label = el('text', {
      x, y: pad.top + plotH + 18, 'text-anchor': 'middle', class: 'svg-label',
    });
    label.textContent = formatTick(value);
    svg.append(label);
  }

  // Axis box
  svg.append(el('rect', {
    x: pad.left, y: pad.top, width: plotW, height: plotH,
    fill: 'none', stroke: gridColor, 'stroke-width': 1,
  }));

  // Convergence target
  if (threshold != null && isFinite_(threshold) && (!useLog || threshold > 0)) {
    const y = toY(threshold);
    if (y >= pad.top && y <= pad.top + plotH) {
      svg.append(el('line', {
        x1: pad.left, x2: pad.left + plotW, y1: y, y2: y,
        stroke: 'currentColor', 'stroke-width': 1,
        'stroke-dasharray': '6 4', opacity: 0.75, class: 'svg-label--station',
      }));
      if (thresholdLabel) {
        const label = el('text', {
          x: pad.left + plotW - 6, y: y - 5,
          'text-anchor': 'end', class: 'svg-label svg-label--station',
        });
        label.textContent = thresholdLabel;
        svg.append(label);
      }
    }
  }

  // Series
  for (const s of clean) {
    if (!s.points.length) continue;
    const d = s.points.map(([x, y]) => `${toX(x)},${toY(y)}`).join(' ');
    svg.append(el('polyline', {
      points: d, fill: 'none', stroke: s.color,
      'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round',
    }));
    // A lone sample would be invisible as a polyline.
    if (s.points.length === 1) {
      svg.append(el('circle', {
        cx: toX(s.points[0][0]), cy: toY(s.points[0][1]), r: 3, fill: s.color,
      }));
    }
  }

  // Axis titles
  if (xLabel) {
    const t = el('text', {
      x: pad.left + plotW / 2, y: height - 6,
      'text-anchor': 'middle', class: 'svg-label',
    });
    t.textContent = xLabel;
    svg.append(t);
  }
  if (yLabel) {
    const t = el('text', {
      x: 12, y: pad.top + plotH / 2,
      'text-anchor': 'middle', class: 'svg-label',
      transform: `rotate(-90 12 ${pad.top + plotH / 2})`,
    });
    t.textContent = yLabel;
    svg.append(t);
  }
}
