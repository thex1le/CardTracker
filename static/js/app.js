let allData = [];
let allSignals = [];
let allNews = [];
let allAlerts = [];
let allScores = {};  // keyed by player_name
let watchlist = [];
let watchlistPlayerIds = new Set();
let userAlerts = [];
let signalsByPlayer = {};
let alertsByPlayer = {};
let sortKey = 'perf_rank';
let sortAsc = true;

const currentYear = new Date().getFullYear();
const seasons = [currentYear - 1, currentYear - 2];

const SIGNAL_ICONS = {
    breakout: 'B',
    callup: 'C',
    milestone: 'M',
    statcast_elite: 'S',
};

// --- Data Loading ---

async function loadData(refresh = false) {
    const loading = document.getElementById('loading');
    const table = document.getElementById('prospects-table');
    const legend = document.getElementById('legend');
    const countDisplay = document.getElementById('count-display');

    loading.style.display = '';
    table.style.display = 'none';

    const url = refresh ? '/api/prospects?refresh=true' : '/api/prospects';
    try {
        const resp = await fetch(url);
        allData = await resp.json();
    } catch (e) {
        loading.innerHTML = '<div style="color:#f44336;">Failed to load data. Check server logs.</div>';
        return;
    }

    loading.style.display = 'none';
    table.style.display = '';
    legend.style.display = '';
    countDisplay.style.display = '';
    renderTable();

    // Load signals in background
    loadSignals();
}

async function loadSignals() {
    try {
        const resp = await fetch('/api/signals');
        allSignals = await resp.json();
    } catch {
        allSignals = [];
    }

    // Index by player name for quick lookup
    signalsByPlayer = {};
    for (const s of allSignals) {
        const key = s.player_name;
        if (!signalsByPlayer[key]) signalsByPlayer[key] = [];
        signalsByPlayer[key].push(s);
    }

    updateSignalCount();
    renderSignalsPanel();
    renderTable(); // re-render to show signal dots
}

async function detectSignals() {
    const btn = document.getElementById('detectBtn');
    btn.disabled = true;
    btn.textContent = 'Detecting...';
    try {
        await fetch('/api/signals/detect', { method: 'POST' });
        await loadSignals();
    } catch (e) {
        console.error('Signal detection failed:', e);
    }
    btn.disabled = false;
    btn.textContent = 'Detect Signals';
}

// --- News & Sentiment ---

async function loadNews() {
    try {
        const [newsResp, alertsResp] = await Promise.all([
            fetch('/api/news?limit=100'),
            fetch('/api/news/alerts'),
        ]);
        allNews = await newsResp.json();
        allAlerts = await alertsResp.json();
    } catch {
        allNews = [];
        allAlerts = [];
    }

    // Index alerts by player name
    alertsByPlayer = {};
    for (const a of allAlerts) {
        const key = a.player_name;
        if (!alertsByPlayer[key] || severityOrder2(a.alert_tier) > severityOrder2(alertsByPlayer[key])) {
            alertsByPlayer[key] = a.alert_tier;
        }
    }

    updateAlertCount();
    renderNewsTab();
    renderTable(); // re-render to show alert dots
}

async function refreshNews() {
    const btn = document.getElementById('newsRefreshBtn');
    btn.disabled = true;
    btn.textContent = 'Refreshing...';
    try {
        const resp = await fetch('/api/news/refresh', { method: 'POST' });
        const data = await resp.json();
        await loadNews();
        // Show toast for any RED alerts
        for (const a of allAlerts.slice(0, 3)) {
            if (a.alert_tier === 'RED') showToast(a.headline, 'red');
            else if (a.alert_tier === 'YELLOW') showToast(a.headline, 'yellow');
        }
        btn.textContent = `Done: ${data.new_events} new`;
        setTimeout(() => { btn.textContent = 'Refresh News'; btn.disabled = false; }, 3000);
    } catch (e) {
        btn.textContent = 'Error';
        setTimeout(() => { btn.textContent = 'Refresh News'; btn.disabled = false; }, 3000);
    }
}

function severityOrder2(tier) {
    return { RED: 3, YELLOW: 2, GREEN: 1 }[tier] || 0;
}

