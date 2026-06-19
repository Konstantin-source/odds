/* ================================================================
   AKTIEN DASHBOARD — Application Logic (Vanilla JS)
   ================================================================ */

// ===== API Module =====
const API = {
  /** POST /api/login */
  async login(password) {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ password }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Login fehlgeschlagen');
    }
    return res.json();
  },

  /** POST /api/logout */
  async logout() {
    const res = await fetch('/api/logout', {
      method: 'POST',
      credentials: 'same-origin',
    });
    if (!res.ok) throw new Error('Logout fehlgeschlagen');
    return res.json();
  },

  /** GET /api/auth/status */
  async checkAuth() {
    const res = await fetch('/api/auth/status', {
      credentials: 'same-origin',
    });
    if (res.status === 401) return { authenticated: false };
    if (!res.ok) throw new Error('Auth-Check fehlgeschlagen');
    return res.json();
  },

  /** GET /api/watchlist */
  async getWatchlist() {
    const res = await fetch('/api/watchlist', {
      credentials: 'same-origin',
    });
    if (res.status === 401) { Auth.showLogin(); throw new Error('Nicht authentifiziert'); }
    if (!res.ok) throw new Error('Watchlist konnte nicht geladen werden');
    return res.json();
  },

  /** POST /api/watchlist */
  async addToWatchlist(ticker, name) {
    const res = await fetch('/api/watchlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ ticker, name }),
    });
    if (res.status === 401) { Auth.showLogin(); throw new Error('Nicht authentifiziert'); }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Hinzufügen fehlgeschlagen');
    }
    return res.json();
  },

  /** DELETE /api/watchlist/{ticker} */
  async removeFromWatchlist(ticker) {
    const res = await fetch(`/api/watchlist/${encodeURIComponent(ticker)}`, {
      method: 'DELETE',
      credentials: 'same-origin',
    });
    if (res.status === 401) { Auth.showLogin(); throw new Error('Nicht authentifiziert'); }
    if (!res.ok) throw new Error('Entfernen fehlgeschlagen');
    return res.json();
  },

  /** GET /api/search?q=... */
  async searchStocks(query) {
    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
      credentials: 'same-origin',
    });
    if (res.status === 401) { Auth.showLogin(); throw new Error('Nicht authentifiziert'); }
    if (!res.ok) throw new Error('Suche fehlgeschlagen');
    return res.json();
  },

  /** GET /api/stock/{ticker}?period=... */
  async getStockData(ticker, period = '1mo') {
    const res = await fetch(`/api/stock/${encodeURIComponent(ticker)}?period=${encodeURIComponent(period)}`, {
      credentials: 'same-origin',
    });
    if (res.status === 401) { Auth.showLogin(); throw new Error('Nicht authentifiziert'); }
    if (!res.ok) throw new Error('Aktiendaten konnten nicht geladen werden');
    return res.json();
  },

  /** POST /api/analysis/{ticker} */
  async getAnalysis(ticker) {
    const res = await fetch(`/api/analysis/${encodeURIComponent(ticker)}`, {
      method: 'POST',
      credentials: 'same-origin',
    });
    if (res.status === 401) { Auth.showLogin(); throw new Error('Nicht authentifiziert'); }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Analyse fehlgeschlagen');
    }
    return res.json();
  },
};


// ===== Toast Module =====
const Toast = {
  /**
   * Show a toast notification
   * @param {string} message
   * @param {'info'|'success'|'error'} type
   */
  show(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = { success: '✅', error: '❌', info: 'ℹ️' };
    toast.innerHTML = `
      <span class="toast-icon">${icons[type] || icons.info}</span>
      <span>${this._escapeHtml(message)}</span>
    `;

    container.appendChild(toast);

    // Auto-dismiss after 4s
    setTimeout(() => {
      toast.classList.add('removing');
      toast.addEventListener('animationend', () => toast.remove(), { once: true });
    }, 4000);
  },

  success(msg) { this.show(msg, 'success'); },
  error(msg) { this.show(msg, 'error'); },
  info(msg) { this.show(msg, 'info'); },

  _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },
};


