/* ── State ───────────────────────────────────────────────────────────────── */
const charts = {}; // ticker → Chart instance

/* ── API helpers ─────────────────────────────────────────────────────────── */
async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(`서버 응답 오류 (HTTP ${res.status}). 잠시 후 다시 시도해주세요.`);
  }
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

/* ── Toast ───────────────────────────────────────────────────────────────── */
function toast(msg, type = 'info', duration = 3500) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), duration);
}

/* ── Loading bar ─────────────────────────────────────────────────────────── */
function setLoadingBar(pct) {
  const bar = document.getElementById('loading-bar');
  bar.style.width = pct + '%';
  if (pct >= 100) setTimeout(() => { bar.style.width = '0'; }, 400);
}

/* ── Format helpers ──────────────────────────────────────────────────────── */
function fmtPrice(price, currency) {
  if (price == null) return 'N/A';
  if (currency === 'KRW') return price.toLocaleString('ko-KR') + ' ₩';
  return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) + ' ' + (currency || '');
}

function fmtChange(change, pct) {
  if (change == null) return '';
  const sign = change >= 0 ? '+' : '';
  return `${sign}${change.toFixed(2)} (${sign}${pct.toFixed(2)}%)`;
}

function fmtDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function changeClass(val) {
  if (val == null) return 'neutral';
  return val > 0 ? 'up' : val < 0 ? 'down' : 'neutral';
}

function fmtMarketCap(cap, currency) {
  if (cap == null) return 'N/A';
  if (currency === 'KRW') {
    if (cap >= 1e12) return (cap / 1e12).toFixed(1) + '조';
    if (cap >= 1e8)  return Math.round(cap / 1e8) + '억';
    return cap.toLocaleString('ko-KR') + '원';
  }
  if (cap >= 1e12) return '$' + (cap / 1e12).toFixed(2) + 'T';
  if (cap >= 1e9)  return '$' + (cap / 1e9).toFixed(2) + 'B';
  if (cap >= 1e6)  return '$' + (cap / 1e6).toFixed(1) + 'M';
  return '$' + cap.toLocaleString();
}

function fmtLargeNum(val, currency) {
  if (val == null) return 'N/A';
  return fmtMarketCap(val, currency);
}

/* ── Mini chart ──────────────────────────────────────────────────────────── */
function renderChart(ticker, chartData) {
  const canvas = document.getElementById(`chart-${ticker}`);
  if (!canvas || !chartData?.length) return;

  if (charts[ticker]) charts[ticker].destroy();

  const labels = chartData.map(d => d.date);
  const prices = chartData.map(d => d.close);
  const first = prices[0];
  const last = prices[prices.length - 1];
  const color = last >= first ? '#3fb950' : '#f85149';

  charts[ticker] = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: prices,
        borderColor: color,
        borderWidth: 1.5,
        fill: true,
        backgroundColor: ctx => {
          const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 90);
          g.addColorStop(0, color + '33');
          g.addColorStop(1, color + '00');
          return g;
        },
        tension: 0.3,
        pointRadius: 0,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: {
        callbacks: {
          label: ctx => `  ${ctx.parsed.y.toLocaleString()}`,
        },
        mode: 'index',
        intersect: false,
      }},
      scales: {
        x: { display: false },
        y: { display: false },
      },
      interaction: { mode: 'index', intersect: false },
    }
  });
}