function updateAlertCount() {
    const badge = document.getElementById('alertCount');
    badge.textContent = allAlerts.length;
    badge.className = allAlerts.length > 0 ? 'badge' : 'badge zero';
}

function alertBadgeHtml(playerName) {
    const tier = alertsByPlayer[playerName];
    if (!tier) return '';
    return `<span class="alert-badge alert-${tier}" title="${tier} alert"></span>`;
}

function renderNewsTab() {
    // Alerts section
    const alertsDiv = document.getElementById('alertsList');
    if (allAlerts.length === 0) {
        alertsDiv.innerHTML = '<div class="no-stats">No active alerts.</div>';
    } else {
        alertsDiv.innerHTML = allAlerts.map(a => `
            <div class="news-card alert-${a.alert_tier}-border">
                <div class="news-card-header">
                    <span class="alert-badge alert-${a.alert_tier}"></span>
                    <span class="news-player">${a.player_name} (${a.player_team})</span>
                    <span class="news-category ${a.category || ''}">${a.category || ''}</span>
                </div>
                <div class="news-headline">${a.headline}</div>
                <div class="news-meta">
                    <span>${a.source}</span>
                    ${a.published_at ? `<span>${new Date(a.published_at).toLocaleDateString()}</span>` : ''}
                </div>
            </div>
        `).join('');
    }

    // News feed
    const newsDiv = document.getElementById('newsList');
    if (allNews.length === 0) {
        newsDiv.innerHTML = '<div class="no-stats">No news loaded yet. Click "Refresh News".</div>';
    } else {
        newsDiv.innerHTML = allNews.slice(0, 50).map(n => `
            <div class="news-card ${n.alert_tier ? 'alert-' + n.alert_tier + '-border' : ''}">
                <div class="news-card-header">
                    ${n.alert_tier ? `<span class="alert-badge alert-${n.alert_tier}"></span>` : ''}
                    <span class="news-player">${n.player_name} (${n.player_team})</span>
                    <span class="news-category ${n.category || ''}">${n.category || ''}</span>
                    <span class="sentiment-indicator sentiment-${n.sentiment}">${n.sentiment} (${n.sentiment_score != null ? n.sentiment_score.toFixed(2) : '?'})</span>
                </div>
                <div class="news-headline">${n.url ? `<a href="${n.url}" target="_blank">${n.headline}</a>` : n.headline}</div>
                ${n.summary ? `<div class="news-summary">${n.summary.substring(0, 200)}${n.summary.length > 200 ? '...' : ''}</div>` : ''}
                <div class="news-meta">
                    <span class="news-source">${n.source}</span>
                    ${n.published_at ? `<span>${new Date(n.published_at).toLocaleDateString()}</span>` : ''}
                </div>
            </div>
        `).join('');
    }
}