// ===== Auth Module =====
const Auth = {
  async init() {
    try {
      const status = await API.checkAuth();
      if (status.authenticated) {
        this.showDashboard();
      } else {
        this.showLogin();
      }
    } catch {
      this.showLogin();
    }
  },

  async login() {
    const input = document.getElementById('password-input');
    const btn = document.getElementById('login-btn');
    const btnText = btn.querySelector('.btn-text');
    const loader = document.getElementById('login-loader');
    const errorEl = document.getElementById('login-error');
    const errorText = document.getElementById('login-error-text');
    const password = input.value.trim();

    if (!password) {
      this._showError(errorEl, errorText, 'Bitte ein Passwort eingeben.');
      return;
    }

    // Loading state
    btn.disabled = true;
    btnText.textContent = 'Anmelden…';
    loader.classList.remove('hidden');
    errorEl.classList.add('hidden');

    try {
      await API.login(password);
      this.showDashboard();
      input.value = '';
    } catch (err) {
      this._showError(errorEl, errorText, err.message);
    } finally {
      btn.disabled = false;
      btnText.textContent = 'Anmelden';
      loader.classList.add('hidden');
    }
  },

  async logout() {
    try {
      await API.logout();
    } catch {
      // Ignore logout errors
    }
    StockDetail.stopRefresh();
    this.showLogin();
    Toast.info('Abgemeldet');
  },

  showLogin() {
    document.getElementById('login-screen').classList.remove('hidden');
    document.getElementById('dashboard').classList.add('hidden');
    document.getElementById('password-input').focus();
  },

  showDashboard() {
    document.getElementById('login-screen').classList.add('hidden');
    document.getElementById('dashboard').classList.remove('hidden');
    Watchlist.load();
  },

  _showError(el, textEl, msg) {
    textEl.textContent = msg;
    el.classList.remove('hidden');
  },
};


// ===== Watchlist Module =====
const Watchlist = {
  items: [],
  selectedTicker: null,

  async load() {
    try {
      const data = await API.getWatchlist();
      this.items = data.watchlist || data || [];
      this.render();
    } catch (err) {
      Toast.error(err.message);
    }
  },

  render() {
    const container = document.getElementById('watchlist');
    const emptyState = document.getElementById('watchlist-empty');
    const count = document.getElementById('watchlist-count');

    count.textContent = this.items.length;

    if (this.items.length === 0) {
      container.innerHTML = '';
      emptyState.classList.remove('hidden');
      return;
    }

    emptyState.classList.add('hidden');
    container.innerHTML = this.items.map((item, i) => {
      const isActive = item.ticker === this.selectedTicker;
      const changeClass = (item.change_percent || 0) >= 0 ? 'up' : 'down';
      const changeSign = (item.change_percent || 0) >= 0 ? '+' : '';
      const price = item.price != null ? StockDetail.formatCurrency(item.price, item.currency || 'USD') : '—';
      const changeStr = item.change_percent != null ? `${changeSign}${item.change_percent.toFixed(2)}%` : '';

      return `
        <div class="watchlist-item ${isActive ? 'active' : ''}"
             data-ticker="${this._escapeAttr(item.ticker)}"
             style="animation-delay: ${i * 40}ms"
             role="button" tabindex="0">
          <div class="watchlist-item-info">
            <div class="watchlist-item-ticker">${this._escapeHtml(item.ticker)}</div>
            <div class="watchlist-item-name">${this._escapeHtml(item.name || '')}</div>
          </div>
          <div class="watchlist-item-price">
            <span class="watchlist-item-value">${price}</span>
            <span class="watchlist-item-change ${changeClass}">${changeStr}</span>
          </div>
          <button class="watchlist-item-remove" data-ticker="${this._escapeAttr(item.ticker)}" title="Entfernen" aria-label="Entfernen">&times;</button>
        </div>
      `;
    }).join('');

    // Bind click events
    container.querySelectorAll('.watchlist-item').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target.closest('.watchlist-item-remove')) return;
        this.select(el.dataset.ticker);
      });
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          this.select(el.dataset.ticker);
        }
      });
    });

    container.querySelectorAll('.watchlist-item-remove').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.remove(btn.dataset.ticker);
      });
    });
  },

  async add(ticker, name) {
    try {
      await API.addToWatchlist(ticker, name);
      Toast.success(`${ticker} zur Watchlist hinzugefügt`);
      await this.load();
      this.select(ticker);
    } catch (err) {
      Toast.error(err.message);
    }
  },

  async remove(ticker) {
    try {
      await API.removeFromWatchlist(ticker);
      Toast.success(`${ticker} entfernt`);
      if (this.selectedTicker === ticker) {
        this.selectedTicker = null;
        StockDetail.stopRefresh();
        document.getElementById('stock-detail').classList.add('hidden');
        document.getElementById('empty-state').classList.remove('hidden');
      }
      await this.load();
    } catch (err) {
      Toast.error(err.message);
    }
  },

  select(ticker) {
    this.selectedTicker = ticker;
    // Update active state
    document.querySelectorAll('.watchlist-item').forEach(el => {
      el.classList.toggle('active', el.dataset.ticker === ticker);
    });
    // Close mobile sidebar
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebar-overlay').classList.add('hidden');
    // Load stock data
    StockDetail.load(ticker);
  },

  _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },

  _escapeAttr(str) {
    return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  },
};


