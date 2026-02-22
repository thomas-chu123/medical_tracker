/* ============================================================
   app.js — 台灣醫療門診追蹤系統 Frontend Logic
   ============================================================ */

const API = '';   // Same origin; change to http://localhost:8000 if needed
let authToken = localStorage.getItem('auth_token') || null;
let currentUser = null;

// ── Utility: API fetch ────────────────────────────────────────
async function apiFetch(path, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

    let resp;
    try {
        resp = await fetch(API + path, { ...opts, headers });
    } catch (err) {
        throw new Error('網路連線失敗，請檢查伺服器狀態');
    }

    if (resp.status === 401) { handleLogout(); return null; }

    if (!resp.ok) {
        let errMsg = `HTTP ${resp.status}`;
        try {
            const err = await resp.json();
            if (resp.status === 422 && Array.isArray(err.detail)) {
                errMsg = err.detail.map(e => e.msg).join(', ');
            } else {
                errMsg = err.detail || errMsg;
                if (typeof errMsg === 'object') {
                    errMsg = JSON.stringify(errMsg);
                }
            }
        } catch (e) {
            // Not a JSON response (likely a 500 crash)
            errMsg = `伺服器發生錯誤 (${resp.status})`;
        }
        throw new Error(errMsg);
    }

    if (resp.status === 204) return null;
    return resp.json();
}

async function apiPost(path, body) {
    return apiFetch(path, { method: 'POST', body: JSON.stringify(body) });
}
async function apiPatch(path, body) {
    return apiFetch(path, { method: 'PATCH', body: JSON.stringify(body) });
}
async function apiDelete(path) {
    return apiFetch(path, { method: 'DELETE' });
}