function showToast(message, type) {
    const toast = document.createElement('div');
    toast.className = `toast${type === 'yellow' ? ' yellow' : ''}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

// --- Signals Panel ---

function updateSignalCount() {
    const badge = document.getElementById('signalCount');
    badge.textContent = allSignals.length;
    badge.className = allSignals.length > 0 ? 'badge' : 'badge zero';
}

function renderSignalsPanel() {
    const list = document.getElementById('signalsList');
    const filter = document.getElementById('signalFilter').value;

    let filtered = allSignals;
    if (filter !== 'all') {
        filtered = allSignals.filter(s => s.signal_type === filter);
    }

    if (filtered.length === 0) {
        list.innerHTML = '<div class="no-stats" style="padding:16px;">No signals found. Click "Detect Signals" to analyze player data.</div>';
        return;
    }

    list.innerHTML = filtered.map(s => `
        <div class="signal-card">
            <div class="signal-card-header">
                <span class="severity-badge severity-${s.severity}"></span>
                <span class="signal-type-badge signal-type-${s.signal_type}">${s.signal_type.replace('_', ' ')}</span>
                <span class="signal-player">${s.player_name} (${s.player_team})</span>
            </div>
            <div class="signal-title">${s.title}</div>
            <div class="signal-desc">${s.description}</div>
            ${s.detected_at ? `<div class="signal-time">${new Date(s.detected_at).toLocaleDateString()}</div>` : ''}
        </div>
    `).join('');
}

function toggleSignalsPanel() {
    const panel = document.getElementById('signalsPanel');
    const btn = document.getElementById('signalsToggle');
    panel.classList.toggle('hidden');
    btn.classList.toggle('active');
}

// --- Table Rendering ---

function rankChangeHtml(change) {
    if (!change || change === 0) return '<span class="rank-change rank-flat">--</span>';
    if (change > 0) return `<span class="rank-change rank-up">+${change}</span>`;
    return `<span class="rank-change rank-down">${change}</span>`;
}

function scoreClass(score, isPitcher) {
    if (score === 0) return 'no-stats';
    if (isPitcher) {
        if (score >= 7) return 'score-high';
        if (score >= 5.5) return 'score-mid';
        return 'score-low';
    } else {
        if (score >= 0.800) return 'score-high';
        if (score >= 0.650) return 'score-mid';
        return 'score-low';
    }
}

function signalDotsHtml(playerName) {
    const signals = signalsByPlayer[playerName];
    if (!signals || signals.length === 0) return '';
    // Deduplicate by type, keep highest severity
    const byType = {};
    for (const s of signals) {
        if (!byType[s.signal_type] || severityOrder(s.severity) > severityOrder(byType[s.signal_type].severity)) {
            byType[s.signal_type] = s;
        }
    }
    return '<div class="signal-dots">' +
        Object.values(byType).map(s =>
            `<span class="signal-dot ${s.signal_type}" title="${s.title}">${SIGNAL_ICONS[s.signal_type] || '?'}</span>`
        ).join('') + '</div>';
}

function severityOrder(sev) {
    return { high: 3, medium: 2, low: 1 }[sev] || 0;
}

function keyStat(p) {
    if (p.score === 0) return '<span class="no-stats">No stats found</span>';
    let parts = [];
    for (const yr of seasons) {
        const splits = p.stats[yr];
        if (!splits || splits.length === 0) continue;
        if (p.is_pitcher) {
            const best = splits.reduce((a, b) => parseFloat(a.ip) > parseFloat(b.ip) ? a : b);
            parts.push(`${yr}: ${best.ip} IP, ${best.era} ERA, ${best.so} K`);
        } else {
            const best = splits.reduce((a, b) => a.ab > b.ab ? a : b);
            parts.push(`${yr}: ${best.avg} AVG, ${best.ops} OPS, ${best.hr} HR`);
        }
    }
    return parts.join(' | ') || '<span class="no-stats">No stats found</span>';
}

function detailRows(p) {
    let html = '';

    // Player signals section
    const signals = signalsByPlayer[p.name];
    if (signals && signals.length > 0) {
        html += '<div class="player-signals"><h4>Active Signals</h4>';
        for (const s of signals) {
            html += `<div class="signal-card ${s.severity}">
                <div class="signal-card-header">
                    <span class="severity-badge severity-${s.severity}"></span>
                    <span class="signal-type-badge signal-type-${s.signal_type}">${s.signal_type.replace('_', ' ')}</span>
                </div>
                <div class="signal-title">${s.title}</div>
                <div class="signal-desc">${s.description}</div>
            </div>`;
        }
        html += '</div>';
    }

    // Season stats
    for (const yr of seasons) {
        const splits = p.stats[yr];
        if (!splits || splits.length === 0) {
            html += `<h4>${yr} Season</h4><p class="no-stats">No stats available</p>`;
            continue;
        }
        html += `<h4>${yr} Season</h4>`;
        if (p.is_pitcher) {
            html += `<table class="stats-table"><thead><tr>
                <th>Level</th><th>W</th><th>L</th><th>ERA</th><th>G</th><th>GS</th>
                <th>IP</th><th>K</th><th>BB</th><th>WHIP</th><th>AVG</th>
            </tr></thead><tbody>`;
            for (const s of splits) {
                html += `<tr>
                    <td>${s.level}</td><td>${s.w}</td><td>${s.l}</td><td>${s.era}</td>
                    <td>${s.g}</td><td>${s.gs}</td><td>${s.ip}</td><td>${s.so}</td>
                    <td>${s.bb}</td><td>${s.whip}</td><td>${s.avg}</td>
                </tr>`;
            }
        } else {
            html += `<table class="stats-table"><thead><tr>
                <th>Level</th><th>G</th><th>AB</th><th>H</th><th>HR</th><th>RBI</th>
                <th>SB</th><th>BB</th><th>K</th><th>AVG</th><th>OBP</th><th>SLG</th><th>OPS</th>
            </tr></thead><tbody>`;
            for (const s of splits) {
                html += `<tr>
                    <td>${s.level}</td><td>${s.g}</td><td>${s.ab}</td><td>${s.h}</td>
                    <td>${s.hr}</td><td>${s.rbi}</td><td>${s.sb}</td><td>${s.bb}</td>
                    <td>${s.so}</td><td>${s.avg}</td><td>${s.obp}</td><td>${s.slg}</td><td>${s.ops}</td>
                </tr>`;
            }
        }
        html += '</tbody></table>';
    }

    return html;
}

function renderTable() {
    const search = document.getElementById('search').value.toLowerCase();
    const posFilter = document.getElementById('posFilter').value;

    let filtered = allData.filter(p => {
        if (search && !p.name.toLowerCase().includes(search) && !p.team.toLowerCase().includes(search)) return false;
        if (posFilter === 'hitter' && p.is_pitcher) return false;
        if (posFilter === 'pitcher' && !p.is_pitcher) return false;
        return true;
    });

    filtered.sort((a, b) => {
        let va = a[sortKey], vb = b[sortKey];
        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();
        if (va < vb) return sortAsc ? -1 : 1;
        if (va > vb) return sortAsc ? 1 : -1;
        return 0;
    });

    document.getElementById('count-display').textContent = `Showing ${filtered.length} of ${allData.length} prospects`;

    const tbody = document.getElementById('table-body');
    let rowsHtml = '';

    for (const p of filtered) {
        const posClass = p.is_pitcher ? 'pos-pitcher' : 'pos-hitter';
        const sc = scoreClass(p.score, p.is_pitcher);
        const scoreDisplay = p.score === 0 ? '-' : p.is_pitcher ? p.score.toFixed(2) : p.score.toFixed(3);
        const rid = `row-${p.perf_rank}`;

        const dbPlayerId = allScores[p.name] ? allScores[p.name].player_id : null;
        const isWatched = dbPlayerId && watchlistPlayerIds.has(dbPlayerId);
        const starClass = isWatched ? 'watch-star watched' : 'watch-star';

        const invScore = allScores[p.name];
        const invTooltip = invScore && invScore.breakdown
            ? `Perf:${invScore.breakdown.performance?.toFixed(0)||'--'} Mom:${invScore.breakdown.momentum?.toFixed(0)||'--'} Card:${invScore.breakdown.card_price?.toFixed(0)||'--'} Sent:${invScore.breakdown.sentiment?.toFixed(0)||'--'} Avail:${invScore.breakdown.availability?.toFixed(0)||'--'}`
            : 'Not computed yet';

        rowsHtml += `<tr data-rid="${rid}">
            <td class="rank-cell">${p.perf_rank}</td>
            <td class="bowman-rank" data-tooltip="FanGraphs #${p.bowman_rank}">${p.bowman_rank}${rankChangeHtml(p.rank_change)}</td>
            <td class="name-cell" data-name="${p.name}" data-tooltip="${p.name} - ${p.team} ${p.pos} (FV:${p.fv||'?'} ETA:${p.eta||'?'})">${p.name}</td>
            <td><span class="team-badge">${p.team}</span></td>
            <td><span class="pos-badge ${posClass}">${p.pos}</span></td>
            <td class="fv-cell" data-tooltip="Future Value grade">${p.fv || '-'}</td>
            <td class="eta-cell" data-tooltip="Expected MLB debut">${p.eta || '-'}</td>
            <td data-tooltip="${invTooltip}">${invScoreHtml(p.name)}</td>
            <td class="score-cell ${sc}" style="font-size:11px;" data-tooltip="${p.is_pitcher ? 'ERA-based: 10 - ERA' : 'Average OPS'}">${scoreDisplay}</td>
            <td>${signalDotsHtml(p.name)}</td>
            <td>${alertBadgeHtml(p.name)}</td>
            <td>${dbPlayerId ? `<button class="${starClass}" data-pid="${dbPlayerId}" data-tooltip="Add to watchlist">&#9733;</button>` : ''}</td>
        </tr>
        <tr class="stats-row" data-detail="${rid}">
            <td colspan="12"><div class="stats-detail">
                ${scoreBreakdownHtml(p.name)}
                ${detailRows(p)}
            </div></td>
        </tr>`;
    }

    tbody.innerHTML = rowsHtml;

    // Attach click handlers for expand/collapse
    tbody.querySelectorAll('.name-cell').forEach(cell => {
        cell.addEventListener('click', () => {
            const tr = cell.closest('tr');
            const rid = tr.dataset.rid;
            const detailTr = tbody.querySelector(`tr[data-detail="${rid}"]`);
            if (detailTr) {
                detailTr.classList.toggle('visible');
                tr.classList.toggle('expanded');
            }
        });
    });

    // Watch star handlers
    tbody.querySelectorAll('.watch-star').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleWatch(parseInt(btn.dataset.pid));
        });
    });

    document.querySelectorAll('thead th').forEach(th => {
        th.classList.remove('sorted-asc', 'sorted-desc');
        if (th.dataset.sort === sortKey) {
            th.classList.add(sortAsc ? 'sorted-asc' : 'sorted-desc');
        }
    });
}

// --- Scores ---

async function loadScores() {
    try {
        const resp = await fetch('/api/scores');
        const data = await resp.json();
        allScores = {};
        for (const s of data) {
            allScores[s.player_name] = s;
        }
    } catch { allScores = {}; }
    renderTable();
}

async function computeScores() {
    const btn = document.getElementById('computeScoresBtn');
    btn.disabled = true;
    btn.textContent = 'Computing...';
    try {
        await fetch('/api/scores/compute', { method: 'POST' });
        await loadScores();
        btn.textContent = 'Done!';
        setTimeout(() => { btn.textContent = 'Compute Scores'; btn.disabled = false; }, 2000);
    } catch {
        btn.textContent = 'Error';
        setTimeout(() => { btn.textContent = 'Compute Scores'; btn.disabled = false; }, 2000);
    }
}

function invScoreHtml(playerName) {
    const s = allScores[playerName];
    if (!s || s.score == null) return '<span class="inv-score inv-score-none">--</span>';
    const val = s.score.toFixed(0);
    const cls = s.score >= 65 ? 'inv-score-high' : s.score >= 40 ? 'inv-score-mid' : 'inv-score-low';
    return `<span class="inv-score ${cls}">${val}</span>`;
}

function scoreBreakdownHtml(playerName) {
    const s = allScores[playerName];
    if (!s || !s.breakdown) return '';
    const b = s.breakdown;
    const bars = [
        { label: 'Performance', val: b.performance, cls: 'perf' },
        { label: 'Momentum', val: b.momentum, cls: 'mom' },
        { label: 'Card Price', val: b.card_price, cls: 'card' },
        { label: 'Sentiment', val: b.sentiment, cls: 'sent' },
        { label: 'Availability', val: b.availability, cls: 'avail' },
    ];
    return '<div class="score-breakdown">' + bars.map(b =>
        `<div class="score-bar-item">
            <div class="score-bar-label">${b.label}</div>
            <div class="score-bar-track"><div class="score-bar-fill ${b.cls}" style="width:${b.val || 0}%"></div></div>
            <div class="score-bar-value">${b.val != null ? b.val.toFixed(0) : '--'}</div>
        </div>`
    ).join('') + '</div>';
}

// --- Watchlist ---

async function loadWatchlist() {
    try {
        const resp = await fetch('/api/watchlist');
        watchlist = await resp.json();
    } catch { watchlist = []; }
    watchlistPlayerIds = new Set(watchlist.map(w => w.player_id));
    renderWatchlistTab();
    renderTable();
}

async function toggleWatch(playerId) {
    if (watchlistPlayerIds.has(playerId)) {
        const item = watchlist.find(w => w.player_id === playerId);
        if (item) await fetch(`/api/watchlist/${item.id}`, { method: 'DELETE' });
    } else {
        await fetch('/api/watchlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ player_id: playerId }),
        });
    }
    await loadWatchlist();
}

function renderWatchlistTab() {
    const div = document.getElementById('watchlistContent');
    if (watchlist.length === 0) {
        div.innerHTML = '<div class="no-stats" style="padding:20px;">Your watchlist is empty. Click the star on the Prospects tab to add players.</div>';
        return;
    }
    div.innerHTML = '<div class="watchlist-grid">' + watchlist.map(w => {
        const scoreClass = w.score >= 65 ? 'inv-score-high' : w.score >= 40 ? 'inv-score-mid' : w.score != null ? 'inv-score-low' : 'inv-score-none';
        const bd = w.score_breakdown || {};
        return `<div class="watchlist-card">
            <div class="watchlist-card-header">
                <h4>${w.player_name} <span class="team-badge">${w.team}</span></h4>
                <button class="watchlist-remove" data-id="${w.id}" title="Remove">&times;</button>
            </div>
            <div class="watchlist-score ${scoreClass}">${w.score != null ? w.score.toFixed(0) : '--'}</div>
            ${w.score_breakdown ? `<div class="score-breakdown">
                ${['performance','momentum','card_price','sentiment','availability'].map(k => {
                    const labels = {performance:'Perf',momentum:'Mom',card_price:'Card',sentiment:'Sent',availability:'Avail'};
                    const cls = {performance:'perf',momentum:'mom',card_price:'card',sentiment:'sent',availability:'avail'};
                    return `<div class="score-bar-item">
                        <div class="score-bar-label">${labels[k]}</div>
                        <div class="score-bar-track"><div class="score-bar-fill ${cls[k]}" style="width:${bd[k]||0}%"></div></div>
                        <div class="score-bar-value">${bd[k]!=null?bd[k].toFixed(0):'--'}</div>
                    </div>`;
                }).join('')}
            </div>` : ''}
            <div style="font-size:11px;color:#5a6080;margin-top:8px;">${w.position} | Added ${w.added_at ? new Date(w.added_at).toLocaleDateString() : ''}</div>
        </div>`;
    }).join('') + '</div>';

    div.querySelectorAll('.watchlist-remove').forEach(btn => {
        btn.addEventListener('click', async () => {
            await fetch(`/api/watchlist/${btn.dataset.id}`, { method: 'DELETE' });
            await loadWatchlist();
        });
    });
}

// --- User Alerts ---

async function loadUserAlerts() {
    try {
        const resp = await fetch('/api/alerts');
        userAlerts = await resp.json();
    } catch { userAlerts = []; }
    const badge = document.getElementById('userAlertCount');
    badge.textContent = userAlerts.length;
    badge.className = userAlerts.length > 0 ? 'badge' : 'badge zero';
    renderAlertsDropdown();
}

function toggleAlertsDropdown() {
    document.getElementById('alertsDropdown').classList.toggle('hidden');
}

function renderAlertsDropdown() {
    const list = document.getElementById('alertsDropdownList');
    if (userAlerts.length === 0) {
        list.innerHTML = '<div style="padding:16px;color:#5a6080;font-size:13px;">No unread alerts.</div>';
        return;
    }
    list.innerHTML = userAlerts.map(a => `
        <div class="alert-dropdown-item" data-id="${a.id}">
            <div class="alert-title">${a.title}</div>
            <div class="alert-body">${a.body || ''}</div>
            <div class="alert-time">${a.created_at ? new Date(a.created_at).toLocaleString() : ''}</div>
        </div>
    `).join('');
}

// --- Tab Navigation ---

function switchTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.tab-btn[data-tab="${tab}"]`).classList.add('active');

    document.getElementById('tab-prospects').style.display = tab === 'prospects' ? '' : 'none';
    document.getElementById('tab-market').style.display = tab === 'market' ? '' : 'none';
    document.getElementById('tab-news').style.display = tab === 'news' ? '' : 'none';
    document.getElementById('tab-watchlist').style.display = tab === 'watchlist' ? '' : 'none';
    document.getElementById('prospects-controls').style.display = tab === 'prospects' ? '' : 'none';
    document.getElementById('market-controls').style.display = tab === 'market' ? '' : 'none';
}