/* ── Analysis markdown-ish renderer ─────────────────────────────────────── */
function renderAnalysis(text) {
  if (!text) return '<span style="color:var(--text-dim)">분석 없음</span>';
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/## (.+)/g, '<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

/* ── Build stock card HTML ───────────────────────────────────────────────── */
function buildCard(ticker, data) {
  const d = data || {};
  const priceClass = changeClass(d.price_change);
  const change30Class = changeClass(d.change_30d);

  // metrics
  const metrics = [
    { label: 'MA5', value: d.ma5 != null ? fmtPrice(d.ma5, d.currency) : 'N/A', class: d.current_price > d.ma5 ? 'up' : 'down' },
    { label: 'MA20', value: d.ma20 != null ? fmtPrice(d.ma20, d.currency) : 'N/A', class: d.current_price > d.ma20 ? 'up' : 'down' },
    { label: 'RSI', value: d.rsi != null ? d.rsi.toFixed(1) : 'N/A', class: d.rsi >= 70 ? 'down' : d.rsi <= 30 ? 'up' : 'neutral' },
    { label: '30일', value: d.change_30d != null ? (d.change_30d > 0 ? '+' : '') + d.change_30d.toFixed(2) + '%' : 'N/A', class: change30Class },
  ];

  const metricsHtml = metrics.map(m =>
    `<div class="metric">
      <div class="metric-label">${m.label}</div>
      <div class="metric-value ${m.class}">${m.value}</div>
    </div>`
  ).join('');

  // news
  const newsHtml = (d.news?.length)
    ? d.news.slice(0, 4).map(n =>
        `<a class="news-item" href="${n.link || '#'}" target="_blank" rel="noopener" title="${n.title}">${n.title}</a>`
      ).join('')
    : `<span class="news-empty">뉴스 없음</span>`;

  const hasData = !!d.current_price;

  return `
<div class="stock-card" id="card-${ticker}">
  <div class="card-header">
    <div>
      <div class="card-ticker">${ticker}</div>
      <div class="card-name">${d.company_name || ticker}</div>
      <div class="card-sector">${d.sector || ''}</div>
    </div>
    <div class="card-price">
      ${hasData ? `
        <div class="price-main ${priceClass}">${fmtPrice(d.current_price, d.currency)}</div>
        <div class="price-change ${priceClass}">${fmtChange(d.price_change, d.price_change_pct)}</div>
      ` : '<div class="price-main neutral">—</div>'}
    </div>
  </div>

  <div class="card-chart">
    <canvas id="chart-${ticker}" height="90"></canvas>
  </div>

  <div class="card-metrics">${metricsHtml}</div>

  <div class="card-financials">
    <div class="fin-section-title">재무 정보</div>
    <div class="fin-grid">
      <div class="fin-item">
        <div class="fin-label">시가총액</div>
        <div class="fin-value">${fmtMarketCap(d.market_cap, d.currency)}</div>
      </div>
      <div class="fin-item">
        <div class="fin-label">PER (Trailing)</div>
        <div class="fin-value">${d.per != null ? d.per.toFixed(1) + 'x' : 'N/A'}</div>
      </div>
      <div class="fin-item">
        <div class="fin-label">PER (Forward)</div>
        <div class="fin-value">${d.forward_per != null ? d.forward_per.toFixed(1) + 'x' : 'N/A'}</div>
      </div>
      <div class="fin-item">
        <div class="fin-label">PBR</div>
        <div class="fin-value">${d.pbr != null ? d.pbr.toFixed(2) + 'x' : 'N/A'}</div>
      </div>
      <div class="fin-item">
        <div class="fin-label">EPS</div>
        <div class="fin-value">${d.eps != null ? fmtPrice(d.eps, d.currency) : 'N/A'}</div>
      </div>
      <div class="fin-item">
        <div class="fin-label">배당수익률</div>
        <div class="fin-value">${d.dividend_yield != null ? d.dividend_yield.toFixed(2) + '%' : 'N/A'}</div>
      </div>
      <div class="fin-item">
        <div class="fin-label">매출액</div>
        <div class="fin-value">${fmtLargeNum(d.revenue, d.currency)}</div>
      </div>
      <div class="fin-item">
        <div class="fin-label">영업이익</div>
        <div class="fin-value">${fmtLargeNum(d.operating_income, d.currency)}</div>
      </div>
      <div class="fin-item">
        <div class="fin-label">ROE</div>
        <div class="fin-value">${d.roe != null ? (d.roe * 100).toFixed(1) + '%' : 'N/A'}</div>
      </div>
      <div class="fin-item">
        <div class="fin-label">부채비율</div>
        <div class="fin-value">${d.debt_to_equity != null ? d.debt_to_equity.toFixed(1) + '%' : 'N/A'}</div>
      </div>
    </div>
  </div>

  <div class="card-news">
    <div class="news-title-row">최근 뉴스</div>
    ${newsHtml}
  </div>

  <div class="card-analysis">
    <div class="analysis-toggle" onclick="toggleAnalysis('${ticker}', this)">
      <span>AI 분석 리포트</span>
      <svg viewBox="0 0 16 16" fill="currentColor"><path d="M4.427 7.427l3.396 3.396a.25.25 0 00.354 0l3.396-3.396A.25.25 0 0011.396 7H4.604a.25.25 0 00-.177.427z"/></svg>
    </div>
    <div class="analysis-body" id="analysis-${ticker}">
      ${renderAnalysis(d.analysis)}
    </div>
  </div>

  <div class="card-footer">
    <span class="card-updated">${d.updated_at ? '갱신: ' + fmtDate(d.updated_at) : '미갱신'}</span>
    <div style="display:flex;gap:6px">
      <button class="btn" onclick="refreshOne('${ticker}')">
        <svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 2.5a5.487 5.487 0 00-4.131 1.869l1.204 1.204A.25.25 0 014.896 6H1.25A.25.25 0 011 5.75V2.104a.25.25 0 01.427-.177l1.38 1.38A7.001 7.001 0 0114.95 7.16a.75.75 0 11-1.49.178A5.501 5.501 0 008 2.5zM1.705 8.005a.75.75 0 01.834.656 5.501 5.501 0 009.592 2.97l-1.204-1.204a.25.25 0 01.177-.427h3.646a.25.25 0 01.25.25v3.646a.25.25 0 01-.427.177l-1.38-1.38A7.001 7.001 0 011.05 8.84a.75.75 0 01.656-.834z"/></svg>
        갱신
      </button>
      <button class="btn btn-danger" onclick="removeStock('${ticker}')">
        <svg viewBox="0 0 16 16" fill="currentColor"><path d="M11 1.75V3h2.25a.75.75 0 010 1.5H2.75a.75.75 0 010-1.5H5V1.75C5 .784 5.784 0 6.75 0h2.5C10.216 0 11 .784 11 1.75zM4.496 6.675l.66 6.6a.25.25 0 00.249.225h5.19a.25.25 0 00.249-.225l.66-6.6a.75.75 0 011.492.149l-.66 6.6A1.748 1.748 0 0110.595 15h-5.19a1.75 1.75 0 01-1.741-1.576l-.66-6.6a.75.75 0 111.492-.149z"/></svg>
        삭제
      </button>
    </div>
  </div>
</div>`;
}

/* ── Toggle analysis ─────────────────────────────────────────────────────── */
function toggleAnalysis(ticker, btn) {
  const body = document.getElementById(`analysis-${ticker}`);
  body.classList.toggle('visible');
  btn.classList.toggle('open');
}

/* ── Add stock ───────────────────────────────────────────────────────────── */
async function addStock() {
  const input = document.getElementById('ticker-input');
  const ticker = input.value.trim().toUpperCase();
  if (!ticker) return;

  const addBtn = document.getElementById('add-btn');
  addBtn.classList.add('loading');
  addBtn.textContent = '추가 중...';
  setLoadingBar(30);

  try {
    const res = await api('POST', '/api/watchlist', { ticker });
    input.value = '';
    setLoadingBar(100);

    // Add card
    document.getElementById('empty-state')?.remove();
    const grid = document.getElementById('stocks-grid');
    const tmp = document.createElement('div');
    tmp.innerHTML = buildCard(ticker, res.data);
    grid.appendChild(tmp.firstElementChild);
    renderChart(ticker, res.data?.chart_data);
    updateWatchlistAITickerSelect();
    toast(`${ticker} 추가 완료`, 'success');
  } catch (e) {
    setLoadingBar(0);
    toast(e.message, 'error');
  } finally {
    addBtn.classList.remove('loading');
    addBtn.textContent = '추가';
  }
}

/* ── Remove stock ────────────────────────────────────────────────────────── */
async function removeStock(ticker) {
  if (!confirm(`${ticker}를 관심 종목에서 삭제할까요?`)) return;
  try {
    await api('DELETE', `/api/watchlist/${ticker}`);
    document.getElementById(`card-${ticker}`)?.remove();
    if (charts[ticker]) { charts[ticker].destroy(); delete charts[ticker]; }
    updateWatchlistAITickerSelect();
    toast(`${ticker} 삭제`, 'info');
    checkEmpty();
  } catch (e) {
    toast(e.message, 'error');
  }
}

/* ── Refresh one ─────────────────────────────────────────────────────────── */
async function refreshOne(ticker) {
  const card = document.getElementById(`card-${ticker}`);
  // Show loading overlay
  const overlay = document.createElement('div');
  overlay.className = 'card-loading';
  overlay.innerHTML = `<div class="spinner"></div><div class="card-loading-text">AI 분석 중...</div>`;
  card.appendChild(overlay);

  try {
    const res = await api('POST', `/api/refresh/${ticker}`);
    // Replace card
    const tmp = document.createElement('div');
    tmp.innerHTML = buildCard(ticker, res.data);
    card.replaceWith(tmp.firstElementChild);
    renderChart(ticker, res.data?.chart_data);
    toast(`${ticker} 갱신 완료`, 'success');
  } catch (e) {
    overlay.remove();
    toast(e.message, 'error');
  }
}

/* ── Refresh all ─────────────────────────────────────────────────────────── */
async function refreshAll() {
  const btn = document.getElementById('refresh-all-btn');
  btn.classList.add('loading');
  btn.textContent = '갱신 중...';
  setLoadingBar(10);

  try {
    const results = await api('POST', '/api/refresh');
    let ok = 0;
    results.forEach(r => {
      if (r.success && r.data) {
        const card = document.getElementById(`card-${r.ticker}`);
        if (card) {
          const tmp = document.createElement('div');
          tmp.innerHTML = buildCard(r.ticker, r.data);
          card.replaceWith(tmp.firstElementChild);
          renderChart(r.ticker, r.data?.chart_data);
        }
        ok++;
      }
    });
    setLoadingBar(100);
    updateLastUpdated();
    toast(`${ok}/${results.length}개 갱신 완료`, ok === results.length ? 'success' : 'info');
  } catch (e) {
    setLoadingBar(0);
    toast(e.message, 'error');
  } finally {
    btn.classList.remove('loading');
    btn.textContent = '전체 갱신';
  }
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function updateLastUpdated() {
  document.getElementById('last-updated').textContent =
    '마지막 갱신: ' + new Date().toLocaleString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

function checkEmpty() {
  const grid = document.getElementById('stocks-grid');
  if (!grid.children.length) {
    const el = document.createElement('div');
    el.id = 'empty-state';
    el.innerHTML = `
      <svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 0a8 8 0 100 16A8 8 0 008 0zM1.5 8a6.5 6.5 0 1113 0 6.5 6.5 0 01-13 0z"/><path d="M6.5 7.75A.75.75 0 017.25 7h1a.75.75 0 01.75.75v2.75h.25a.75.75 0 010 1.5h-2a.75.75 0 010-1.5h.25v-2h-.25a.75.75 0 01-.75-.75zM8 6a1 1 0 100-2 1 1 0 000 2z"/></svg>
      <h2>관심 종목이 없습니다</h2>
      <p>위 검색창에 티커를 입력해 종목을 추가하세요.<br>한국 주식은 <strong>005930.KS</strong> 형식으로 입력하세요.</p>`;
    grid.replaceWith(el);
  }
}

/* ── Init ────────────────────────────────────────────────────────────────── */
async function init() {
  setLoadingBar(20);
  try {
    const list = await api('GET', '/api/watchlist');
    const grid = document.getElementById('stocks-grid');

    if (!list.length) {
      checkEmpty();
      return;
    }

    list.forEach(({ ticker, data }) => {
      const tmp = document.createElement('div');
      tmp.innerHTML = buildCard(ticker, data);
      grid.appendChild(tmp.firstElementChild);
    });

    // Charts after DOM is ready
    list.forEach(({ ticker, data }) => renderChart(ticker, data?.chart_data));
    updateWatchlistAITickerSelect();
    setLoadingBar(100);
  } catch (e) {
    setLoadingBar(0);
    toast('데이터 로딩 실패: ' + e.message, 'error');
  }
}

/* ── Tab switching ───────────────────────────────────────────────────────── */
function switchTab(tab) {
  ['watchlist', 'research', 'fdd', 'news'].forEach(t => {
    const page = document.getElementById(`page-${t}`);
    const btn  = document.getElementById(`tab-${t}`);
    if (page) page.style.display = t === tab ? '' : 'none';
    if (btn)  btn.classList.toggle('active', t === tab);
  });
  document.getElementById('refresh-all-btn').style.display = tab === 'watchlist' ? '' : 'none';
  if (tab === 'research') loadResearchHistory();
  if (tab === 'fdd') loadFDDHistory();
}

/* ══════════════════════════════════════════════════════════════
   FDD — File Upload
══════════════════════════════════════════════════════════════ */
let fddFile = null;

function fddInitDropzone() {
  const zone = document.getElementById('fdd-dropzone');
  const input = document.getElementById('fdd-file-input');
  if (!zone) return;

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) fddSetFile(file);
  });
  input.addEventListener('change', () => {
    if (input.files[0]) fddSetFile(input.files[0]);
  });
}