// ── Toast notifications ───────────────────────────────────────
function toast(msg, type = 'info', duration = 3500) {
    const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<span>${icons[type]}</span><span>${msg}</span>`;
    document.getElementById('toast-container').appendChild(el);
    setTimeout(() => el.remove(), duration);
}

// ── Auth ──────────────────────────────────────────────────────
function switchTab(tab) {
    document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById('login-form').style.display = tab === 'login' ? '' : 'none';
    document.getElementById('register-form').style.display = tab === 'register' ? '' : 'none';
}

async function handleLogin(e) {
    e.preventDefault();
    const btn = document.getElementById('login-btn');
    btn.disabled = true; btn.textContent = '登入中…';
    try {
        const email = document.getElementById('login-email').value;
        const password = document.getElementById('login-password').value;

        const data = await apiPost('/api/auth/login', { email, password });
        if (!data || !data.access_token) {
            throw new Error('伺服器未回傳 Token，請稍後再試');
        }
        authToken = data.access_token;
        localStorage.setItem('auth_token', authToken);
        // Pass user profile from login response — skip extra /api/users/me call
        await initApp(data.user);
    } catch (err) {
        toast(err.message, 'error');
    } finally {
        btn.disabled = false; btn.textContent = '登入';
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const btn = document.getElementById('register-btn');
    btn.disabled = true; btn.textContent = '建立中…';
    try {
        const res = await apiPost('/api/auth/register', {
            email: document.getElementById('reg-email').value,
            password: document.getElementById('reg-password').value,
            display_name: document.getElementById('reg-name').value,
        });
        toast(res.message || '帳號建立成功！請登入', 'success', 8000);
        switchTab('login');
    } catch (err) {
        let msg = err.message;
        if (msg.includes('rate limit')) {
            msg = '註冊過於頻繁，請更換 Email 或等 10 分鐘後再試';
        }
        toast(msg, 'error', 6000);
    } finally {
        btn.disabled = false; btn.textContent = '建立帳號';
    }
}

function handleLogout() {
    authToken = null;
    localStorage.removeItem('auth_token');
    currentUser = null;
    document.getElementById('app').style.display = 'none';
    document.getElementById('auth-page').classList.add('show');
}

// ── App init ──────────────────────────────────────────────────
async function initApp(userFromLogin = null) {
    if (userFromLogin) {
        // Fresh login: use profile from login response, no extra API call needed
        currentUser = userFromLogin;
    } else {
        // Page reload: fetch profile with stored token
        try {
            currentUser = await apiFetch('/api/users/me');
            if (!currentUser) return;
        } catch {
            handleLogout(); return;
        }
    }

    // Show app
    document.getElementById('auth-page').classList.remove('show');
    document.getElementById('app').style.display = 'grid';

    // Set user info
    const name = currentUser.display_name || 'User';
    document.getElementById('user-name-display').textContent = name;
    document.getElementById('user-avatar').textContent = name[0].toUpperCase();
    document.getElementById('profile-name').value = name;
    if (currentUser.line_notify_token)
        document.getElementById('line-token').value = currentUser.line_notify_token;

    // Reveal admin nav if user is admin
    if (currentUser.is_admin) {
        const adminBtn = document.getElementById('admin-nav-btn');
        if (adminBtn) adminBtn.style.display = '';
    }

    // Load dashboard
    loadDashboard();
}

// ── Navigation ────────────────────────────────────────────────
function navigate(btn, pageId) {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    if (btn) btn.classList.add('active');
    document.getElementById('page-' + pageId).classList.add('active');

    // Show/hide add-tracking nav item
    const navAddTracking = document.getElementById('nav-add-tracking');
    if (navAddTracking) navAddTracking.style.display = pageId === 'add-tracking' ? '' : 'none';

    // Lazy-load page data
    if (pageId === 'dashboard') {
        loadDashboard();
    } else if (pageId === 'hospitals') {
        loadHospitalsPage();
    } else if (pageId === 'tracking') {
        loadTracking();
    } else if (pageId === 'notifications') {
        loadNotifications();
    } else if (pageId === 'profile') {
        loadProfile();
    } else if (pageId === 'admin') {
        loadAdminUsers();
        loadSchedulerStatus();
        loadServerLogs();
    } else if (pageId === 'add-tracking') {
        // Reset stepper state
        Object.assign(_st, { step: 1, hospitalId: '', hospitalName: '', cat: '', deptId: '', deptName: '', doctorId: '', doctorName: '' });
        stepperGoTo(1);
        document.getElementById('stepper-breadcrumb').innerHTML = '';
        loadStepperHospitals();
    }
}

// ── Dashboard ─────────────────────────────────────────────────
async function loadDashboard() {
    // Fire requests in parallel including crowd-analysis
    const [gStats, subs, crowdStats] = await Promise.all([
        apiFetch('/api/stats/global').catch(() => null),
        apiFetch('/api/tracking').catch(() => []),
        apiFetch('/api/stats/crowd-analysis').catch(() => null),
    ]);

    if (gStats) {
        document.getElementById('stat-hospitals').textContent = gStats.hospitals;
        document.getElementById('stat-doctors').textContent = gStats.doctors;
        document.getElementById('stat-alerts').textContent = gStats.snapshots_today;
    }

    const activeSubs = (subs || []);
    document.getElementById('stat-tracking').textContent = activeSubs.filter(s => s.is_active).length;
    document.getElementById('last-update-label').textContent = `最後更新：${new Date().toLocaleString('zh-TW')}`;

    if (crowdStats) {
        renderCrowdChart(crowdStats);
    }

    renderDashboardTracking(activeSubs);
}

let crowdChartInstance = null;
function renderCrowdChart(stats) {
    const ctx = document.getElementById('crowd-chart');
    if (!ctx) return;

    if (crowdChartInstance) {
        crowdChartInstance.destroy();
    }

    crowdChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: stats.labels,
            datasets: [{
                label: '平均掛號人數 (近期平均)',
                data: stats.data,
                backgroundColor: [
                    'rgba(59, 130, 246, 0.7)', // Morning (blue)
                    'rgba(16, 185, 129, 0.7)', // Afternoon (green)
                    'rgba(245, 158, 11, 0.7)'  // Evening (yellow/orange)
                ],
                borderColor: [
                    'rgb(59, 130, 246)',
                    'rgb(16, 185, 129)',
                    'rgb(245, 158, 11)'
                ],
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => ` 平均約 ${ctx.raw} 人`
                    }
                }
            },
            scales: {
                y: { beginAtZero: true, title: { display: true, text: '平均掛號人數' } }
            }
        }
    });
}

async function renderDashboardTracking(subs) {
    const grid = document.getElementById('dashboard-tracking-grid');
    const activeSubs = subs.filter(s => s.is_active);
    if (!activeSubs.length) {
        grid.innerHTML = `<div class="empty-state">
      <div class="empty-icon">🔔</div>
      <p>尚未設定任何追蹤<br><a href="#" onclick="navigate(document.querySelector('[data-page=tracking]'), 'tracking')">新增第一個門診追蹤</a></p>
    </div>`;
        return;
    }

    const cards = await Promise.all(activeSubs.map(async sub => {
        const snap = await apiFetch(`/api/doctors/${sub.doctor_id}/latest`).catch(() => null);
        return renderClinicCard(sub, snap);
    }));
    grid.innerHTML = cards.join('');
}

function renderClinicCard(sub, snap) {
    const remaining = snap?.remaining ?? '—';
    const total = snap?.total_quota ?? '?';
    const current = snap?.current_number ?? '—';
    const isNum = typeof remaining === 'number';
    const pct = isNum && total ? Math.round((1 - remaining / total) * 100) : 0;
    const barClass = pct >= 90 ? 'danger' : pct >= 70 ? 'warning' : 'safe';
    const pillDone = (flag, label) => `<span class="threshold-pill ${flag ? 'done' : 'active'}">${label}</span>`;

    const doctorLabel = sub.doctor_name || ('ID: ' + sub.doctor_id?.slice(0, 8) + '…');
    const deptLabel = sub.department_name || '';
    const hospLabel = sub.hospital_name || '';
    const sessionLabel = [sub.session_date, sub.session_type ? sub.session_type + '診' : ''].filter(Boolean).join(' ');

    let distanceHtml = '';
    if (isNum && sub.appointment_number && typeof current === 'number') {
        const diff = sub.appointment_number - current;
        if (diff > 0) {
            distanceHtml = `<div style="font-size:13px; color:var(--text-muted)">距您的 ${sub.appointment_number} 號還差 <strong style="color:var(--text)">${diff}</strong> 號</div>`;
        } else if (diff === 0) {
            distanceHtml = `<div style="font-size:13px; color:var(--text-muted)"><strong>⭐ 到號了！</strong></div>`;
        } else {
            distanceHtml = `<div style="font-size:13px; color:var(--text-muted)">⚠️ 您的號碼已過號</div>`;
        }
    } else if (isNum) {
        distanceHtml = `<div style="font-size:13px; color:var(--text-muted)">距滿號還剩 <strong style="color:var(--text)">${remaining}</strong> 號</div>`;
    }

    return `
  <div class="clinic-card">
    <div class="doctor-name">👨‍⚕️ ${escHtml(doctorLabel)}</div>
    ${deptLabel ? `<div style="font-size:12px; color:var(--text-muted); margin-bottom:2px">🏥 ${escHtml(hospLabel)}｜${escHtml(deptLabel)}</div>` : ''}
    <span class="dept-tag">📅 ${escHtml(sessionLabel)}</span>
    <div class="number-display">
      <div class="current-num">${current}</div>
      <div class="num-label">目前號 / ${total} 總號</div>
    </div>
    ${isNum ? `
    <div class="progress-wrap" style="margin-bottom:10px">
      <div class="progress-bar ${barClass}" style="width:${pct}%"></div>
    </div>
    ${distanceHtml}
    ` : ''}
    <div class="threshold-pills" style="margin-top:10px">
      ${sub.notify_at_20 ? pillDone(sub.notified_20, '前20') : ''}
      ${sub.notify_at_10 ? pillDone(sub.notified_10, '前10') : ''}
      ${sub.notify_at_5 ? pillDone(sub.notified_5, '前5') : ''}
    </div>
  </div>`;
}

async function refreshAll() {
    toast('正在更新資料…', 'info');
    try {
        await apiPost('/api/admin/scrape-now', {});
        await new Promise(r => setTimeout(r, 1500));
        await loadDashboard();
        toast('資料已更新', 'success');
    } catch {
        toast('更新失敗', 'error');
    }
}

// ── Combobox engine ───────────────────────────────────────────
// Each combobox: { cbId, items: [{value, label}], onSelect, inputId }
const _combos = {};

function buildCombo(cbId, items, onSelect) {
    _combos[cbId] = { items, onSelect, filtered: items };
    const list = document.getElementById(cbId + '-list');
    _renderComboList(cbId, items);
}

function _renderComboList(cbId, items) {
    const list = document.getElementById(cbId + '-list');
    if (!items.length) {
        list.innerHTML = '<div class="combo-opt no-result">無結果</div>';
        return;
    }
    list.innerHTML = items.map((it, i) =>
        `<div class="combo-opt" data-value="${escHtml(it.value)}" data-cb="${cbId}"
            onclick="selectCombo('${cbId}','${it.value}','${escHtml(it.label)}')">${escHtml(it.label)}</div>`
    ).join('');
}

function openCombo(cbId) {
    document.querySelectorAll('.combobox.open').forEach(el => {
        if (el.id !== cbId) el.classList.remove('open');
    });
    document.getElementById(cbId).classList.add('open');
}

function closeCombo(cbId) {
    document.getElementById(cbId)?.classList.remove('open');
}

function toggleCombo(cbId) {
    const el = document.getElementById(cbId);
    const inp = el.querySelector('input[type=text]');
    if (inp.disabled) return;
    el.classList.toggle('open');
    if (el.classList.contains('open')) inp.focus();
}

function filterCombo(cbId) {
    const cb = _combos[cbId];
    if (!cb) return;
    const inp = document.getElementById(cbId).querySelector('input[type=text]');
    const q = inp.value.toLowerCase();
    const filtered = q ? cb.items.filter(it => it.label.toLowerCase().includes(q)) : cb.items;
    _renderComboList(cbId, filtered);
    openCombo(cbId);
}

function selectCombo(cbId, value, label) {
    const inp = document.getElementById(cbId).querySelector('input[type=text]');
    inp.value = label;
    closeCombo(cbId);
    const cb = _combos[cbId];
    if (cb?.onSelect) cb.onSelect(value, label);
}

// Close comboboxes when clicking outside
document.addEventListener('click', e => {
    if (!e.target.closest('.combobox')) {
        document.querySelectorAll('.combobox.open').forEach(el => el.classList.remove('open'));
    }
});

// ── Hospitals page (Chip + Grid) ──────────────────────────────
let allDoctors = [];
let _hsHospitalId = null;
let _hsHospitalName = '';

let allDepts = [];   // stores current category's dept list for filtering

async function loadHospitalsPage() {
    const inp = document.getElementById('hospital-input');
    if (inp.dataset.loaded === '1') return;
    inp.disabled = false;
    inp.dataset.loaded = '1';

    const hospitals = await apiFetch('/api/hospitals') || [];
    buildCombo('cb-hospital', hospitals.map(h => ({ value: h.id, label: h.name })), async (hospId, hospName) => {
        _hsHospitalId = hospId;
        _hsHospitalName = hospName;
        document.getElementById('hs-category-wrap').style.display = 'none';
        document.getElementById('hs-dept-wrap').style.display = 'none';
        document.getElementById('doctors-grid').innerHTML = '<div class="spinner"></div>';
        // Show search controls immediately after hospital selection
        const searchWrap = document.getElementById('hs-search-controls');
        searchWrap.style.display = 'flex';
        const deptSearchEl = document.getElementById('dept-search');
        if (deptSearchEl) deptSearchEl.value = '';
        _hsBreadcrumb([hospName]);

        const cats = await apiFetch(`/api/hospitals/${hospId}/categories`) || [];
        if (cats.length) {
            _hsRenderCategoryChips(hospId, hospName, cats);
        } else {
            // No categories — load all depts directly
            const depts = await apiFetch(`/api/hospitals/${hospId}/departments`) || [];
            _hsRenderDeptGrid(hospId, hospName, null, depts);
        }
    });
}

function _hsBreadcrumb(parts) {
    const el = document.getElementById('hs-breadcrumb');
    el.style.display = parts.length ? 'flex' : 'none';
    el.innerHTML = parts.map((p, i) => i < parts.length - 1
        ? `<span class="bc-link" onclick="void(0)">${escHtml(p)}</span><span class="bc-sep">›</span>`
        : `<span class="bc-cur">${escHtml(p)}</span>`).join('');
}

function _hsRenderCategoryChips(hospId, hospName, cats) {
    const wrap = document.getElementById('hs-category-wrap');
    const chips = document.getElementById('hs-category-chips');
    chips.innerHTML = cats.map(c =>
        `<button class="cat-chip" onclick="hsSelectCategory('${hospId}','${escHtml(hospName)}','${escHtml(c)}')">${escHtml(c)}</button>`
    ).join('');
    wrap.style.display = 'block';
    document.getElementById('hs-dept-wrap').style.display = 'none';
    document.getElementById('doctors-grid').innerHTML =
        '<div class="empty-state"><div class="empty-icon">🏷️</div><p>請選擇科室類別</p></div>';
}

async function hsSelectCategory(hospId, hospName, cat) {
    document.querySelectorAll('#hs-category-chips .cat-chip').forEach(b =>
        b.classList.toggle('active', b.textContent === cat));
    _hsBreadcrumb([hospName, cat]);
    document.getElementById('doctors-grid').innerHTML = '<div class="spinner"></div>';
    // Reset dept search when switching category
    const deptSearchEl = document.getElementById('dept-search');
    if (deptSearchEl) deptSearchEl.value = '';
    const depts = await apiFetch(`/api/hospitals/${hospId}/departments?category=${encodeURIComponent(cat)}`) || [];
    _hsRenderDeptGrid(hospId, hospName, cat, depts);
}

function _hsDeptButtons(depts, hospName, cat) {
    return depts.length
        ? depts.map(d =>
            `<button class="dept-btn" onclick="hsSelectDept('${d.id}','${escHtml(d.name)}','${escHtml(hospName)}','${cat ? escHtml(cat) : ''}')">${escHtml(d.name)}<\/button>`
        ).join('')
        : '<div style="color:var(--text-muted);font-size:14px">找不到符合的科室<\/div>';
}

function _hsRenderDeptGrid(hospId, hospName, cat, depts) {
    const wrap = document.getElementById('hs-dept-wrap');
    const label = document.getElementById('hs-dept-label');
    const grid = document.getElementById('hs-dept-grid');
    // Store for filter
    _hsDeptAll = { depts, hospName, cat };
    label.textContent = cat ? `${cat} — 請選擇科室` : '請選擇科室';
    grid.innerHTML = depts.length
        ? _hsDeptButtons(depts, hospName, cat)
        : '<div style="color:var(--text-muted);font-size:14px">此類別下無科室資料<\/div>';
    wrap.style.display = 'block';
    document.getElementById('doctors-grid').innerHTML =
        '<div class="empty-state"><div class="empty-icon">🏥<\/div><p>請選擇科室<\/p><\/div>';
}

let _hsDeptAll = { depts: [], hospName: '', cat: '' };

function filterHospitalSearch() {
    const dq = (document.getElementById('dept-search')?.value || '').toLowerCase().trim();
    const docq = (document.getElementById('doctor-search')?.value || '').toLowerCase().trim();
    const { depts, hospName, cat } = _hsDeptAll;

    // Reset UI if dept search is cleared while in category mode
    if (cat && !dq) {
        document.getElementById('hs-dept-grid').innerHTML = _hsDeptButtons(depts, hospName, cat);
        document.getElementById('hs-dept-label').textContent = `${cat} — 請選擇科室`;
        return;
    }

    // Reset UI if dept search is cleared while NO category is selected
    if (!cat && !dq && _hsHospitalId) {
        document.getElementById('hs-dept-wrap').style.display = 'none';
        document.getElementById('hs-category-wrap').style.display = 'block';
        return;
    }

    if (cat) {
        // Filter within current category locally
        let filteredDepts = dq ? depts.filter(d => d.name.toLowerCase().includes(dq)) : depts;
        document.getElementById('hs-dept-grid').innerHTML = _hsDeptButtons(filteredDepts, hospName, cat);
        document.getElementById('hs-dept-label').textContent = dq
            ? `搜尋「${dq}」— 找到 ${filteredDepts.length} 個科室`
            : `${cat} — 請選擇科室`;
        document.getElementById('hs-dept-wrap').style.display = 'block';
    } else if (_hsHospitalId && dq) {
        // No category selected — do full-hospital API search for depts
        apiFetch(`/api/hospitals/${_hsHospitalId}/departments?q=${encodeURIComponent(dq)}`).then(results => {
            const deptWrap = document.getElementById('hs-dept-wrap');
            // Hide categories if searching
            document.getElementById('hs-category-wrap').style.display = 'none';
            document.getElementById('hs-dept-label').textContent = `搜尋「${dq}」— 找到 ${(results || []).length} 個科室`;
            const html = (results || []).length
                ? (results || []).map(d =>
                    `<button class="dept-btn" onclick="hsSelectDeptFromSearch('${d.id}','${escHtml(d.name)}','${escHtml(hospName)}')">${escHtml(d.name)}</button>`
                ).join('')
                : '<div style="color:var(--text-muted);font-size:14px">找不到符合的科室</div>';
            document.getElementById('hs-dept-grid').innerHTML = html;
            deptWrap.style.display = 'block';

            // If also searching for doctor, we reset the doctors grid because we are searching across depts
            if (docq) {
                document.getElementById('doctors-grid').innerHTML = '<div class="spinner"></div>';
            }
        });
    }

    // Filter doctors locally if we have results
    if (allDoctors.length) {
        let filteredDocs = docq ? allDoctors.filter(d => d.name.toLowerCase().includes(docq)) : allDoctors;
        renderDoctorCards(filteredDocs);
    } else if (docq && _hsHospitalId) {
        // Optional: If doctor search is entered but no dept selected, 
        // maybe search globally in that hospital? 
        // For now, keep it simple: doctor search only works after selecting a dept/performing a dept search.
    }
}

function resetHospitalSearch() {
    const ds = document.getElementById('dept-search');
    const docs = document.getElementById('doctor-search');
    if (ds) ds.value = '';
    if (docs) docs.value = '';

    // If a hospital is selected, reset to category view
    if (_hsHospitalId) {
        document.getElementById('hs-dept-wrap').style.display = 'none';
        document.getElementById('hs-category-wrap').style.display = 'block';
        document.getElementById('doctors-grid').innerHTML =
            '<div class="empty-state"><div class="empty-icon">🏷️</div><p>請選擇科室類別</p></div>';
        allDoctors = [];
        _hsBreadcrumb([_hsHospitalName]);
        // De-select any active chips
        document.querySelectorAll('#hs-category-chips .cat-chip').forEach(b => b.classList.remove('active'));
    }
}

function filterDepts() {
    filterHospitalSearch();
}

function filterDoctors() {
    filterHospitalSearch();
}

async function hsSelectDept(deptId, deptName, hospName, cat) {
    // Clear doctor search + previous results to prevent stacking
    const docSearchEl = document.getElementById('doctor-search');
    if (docSearchEl) docSearchEl.value = '';
    allDoctors = [];

    document.querySelectorAll('#hs-dept-grid .dept-btn').forEach(b =>
        b.classList.toggle('active', b.textContent === deptName));
    const parts = cat ? [hospName, cat, deptName] : [hospName, deptName];
    _hsBreadcrumb(parts);
    document.getElementById('doctors-grid').innerHTML = '<div class="spinner"></div>';
    const docs = await apiFetch(`/api/departments/${deptId}/doctors`) || [];
    allDoctors = docs;
    renderDoctorCards(docs);
}

/**
 * Called when user clicks a dept from cross-hospital search results.
 * Fetches dept info (including category), then auto-selects the chip + dept,
 * and shows doctors — preventing state from the previous view from leaking.
 */
async function hsSelectDeptFromSearch(deptId, deptName, hospName) {
    // Reset: hide dept grid, clear search, hide any stale doctor list
    document.getElementById('hs-dept-wrap').style.display = 'none';
    document.getElementById('doctors-grid').innerHTML = '<div class="spinner"></div>';
    allDoctors = [];
    const docSearchEl = document.getElementById('doctor-search');
    if (docSearchEl) docSearchEl.value = '';

    // Fetch the dept's category from API
    const deptInfo = await apiFetch(`/api/departments/${deptId}`);
    const cat = deptInfo?.category || '';

    // Auto-highlight the matching category chip
    if (cat) {
        document.querySelectorAll('#hs-category-chips .cat-chip').forEach(b =>
            b.classList.toggle('active', b.textContent === cat));
    }

    // Fetch depts for that category and render them
    const depts = cat
        ? (await apiFetch(`/api/hospitals/${_hsHospitalId}/departments?category=${encodeURIComponent(cat)}`) || [])
        : [{ id: deptId, name: deptName }];
    _hsRenderDeptGrid(_hsHospitalId, hospName, cat, depts);

    // Auto-highlight the dept button and load doctors
    await hsSelectDept(deptId, deptName, hospName, cat);
}

// Obsolete, replaced by filterHospitalSearch


function renderDoctorCards(doctors) {
    const grid = document.getElementById('doctors-grid');
    if (!doctors || doctors.length === 0) {
        grid.innerHTML = `<div class="empty-state"><div class="empty-icon">👨‍⚕️</div><p>此科室目前無醫師資料</p></div>`;
        return;
    }
    grid.innerHTML = doctors.map(d => `
    <div class="card" style="cursor:pointer" onclick="showDoctorDetail('${d.id}','${escHtml(d.name)}')">
      <div style="display:flex; justify-content:space-between; align-items:flex-start">
        <div>
          <div style="font-weight:600; font-size:15px; margin-bottom:4px">👨‍⚕️ ${escHtml(d.name)}</div>
          <div style="font-size:12px; color:var(--text-muted)">${escHtml(d.specialty || '')}</div>
        </div>
        <button class="btn btn-primary btn-sm" onclick="event.stopPropagation(); quickTrack('${d.id}','${escHtml(d.name)}')">＋ 追蹤</button>
      </div>
    </div>`).join('');
}

// ── Add Tracking Stepper ───────────────────────────────────────
const _st = { step: 1, hospitalId: '', hospitalName: '', cat: '', deptId: '', deptName: '', doctorId: '', doctorName: '' };

async function loadStepperHospitals() {
    const grid = document.getElementById('step1-hospital-grid');
    const hospitals = await apiFetch('/api/hospitals') || [];
    if (!hospitals.length) { grid.innerHTML = '<div class="empty-state"><p>無醫院資料</p></div>'; return; }
    grid.innerHTML = hospitals.map(h =>
        `<button class="dept-btn" onclick="stepperSelectHospital('${h.id}','${escHtml(h.name)}')">${escHtml(h.name)}</button>`
    ).join('');
}

async function stepperSelectHospital(hospId, hospName) {
    _st.hospitalId = hospId; _st.hospitalName = hospName;
    _st.cat = ''; _st.deptId = ''; _st.deptName = ''; _st.doctorId = ''; _st.doctorName = '';
    _stepperBreadcrumb();
    stepperGoTo(2);
    // Load categories or depts
    const cats = await apiFetch(`/api/hospitals/${hospId}/categories`) || [];
    const chips = document.getElementById('step2-category-chips');
    const grid = document.getElementById('step2-dept-grid');
    if (cats.length) {
        chips.innerHTML = cats.map(c =>
            `<button class="cat-chip" onclick="stepperSelectCategory('${escHtml(c)}')">${escHtml(c)}</button>`
        ).join('');
        chips.style.display = 'flex';
        grid.innerHTML = '<div style="color:var(--text-muted);font-size:14px;margin-top:8px">請先選擇類別</div>';
    } else {
        chips.style.display = 'none';
        const depts = await apiFetch(`/api/hospitals/${hospId}/departments`) || [];
        grid.innerHTML = _stepperDeptButtons(depts);
    }
}

async function stepperSelectCategory(cat) {
    _st.cat = cat;
    document.querySelectorAll('#step2-category-chips .cat-chip').forEach(b =>
        b.classList.toggle('active', b.textContent === cat));
    const grid = document.getElementById('step2-dept-grid');
    grid.innerHTML = '<div class="spinner"></div>';
    const depts = await apiFetch(`/api/hospitals/${_st.hospitalId}/departments?category=${encodeURIComponent(cat)}`) || [];
    grid.innerHTML = _stepperDeptButtons(depts);
    _stepperBreadcrumb();
}

function _stepperDeptButtons(depts) {
    return depts.length
        ? depts.map(d => `<button class="dept-btn" onclick="stepperSelectDept('${d.id}','${escHtml(d.name)}')">${escHtml(d.name)}</button>`).join('')
        : '<div style="color:var(--text-muted);font-size:14px">此類別無科室</div>';
}

async function stepperSelectDept(deptId, deptName) {
    _st.deptId = deptId; _st.deptName = deptName;
    document.getElementById('modal-dept').value = deptId;
    _stepperBreadcrumb();
    stepperGoTo(3);
    const docs = await apiFetch(`/api/departments/${deptId}/doctors`) || [];
    const grid = document.getElementById('step3-doctor-grid');
    grid.innerHTML = docs.length
        ? docs.map(d => `
            <div class="card" style="cursor:pointer" onclick="stepperSelectDoctor('${d.id}','${escHtml(d.name)}')">
              <div style="font-weight:600">👨‍⚕️ ${escHtml(d.name)}</div>
              <div style="font-size:12px;color:var(--text-muted)">${escHtml(d.specialty || '')}</div>
            </div>`).join('')
        : '<div class="empty-state"><p>此科室無醫師</p></div>';
}

async function stepperSelectDoctor(docId, docName) {
    _st.doctorId = docId; _st.doctorName = docName;
    document.getElementById('modal-doctor').value = docId;
    _stepperBreadcrumb();
    stepperGoTo(4);
    await loadModalSchedules();
}

function stepperNextFromStep4() {
    const date = document.getElementById('modal-date').value;
    const session = document.getElementById('modal-session').value;
    if (!date) { toast('請選擇就診日期', 'warning'); return; }
    if (!session) { toast('請選擇診次', 'warning'); return; }
    // Build confirm summary
    const apptNum = document.getElementById('modal-appointment-number').value;
    const notify = [
        document.getElementById('notify-20').checked ? '前20號' : '',
        document.getElementById('notify-10').checked ? '前10號' : '',
        document.getElementById('notify-5').checked ? '前5號' : ''
    ].filter(Boolean).join('、');
    document.getElementById('confirm-summary').innerHTML = `
      <div>🏥 <b>醫院：</b>${escHtml(_st.hospitalName)}</div>
      ${_st.cat ? `<div>🏷️ <b>類別：</b>${escHtml(_st.cat)}</div>` : ''}
      <div>🩺 <b>科室：</b>${escHtml(_st.deptName)}</div>
      <div>👨‍⚕️ <b>醫師：</b>${escHtml(_st.doctorName)}</div>
      <div>📅 <b>日期：</b>${date} ${session}診</div>
      ${apptNum ? `<div>🎫 <b>掛號號碼：</b>${apptNum} 號</div>` : ''}
      <div>🔔 <b>通知門檻：</b>${notify || '（未設定）'}</div>
    `;
    stepperGoTo(5);
}

function stepperGoTo(step) {
    _st.step = step;
    for (let i = 1; i <= 5; i++) {
        document.getElementById(`step-${i}-content`).style.display = i === step ? '' : 'none';
    }
    document.querySelectorAll('.stepper-step').forEach(el => {
        const n = parseInt(el.dataset.step);
        el.classList.toggle('active', n === step);
        el.classList.toggle('done', n < step);
    });
    const subtitles = ['選擇醫院', '選擇科室', '選擇醫師', '選擇日期與設定通知', '確認並送出'];
    document.getElementById('stepper-subtitle').textContent = subtitles[step - 1] || '';
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function _stepperBreadcrumb() {
    const parts = [_st.hospitalName, _st.cat, _st.deptName, _st.doctorName].filter(Boolean);
    const el = document.getElementById('stepper-breadcrumb');
    el.innerHTML = parts.map((p, i) => i < parts.length - 1
        ? `<span class="bc-link">${escHtml(p)}</span><span class="bc-sep">›</span>`
        : `<span class="bc-cur">${escHtml(p)}</span>`).join('');
}

function cancelAddTracking() {
    navigate(document.querySelector('[data-page=tracking]'), 'tracking');
}

async function quickTrack(doctorId, doctorName) {
    // Collect context from existing selections if possible
    _st.hospitalId = _hsHospitalId;
    _st.hospitalName = _hsHospitalName;
    _st.deptId = ''; // will be filled or we fetch
    _st.deptName = '';
    _st.doctorId = doctorId;
    _st.doctorName = doctorName;

    // Use the new info endpoint to get perfect context
    const info = await apiFetch(`/api/doctors/${doctorId}/info`);
    if (info) {
        _st.hospitalId = info.hospital_id;
        _st.hospitalName = info.hospital_name;
        _st.deptId = info.department_id;
        _st.deptName = info.department_name;
    }

    // Go to "add-tracking" page
    const page = document.querySelector('[data-page="add-tracking"]');
    navigate(page, 'add-tracking');

    // Jump to Step 4 (Confirm/Preview) directly as we have doctor/dept info
    stepperGoTo(4);
    loadModalSchedules();
}

// Keep as noop stubs so old call-sites don't crash
function openTrackingModal() { openAddTracking(); }
function closeTrackingModal() { cancelAddTracking(); }

// 醫師數據 – 傳給日期選單
let _doctorSchedules = [];

async function loadModalSchedules() {
    const docId = document.getElementById('modal-doctor').value;
    const dateSel = document.getElementById('modal-date');
    const sessionSel = document.getElementById('modal-session');
    dateSel.innerHTML = '<option value="">— 載入中… —</option>';
    dateSel.disabled = true;
    sessionSel.innerHTML = '<option value="">— 請先選擇日期 —</option>';
    sessionSel.disabled = true;
    if (!docId) return;

    _doctorSchedules = await apiFetch(`/api/doctors/${docId}/schedules`) || [];

    if (!_doctorSchedules.length) {
        dateSel.innerHTML = '<option value="">— 尚無門診資料 —</option>';
        return;
    }

    const dates = [...new Set(_doctorSchedules.map(s => s.session_date))];
    dateSel.innerHTML = '<option value="">— 選擇就診日期 —</option>' +
        dates.map(d => {
            const label = new Date(d + 'T00:00:00').toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric', weekday: 'short' });
            return `<option value="${d}">${label}</option>`;
        }).join('');
    dateSel.disabled = false;
    dateSel.onchange = loadModalSessionsFromDate;
}

function loadModalSessionsFromDate() {
    const date = document.getElementById('modal-date').value;
    const sessionSel = document.getElementById('modal-session');
    sessionSel.innerHTML = '<option value="">— 選擇診次 —</option>';
    sessionSel.disabled = true;
    if (!date) return;
    const sessions = _doctorSchedules
        .filter(s => s.session_date === date && s.session_type)
        .map(s => s.session_type);
    const unique = [...new Set(sessions)];
    if (!unique.length) {
        sessionSel.innerHTML = '<option value="上午">上午</option><option value="下午">下午</option><option value="晚上">晚上</option>';
    } else {
        sessionSel.innerHTML = unique.map(s => `<option value="${s}">${s}</option>`).join('');
    }
    sessionSel.disabled = false;
}


async function showDoctorDetail(doctorId, name) {
    document.getElementById('doctor-modal-title').textContent = `👨‍⚕️ ${name}`;
    document.getElementById('doctor-modal').classList.add('open');
    document.getElementById('doctor-modal-body').innerHTML = `<div class="spinner"></div>`;

    const snaps = await apiFetch(`/api/doctors/${doctorId}/snapshots?limit=10`) || [];
    if (!snaps.length) {
        document.getElementById('doctor-modal-body').innerHTML =
            `<div class="empty-state"><div class="empty-icon">📊</div><p>尚無門診資料</p></div>`;
        return;
    }

    document.getElementById('doctor-modal-body').innerHTML = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>日期</th><th>診次</th><th>總額</th><th>已掛</th><th>目前號</th><th>狀態</th></tr>
        </thead>
        <tbody>
          ${snaps.map(s => `
          <tr>
            <td>${s.session_date}</td>
            <td>${s.session_type || '—'}</td>
            <td>${s.total_quota ?? '—'}</td>
            <td>${s.current_registered ?? '—'}</td>
            <td><strong>${s.current_number ?? '—'}</strong></td>
            <td>${s.is_full
            ? '<span class="badge badge-danger">額滿</span>'
            : '<span class="badge badge-success">可掛</span>'}
            </td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}