// --- Market Functions ---

async function searchMarket(playerName) {
    if (!playerName) return;

    const resultsDiv = document.getElementById('market-results');
    const contentDiv = document.getElementById('market-content');
    const loadingDiv = document.getElementById('market-loading');

    contentDiv.style.display = 'none';
    resultsDiv.style.display = 'none';
    loadingDiv.style.display = '';

    // Find player in our data
    const player = allData.find(p => p.name.toLowerCase().includes(playerName.toLowerCase()));
    if (!player || !player.player_id) {
        loadingDiv.style.display = 'none';
        resultsDiv.style.display = '';
        resultsDiv.innerHTML = '<div class="market-intro"><p class="no-stats">Player not found or no MLB ID available.</p></div>';
        return;
    }

    // Find the DB player ID by searching prospects
    // First, trigger a price refresh for this player
    try {
        // We need the internal DB ID. Search by name in the prospects endpoint data.
        // Use the market refresh endpoint which accepts player_id (DB ID).
        // For now, we'll fetch the market data which also works by external ID.

        // Refresh prices (scrapes 130point)
        const refreshResp = await fetch(`/api/players/${player.player_id}/market/refresh`, { method: 'POST' });

        // Fetch market summary
        const marketResp = await fetch(`/api/players/${player.player_id}/market`);
        const marketData = await marketResp.json();

        loadingDiv.style.display = 'none';
        resultsDiv.style.display = '';
        renderMarketResults(player, marketData);
    } catch (e) {
        loadingDiv.style.display = 'none';
        resultsDiv.style.display = '';
        resultsDiv.innerHTML = `<div class="market-intro"><p class="no-stats">Error fetching market data: ${e.message}</p></div>`;
    }
}