// ===== Search Module =====
const Search = {
  debounceTimer: null,

  init() {
    const input = document.getElementById('search-input');
    const clearBtn = document.getElementById('search-clear');

    input.addEventListener('input', () => {
      const query = input.value.trim();
      clearBtn.classList.toggle('hidden', query.length === 0);

      clearTimeout(this.debounceTimer);
      if (query.length < 2) {
        this.hide();
        return;
      }
      this.debounceTimer = setTimeout(() => this.search(query), 300);
    });

    clearBtn.addEventListener('click', () => {
      input.value = '';
      clearBtn.classList.add('hidden');
      this.hide();
    });

    // Close dropdown on outside click
    document.addEventListener('click', (e) => {
      if (!e.target.closest('#search-container')) {
        this.hide();
      }
    });
  },

  async search(query) {
    try {
      const data = await API.searchStocks(query);
      const results = data.results || data || [];
      this.renderResults(results);
    } catch (err) {
      Toast.error(err.message);
    }
  },

  renderResults(results) {
    const container = document.getElementById('search-results');

    if (results.length === 0) {
      container.innerHTML = '<div class="search-no-results">Keine Ergebnisse gefunden</div>';
      container.classList.remove('hidden');
      return;
    }

    container.innerHTML = results.map(r => `
      <div class="search-result-item"
           data-ticker="${Watchlist._escapeAttr(r.ticker || r.symbol || '')}"
           data-name="${Watchlist._escapeAttr(r.name || r.shortname || '')}">
        <div class="search-result-info">
          <span class="search-result-ticker">${Watchlist._escapeHtml(r.ticker || r.symbol || '')}</span>
          <span class="search-result-name">${Watchlist._escapeHtml(r.name || r.shortname || '')}</span>
        </div>
        <span class="search-result-add">+</span>
      </div>
    `).join('');

    container.classList.remove('hidden');

    container.querySelectorAll('.search-result-item').forEach(el => {
      el.addEventListener('click', () => {
        Watchlist.add(el.dataset.ticker, el.dataset.name);
        document.getElementById('search-input').value = '';
        document.getElementById('search-clear').classList.add('hidden');
        this.hide();
      });
    });
  },

  hide() {
    document.getElementById('search-results').classList.add('hidden');
  },
};