function fddSetFile(file) {
  const allowed = ['pdf', 'xlsx', 'xls', 'xlsm'];
  const ext = file.name.split('.').pop().toLowerCase();
  if (!allowed.includes(ext)) {
    toast('PDF 또는 Excel 파일만 업로드 가능합니다', 'error'); return;
  }
  if (file.size > 20 * 1024 * 1024) {
    toast('파일 크기가 20MB를 초과합니다', 'error'); return;
  }
  fddFile = file;
  document.getElementById('fdd-file-name').textContent = `📎 ${file.name} (${(file.size/1024/1024).toFixed(1)}MB)`;
  document.getElementById('fdd-file-info').style.display = 'flex';
  document.getElementById('fdd-dropzone').style.display = 'none';
  document.getElementById('fdd-submit-btn').disabled = false;
}

function fddClearFile() {
  fddFile = null;
  document.getElementById('fdd-file-info').style.display = 'none';
  document.getElementById('fdd-dropzone').style.display = '';
  document.getElementById('fdd-submit-btn').disabled = true;
  document.getElementById('fdd-file-input').value = '';
}

/* ── FDD Run ─────────────────────────────────────────────────────────────── */
async function runFDD() {
  if (!fddFile) { toast('파일을 먼저 업로드해주세요', 'error'); return; }

  const companyName = document.getElementById('fdd-company-input').value.trim();
  const submitBtn = document.getElementById('fdd-submit-btn');
  submitBtn.disabled = true;
  submitBtn.textContent = '분석 중...';

  // 결과 영역 초기화
  document.getElementById('fdd-result-placeholder').style.display = 'none';
  document.getElementById('fdd-result').innerHTML = '';

  // Agent 진행 UI 표시
  const agentsEl = document.getElementById('fdd-agents');
  agentsEl.style.display = '';
  fddSetAgentStep(1, 'active');
  fddSetAgentStep(2, 'waiting');
  fddSetAgentStep(3, 'waiting');

  // Agent 스텝 타이머 시뮬레이션
  const stepTimer = setTimeout(() => fddSetAgentStep(2, 'active'), 15000);
  const stepTimer2 = setTimeout(() => fddSetAgentStep(3, 'active'), 35000);

  try {
    const formData = new FormData();
    formData.append('file', fddFile);
    formData.append('company_name', companyName);

    setLoadingBar(20);
    const res = await fetch('/api/fdd/upload', { method: 'POST', body: formData });
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch {
      throw new Error(`서버 응답 오류 (HTTP ${res.status}). 잠시 후 다시 시도해주세요.`);
    }
    clearTimeout(stepTimer); clearTimeout(stepTimer2);

    if (!res.ok) { throw new Error(data.error || `HTTP ${res.status}`); }

    fddSetAgentStep(1, 'done');
    fddSetAgentStep(2, 'done');
    fddSetAgentStep(3, 'done');
    setLoadingBar(100);

    renderFDDResult(data);
    loadFDDHistory();
    toast(`${data.company_name || companyName} 재무실사 완료`, 'success');
  } catch (e) {
    clearTimeout(stepTimer); clearTimeout(stepTimer2);
    fddSetAgentStep(1, 'error');
    setLoadingBar(0);
    toast('재무실사 실패: ' + e.message, 'error');
    document.getElementById('fdd-result-placeholder').style.display = '';
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = '재무실사 시작';
  }
}