function renderMarketResults(player, data) {
    const div = document.getElementById('market-results');

    if (!data.has_data || data.cards.length === 0) {
        div.innerHTML = `
            <div class="market-player-header">
                <h3>${player.name}</h3>
                <span class="team-badge">${player.team}</span>
            </div>
            <div class="no-stats" style="padding:20px;">No card sales data found. The scraper may not have found matching listings.</div>
        `;
        return;
    }

    let html = `
        <div class="market-player-header">
            <h3>${player.name}</h3>
            <span class="team-badge">${player.team}</span>
            <span style="color:#5a6080;font-size:13px;">${data.total_cards} card types found</span>
        </div>
        <div class="card-grid">
    `;

    for (const card of data.cards) {
        const trend = card.trend || {};
        const spike = card.volume_spike;
        const hasTrend = trend.data_points > 0;

        const trendClass = trend.trend_direction === 'up' ? 'trend-up' : trend.trend_direction === 'down' ? 'trend-down' : '';
        const trendArrow = trend.trend_direction === 'up' ? '+' : '';

        html += `<div class="card-tile">`;
        html += `<div class="card-tile-header">`;
        html += `<div class="card-tile-name">${card.name}</div>`;
        html += `<div class="card-tile-badges">`;
        if (card.is_auto) html += `<span class="card-badge auto">AUTO</span>`;
        if (card.is_graded) html += `<span class="card-badge graded">${card.grade || 'GRADED'}</span>`;
        if (spike) html += `<span class="card-badge spike" title="Volume spike: ${spike.spike_ratio}x normal">VOL SPIKE</span>`;
        html += `</div></div>`;

        if (hasTrend) {
            html += `<div class="price-summary">`;
            html += `<div class="price-stat"><div class="price-stat-label">Avg</div><div class="price-stat-value">$${(trend.avg_price_cents / 100).toFixed(2)}</div></div>`;
            html += `<div class="price-stat"><div class="price-stat-label">Latest</div><div class="price-stat-value">$${(trend.latest_price_cents / 100).toFixed(2)}</div></div>`;
            html += `<div class="price-stat"><div class="price-stat-label">Range</div><div class="price-stat-value">$${(trend.min_price_cents / 100).toFixed(0)}-$${(trend.max_price_cents / 100).toFixed(0)}</div></div>`;
            html += `<div class="price-stat"><div class="price-stat-label">Trend</div><div class="price-stat-value ${trendClass}">${trendArrow}${trend.trend_pct}%</div></div>`;
            html += `</div>`;

            // Sparkline
            if (trend.sparkline && trend.sparkline.length > 0) {
                const maxVal = Math.max(...trend.sparkline);
                html += `<div class="sparkline-container">`;
                for (const val of trend.sparkline) {
                    const pct = maxVal > 0 ? (val / maxVal) * 100 : 0;
                    html += `<div class="sparkline-bar" style="height:${Math.max(pct, 5)}%" title="$${(val / 100).toFixed(2)}"></div>`;
                }
                html += `</div>`;
            }

            html += `<div style="color:#5a6080;font-size:11px;">${trend.data_points} sales tracked</div>`;
        } else {
            html += `<div class="no-stats" style="padding:8px 0;">No price data yet</div>`;
        }

        html += `</div>`;
    }

    html += `</div>`;
    div.innerHTML = html;
}