// ── Tracking list ─────────────────────────────────────────────
async function loadTracking() {
    const subs = await apiFetch('/api/tracking') || [];
    const list = document.getElementById('tracking-list');
    if (!subs.length) {
        list.innerHTML = `<div class="empty-state" style="grid-column:1/-1">
      <div class="empty-icon">🔔</div>
      <p>尚無追蹤設定<br><button class="btn btn-primary" onclick="openTrackingModal()" style="margin-top:12px">新增追蹤</button></p>
    </div>`;
        return;
    }

    const today = new Date().toISOString().split('T')[0];
    const active = subs.filter(s => s.session_date >= today);
    const expired = subs.filter(s => s.session_date < today);

    let html = '';
    if (active.length) {
        html += active.map(s => renderTrackingCard(s, false)).join('');
    }
    if (expired.length) {
        html += `<div class="tracking-section-title" style="grid-column:1/-1">📁 已過期的追蹤</div>`;
        html += expired.map(s => renderTrackingCard(s, true)).join('');
    }
    list.innerHTML = html;
}

function renderTrackingCard(sub, isExpired = false) {
    const pill = (on, done, label) => !on ? '' :
        `<span class="threshold-pill ${done ? 'done' : 'active'}">${label} ${done ? '✓' : '⏳'}</span>`;
    const email = sub.notify_email ? '📧 Email' : '';
    const line = sub.notify_line ? '📲 LINE' : '';

    const doctor = escHtml(sub.doctor_name || sub.doctor_id?.slice(0, 8) + '…');
    const dept = escHtml(sub.department_name || '');
    const hospital = escHtml(sub.hospital_name || '');
    const sessionLabel = [sub.session_date, sub.session_type ? sub.session_type + '診' : ''].filter(Boolean).join(' ');
    const apptNo = sub.appointment_number ? `掛號號碼：${sub.appointment_number}` : '';

    const expiredClass = isExpired ? 'expired' : (sub.is_active ? '' : 'inactive');

    return `
  <div class="tracking-card ${expiredClass}" id="sub-${sub.id}">
    <div class="tc-header">
      <div>
        <div style="font-weight:600; font-size:15px">👨‍⚕️ ${doctor}</div>
        ${dept ? `<div style="font-size:12px; color:var(--accent); margin-top:2px">🏥 ${hospital}｜${dept}</div>` : ''}
        <div style="font-size:13px; color:var(--text-muted); margin-top:4px">📅 ${sessionLabel}</div>
        ${apptNo ? `<div style="font-size:12px; color:var(--text-muted)">🎫 ${apptNo}</div>` : ''}
        <div style="font-size:12px; color:var(--text-dim); margin-top:2px">${email} ${line}</div>
      </div>
      ${isExpired ? '' : `<div class="tc-actions">
        <button class="btn btn-secondary btn-sm" onclick="toggleSubActive('${sub.id}', ${!sub.is_active})">
          ${sub.is_active ? '暫停' : '啟用'}
        </button>
        <button class="btn btn-danger btn-sm" onclick="deleteSub('${sub.id}')">刪除</button>
      </div>`}
    </div>
    <div class="threshold-pills">
      ${pill(sub.notify_at_20, sub.notified_20, '前20')}
      ${pill(sub.notify_at_10, sub.notified_10, '前10')}
      ${pill(sub.notify_at_5, sub.notified_5, '前5')}
    </div>
  </div>`;
}