// ===== StockDetail Module =====
const StockDetail = {
  currentTicker: null,
  currentPeriod: '1mo',
  refreshInterval: null,
  previousPrice: null,

  async load(ticker, period) {
    if (period) this.currentPeriod = period;
    this.currentTicker = ticker;

    const detailEl = document.getElementById('stock-detail');
    const emptyEl = document.getElementById('empty-state');

    emptyEl.classList.add('hidden');
    detailEl.classList.remove('hidden');

    // Show loading skeletons
    this._showSkeletons();

    try {
      const data = await API.getStockData(ticker, this.currentPeriod);
      this.renderHeader(data);
      this.renderChart(data.history || []);
      this.renderMetrics(data.quote || {}, data.fundamentals || {});
      this.renderIndicators(data.technicals || {});

      // Clear previous analysis
      document.getElementById('analysis-result').classList.add('hidden');
      document.getElementById('analysis-loading').classList.add('hidden');

      // Start auto-refresh
      this.startRefresh();
    } catch (err) {
      Toast.error(err.message);
    }
  },

  _showSkeletons() {
    document.getElementById('metrics-grid').innerHTML =
      Array(8).fill('<div class="skeleton skeleton-card"></div>').join('');
    document.getElementById('indicators-grid').innerHTML =
      Array(3).fill('<div class="skeleton skeleton-card"></div>').join('');
  },

  renderHeader(data) {
    const quote = data.quote || {};
    const nameEl = document.getElementById('stock-name');
    const tickerEl = document.getElementById('stock-ticker');
    const priceEl = document.getElementById('stock-price');
    const changeEl = document.getElementById('stock-change');

    nameEl.textContent = quote.name || data.name || this.currentTicker;
    tickerEl.textContent = this.currentTicker;

    const price = quote.price ?? quote.regularMarketPrice ?? 0;
    const changePct = quote.change_percent ?? quote.regularMarketChangePercent ?? 0;
    const currency = quote.currency || 'USD';

    // Price change animation
    if (this.previousPrice !== null && this.previousPrice !== price) {
      priceEl.classList.remove('price-up', 'price-down');
      void priceEl.offsetWidth; // force reflow
      priceEl.classList.add(price > this.previousPrice ? 'price-up' : 'price-down');
    }
    this.previousPrice = price;

    priceEl.textContent = this.formatCurrency(price, currency);

    const sign = changePct >= 0 ? '+' : '';
    changeEl.textContent = `${sign}${changePct.toFixed(2)}%`;
    changeEl.className = `stock-change ${changePct >= 0 ? 'up' : 'down'}`;
  },

  renderChart(history) {
    const canvas = document.getElementById('sparkline-chart');
    const container = document.getElementById('chart-container');
    const ctx = canvas.getContext('2d');

    const dpr = window.devicePixelRatio || 1;
    const rect = container.getBoundingClientRect();
    const width = rect.width - 48; // padding
    const height = 240;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, width, height);

    if (!history || history.length < 2) {
      ctx.fillStyle = 'rgba(148, 163, 184, 0.3)';
      ctx.font = '14px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Keine Kursdaten verfügbar', width / 2, height / 2);
      return;
    }

    const prices = history.map(h => h.close ?? h.price ?? h);
    const validPrices = prices.filter(p => typeof p === 'number' && !isNaN(p));
    if (validPrices.length < 2) return;

    const minPrice = Math.min(...validPrices);
    const maxPrice = Math.max(...validPrices);
    const range = maxPrice - minPrice || 1;

    const paddingTop = 20;
    const paddingBottom = 30;
    const chartHeight = height - paddingTop - paddingBottom;
    const stepX = width / (validPrices.length - 1);

    const isUp = validPrices[validPrices.length - 1] >= validPrices[0];
    const lineColor = isUp ? '#10b981' : '#ef4444';
    const fillColorTop = isUp ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)';
    const fillColorBottom = 'rgba(0, 0, 0, 0)';

    // Grid lines
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.06)';
    ctx.lineWidth = 1;
    for (let i = 0; i < 5; i++) {
      const y = paddingTop + (chartHeight / 4) * i;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // Price labels on grid
    ctx.fillStyle = 'rgba(148, 163, 184, 0.35)';
    ctx.font = '10px Inter, sans-serif';
    ctx.textAlign = 'right';
    for (let i = 0; i < 5; i++) {
      const y = paddingTop + (chartHeight / 4) * i;
      const priceVal = maxPrice - (range / 4) * i;
      ctx.fillText(this.formatNumber(priceVal), width - 4, y - 4);
    }

    // Build points
    const points = validPrices.map((p, i) => ({
      x: i * stepX,
      y: paddingTop + chartHeight - ((p - minPrice) / range) * chartHeight,
    }));

    // Gradient fill
    const gradient = ctx.createLinearGradient(0, paddingTop, 0, height);
    gradient.addColorStop(0, fillColorTop);
    gradient.addColorStop(1, fillColorBottom);

    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      // Smooth curve with quadratic bezier
      const prev = points[i - 1];
      const curr = points[i];
      const cpx = (prev.x + curr.x) / 2;
      ctx.quadraticCurveTo(prev.x + (curr.x - prev.x) * 0.5, prev.y, cpx, (prev.y + curr.y) / 2);
      if (i === points.length - 1) {
        ctx.quadraticCurveTo(cpx, (prev.y + curr.y) / 2, curr.x, curr.y);
      }
    }

    // Close for fill
    const linePath = new Path2D();
    linePath.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      linePath.lineTo(points[i].x, points[i].y);
    }

    // Fill area
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i].x, points[i].y);
    }
    ctx.lineTo(points[points.length - 1].x, height);
    ctx.lineTo(points[0].x, height);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Draw line
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i].x, points[i].y);
    }
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();

    // Endpoint dot
    const last = points[points.length - 1];
    ctx.beginPath();
    ctx.arc(last.x, last.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = lineColor;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(last.x, last.y, 7, 0, Math.PI * 2);
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.3;
    ctx.stroke();
    ctx.globalAlpha = 1;

    // Hover tooltip
    this._setupChartTooltip(canvas, container, points, validPrices, history, stepX, paddingTop, chartHeight, minPrice, range);
  },

  _setupChartTooltip(canvas, container, points, prices, history, stepX, paddingTop, chartHeight, minPrice, range) {
    const tooltip = document.getElementById('chart-tooltip');

    const onMove = (e) => {
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const idx = Math.round(mouseX / stepX);

      if (idx < 0 || idx >= points.length) {
        tooltip.classList.add('hidden');
        return;
      }

      const point = points[idx];
      const price = prices[idx];
      const entry = history[idx];
      const date = entry && entry.date ? new Date(entry.date).toLocaleDateString('de-DE') : '';

      tooltip.innerHTML = `<strong>${this.formatNumber(price)}</strong>${date ? `<br/>${date}` : ''}`;
      tooltip.classList.remove('hidden');

      // Position tooltip
      const tipW = tooltip.offsetWidth;
      const tipH = tooltip.offsetHeight;
      let left = point.x + 24 + 12; // 24 = container padding
      let top = point.y + 24 - tipH / 2;
      if (left + tipW > container.offsetWidth - 24) left = point.x + 24 - tipW - 12;
      tooltip.style.left = left + 'px';
      tooltip.style.top = top + 'px';
    };

    const onLeave = () => {
      tooltip.classList.add('hidden');
    };

    // Remove old listeners by replacing the canvas
    canvas.removeEventListener('mousemove', canvas._tooltipMove);
    canvas.removeEventListener('mouseleave', canvas._tooltipLeave);
    canvas._tooltipMove = onMove;
    canvas._tooltipLeave = onLeave;
    canvas.addEventListener('mousemove', onMove);
    canvas.addEventListener('mouseleave', onLeave);
  },

  renderMetrics(quote, fundamentals) {
    const grid = document.getElementById('metrics-grid');
    const data = { ...quote, ...fundamentals };

    const metrics = [
      { icon: '🏢', label: 'Marktkapitalisierung', value: this.formatLargeNumber(data.market_cap ?? data.marketCap) },
      { icon: '📊', label: 'KGV (P/E)', value: data.pe_ratio ?? data.trailingPE ? this.formatNumber(data.pe_ratio ?? data.trailingPE) : '—' },
      { icon: '💰', label: 'Dividendenrendite', value: data.dividend_yield != null ? this.formatPercent(data.dividend_yield * (data.dividend_yield < 1 ? 100 : 1)) : '—' },
      { icon: '📈', label: 'Beta', value: data.beta != null ? this.formatNumber(data.beta) : '—' },
      { icon: '⬆️', label: '52W Hoch', value: data.fifty_two_week_high ?? data.fiftyTwoWeekHigh ? this.formatNumber(data.fifty_two_week_high ?? data.fiftyTwoWeekHigh) : '—' },
      { icon: '⬇️', label: '52W Tief', value: data.fifty_two_week_low ?? data.fiftyTwoWeekLow ? this.formatNumber(data.fifty_two_week_low ?? data.fiftyTwoWeekLow) : '—' },
      { icon: '📦', label: 'Volumen', value: this.formatLargeNumber(data.volume ?? data.regularMarketVolume) },
      { icon: '🏭', label: 'Sektor', value: data.sector || '—' },
    ];

    grid.innerHTML = metrics.map((m, i) => `
      <div class="metric-card" style="animation-delay: ${i * 60}ms">
        <span class="metric-icon">${m.icon}</span>
        <div class="metric-label">${m.label}</div>
        <div class="metric-value">${m.value}</div>
      </div>
    `).join('');
  },

  renderIndicators(technicals) {
    const grid = document.getElementById('indicators-grid');

    // RSI
    const rsi = technicals.rsi ?? technicals.RSI;
    const rsiSignal = rsi != null ? (rsi < 30 ? 'bullish' : rsi > 70 ? 'bearish' : 'neutral') : 'neutral';
    const rsiLabel = rsi != null ? (rsi < 30 ? 'Überverkauft' : rsi > 70 ? 'Überkauft' : 'Neutral') : '—';
    const rsiGaugeClass = rsi != null ? (rsi < 30 ? 'oversold' : rsi > 70 ? 'overbought' : 'neutral') : 'neutral';

    // SMA
    const sma50 = technicals.sma_50 ?? technicals.SMA_50;
    const sma200 = technicals.sma_200 ?? technicals.SMA_200;
    const smaSignal = sma50 != null && sma200 != null
      ? (sma50 > sma200 ? 'bullish' : 'bearish')
      : 'neutral';
    const smaLabel = sma50 != null && sma200 != null
      ? (sma50 > sma200 ? 'Golden Cross' : 'Death Cross')
      : '—';

    // EMA
    const ema20 = technicals.ema_20 ?? technicals.EMA_20;
    const currentPrice = technicals.current_price ?? technicals.price;
    const emaSignal = ema20 != null && currentPrice != null
      ? (currentPrice > ema20 ? 'bullish' : 'bearish')
      : 'neutral';
    const emaLabel = ema20 != null && currentPrice != null
      ? (currentPrice > ema20 ? 'Aufwärtstrend' : 'Abwärtstrend')
      : '—';

    grid.innerHTML = `
      <div class="indicator-card" style="animation-delay: 0ms">
        <div class="indicator-header">
          <span class="indicator-name">RSI (14)</span>
          <span class="indicator-signal ${rsiSignal}">${rsiLabel}</span>
        </div>
        <div class="indicator-value">${rsi != null ? rsi.toFixed(1) : '—'}</div>
        <div class="indicator-detail">Relative Strength Index</div>
        ${rsi != null ? `
          <div class="rsi-gauge">
            <div class="rsi-gauge-fill ${rsiGaugeClass}" style="width: ${Math.min(100, rsi)}%"></div>
          </div>
        ` : ''}
      </div>

      <div class="indicator-card" style="animation-delay: 80ms">
        <div class="indicator-header">
          <span class="indicator-name">SMA 50 / 200</span>
          <span class="indicator-signal ${smaSignal}">${smaLabel}</span>
        </div>
        <div class="indicator-value">${sma50 != null ? this.formatNumber(sma50) : '—'}</div>
        <div class="indicator-detail">
          ${sma200 != null ? `SMA 200: ${this.formatNumber(sma200)}` : 'Simple Moving Average'}
        </div>
      </div>

      <div class="indicator-card" style="animation-delay: 160ms">
        <div class="indicator-header">
          <span class="indicator-name">EMA 20</span>
          <span class="indicator-signal ${emaSignal}">${emaLabel}</span>
        </div>
        <div class="indicator-value">${ema20 != null ? this.formatNumber(ema20) : '—'}</div>
        <div class="indicator-detail">Exponential Moving Average</div>
      </div>
    `;
  },

  startRefresh() {
    this.stopRefresh();
    this.refreshInterval = setInterval(() => {
      if (this.currentTicker) {
        this.load(this.currentTicker);
        Watchlist.load();
      }
    }, 60000);
  },

  stopRefresh() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  },

  // --- Formatting helpers ---

  formatNumber(num) {
    if (num == null || isNaN(num)) return '—';
    return new Intl.NumberFormat('de-DE', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(num);
  },

  formatPercent(num) {
    if (num == null || isNaN(num)) return '—';
    const sign = num >= 0 ? '+' : '';
    return `${sign}${new Intl.NumberFormat('de-DE', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(num)}%`;
  },

  formatCurrency(num, currency = 'USD') {
    if (num == null || isNaN(num)) return '—';
    try {
      return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(num);
    } catch {
      return this.formatNumber(num);
    }
  },

  formatLargeNumber(num) {
    if (num == null || isNaN(num)) return '—';
    const abs = Math.abs(num);
    if (abs >= 1e12) return this.formatNumber(num / 1e12) + ' Bio.';
    if (abs >= 1e9) return this.formatNumber(num / 1e9) + ' Mrd.';
    if (abs >= 1e6) return this.formatNumber(num / 1e6) + ' Mio.';
    if (abs >= 1e3) return this.formatNumber(num / 1e3) + ' Tsd.';
    return this.formatNumber(num);
  },
};


