const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
const percent = new Intl.NumberFormat('en-US', { style: 'percent', maximumFractionDigits: 2 });
const charts = [];

function text(id, value) { document.getElementById(id).textContent = value; }
function setTone(element, value) {
  element.classList.remove('positive', 'negative');
  element.classList.add(value >= 0 ? 'positive' : 'negative');
}
function baseOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { intersect: false, mode: 'index' },
    plugins: {
      legend: { labels: { color: '#cbd5e1', usePointStyle: true, boxWidth: 8 } },
      tooltip: { backgroundColor: '#0f172a', borderColor: 'rgba(148,163,184,.3)', borderWidth: 1 }
    },
    scales: {
      x: { ticks: { color: '#8292aa', maxTicksLimit: 10 }, grid: { color: 'rgba(148,163,184,.06)' } },
      y: { ticks: { color: '#8292aa' }, grid: { color: 'rgba(148,163,184,.08)' } }
    }
  };
}

function render(payload) {
  charts.splice(0).forEach(chart => chart.destroy());
  const { metadata, forecast, metrics, series, feature_importance: features } = payload;
  const badge = document.getElementById('statusBadge');
  badge.textContent = metadata.status === 'live' ? 'LIVE PUBLIC DATA' : 'DEMO DATA';
  badge.className = `status-badge ${metadata.status}`;
  document.getElementById('sheetLink').href = metadata.sheet_url;
  text('dataThrough', `Data through ${metadata.data_through}`);
  text('forecastDate', `For ${forecast.next_date} · predicted close ${number.format(forecast.predicted_close)}`);
  const forecastElement = document.getElementById('forecastReturn');
  forecastElement.textContent = percent.format(forecast.predicted_return);
  setTone(forecastElement, forecast.predicted_return);
  text('signal', forecast.signal);
  text('confidence', `${percent.format(forecast.confidence)} relative confidence`);
  text('directionalAccuracy', percent.format(metrics.directional_accuracy));
  const spread = metrics.strategy_cagr - metrics.benchmark_cagr;
  const spreadElement = document.getElementById('strategyVsBenchmark');
  spreadElement.textContent = `${spread >= 0 ? '+' : ''}${percent.format(spread)}`;
  setTone(spreadElement, spread);
  text('drawdown', `Strategy max drawdown ${percent.format(metrics.strategy_max_drawdown)}`);
  text('footerMeta', `${metadata.model} · run ${metadata.run_id} · generated ${metadata.generated_at_utc} · research only`);

  const warning = document.getElementById('warning');
  if (metadata.status !== 'live' || metadata.revision_bias_flag) {
    warning.classList.remove('hidden');
    warning.textContent = metadata.status !== 'live'
      ? 'This packaged preview uses deterministic demo data. The scheduled GitHub Action replaces it with public market data after deployment.'
      : metadata.revision_bias_note;
  } else warning.classList.add('hidden');

  const labels = series.map(row => row.date);
  const entries = series.map(row => row.signal === 'ENTER' ? row.actual_close : null);
  const exits = series.map(row => row.signal === 'EXIT' ? row.actual_close : null);
  charts.push(new Chart(document.getElementById('priceChart'), {
    type: 'line',
    data: { labels, datasets: [
      { label: 'Actual close', data: series.map(r => r.actual_close), borderColor: '#38bdf8', backgroundColor: 'rgba(56,189,248,.12)', borderWidth: 2, pointRadius: 0, tension: .12 },
      { label: 'Predicted close', data: series.map(r => r.predicted_close), borderColor: '#a78bfa', borderDash: [5,5], borderWidth: 1.5, pointRadius: 0, tension: .12 },
      { label: 'Enter', data: entries, borderColor: '#34d399', backgroundColor: '#34d399', showLine: false, pointRadius: 5, pointStyle: 'triangle' },
      { label: 'Exit', data: exits, borderColor: '#fb7185', backgroundColor: '#fb7185', showLine: false, pointRadius: 5, pointStyle: 'rectRot' }
    ]},
    options: baseOptions()
  }));

  charts.push(new Chart(document.getElementById('derivativeChart'), {
    type: 'line',
    data: { labels, datasets: [
      { label: 'Velocity', data: series.map(r => r.velocity), borderColor: '#38bdf8', borderWidth: 1.5, pointRadius: 0 },
      { label: 'Acceleration', data: series.map(r => r.acceleration), borderColor: '#fbbf24', borderWidth: 1.2, pointRadius: 0 },
      { label: 'Jerk', data: series.map(r => r.jerk), borderColor: '#fb7185', borderWidth: 1, pointRadius: 0 },
      { label: 'Opposite velocity', data: series.map(r => r.opposite_velocity), borderColor: '#94a3b8', borderDash: [4,4], borderWidth: 1, pointRadius: 0 }
    ]},
    options: baseOptions()
  }));

  charts.push(new Chart(document.getElementById('equityChart'), {
    type: 'line',
    data: { labels, datasets: [
      { label: 'Signal strategy', data: series.map(r => r.strategy_equity), borderColor: '#34d399', borderWidth: 2, pointRadius: 0 },
      { label: 'Buy and hold', data: series.map(r => r.benchmark_equity), borderColor: '#94a3b8', borderWidth: 1.5, pointRadius: 0 }
    ]},
    options: baseOptions()
  }));

  const ordered = [...features].reverse();
  charts.push(new Chart(document.getElementById('featureChart'), {
    type: 'bar',
    data: { labels: ordered.map(r => r.feature), datasets: [{
      label: 'Current contribution',
      data: ordered.map(r => r.contribution),
      backgroundColor: ordered.map(r => r.contribution >= 0 ? 'rgba(52,211,153,.72)' : 'rgba(251,113,133,.72)'),
      borderWidth: 0
    }]},
    options: { ...baseOptions(), indexAxis: 'y', plugins: { ...baseOptions().plugins, legend: { display: false } } }
  }));
}

fetch('data/latest.json', { cache: 'no-store' })
  .then(response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
  .then(render)
  .catch(error => {
    const warning = document.getElementById('warning');
    warning.classList.remove('hidden');
    warning.textContent = `Could not load model output: ${error.message}`;
    document.getElementById('statusBadge').textContent = 'DATA ERROR';
  });