async function submitTracking(e) {
    e.preventDefault();
    const docId = document.getElementById('modal-doctor').value;
    const deptId = document.getElementById('modal-dept').value;
    const sessionDate = document.getElementById('modal-date').value;
    const sessionType = document.getElementById('modal-session').value;

    if (!docId) { toast('請選擇醫師', 'warning'); return; }
    if (!sessionDate) { toast('請選擇就診日期', 'warning'); return; }
    if (!sessionType) { toast('請選擇診次', 'warning'); return; }

    const btn = document.getElementById('submit-tracking-btn');
    btn.disabled = true; btn.textContent = '新增中…';

    const apptNumValue = document.getElementById('modal-appointment-number').value;
    const apptNum = apptNumValue ? parseInt(apptNumValue, 10) : null;

    try {
        await apiPost('/api/tracking', {
            doctor_id: docId,
            department_id: deptId || undefined,
            session_date: sessionDate,
            session_type: sessionType,
            appointment_number: apptNum,
            notify_at_20: document.getElementById('notify-20').checked,
            notify_at_10: document.getElementById('notify-10').checked,
            notify_at_5: document.getElementById('notify-5').checked,
            notify_email: document.getElementById('notify-email').checked,
            notify_line: document.getElementById('notify-line').checked,
        });
        toast('追蹤已新增！', 'success');
        cancelAddTracking();
        loadTracking();
    } catch (e) { toast(e.message, 'error'); }
    finally { btn.disabled = false; btn.textContent = '確認新增'; }
}