function fddSetAgentStep(n, state) {
  const el = document.getElementById(`fdd-step${n}`);
  const statusEl = document.getElementById(`fdd-step${n}-status`);
  if (!el || !statusEl) return;
  el.className = `agent-step ${state}`;
  statusEl.textContent = state === 'done' ? '✅' : state === 'active' ? '⚙️' : state === 'error' ? '❌' : '⏳';
}

/* ── FDD Result Render ───────────────────────────────────────────────────── */
const FDD_SECTION_META = [
  { icon: '📋', color: '#58a6ff' },
  { icon: '💹', color: '#3fb950' },
  { icon: '🏦', color: '#d29922' },
  { icon: '💵', color: '#bc8cff' },
  { icon: '⚖️', color: '#f0883e' },
  { icon: '🚨', color: '#f85149' },
  { icon: '🔎', color: '#79c0ff' },
  { icon: '📌', color: '#56d364' },
];

function renderFDDResult(data) {
  const container = document.getElementById('fdd-result');
  const sections = parseReportSections(data.report);

  const sectionsHtml = sections.map((s, i) => {
    const meta = FDD_SECTION_META[i] || { icon: '📄', color: '#8b949e' };
    return `
      <div class="res-section">
        <div class="res-section-header" onclick="toggleResSection(this)">
          <span class="res-section-icon" style="color:${meta.color}">${meta.icon}</span>
          <span class="res-section-title">${s.title}</span>
          <svg class="res-chevron" viewBox="0 0 16 16" fill="currentColor">
            <path d="M4.427 7.427l3.396 3.396a.25.25 0 00.354 0l3.396-3.396A.25.25 0 0011.396 7H4.604a.25.25 0 00-.177.427z"/>
          </svg>
        </div>
        <div class="res-section-body visible">${renderReportMarkdown(s.content)}</div>
      </div>`;
  }).join('');

  showFDDAIPanel(data.company_name);

  container.innerHTML = `
    <div class="res-card">
      <div class="res-card-header" style="background:linear-gradient(135deg,rgba(210,153,34,.1),rgba(240,136,62,.07))">
        <div>
          <div class="res-company-name">${data.company_name || '재무실사 리포트'}</div>
          <div class="res-meta">신한투자증권 AI Financial Due Diligence &nbsp;·&nbsp; ${fmtDate(data.analyzed_at)}</div>
          <div class="res-meta" style="margin-top:2px">📎 ${data.filename}</div>
        </div>
      </div>
      <div class="res-sections">${sectionsHtml}</div>
    </div>`;
}