// ===== Analysis Module =====
const Analysis = {
  async request(ticker) {
    const resultEl = document.getElementById('analysis-result');
    const loadingEl = document.getElementById('analysis-loading');
    const btn = document.getElementById('analyze-btn');

    resultEl.classList.add('hidden');
    loadingEl.classList.remove('hidden');
    btn.disabled = true;

    try {
      const data = await API.getAnalysis(ticker);
      this.renderResult(data);
    } catch (err) {
      Toast.error(err.message);
      loadingEl.classList.add('hidden');
    } finally {
      btn.disabled = false;
    }
  },

  renderResult(data) {
    const resultEl = document.getElementById('analysis-result');
    const loadingEl = document.getElementById('analysis-loading');
    loadingEl.classList.add('hidden');

    // Check if we have analysis data
    if (!data || (!data.recommendation && !data.empfehlung)) {
      resultEl.innerHTML = `
        <div class="analysis-fallback">
          <p>🤖 KI-Analyse ist derzeit nicht verfügbar.</p>
          <p>Bitte stelle sicher, dass ein LLM-Endpunkt konfiguriert ist.</p>
        </div>
      `;
      resultEl.classList.remove('hidden');
      return;
    }

    const rec = data.recommendation || data.empfehlung || '';
    const recLower = rec.toLowerCase();
    let badgeClass = 'hold';
    let badgeLabel = rec;

    if (recLower.includes('kauf') || recLower.includes('buy')) {
      badgeClass = 'buy';
    } else if (recLower.includes('verkauf') || recLower.includes('sell')) {
      badgeClass = 'sell';
    }

    const confidence = data.confidence ?? data.konfidenz ?? 0;
    const reasoning = data.reasoning || data.begruendung || data.begründung || '';
    const risks = data.risks || data.risiken || [];
    const opportunities = data.opportunities || data.chancen || [];

    resultEl.innerHTML = `
      <div class="analysis-recommendation">
        <span class="recommendation-badge ${badgeClass}">
          ${badgeClass === 'buy' ? '🟢' : badgeClass === 'sell' ? '🔴' : '🟡'}
          ${this._escapeHtml(badgeLabel)}
        </span>
        <div class="confidence-container">
          <span class="confidence-label">Konfidenz</span>
          <div class="confidence-bar">
            <div class="confidence-fill" style="width: ${Math.round(confidence * 100)}%"></div>
          </div>
          <span class="confidence-value">${Math.round(confidence * 100)}%</span>
        </div>
      </div>

      ${reasoning ? `
        <div class="analysis-section-title">📝 Begründung</div>
        <p class="analysis-text">${this._escapeHtml(reasoning)}</p>
      ` : ''}

      ${risks.length > 0 ? `
        <div class="analysis-section-title">⚠️ Risiken</div>
        <ul class="analysis-list risks">
          ${risks.map(r => `<li>${this._escapeHtml(r)}</li>`).join('')}
        </ul>
      ` : ''}

      ${opportunities.length > 0 ? `
        <div class="analysis-section-title">💡 Chancen</div>
        <ul class="analysis-list opportunities">
          ${opportunities.map(o => `<li>${this._escapeHtml(o)}</li>`).join('')}
        </ul>
      ` : ''}
    `;

    resultEl.classList.remove('hidden');
  },

  _escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },
};