async function quickTrack(doctorId, doctorName) {
    // Pre-fill stepper state from current hospital-search context
    _st.hospitalId = _hsHospitalId || '';
    _st.hospitalName = _hsHospitalName || '';
    _st.cat = _hsDeptAll?.cat || '';
    _st.deptId = '';
    _st.deptName = '';
    _st.doctorId = doctorId;
    _st.doctorName = doctorName;

    // Try to resolve dept from the currently selected dept button
    const activeDeptBtn = document.querySelector('#hs-dept-grid .dept-btn.active');
    if (activeDeptBtn) {
        _st.deptName = activeDeptBtn.textContent.trim();
    }
    // Resolve deptId from current breadcrumb state stored in _hsDeptAll
    if (_hsDeptAll?.depts?.length) {
        const found = _hsDeptAll.depts.find(d => d.name === _st.deptName);
        if (found) _st.deptId = found.id;
    }

    // Fetch doctor's dept info if we still don't have it
    if (!_st.deptId) {
        const docInfo = await apiFetch(`/api/doctors/${doctorId}/info`).catch(() => null);
        if (docInfo) {
            _st.hospitalId = docInfo.hospital_id;
            _st.hospitalName = docInfo.hospital_name;
            _st.deptId = docInfo.department_id;
            _st.deptName = docInfo.department_name;
        }
    }

    document.getElementById('modal-doctor').value = doctorId;
    _stepperBreadcrumb();

    navigate(document.querySelector('[data-page=add-tracking]'), 'add-tracking');
    // Small delay to let page render, then jump to step 4
    setTimeout(async () => {
        stepperGoTo(4);
        await loadModalSchedules();
    }, 80);
}