async function refreshAllMarket() {
    const btn = document.getElementById('marketRefreshAllBtn');
    btn.disabled = true;
    btn.textContent = 'Refreshing (slow)...';
    try {
        const resp = await fetch('/api/market/refresh-all', { method: 'POST' });
        const data = await resp.json();
        btn.textContent = `Done: ${data.new_listings} new`;
        setTimeout(() => { btn.textContent = 'Refresh All Prices'; btn.disabled = false; }, 3000);
    } catch (e) {
        btn.textContent = 'Error';
        setTimeout(() => { btn.textContent = 'Refresh All Prices'; btn.disabled = false; }, 3000);
    }
}

// --- Event Listeners ---

document.getElementById('search').addEventListener('input', renderTable);
document.getElementById('posFilter').addEventListener('change', renderTable);
document.getElementById('sortBy').addEventListener('change', e => {
    sortKey = e.target.value;
    sortAsc = (sortKey === 'perf_rank' || sortKey === 'bowman_rank' || sortKey === 'name' || sortKey === 'team');
    renderTable();
});
document.querySelectorAll('thead th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
        const key = th.dataset.sort;
        if (sortKey === key) {
            sortAsc = !sortAsc;
        } else {
            sortKey = key;
            sortAsc = (key === 'perf_rank' || key === 'bowman_rank' || key === 'name' || key === 'team');
        }
        document.getElementById('sortBy').value = key;
        renderTable();
    });
});