// ===== App Initialization =====
document.addEventListener('DOMContentLoaded', () => {
  // Auth
  Auth.init();

  // Login form
  document.getElementById('login-form').addEventListener('submit', (e) => {
    e.preventDefault();
    Auth.login();
  });

  // Logout
  document.getElementById('logout-btn').addEventListener('click', () => {
    Auth.logout();
  });

  // Search
  Search.init();

  // Analyze button
  document.getElementById('analyze-btn').addEventListener('click', () => {
    if (StockDetail.currentTicker) {
      Analysis.request(StockDetail.currentTicker);
    }
  });

  // Chart period buttons
  document.getElementById('chart-period-btns').addEventListener('click', (e) => {
    const btn = e.target.closest('.period-btn');
    if (!btn) return;
    document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const period = btn.dataset.period;
    if (StockDetail.currentTicker) {
      StockDetail.load(StockDetail.currentTicker, period);
    }
  });

  // Mobile sidebar toggle
  const sidebar = document.getElementById('sidebar');
  const sidebarToggle = document.getElementById('sidebar-toggle');
  const sidebarOverlay = document.getElementById('sidebar-overlay');

  sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    sidebarOverlay.classList.toggle('hidden');
  });

  sidebarOverlay.addEventListener('click', () => {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.add('hidden');
  });

  // Resize chart on window resize
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (StockDetail.currentTicker) {
        // Re-fetch to re-render chart at new size
        StockDetail.load(StockDetail.currentTicker);
      }
    }, 250);
  });
});