// ── Notifications ─────────────────────────────────────────────


async function loadNotifications() {
    const subs = await apiFetch('/api/tracking') || [];
    const tbody = document.getElementById('notif-table-body');

    if (!subs.length) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:32px; color:var(--text-muted)">尚無通知</td></tr>`;
        return;
    }

    // Load logs for each sub
    const allLogs = [];
    for (const sub of subs.slice(0, 5)) {
        const logs = await apiFetch(`/api/tracking/${sub.id}/logs`).catch(() => []) || [];
        logs.forEach(l => { l._sub = sub; allLogs.push(l); });
    }
    allLogs.sort((a, b) => new Date(b.sent_at) - new Date(a.sent_at));

    if (!allLogs.length) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:32px; color:var(--text-muted)">尚無通知紀錄</td></tr>`;
        return;
    }

    tbody.innerHTML = allLogs.map(l => `
    <tr>
      <td style="color:var(--text-muted); font-size:13px">${new Date(l.sent_at).toLocaleString('zh-TW')}</td>
      <td>${l._sub?.session_date || '—'} ${l._sub?.session_type || ''}</td>
      <td><span class="badge badge-warning">前 ${l.threshold} 號</span></td>
      <td>${l.channel === 'email' ? '📧 Email' : '📲 LINE'}</td>
      <td>${l.success
            ? '<span class="badge badge-success">成功</span>'
            : '<span class="badge badge-danger">失敗</span>'}
      </td>
    </tr>`).join('');
}