/* ── FDD History ─────────────────────────────────────────────────────────── */
async function loadFDDHistory() {
  try {
    const history = await api('GET', '/api/fdd/history');
    const el = document.getElementById('fdd-history');
    if (!history.length) { el.innerHTML = ''; return; }
    el.innerHTML = `
      <div class="fdd-history-title">최근 분석 이력</div>
      ${history.map(h => `
        <div class="fdd-history-item" onclick="loadFDDCache('${h.cache_file}')">
          <div class="fdd-history-company">${h.company_name}</div>
          <div class="fdd-history-meta">${h.filename} · ${fmtDate(h.analyzed_at)}</div>
        </div>`).join('')}`;
  } catch (_) {}
}

async function loadFDDCache(cacheFile) {
  try {
    const data = await api('GET', `/api/fdd/cache/${encodeURIComponent(cacheFile)}`);
    document.getElementById('fdd-result-placeholder').style.display = 'none';
    renderFDDResult(data);
    document.getElementById('fdd-agents').style.display = 'none';
  } catch (e) {
    toast('이력 불러오기 실패', 'error');
  }
}

/* ── Research: history ───────────────────────────────────────────────────── */
async function loadResearchHistory() {
  try {
    const history = await api('GET', '/api/research/history');
    const bar = document.getElementById('research-history-bar');
    if (!history.length) { bar.innerHTML = ''; return; }
    bar.innerHTML = `
      <div class="history-bar">
        <span class="history-label">최근 검색:</span>
        ${history.slice(0, 8).map(h =>
          `<button class="history-chip" onclick="loadResearchFromHistory('${h.company}')">${h.company}</button>`
        ).join('')}
      </div>`;
  } catch (_) {}
}

async function loadResearchFromHistory(company) {
  document.getElementById('research-input').value = company;
  // 캐시에서 바로 로드
  try {
    const result = await api('GET', `/api/research/${encodeURIComponent(company)}`);
    renderResearchResult(result);
  } catch (_) {
    researchCompany();
  }
}

/* ── Research: main ──────────────────────────────────────────────────────── */
async function researchCompany(forceRefresh = false) {
  const input = document.getElementById('research-input');
  const company = input.value.trim();
  if (!company) { toast('회사명을 입력해주세요', 'error'); return; }

  // 로딩 UI
  document.getElementById('research-result').innerHTML = '';
  document.getElementById('research-loading').style.display = '';
  document.getElementById('research-btn').disabled = true;
  setLoadingBar(15);

  // 스텝 애니메이션
  const steps = ['step-search', 'step-analyze', 'step-done'];
  let stepIdx = 0;
  const stepTimer = setInterval(() => {
    steps.forEach((id, i) => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle('active', i === stepIdx);
    });
    stepIdx = (stepIdx + 1) % steps.length;
  }, 4000);

  try {
    const result = await api('POST', '/api/research', { company, refresh: forceRefresh });
    clearInterval(stepTimer);
    setLoadingBar(100);
    document.getElementById('research-loading').style.display = 'none';
    renderResearchResult(result);
    loadResearchHistory();
    toast(`${company} 리서치 완료`, 'success');
  } catch (e) {
    clearInterval(stepTimer);
    setLoadingBar(0);
    document.getElementById('research-loading').style.display = 'none';
    toast(e.message, 'error');
  } finally {
    document.getElementById('research-btn').disabled = false;
  }
}

/* ── Research: render result ─────────────────────────────────────────────── */
const SECTION_META = [
  { icon: '🏢', color: '#58a6ff' },
  { icon: '⚙️', color: '#3fb950' },
  { icon: '💰', color: '#d29922' },
  { icon: '📊', color: '#bc8cff' },
  { icon: '🚀', color: '#f0883e' },
  { icon: '📰', color: '#8b949e' },
];

function renderResearchResult(data) {
  const container = document.getElementById('research-result');
  const sections = parseReportSections(data.report);

  const sectionsHtml = sections.map((s, i) => {
    const meta = SECTION_META[i] || { icon: '📋', color: '#8b949e' };
    return `
      <div class="res-section">
        <div class="res-section-header" onclick="toggleResSection(this)">
          <span class="res-section-icon" style="color:${meta.color}">${meta.icon}</span>
          <span class="res-section-title">${s.title}</span>
          <svg class="res-chevron" viewBox="0 0 16 16" fill="currentColor">
            <path d="M4.427 7.427l3.396 3.396a.25.25 0 00.354 0l3.396-3.396A.25.25 0 0011.396 7H4.604a.25.25 0 00-.177.427z"/>
          </svg>
        </div>
        <div class="res-section-body visible">${renderReportMarkdown(s.content)}</div>
      </div>`;
  }).join('');

  const sourcesHtml = data.sources?.length ? `
    <div class="res-sources">
      <div class="res-sources-title">📎 참고 출처</div>
      <div class="res-sources-list">
        ${data.sources.slice(0, 10).map(s =>
          `<a href="${s.url}" target="_blank" rel="noopener" class="res-source-link" title="${s.title}">${s.title}</a>`
        ).join('')}
      </div>
    </div>` : '';

  showResearchAIPanel(data.company_name);

  container.innerHTML = `
    <div class="res-card">
      <div class="res-card-header">
        <div>
          <div class="res-company-name">${data.company_name}</div>
          <div class="res-meta">신한투자증권 AI 리서치 리포트 &nbsp;·&nbsp; ${fmtDate(data.researched_at)}</div>
        </div>
        <button class="btn btn-primary" onclick="researchCompany(true)">
          <svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 2.5a5.487 5.487 0 00-4.131 1.869l1.204 1.204A.25.25 0 014.896 6H1.25A.25.25 0 011 5.75V2.104a.25.25 0 01.427-.177l1.38 1.38A7.001 7.001 0 0114.95 7.16a.75.75 0 11-1.49.178A5.501 5.501 0 008 2.5z"/></svg>
          재분석
        </button>
      </div>
      <div class="res-sections">${sectionsHtml}</div>
      ${sourcesHtml}
    </div>`;
}