document.getElementById('refreshBtn').addEventListener('click', async () => {
    const btn = document.getElementById('refreshBtn');
    btn.disabled = true;
    btn.textContent = 'Refreshing...';
    await loadData(true);
    btn.disabled = false;
    btn.textContent = 'Refresh Data';
});

document.getElementById('detectBtn').addEventListener('click', detectSignals);
document.getElementById('computeScoresBtn').addEventListener('click', computeScores);
document.getElementById('signalsToggle').addEventListener('click', toggleSignalsPanel);
document.getElementById('signalFilter').addEventListener('change', renderSignalsPanel);
document.getElementById('alertsBell').addEventListener('click', toggleAlertsDropdown);
document.getElementById('markAllRead').addEventListener('click', async () => {
    for (const a of userAlerts) {
        await fetch(`/api/alerts/${a.id}/read`, { method: 'POST' });
    }
    await loadUserAlerts();
});

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// Market search
document.getElementById('marketSearchBtn').addEventListener('click', () => {
    searchMarket(document.getElementById('marketSearch').value);
});
document.getElementById('marketSearch').addEventListener('keydown', e => {
    if (e.key === 'Enter') searchMarket(e.target.value);
});
document.getElementById('marketRefreshAllBtn').addEventListener('click', refreshAllMarket);
document.getElementById('newsRefreshBtn').addEventListener('click', refreshNews);

// Initial load
loadData();
loadNews();
loadScores();
loadWatchlist();
loadUserAlerts();