// ── Profile ───────────────────────────────────────────────────
async function saveProfile(e) {
    e.preventDefault();
    try {
        await apiPatch('/api/users/me', { display_name: document.getElementById('profile-name').value });
        toast('個人資料已儲存', 'success');
        document.getElementById('user-name-display').textContent =
            document.getElementById('profile-name').value;
    } catch (e) { toast(e.message, 'error'); }
}

async function saveLineToken(e) {
    e.preventDefault();
    try {
        await apiPatch('/api/users/me', { line_notify_token: document.getElementById('line-token').value });
        toast('LINE Notify Token 已儲存', 'success');
    } catch (e) { toast(e.message, 'error'); }
}

// ── Modal helpers ─────────────────────────────────────────────
function closeModalIfOverlay(e) {
    if (e.target.classList.contains('modal-overlay'))
        e.target.classList.remove('open');
}

// ── Admin user management ─────────────────────────────────────
async function loadAdminUsers() {
    const tbody = document.getElementById('admin-users-tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="7" style="padding:20px; text-align:center; color:var(--text-muted)">載入中…</td></tr>';

    const users = await apiFetch('/api/users/') || [];
    if (!users.length) {
        tbody.innerHTML = '<tr><td colspan="7" style="padding:20px; text-align:center; color:var(--text-muted)">無用戶資料</td></tr>';
        return;
    }

    tbody.innerHTML = users.map(u => {
        const isAdmin = u.is_admin ? '✅ 管理員' : '—';
        const adminBtnLabel = u.is_admin ? '撤銷管理員' : '授予管理員';
        const adminBtnClass = u.is_admin ? 'btn-danger' : 'btn-secondary';
        const verified = u.is_verified ? '✅' : '❌';
        const createdAt = u.created_at ? new Date(u.created_at).toLocaleDateString('zh-TW') : '—';
        const isSelf = currentUser && u.id === currentUser.id;
        const displayName = escHtml(u.display_name || '—');

        const actions = isSelf
            ? `<span style="color:var(--text-muted); font-size:12px">(自己)</span>`
            : `<div style="display:flex; gap:6px; flex-wrap:wrap">
                <button class="btn btn-secondary btn-sm" onclick="openEditUserModal('${u.id}', '${escHtml(u.display_name || '')}')">✏️ 編輯</button>
                <button class="btn ${adminBtnClass} btn-sm" onclick="toggleUserAdmin('${u.id}', ${!u.is_admin})">${adminBtnLabel}</button>
                ${!u.is_admin ? `<button class="btn btn-danger btn-sm" onclick="deleteUser('${u.id}', '${escHtml(u.email || u.id)}')">🗑️ 刪除</button>` : ''}
               </div>`;

        return `<tr style="border-bottom:1px solid var(--border)">
            <td style="padding:10px 12px">${escHtml(u.email || '—')}</td>
            <td style="padding:10px 12px">${displayName}</td>
            <td style="padding:10px 12px; text-align:center">${verified}</td>
            <td style="padding:10px 12px">${isAdmin}</td>
            <td style="padding:10px 12px">${createdAt}</td>
            <td style="padding:10px 12px">${actions}</td>
        </tr>`;
    }).join('');
}

async function toggleUserAdmin(userId, grantAdmin) {
    try {
        await apiFetch(`/api/users/${userId}/admin?is_admin=${grantAdmin}`, { method: 'PATCH' });
        toast(grantAdmin ? '已授予管理員權限' : '已撤銷管理員權限', 'success');
        await loadAdminUsers();
    } catch (e) { toast(e.message, 'error'); }
}

async function toggleScheduler(resume) {
    try {
        const endpoint = resume ? '/api/admin/scheduler/resume' : '/api/admin/scheduler/pause';
        await apiPost(endpoint, {});
        toast(`排程已${resume ? '恢復' : '暫停'}`, 'success');
        loadSchedulerStatus();
    } catch (e) { toast(e.message, 'error'); }
}

function openEditUserModal(userId, currentName) {
    document.getElementById('edit-user-id').value = userId;
    document.getElementById('edit-display-name').value = currentName;
    document.getElementById('edit-new-password').value = '';
    document.getElementById('admin-edit-modal').classList.add('open');
}

async function submitAdminEdit(e) {
    e.preventDefault();
    const userId = document.getElementById('edit-user-id').value;
    const displayName = document.getElementById('edit-display-name').value.trim();
    const newPwd = document.getElementById('edit-new-password').value;
    const btn = document.getElementById('admin-edit-submit-btn');
    btn.disabled = true; btn.textContent = '儲存中…';
    try {
        await apiFetch(`/api/users/${userId}/edit`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                display_name: displayName || null,
                new_password: newPwd || null,
            }),
        });
        toast('使用者資料已更新', 'success');
        document.getElementById('admin-edit-modal').classList.remove('open');
        await loadAdminUsers();
    } catch (e) { toast(e.message, 'error'); }
    finally { btn.disabled = false; btn.textContent = '儲存'; }
}