function toggleResSection(header) {
  const body = header.nextElementSibling;
  const chevron = header.querySelector('.res-chevron');
  body.classList.toggle('visible');
  chevron.classList.toggle('open');
}

/* ── Research: parse report sections ────────────────────────────────────── */
function parseReportSections(report) {
  if (!report) return [];
  const sections = [];
  // ## N. 섹션명 패턴으로 분할
  const parts = report.split(/(?=^## \d+\.)/m);
  for (const part of parts) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const firstLine = trimmed.split('\n')[0].replace(/^##\s*\d+\.\s*/, '').trim();
    const content = trimmed.split('\n').slice(1).join('\n').trim();
    if (firstLine) sections.push({ title: firstLine, content });
  }
  return sections;
}

function renderReportMarkdown(text) {
  if (!text) return '<span style="color:var(--text-dim)">정보 없음</span>';
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^-{1}\s+(.+)$/gm, '<li>$1</li>')
    .replace(/(<li>[\s\S]*?<\/li>(?:\s*<li>[\s\S]*?<\/li>)*)/g, '<ul>$1</ul>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br>');
}

/* ══════════════════════════════════════════════════════════════
   News Sentiment & Investment Idea
══════════════════════════════════════════════════════════════ */

let _nsPeriod = 7;

function nsSetPeriod(days) {
  _nsPeriod = days;
  document.getElementById('ns-period-7').classList.toggle('active', days === 7);
  document.getElementById('ns-period-30').classList.toggle('active', days === 30);
}

function nsSetAgentStep(n, state) {
  const el = document.getElementById(`ns-step${n}`);
  const statusEl = document.getElementById(`ns-step${n}-status`);
  if (!el || !statusEl) return;
  el.className = `agent-step ${state}`;
  statusEl.textContent = state === 'done' ? '✅' : state === 'active' ? '⚙️' : state === 'error' ? '❌' : '⏳';
}

async function runNewsSentiment() {
  const query = document.getElementById('ns-input').value.trim();
  if (!query) { toast('종목명 또는 티커를 입력해주세요', 'error'); return; }

  const btn = document.getElementById('ns-btn');
  btn.disabled = true;
  btn.textContent = '분석 중...';
  setLoadingBar(10);

  // Agent 진행 UI 표시
  const agentsEl = document.getElementById('ns-agents');
  agentsEl.style.display = '';
  nsSetAgentStep(1, 'active');
  nsSetAgentStep(2, 'waiting');
  nsSetAgentStep(3, 'waiting');
  document.getElementById('ns-result').innerHTML = '';

  // 스텝 타이머 시뮬레이션
  const t1 = setTimeout(() => nsSetAgentStep(2, 'active'), 8000);
  const t2 = setTimeout(() => nsSetAgentStep(3, 'active'), 20000);

  try {
    const result = await api('POST', '/api/news-sentiment', { query, days: _nsPeriod });
    clearTimeout(t1); clearTimeout(t2);
    nsSetAgentStep(1, 'done');
    nsSetAgentStep(2, 'done');
    nsSetAgentStep(3, 'done');
    setLoadingBar(100);
    renderNewsSentimentResult(result);
    toast(`${query} 뉴스 분석 완료`, 'success');
  } catch (e) {
    clearTimeout(t1); clearTimeout(t2);
    nsSetAgentStep(1, 'error');
    setLoadingBar(0);
    toast('분석 실패: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Analyze News Flow';
  }
}

/* ── Render 3 cards ──────────────────────────────────────────────────────── */
function renderNewsSentimentResult(data) {
  const container = document.getElementById('ns-result');

  // sentiment article map
  const sentMap = {};
  (data.sentiment?.articles || []).forEach(a => { sentMap[a.index] = a; });

  const label = data.display_name && data.display_name !== data.query
    ? `${data.display_name} (${data.query})`
    : data.query;

  container.innerHTML = [
    renderNSNewsCard(data.news || [], sentMap, data.period_days, label),
    renderNSSentimentCard(data.sentiment || {}, data.news?.length || 0),
    renderNSIdeaCard(data.investment_idea || {}, label, data.analyzed_at),
  ].join('');
}

/* ── Card 1: Recent News ─────────────────────────────────────────────────── */
function renderNSNewsCard(news, sentMap, days, label) {
  const items = news.map((a, i) => {
    const sa = sentMap[i + 1] || {};
    const sent = sa.sentiment || 'neutral';
    const badgeClass = `ns-badge-${sent}`;
    const badgeLabel = sent === 'positive' ? '긍정' : sent === 'negative' ? '부정' : '중립';
    return `
      <div class="ns-news-item">
        <span class="ns-news-badge ${badgeClass}">${badgeLabel}</span>
        <div class="ns-news-body">
          <a class="ns-news-title" href="${a.url || '#'}" target="_blank" rel="noopener" title="${a.title}">${a.title}</a>
          ${sa.reason ? `<div class="ns-news-reason">${sa.reason}</div>` : ''}
        </div>
        <div class="ns-news-right">
          <div class="ns-news-date">${a.date || ''}</div>
          <div class="ns-news-source">${a.source || ''}</div>
        </div>
      </div>`;
  }).join('');

  return `
    <div class="ns-card">
      <div class="ns-card-header">
        <span class="ns-card-icon">📰</span>
        <span class="ns-card-title">Recent News</span>
        <span class="ns-card-meta">${label || ''} · 최근 ${days}일 · ${news.length}건</span>
      </div>
      <div class="ns-news-list">${items || '<div style="padding:16px 20px;color:var(--text-dim);font-size:.85rem">뉴스 없음</div>'}</div>
    </div>`;
}

/* ── Card 2: Sentiment Summary ───────────────────────────────────────────── */
function renderNSSentimentCard(s, total) {
  const overall = s.overall_sentiment || 'neutral';
  const pos = s.positive_count || 0;
  const neu = s.neutral_count  || 0;
  const neg = s.negative_count || 0;
  const safeTotal = total || (pos + neu + neg) || 1;

  const overallLabel = overall === 'positive' ? '긍정적 POSITIVE' :
                       overall === 'negative' ? '부정적 NEGATIVE' : '중립 NEUTRAL';
  const overallClass = `ns-overall-${overall}`;

  const themes = (s.key_themes || []).map(t =>
    `<span class="ns-theme-chip">${t}</span>`).join('');

  const reasons = (s.main_reasons || []).map(r =>
    `<li>${r}</li>`).join('');

  return `
    <div class="ns-card">
      <div class="ns-card-header">
        <span class="ns-card-icon">📊</span>
        <span class="ns-card-title">Sentiment Summary</span>
        <span class="ns-card-meta">Agent 2 분석</span>
      </div>
      <div class="ns-sentiment-body">
        <div class="ns-overall-row">
          <div class="ns-overall-badge ${overallClass}">${overallLabel}</div>
          <div class="ns-count-chips">
            <span class="ns-count-chip ns-chip-pos">▲ 긍정 ${pos}</span>
            <span class="ns-count-chip ns-chip-neu">— 중립 ${neu}</span>
            <span class="ns-count-chip ns-chip-neg">▼ 부정 ${neg}</span>
          </div>
        </div>
        <div class="ns-bar-section">
          ${[
            { label: '긍정', count: pos, cls: 'pos' },
            { label: '중립', count: neu, cls: 'neu' },
            { label: '부정', count: neg, cls: 'neg' },
          ].map(b => `
            <div class="ns-bar-row">
              <span class="ns-bar-label">${b.label}</span>
              <div class="ns-bar-track">
                <div class="ns-bar-fill ns-bar-fill-${b.cls}" style="width:${Math.round(b.count/safeTotal*100)}%"></div>
              </div>
              <span class="ns-bar-count">${b.count}</span>
            </div>`).join('')}
        </div>
        ${themes ? `
        <div class="ns-themes-section">
          <div class="ns-section-label">주요 테마</div>
          <div class="ns-theme-chips">${themes}</div>
        </div>` : ''}
        ${reasons ? `
        <div>
          <div class="ns-section-label">주요 이유</div>
          <ul class="ns-reasons-list">${reasons}</ul>
        </div>` : ''}
      </div>
    </div>`;
}

/* ── Card 3: Investment Idea ─────────────────────────────────────────────── */
function renderNSIdeaCard(idea, query, analyzedAt) {
  const rec = idea.recommendation || '중립 관망';
  const recClass = rec === '매수 검토' ? 'ns-rec-buy' :
                   rec === '리스크 주의' ? 'ns-rec-risk' : 'ns-rec-neutral';

  const bullHtml = (idea.bullish_points || []).map(p =>
    `<div class="ns-idea-point">${p}</div>`).join('');
  const bearHtml = (idea.bearish_points || []).map(p =>
    `<div class="ns-idea-point">${p}</div>`).join('');
  const watchHtml = (idea.watch_items || []).map(w =>
    `<span class="ns-watch-item">${w}</span>`).join('');

  return `
    <div class="ns-card">
      <div class="ns-card-header">
        <span class="ns-card-icon">💡</span>
        <span class="ns-card-title">Investment Idea</span>
        <span class="ns-card-meta">Agent 3 · ${fmtDate(analyzedAt)}</span>
      </div>
      <div class="ns-idea-body">
        <div class="ns-rec-row">
          <span class="ns-rec-badge ${recClass}">${rec}</span>
          <span class="ns-rec-label">⚠️ 본 내용은 참고용이며 투자 권유가 아닙니다</span>
        </div>
        <div class="ns-conclusion">${idea.core_conclusion || ''}</div>
        <div class="ns-idea-grid">
          <div class="ns-idea-col ns-idea-col-bull">
            <div class="ns-idea-col-title">Bullish Points</div>
            ${bullHtml || '<div class="ns-idea-point">없음</div>'}
          </div>
          <div class="ns-idea-col ns-idea-col-bear">
            <div class="ns-idea-col-title">Bearish Points</div>
            ${bearHtml || '<div class="ns-idea-point">없음</div>'}
          </div>
        </div>
        ${watchHtml ? `
        <div class="ns-watch-section">
          <div class="ns-section-label" style="color:var(--yellow)">Watch Items</div>
          <div class="ns-watch-items">${watchHtml}</div>
        </div>` : ''}
      </div>
    </div>`;
}

/* ══════════════════════════════════════════════════════════════
   AI Analyst Panel
══════════════════════════════════════════════════════════════ */

let _researchCurrentCompany = null;
let _fddCurrentCompany = null;

/** 관심 종목 탭: 카드가 추가/삭제될 때마다 ticker select 동기화 */
function updateWatchlistAITickerSelect() {
  const sel = document.getElementById('watchlist-ai-ticker-select');
  if (!sel) return;
  const cards = document.querySelectorAll('.stock-card');
  const tickers = Array.from(cards).map(c => c.id.replace('card-', ''));
  const current = sel.value;
  sel.innerHTML = '<option value="">전체 (선택 없음)</option>';
  tickers.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t;
    opt.textContent = t;
    if (t === current) opt.selected = true;
    sel.appendChild(opt);
  });
}

/** 비상장사 리서치 탭: 결과가 나온 뒤 패널 표시 */
function showResearchAIPanel(companyName) {
  _researchCurrentCompany = companyName;
  const panel = document.getElementById('research-ai-panel');
  const badge = document.getElementById('research-ai-context-badge');
  if (panel) panel.style.display = '';
  if (badge) badge.textContent = companyName;
}

/** 재무실사 탭: 결과가 나온 뒤 패널 표시 */
function showFDDAIPanel(companyName) {
  _fddCurrentCompany = companyName;
  const panel = document.getElementById('fdd-ai-panel');
  const badge = document.getElementById('fdd-ai-context-badge');
  if (panel) panel.style.display = '';
  if (badge) badge.textContent = companyName || '업로드된 재무제표';
}

/** /api/analyze 호출 공통 함수 */
async function submitAnalyzeQuery(tabId) {
  const textarea = document.getElementById(`${tabId}-ai-textarea`);
  const resultEl = document.getElementById(`${tabId}-ai-result`);
  const btn      = document.getElementById(`${tabId}-ai-btn`);

  const question = textarea?.value.trim();
  if (!question) { toast('질문을 입력해주세요', 'error'); return; }
  if (question.length > 4000) { toast('질문이 너무 깁니다 (최대 4000자)', 'error'); return; }

  // 컨텍스트 빌드
  let context = null;
  if (tabId === 'watchlist') {
    const ticker = document.getElementById('watchlist-ai-ticker-select')?.value;
    if (ticker) context = { ticker };
  } else if (tabId === 'research' && _researchCurrentCompany) {
    context = { company: _researchCurrentCompany };
  } else if (tabId === 'fdd' && _fddCurrentCompany) {
    context = { company: _fddCurrentCompany };
  }

  btn.disabled = true;
  resultEl.innerHTML = `
    <div class="ai-loading-indicator">
      <div class="spinner"></div>
      <span>Claude가 분석 중입니다... (최대 30초 소요)</span>
    </div>`;
  setLoadingBar(20);

  try {
    const result = await api('POST', '/api/analyze', { question, context });
    setLoadingBar(100);
    renderAIAnswer(`${tabId}-ai-result`, result);
  } catch (e) {
    setLoadingBar(0);
    resultEl.innerHTML = `<div style="color:var(--red);font-size:.85rem;padding:12px 0">오류: ${e.message}</div>`;
    toast('분석 요청 실패: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

function renderAIAnswer(containerId, result) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const answerHtml = renderAnalysis(result.answer);
  const tokenInfo  = `입력 ${(result.input_tokens || 0).toLocaleString()} / 출력 ${(result.output_tokens || 0).toLocaleString()} 토큰`;

  const thinkingHtml = result.thinking ? `
    <div class="ai-thinking-toggle" onclick="toggleAIThinking(this)">
      <svg viewBox="0 0 16 16" fill="currentColor"><path d="M4.427 7.427l3.396 3.396a.25.25 0 00.354 0l3.396-3.396A.25.25 0 0011.396 7H4.604a.25.25 0 00-.177.427z"/></svg>
      💭 내부 추론 과정 보기 (Thinking)
    </div>
    <div class="ai-thinking-body">${result.thinking.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
  ` : '';

  el.innerHTML = `
    <div class="ai-answer-card">
      <div class="ai-answer-header">
        <span style="font-size:.9rem">🤖</span>
        <span class="ai-answer-title">AI 애널리스트 답변</span>
        <span class="ai-token-info">${tokenInfo}</span>
      </div>
      <div class="ai-answer-body">${answerHtml}</div>
      ${thinkingHtml}
    </div>`;
}

function toggleAIThinking(btn) {
  btn.nextElementSibling.classList.toggle('visible');
  btn.classList.toggle('open');
}

/* ── Event listeners ─────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  init();

  document.getElementById('ticker-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') addStock();
  });

  document.getElementById('add-btn').addEventListener('click', addStock);
  document.getElementById('refresh-all-btn').addEventListener('click', refreshAll);

  document.getElementById('research-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') researchCompany();
  });
  document.getElementById('research-btn').addEventListener('click', () => researchCompany());

  fddInitDropzone();

  // News Sentiment 이벤트
  document.getElementById('ns-btn').addEventListener('click', runNewsSentiment);
  document.getElementById('ns-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') runNewsSentiment();
  });

  // AI 질문 패널 이벤트
  document.getElementById('watchlist-ai-btn').addEventListener('click', () => submitAnalyzeQuery('watchlist'));
  document.getElementById('research-ai-btn').addEventListener('click', () => submitAnalyzeQuery('research'));
  document.getElementById('fdd-ai-btn').addEventListener('click', () => submitAnalyzeQuery('fdd'));

  // Ctrl+Enter 단축키
  ['watchlist', 'research', 'fdd'].forEach(tabId => {
    const ta = document.getElementById(`${tabId}-ai-textarea`);
    if (ta) ta.addEventListener('keydown', e => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submitAnalyzeQuery(tabId);
    });
  });
});