async function deleteUser(userId, label) {
    if (!confirm(`確定要刪除「${label}」？此操作無法還原，其追蹤設定也會一併刪除。`)) return;
    try {
        await apiFetch(`/api/users/${userId}`, { method: 'DELETE' });
        toast(`使用者 ${label} 已刪除`, 'success');
        await loadAdminUsers();
    } catch (e) { toast(e.message, 'error'); }
}



// ── Helpers ───────────────────────────────────────────────────
function escHtml(str) {
    return String(str).replace(/[&<>"']/g, m =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
}

// ── Boot ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    if (authToken) {
        await initApp();
    } else {
        document.getElementById('auth-page').classList.add('show');
    }
});

// ══════════════════════════════════════
// ADMIN - SCHEDULER & LOGS
// ══════════════════════════════════════

async function loadSchedulerStatus() {
    try {
        const res = await apiFetch('/api/admin/scheduler');
        const badge = document.getElementById('scheduler-status-badge');
        const btnPause = document.getElementById('btn-pause-scheduler');
        const btnResume = document.getElementById('btn-resume-scheduler');

        if (res.is_running) {
            badge.textContent = '運行中 (Running)';
            badge.style.background = 'var(--success)';
            badge.style.color = '#fff';
            btnPause.disabled = false;
            btnResume.disabled = true;
        } else {
            badge.textContent = '已暫停 (Paused)';
            badge.style.background = 'var(--warning)';
            badge.style.color = '#fff';
            btnPause.disabled = true;
            btnResume.disabled = false;
        }

        const listDiv = document.getElementById('scheduler-jobs-list');
        if (!res.jobs || res.jobs.length === 0) {
            listDiv.innerHTML = '<span style="color:var(--text-muted)">無排程任務</span>';
        } else {
            const html = res.jobs.map(j => {
                const nt = j.next_run_time ? new Date(j.next_run_time).toLocaleString() : '無';
                return `<div><b>${j.name}</b><br><span style="color:var(--text-muted)">下次執行: ${nt}</span></div>`;
            }).join('<br>');
            listDiv.innerHTML = html;
        }
    } catch (e) {
        toast(e.message, 'error');
    }
}

async function toggleScheduler(resume) {
    try {
        const endpoint = resume ? '/api/admin/scheduler/resume' : '/api/admin/scheduler/pause';
        await apiPost(endpoint, {});
        toast(`排程已${resume ? '恢復' : '暫停'}`, 'success');
        loadSchedulerStatus();
    } catch (e) {
        toast(e.message, 'error');
    }
}

async function loadServerLogs() {
    try {
        const res = await apiFetch('/api/admin/logs?lines=200');
        const pre = document.getElementById('server-log-content');
        if (res.content) {
            pre.textContent = res.content;
            // auto scroll to bottom
            pre.scrollTop = pre.scrollHeight;
        } else {
            pre.textContent = "尚無記錄";
        }

        const sizeKb = (res.size_bytes / 1024).toFixed(1);
        document.getElementById('log-file-size').textContent = `大小: ${sizeKb} KB`;
        document.getElementById('log-file-time').textContent = `最後更新: ${res.last_modified ? new Date(res.last_modified).toLocaleString() : '--'}`;
    } catch (e) {
        toast(e.message, 'error');
        document.getElementById('server-log-content').textContent = "讀取日誌失敗: " + e.message;
    }
}

async function clearServerLogs() {
    if (!confirm("確定要清空伺服器日誌嗎？此操作無法還原。")) return;
    try {
        await apiDelete('/api/admin/logs');
        toast('日誌已清空', 'success');
        loadServerLogs();
    } catch (e) {
        toast(e.message, 'error');
    }
}
