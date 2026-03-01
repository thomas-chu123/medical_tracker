/* ============================================================
   app.js — 台灣醫療門診追蹤系統 Frontend Logic
   Version: 2026.02.28-refactor
   ============================================================ */

const API = '';   // Same origin; change to http://localhost:8000 if needed
let authToken = localStorage.getItem('auth_token') || null;
let currentUser = null;

// ── AppState: Unified application state ───────────────────────
const AppState = {
    // Auth
    authToken: localStorage.getItem('auth_token') || null,
    currentUser: null,

    // Dashboard
    dashboard: {
        hospitals: [],
        selectedHospitalId: null,
        subscriptions: [],
    },

    // Hospital Search
    hospitalSearch: {
        selectedHospitalId: null,
        selectedHospitalName: '',
        selectedDepartmentId: null,
        selectedDepartmentName: '',
        allDepartments: [],
        allDoctors: [],
        doctorSearchTimer: null,
        departmentData: { depts: [], hospName: '', cat: '' },
    },

    // Add Tracking Stepper
    stepper: {
        step: 1,
        hospitalId: '',
        hospitalName: '',
        category: '',
        departmentId: '',
        departmentName: '',
        doctorId: '',
        doctorName: '',
        doctorSchedules: [],
    },

    // Tracking Management
    tracking: {
        subscriptions: [],
        currentTab: 'current',
    },

    // Notifications
    notifications: {
        logs: [],
        currentTab: 'current',
    },

    // Charts
    charts: {
        crowdChart: null,
        deptComparisonChart: null,
        doctorComparisonChart: null,
        doctorSpeedChart: null,
    },

    // Analysis
    analysis: {
        ranking: [],
    },

    // Components
    combos: {},
};

// ── Global State ──────────────────────────────────────────────
let _dashHospitals = [];
let _selectedDashHospId = null;
let _allDashboardSubs = [];
let _notificationLogsBySubscription = {}; // Map: sub_id -> {threshold: [logs]}

// ── Utility: API fetch ────────────────────────────────────────
async function apiFetch(path, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (AppState.authToken) headers['Authorization'] = `Bearer ${AppState.authToken}`;

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

    // 控制 QR Code 顯示
    const qrContainer = document.getElementById('line-qr-container');
    if (qrContainer) {
        qrContainer.style.display = tab === 'login' ? 'block' : 'none';
    }
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
        AppState.authToken = data.access_token;
        localStorage.setItem('auth_token', authToken);

        // Show success feedback before reloading
        toast('登入成功！重新載入中…', 'success', 2000);

        // Wait for toast to be visible, then reload to clear cached UI state
        setTimeout(() => {
            window.location.reload();
        }, 500);
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
            line_user_id: document.getElementById('reg-line-user-id').value || undefined,
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
    AppState.authToken = null;
    localStorage.removeItem('auth_token');
    currentUser = null;
    AppState.currentUser = null;
    document.body.classList.remove('is-admin');
    document.getElementById('app').style.display = 'none';
    document.getElementById('auth-page').classList.add('show');
}

// ── App init ──────────────────────────────────────────────────
async function initApp(userFromLogin = null) {
    // Show app shell IMMEDIATELY for better perceived performance
    document.getElementById('auth-page').classList.remove('show');
    document.getElementById('app').style.display = 'grid';

    if (userFromLogin) {
        // Fresh login: use profile from login response
        currentUser = userFromLogin;
        AppState.currentUser = userFromLogin;
    } else {
        // Page reload: fetch profile with stored token
        try {
            currentUser = await apiFetch('/api/users/me');
            AppState.currentUser = currentUser;
            if (!currentUser) return;
        } catch (e) {
            console.error('[initApp] Failed to load profile:', e);
            handleLogout(); return;
        }
    }

    // Set user info
    const name = currentUser.display_name || 'User';
    const displayEl = document.getElementById('user-name-display');
    const avatarEl = document.getElementById('user-avatar');
    const profileNameEl = document.getElementById('profile-name');
    const lineUserIdEl = document.getElementById('line-user-id');

    if (displayEl) displayEl.textContent = name;
    if (avatarEl) avatarEl.textContent = name[0].toUpperCase();
    if (profileNameEl) profileNameEl.value = name;
    if (lineUserIdEl && currentUser.line_user_id) lineUserIdEl.value = currentUser.line_user_id;

    // Manage admin nav button visibility
    const adminBtn = document.getElementById('admin-nav-btn');
    if (adminBtn) {
        if (currentUser.is_admin) {
            adminBtn.style.display = 'flex';
            document.body.classList.add('is-admin');
        } else {
            adminBtn.style.display = 'none';
            document.body.classList.remove('is-admin');
        }
    }

    // Load dashboard
    loadDashboard();
}

// ── Mobile Navigation Drawer ──────────────────────────────────
function toggleMobileMenu() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('mobile-overlay');
    const isOpen = sidebar.classList.contains('open');
    if (isOpen) {
        sidebar.classList.remove('open');
        overlay.classList.remove('open');
    } else {
        sidebar.classList.add('open');
        overlay.classList.add('open');
    }
}

function closeMobileMenu() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('mobile-overlay');
    sidebar.classList.remove('open');
    overlay.classList.remove('open');
}

// ── Navigation ────────────────────────────────────────────────
function navigate(btn, pageId, options = {}) {
    // Close mobile drawer when navigating
    closeMobileMenu();
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
        _currentTrackingTab = 'current';
        // Reset tab button styles
        const btnCurr = document.getElementById('btn-tab-tracking-current');
        const btnPast = document.getElementById('btn-tab-tracking-past');
        if (btnCurr) btnCurr.className = 'btn btn-primary';
        if (btnPast) btnPast.className = 'btn btn-secondary';
        loadTracking();
    } else if (pageId === 'notifications') {
        loadNotifications();
    } else if (pageId === 'analysis') {
        switchAnalysisSheet('sheet1');
    } else if (pageId === 'profile') {
        loadProfile();
    } else if (pageId === 'admin') {
        switchAdminTab('users');
    } else if (pageId === 'add-tracking') {
        console.log('[navigate] add-tracking hit, skipReset:', options.skipReset, 'stepper BEFORE:', JSON.parse(JSON.stringify(AppState.stepper)));
        if (!options.skipReset) {
            // Reset stepper state only if not skipped (e.g., from quickTrack)
            Object.assign(AppState.stepper, { step: 1, hospitalId: '', hospitalName: '', cat: '', deptId: '', deptName: '', doctorId: '', doctorName: '' });
            console.log('[navigate] stepper RESET');
            stepperGoTo(1);
            document.getElementById('stepper-breadcrumb').innerHTML = '';
            loadStepperHospitals();
        }
    }
}

// ── Dashboard ─────────────────────────────────────────────────
async function loadDashboard() {
    console.log('[Dashboard] loadDashboard() called');

    // Fire fast requests immediately, load subscriptions asynchronously in background
    const qs = _selectedDashHospId ? `?hospital_id=${_selectedDashHospId}` : '';

    // 1. Load fast data immediately (hospitals, stats, crowdStats)
    console.log('[Dashboard] Loading fast data...');
    const [hospList, gStats, crowdStats] = await Promise.all([
        // Only fetch hospitals if list is empty
        !_dashHospitals.length ? apiFetch('/api/hospitals').catch(() => []) : Promise.resolve(_dashHospitals),
        apiFetch(`/api/stats/global${qs}`).catch(() => null),
        apiFetch(`/api/stats/crowd-analysis${qs}`).catch(() => null),
    ]);

    // Update hospital list if fetched
    if (!_dashHospitals.length && hospList) {
        _dashHospitals = hospList;
        renderDashHospList();
    }

    // 2. Update Stats
    if (gStats) {
        document.getElementById('stat-hospitals').textContent = gStats.hospitals;
        document.getElementById('stat-doctors').textContent = gStats.doctors;
        document.getElementById('stat-alerts').textContent = gStats.notifications_today || '0';
    }

    // 3. Render Crowd Chart
    if (crowdStats) {
        renderCrowdChart(crowdStats);
    }

    // 4. Load tracking subscriptions in background (don't wait for it)
    // This prevents slow tracking queries from blocking the UI
    console.log('[Dashboard] Calling _loadTrackingAsync()');
    _loadTrackingAsync();

    // 5. Update timestamp
    document.getElementById('last-update-label').textContent = `最後更新：${new Date().toLocaleString('zh-TW')}`;

    console.log('[Dashboard] loadDashboard() completed');
}

// Load tracking subscriptions asynchronously in background
async function _loadTrackingAsync() {
    try {
        console.log('[Dashboard] Starting _loadTrackingAsync...');
        const [subs, logs] = await Promise.all([
            apiFetch('/api/tracking/').catch(() => []),
            apiFetch('/api/tracking/logs/all').catch(() => [])
        ]);
        console.log('[Dashboard] API response (raw):', subs);
        console.log('[Dashboard] API response type:', typeof subs);
        console.log('[Dashboard] API response is array:', Array.isArray(subs));

        _allDashboardSubs = (subs || []).filter(s => s.is_active);
        console.log('[Dashboard] Loaded tracking subs (filtered):', _allDashboardSubs.length);
        console.log('[Dashboard] Filtered subs:', _allDashboardSubs);

        // Build notification logs index
        _notificationLogsBySubscription = {};
        for (const log of (logs || [])) {
            const subId = log.subscription_id;
            const threshold = log.threshold;
            if (!_notificationLogsBySubscription[subId]) {
                _notificationLogsBySubscription[subId] = {};
            }
            if (!_notificationLogsBySubscription[subId][threshold]) {
                _notificationLogsBySubscription[subId][threshold] = [];
            }
            _notificationLogsBySubscription[subId][threshold].push(log);
        }

        document.getElementById('stat-tracking').textContent = _allDashboardSubs.length;

        const grid = document.getElementById('dashboard-tracking-grid');
        console.log('[Dashboard] Grid element found:', !!grid);

        // Re-render tracking cards with new data
        console.log('[Dashboard] About to call renderDashboardTracking()');
        renderDashboardTracking();
        console.log('[Dashboard] renderDashboardTracking() called');
    } catch (err) {
        console.error('[Dashboard] Error loading tracking subscriptions:', err);
        // Keep showing old data or empty state
    }
}

/** Dashboard Hospital Filter Logic **/
function renderDashHospList(filterText = '') {
    const list = document.getElementById('dash-hosp-list');
    let q = filterText.toLowerCase().trim();

    const selectedHosp = _dashHospitals.find(h => h.id === _selectedDashHospId);
    if (selectedHosp && selectedHosp.name.toLowerCase().trim() === q) {
        q = ''; // Skip filtering if input matches the currently selected hospital
    }

    // Add "All Hospitals" option
    let items = [{ id: null, name: '全部醫院' }, ..._dashHospitals];
    if (q) {
        items = items.filter(h => h.name.toLowerCase().includes(q));
    }

    if (!items.length) {
        list.innerHTML = '<div class="combo-opt no-result">無匹配醫院</div>';
        return;
    }

    list.innerHTML = items.map(h => `
        <div class="combo-opt" onclick="selectDashHosp('${h.id}', '${escHtml(h.name)}')">
            ${h.id === null ? '🌐' : '🏥'} ${escHtml(h.name)}
        </div>
    `).join('');
}

function filterDashHosp(val) {
    renderDashHospList(val);
    document.getElementById('dash-hosp-combo').classList.add('open');
}

function showDashHospList() {
    renderDashHospList(document.querySelector('#dash-hosp-combo input').value);
    document.getElementById('dash-hosp-combo').classList.add('open');
}

function toggleDashHosp() {
    const el = document.getElementById('dash-hosp-combo');
    const inp = el.querySelector('input');
    el.classList.toggle('open');
    if (el.classList.contains('open')) {
        renderDashHospList(inp.value);
        inp.focus();
    }
}

function selectDashHosp(id, name) {
    _selectedDashHospId = (id === 'null' || id === null) ? null : id;
    const inp = document.querySelector('#dash-hosp-combo input');
    inp.value = _selectedDashHospId ? name : '';
    document.getElementById('dash-hosp-combo').classList.remove('open');

    // Refresh data
    loadDashboard();
}

// Close dash hospital combo when clicking outside
document.addEventListener('click', e => {
    if (!e.target.closest('#dash-hosp-combo')) {
        document.getElementById('dash-hosp-combo')?.classList.remove('open');
    }
});

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

async function renderDashboardTracking() {
    console.log('[renderDashboardTracking] Called with _allDashboardSubs:', _allDashboardSubs.length);

    const grid = document.getElementById('dashboard-tracking-grid');
    console.log('[renderDashboardTracking] Grid element:', grid);
    console.log('[renderDashboardTracking] Grid display:', grid?.style.display);
    console.log('[renderDashboardTracking] Grid classes:', grid?.className);
    console.log('[renderDashboardTracking] Grid visible:', grid?.offsetHeight);

    // Get today's date in YYYY-MM-DD format (Taiwan timezone)
    const todayStr = new Date().toLocaleString('sv-SE', { timeZone: 'Asia/Taipei' }).substring(0, 10);

    // Filter by selected hospital and date (only show active upcoming sessions)
    let filtered = _allDashboardSubs.filter(s => (s.session_date || '') >= todayStr);
    if (_selectedDashHospId) {
        filtered = filtered.filter(s => s.hospital_id === _selectedDashHospId);
    }

    console.log('[renderDashboardTracking] Filtered items:', filtered.length);

    if (!filtered.length) {
        grid.innerHTML = `<div class="empty-state">
      <div class="empty-icon">🔔</div>
      <p>目前無相關追蹤項目<br><a href="#" onclick="navigate(document.querySelector('[data-page=tracking]'), 'tracking')">前往追蹤清單</a></p>
    </div>`;
        console.log('[renderDashboardTracking] Rendered empty state');
        return;
    }

    const cards = filtered.map(sub => renderClinicCard(sub, null));
    grid.innerHTML = cards.join('');
    console.log('[renderDashboardTracking] Rendered', cards.length, 'cards');
}

function renderClinicCard(sub, snap) {
    console.log('renderClinicCard data - sub room:', sub.clinic_room, 'snap room:', snap?.clinic_room);

    // 1. Unified Progress Source
    const current = (sub.current_number != null) ? sub.current_number : (snap?.current_number != null ? snap.current_number : '—');
    const total_quota = (sub.total_quota != null) ? sub.total_quota : (snap?.total_quota != null ? snap.total_quota : '—');
    const current_registered = (sub.current_registered != null) ? sub.current_registered : (snap?.current_registered != null ? snap.current_registered : '—');
    const waiting_list = sub.waiting_list || snap?.waiting_list || [];
    const eta = sub.eta || snap?.eta;

    // 2. Updated Number Display
    let numberDisplayHtml = `目前: ${current}號 / 總號: ${total_quota}號 / 掛號: ${current_registered}人`;
    let total = total_quota === '—' ? (current_registered === '—' ? 0 : current_registered) : total_quota;

    // 3. Status & Progress
    const remaining = sub.remaining ?? '—';
    const status = sub.status;
    const isNum = typeof remaining === 'number';
    const isFinished = status === '看診完畢' || status === '已關診';

    const pct = isNum && total > 0 && typeof total === 'number' ? Math.round((1 - remaining / total) * 100) : 0;
    const barClass = pct >= 90 ? 'danger' : pct >= 70 ? 'warning' : 'safe';

    // Helper function outside of pillDone for better performance
    const hasSuccessfulNotification = (threshold) => {
        try {
            if (!_notificationLogsBySubscription || !sub.id) return false;
            const logs = _notificationLogsBySubscription[sub.id]?.[threshold] || [];
            return logs.some(log => log.success === true);
        } catch (e) {
            console.warn('[pillDone] Error checking notification logs:', e);
            return false;
        }
    };

    const pillDone = (flagNotified, label, threshold, shouldSkip = false) => {
        try {
            // Check if actually sent (successful log exists)
            if (hasSuccessfulNotification(threshold)) {
                return `<span class="threshold-pill done">✅${label}</span>`;
            }

            // If marked notified but no successful log, it was skipped
            if (flagNotified || shouldSkip) {
                return `<span class="threshold-pill skipped">⏸️${label}</span>`;
            }

            // Otherwise pending
            return `<span class="threshold-pill pending">⏳${label}</span>`;
        } catch (e) {
            console.warn('[pillDone] Error rendering pill:', e);
            // Fallback: just show basic status
            return flagNotified ? `<span class="threshold-pill done">✅${label}</span>` : `<span class="threshold-pill pending">⏳${label}</span>`;
        }
    };

    // 4. Labels & Badges
    const doctorLabel = sub.doctor_name || ('ID: ' + sub.doctor_id?.slice(0, 8) + '…');
    const deptLabel = sub.department_name || '';
    const hospLabel = sub.hospital_name || '';
    const sessionLabel = [sub.session_date, sub.session_type ? sub.session_type + '診' : ''].filter(Boolean).join(' ');
    const apptNoHtml = `<div style="font-size:12px; color:var(--text-muted); margin-top:2px">🎫 我的號碼：${(sub.appointment_number != null) ? sub.appointment_number : '<span style="opacity:0.6">(未填寫)</span>'}</div>`;
    const statusBadge = status ? `<span class="status-badge ${isFinished ? 'finished' : 'upcoming'}">${status}</span>` : '';

    // 5. Waiting People & Distance
    let distanceHtml = '';
    if (isNum && sub.appointment_number && waiting_list.length > 0) {
        const countAhead = waiting_list.filter(x => x < sub.appointment_number).length;
        if (countAhead > 0) {
            distanceHtml = `<div style="font-size:13px; color:var(--text-muted)">前有 <strong style="color:var(--text)">${countAhead}</strong> 位等候人士</div>`;
        } else if (waiting_list.includes(sub.appointment_number)) {
            distanceHtml = `<div style="font-size:13px; color:var(--text-muted)"><strong>⭐ 到號了！(輪到您看診)</strong></div>`;
        } else if (sub.appointment_number <= current) {
            distanceHtml = `<div style="font-size:13px; color:var(--text-muted)">⚠️ 您的號碼已過號</div>`;
        }
    } else if (isNum && !isFinished) {
        distanceHtml = `<div style="font-size:13px; color:var(--text-muted)">剩餘 <strong style="color:var(--text)">${remaining}</strong> 位等候人士</div>`;
    }

    // 6. ETA Display
    const etaHtml = eta ? `<div style="font-size:12px; color:var(--primary); margin-top:4px">⏱️ 預計看診：<strong>${eta}</strong></div>` : '';

    // Create onclick handler - show waiting list when clicked
    const clinicRoom = sub.clinic_room || snap?.clinic_room;
    const onclickHandler = clinicRoom ? `onclick="showClinicWaitingList('${escHtml(sub.doctor_name || 'N/A')}', '${escHtml(clinicRoom)}', '${sub.doctor_id}')"` : '';
    const cursorStyle = clinicRoom ? 'cursor:pointer;' : '';

    return `
  <div class="clinic-card ${isFinished ? 'status-finished' : ''}" style="${cursorStyle}" ${onclickHandler}>
    <div class="doctor-name">👨‍⚕️ ${escHtml(doctorLabel)} ${statusBadge}</div>
    ${deptLabel ? `<div style="font-size:12px; color:var(--text-muted); margin-bottom:2px">🏥 ${escHtml(hospLabel)}｜${escHtml(deptLabel)}</div>` : ''}
    <div style="margin-bottom: 8px;">
      <span class="dept-tag">📅 ${escHtml(sessionLabel)}</span>
      ${(sub.clinic_room || snap?.clinic_room) ? `<span class="dept-tag" style="margin-left:6px;">🚪 診間：${escHtml(sub.clinic_room || snap.clinic_room)}診</span>` : ''}
    </div>
    ${apptNoHtml}
    ${etaHtml}
    <div class="number-display">
      <div class="current-num ${isFinished ? 'text-muted' : ''}">${isFinished ? '完畢' : current}</div>
      <div class="num-label">${numberDisplayHtml}</div>
    </div>
    ${isNum ? `
    <div class="progress-wrap" style="margin-bottom:10px">
      <div class="progress-bar ${isFinished ? 'muted' : barClass}" style="width:${pct}%"></div>
    </div>
    ${distanceHtml}
    ` : ''}
    <div class="threshold-pills" style="margin-top:10px">
      ${sub.notify_at_20 ? pillDone(sub.notified_20, '前20人', 20, typeof current === 'number' && sub.appointment_number && current > sub.appointment_number) : ''}
      ${sub.notify_at_10 ? pillDone(sub.notified_10, '前10人', 10, typeof current === 'number' && sub.appointment_number && current > sub.appointment_number) : ''}
      ${sub.notify_at_5 ? pillDone(sub.notified_5, '前5人', 5, typeof current === 'number' && sub.appointment_number && current > sub.appointment_number) : ''}
    </div>
  </div>`;
}

async function refreshAll() {
    toast('正在更新資料…', 'info');
    try {
        await apiPost('/api/stats/scrape-now', {});
        await new Promise(r => setTimeout(r, 1500));
        await loadDashboard();
        toast('資料已更新', 'success');
    } catch {
        toast('更新失敗', 'error');
    }
}

async function showClinicWaitingList(doctorName, clinicRoom, doctorId) {
    const modal = document.getElementById('clinic-waiting-modal');
    document.getElementById('clinic-waiting-title').textContent = `🚪 診間 ${escHtml(clinicRoom)}診 - ${escHtml(doctorName)}`;
    document.getElementById('clinic-waiting-body').innerHTML = '<div class="spinner"></div>';

    modal.classList.add('open');

    try {
        // Fetch latest snapshot for this doctor's clinic room
        const snap = await apiFetch(`/api/snapshots/doctor/${doctorId}/current?clinic_room=${encodeURIComponent(clinicRoom)}`);
        if (!snap) {
            document.getElementById('clinic-waiting-body').innerHTML =
                '<div class="empty-state"><p>無法獲取候診列表資料</p></div>';
            return;
        }

        // Get today's date (Taiwan timezone)
        const today = new Date();
        today.setMilliseconds(0);
        const todayStr = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
        const sessionDate = snap.session_date || '';
        const isToday = sessionDate === todayStr;

        // Update subtitle based on whether it's today
        if (isToday) {
            document.getElementById('clinic-waiting-subtitle').textContent = `原生候診列表 (每3分鐘更新)`;
        } else {
            document.getElementById('clinic-waiting-subtitle').textContent = `${sessionDate} 排班信息（未來日期，無實時進度）`;
        }

        const queueDetails = snap.clinic_queue_details || [];

        // Build statistics section
        let html = `
            <div style="padding:16px">
                <div style="background:var(--bg-elevated); padding:16px; border-radius:8px; margin-bottom:16px">
                    <div style="font-weight:600; margin-bottom:12px">📊 統計資訊</div>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; font-size:13px">
                        <div><span style="color:var(--text-muted)">目前號碼：</span><strong style="font-size:16px">${snap.current_number || '—'}</strong></div>
                        <div><span style="color:var(--text-muted)">已掛號人數：</span><strong>${snap.current_registered || '—'}</strong></div>
                        <div><span style="color:var(--text-muted)">總名額：</span><strong>${snap.total_quota || '—'}</strong></div>
                        ${isToday ? `<div><span style="color:var(--text-muted)">等候人數：</span><strong>${queueDetails.filter(q => q.number > snap.current_number && q.status !== '完成').length}</strong></div>` : ''}
                    </div>
                </div>
        `;

        // Only show queue details if it's today
        if (!isToday) {
            document.getElementById('clinic-waiting-body').innerHTML = html + '<div class="empty-state"><p>⏳ 該日期為未來排班，醫院只提供當日的實時進度資料</p></div></div>';
            return;
        }

        // If no queue details, show simple message
        if (!queueDetails || queueDetails.length === 0) {
            html += '<div class="empty-state"><p>目前無候診資料</p></div>';
            document.getElementById('clinic-waiting-body').innerHTML = html + '</div>';
            return;
        }

        // Build scrollable table
        html += `
                <div style="border-radius:8px; border:1px solid var(--border-subtle); overflow:hidden; max-height:400px; overflow-y:auto">
                    <table style="width:100%; border-collapse:collapse; font-size:13px">
                        <thead style="position:sticky; top:0; background:var(--bg-elevated); z-index:10">
                            <tr style="border-bottom:1px solid var(--border-subtle)">
                                <th style="padding:12px; text-align:center; font-weight:600; width:40%">看診號</th>
                                <th style="padding:12px; text-align:center; font-weight:600; width:60%">目前看診情形</th>
                            </tr>
                        </thead>
                        <tbody>
        `;

        queueDetails.forEach((item, idx) => {
            const isCurrent = item.number === snap.current_number;
            const rowBg = isCurrent ? 'background:var(--danger); color:white' :
                item.status === '完成' ? 'background:var(--bg-elevated)' : '';
            const rowStyle = rowBg ? `style="${rowBg}"` : '';

            html += `
                            <tr ${rowStyle} style="border-bottom:1px solid var(--border-subtle)">
                                <td style="padding:12px; text-align:center; font-weight:600">${item.number}</td>
                                <td style="padding:12px; text-align:center">${item.status}</td>
                            </tr>
            `;
        });

        html += `
                        </tbody>
                    </table>
                </div>
            </div>
        `;

        document.getElementById('clinic-waiting-body').innerHTML = html;
    } catch (err) {
        console.error('Error loading waiting list:', err);
        document.getElementById('clinic-waiting-body').innerHTML =
            '<div class="empty-state"><p>載入失敗，請稍後重試</p></div>';
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
        // 🔴 FIX: Clear previous state when switching hospitals
        _currentHsDeptId = null;
        allDoctors = [];
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
        '<div class="empty-state"><div class="empty-icon">🏷️</div><p>請選擇科室類別，或輸入名稱搜尋全院</p></div>';
}

async function hsSelectCategory(hospId, hospName, cat) {
    document.querySelectorAll('#hs-category-chips .cat-chip').forEach(b =>
        b.classList.toggle('active', b.textContent === cat));
    _hsBreadcrumb([hospName, cat]);

    // Reset dept search when switching category
    const deptSearchEl = document.getElementById('dept-search');
    if (deptSearchEl) { deptSearchEl.value = ''; deptSearchEl.dataset.lastVal = ''; }

    // Reset doctor search
    const docSearchEl = document.getElementById('doctor-search');
    if (docSearchEl) { docSearchEl.value = ''; }

    // 🔴 FIX: Clear state when switching categories
    _currentHsDeptId = null;
    allDoctors = [];

    document.getElementById('doctors-grid').innerHTML = '<div class="spinner"></div>';
    const depts = await apiFetch(`/api/hospitals/${hospId}/departments?category=${encodeURIComponent(cat)}`) || [];
    _hsRenderDeptGrid(hospId, hospName, cat, depts);

    // Apply existing doctor/dept filters (if any) to the newly selected category
    filterHospitalSearch();
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
    _currentHsDeptId = null; // 🔴 FIX: Clear dept selection
    allDoctors = []; // 🔴 FIX: Clear doctors list when switching categories
    label.textContent = cat ? `${cat} — 請選擇科室` : '請選擇科室';
    grid.innerHTML = depts.length
        ? _hsDeptButtons(depts, hospName, cat)
        : '<div style="color:var(--text-muted);font-size:14px">此類別下無科室資料<\/div>';
    wrap.style.display = 'block';
    document.getElementById('doctors-grid').innerHTML =
        '<div class="empty-state"><div class="empty-icon">🏥</div><p>請選擇科室，或輸入醫師名稱搜尋</p></div>';
}

let _hsDeptAll = { depts: [], hospName: '', cat: '' };
let _currentHsDeptId = null;
let _doctorSearchTimer = null;

function filterHospitalSearch() {
    const dq = (document.getElementById('dept-search')?.value || '').toLowerCase().trim();
    const docq = (document.getElementById('doctor-search')?.value || '').toLowerCase().trim();
    const { depts, hospName, cat } = _hsDeptAll;

    const dsNode = document.getElementById('dept-search');
    const prevDq = dsNode?.dataset.lastVal || '';
    if (dq !== prevDq && dsNode) {
        _currentHsDeptId = null; // Unselect dept if user manually edits dept-search
        allDoctors = []; // 🔴 FIX: Clear doctors when dept is unselected
        dsNode.dataset.lastVal = dq;
    }

    if (!dq && cat) {
        document.getElementById('hs-dept-grid').innerHTML = _hsDeptButtons(depts, hospName, cat);
        document.getElementById('hs-dept-label').textContent = `${cat} — 請選擇科室`;
        document.getElementById('hs-dept-wrap').style.display = 'block';
    }
    else if (!dq && !cat && _hsHospitalId) {
        document.getElementById('hs-dept-wrap').style.display = 'none';
        document.getElementById('hs-category-wrap').style.display = 'block';
    }
    else if (_hsHospitalId && dq) {
        // If there's a search query, always search the whole hospital departments
        apiFetch(`/api/hospitals/${_hsHospitalId}/departments?q=${encodeURIComponent(dq)}`).then(results => {
            const deptWrap = document.getElementById('hs-dept-wrap');
            document.getElementById('hs-category-wrap').style.display = 'none';
            document.getElementById('hs-dept-label').textContent = `搜尋「${dq}」— 找到 ${(results || []).length} 個科室`;
            const html = (results || []).length
                ? (results || []).map(d =>
                    `<button class="dept-btn" onclick="hsSelectDeptFromSearch('${d.id}','${escHtml(d.name)}','${escHtml(hospName)}')">${escHtml(d.name)}</button>`
                ).join('')
                : '<div style="color:var(--text-muted);font-size:14px">找不到符合的科室</div>';
            document.getElementById('hs-dept-grid').innerHTML = html;
            deptWrap.style.display = 'block';
        });
    }

    clearTimeout(_doctorSearchTimer);
    _doctorSearchTimer = setTimeout(async () => {
        if (!_hsHospitalId) return;

        if (!docq && !_currentHsDeptId) {
            // Revert to empty state if no search text and no department selected
            allDoctors = []; // 🔴 FIX: Additional safeguard to clear doctors in empty state
            document.getElementById('doctors-grid').innerHTML =
                '<div class="empty-state"><div class="empty-icon">🏥</div><p>請選擇科室，或輸入醫師名稱搜尋</p></div>';
            return;
        } else if (!docq && _currentHsDeptId && allDoctors.length) {
            renderDoctorCards(allDoctors);
            return;
        }

        document.getElementById('doctors-grid').innerHTML = '<div class="spinner"></div>';
        try {
            let url = `/api/hospitals/${_hsHospitalId}/doctors`;
            const params = new URLSearchParams();
            if (docq) params.append('q', docq);
            if (_currentHsDeptId) params.append('department_id', _currentHsDeptId);

            if (params.toString()) url += `?${params.toString()}`;
            let docs = await apiFetch(url) || [];

            if (!_currentHsDeptId) {
                if (cat && _hsDeptAll.depts.length) {
                    const validIds = new Set(_hsDeptAll.depts.map(d => d.id));
                    docs = docs.filter(d => validIds.has(d.department_id));
                }
                if (dq) {
                    docs = docs.filter(d => (d.department_name || '').toLowerCase().includes(dq));
                }
            }

            renderDoctorCards(docs);
        } catch (e) {
            console.error('Doctor search error:', e);
            document.getElementById('doctors-grid').innerHTML = '<div class="empty-state"><p>載入失敗</p></div>';
        }
    }, 300);
}

function resetHospitalSearch() {
    const ds = document.getElementById('dept-search');
    const docs = document.getElementById('doctor-search');
    if (ds) { ds.value = ''; ds.dataset.lastVal = ''; }
    if (docs) docs.value = '';

    _currentHsDeptId = null;

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
    _currentHsDeptId = deptId;
    const docSearchEl = document.getElementById('doctor-search');
    const dsNode = document.getElementById('dept-search');
    if (docSearchEl) docSearchEl.value = '';
    if (dsNode) { dsNode.value = deptName; dsNode.dataset.lastVal = deptName.toLowerCase(); }
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
async function loadStepperHospitals() {
    const grid = document.getElementById('step1-hospital-grid');
    const hospitals = await apiFetch('/api/hospitals') || [];
    if (!hospitals.length) { grid.innerHTML = '<div class="empty-state"><p>無醫院資料</p></div>'; return; }
    grid.innerHTML = hospitals.map(h =>
        `<button class="dept-btn" onclick="stepperSelectHospital('${h.id}','${escHtml(h.name)}')">${escHtml(h.name)}</button>`
    ).join('');
}

async function stepperSelectHospital(hospId, hospName) {
    AppState.stepper.hospitalId = hospId;
    AppState.stepper.hospitalName = hospName;
    AppState.stepper.category = '';
    AppState.stepper.departmentId = '';
    AppState.stepper.departmentName = '';
    AppState.stepper.doctorId = '';
    AppState.stepper.doctorName = '';
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
    AppState.stepper.category = cat;
    document.querySelectorAll('#step2-category-chips .cat-chip').forEach(b =>
        b.classList.toggle('active', b.textContent === cat));
    const grid = document.getElementById('step2-dept-grid');
    grid.innerHTML = '<div class="spinner"></div>';
    const depts = await apiFetch(`/api/hospitals/${AppState.stepper.hospitalId}/departments?category=${encodeURIComponent(cat)}`) || [];
    grid.innerHTML = _stepperDeptButtons(depts);
    _stepperBreadcrumb();
}

function _stepperDeptButtons(depts) {
    return depts.length
        ? depts.map(d => `<button class="dept-btn" onclick="stepperSelectDept('${d.id}','${escHtml(d.name)}')">${escHtml(d.name)}</button>`).join('')
        : '<div style="color:var(--text-muted);font-size:14px">此類別無科室</div>';
}

async function stepperSelectDept(deptId, deptName) {
    AppState.stepper.deptId = deptId; AppState.stepper.deptName = deptName;
    document.getElementById('modal-dept').value = deptId;
    _stepperBreadcrumb();
    stepperGoTo(3);
    const docs = await apiFetch(`/api/departments/${deptId}/doctors`) || [];
    const grid = document.getElementById('step3-doctor-grid');
    grid.innerHTML = docs.length
        ? docs.map(d => `
            <div class="card">
              <div style="display:flex; justify-content:space-between; align-items:center; cursor:pointer" onclick="stepperSelectDoctor('${d.id}','${escHtml(d.name)}')">
                <div style="flex:1">
                  <div style="font-weight:600">👨‍⚕️ ${escHtml(d.name)}</div>
                  <div style="font-size:12px;color:var(--text-muted)">${escHtml(d.specialty || '')}</div>
                </div>
                <button class="btn btn-primary" onclick="event.stopPropagation(); quickTrack('${d.id}','${escHtml(d.name)}')" style="margin-left:12px; white-space:nowrap; padding:4px 8px; font-size:11px;">＋ 追蹤</button>
              </div>
            </div>`).join('')
        : '<div class="empty-state"><p>此科室無醫師</p></div>';
}

async function stepperSelectDoctor(docId, docName) {
    AppState.stepper.doctorId = docId; AppState.stepper.doctorName = docName;
    document.getElementById('modal-doctor').value = docId;
    _stepperBreadcrumb();

    // Show doctor detail (clinic schedule) in modal first
    await showDoctorDetail(docId, docName);
}

function stepperNextFromStep4() {
    const date = document.getElementById('modal-date').value;
    const session = document.getElementById('modal-session').value;

    console.log('[stepperNextFromStep4] 驗證表單', { date, session });

    if (!date) {
        toast('⚠️ 請選擇就診日期', 'warning');
        return;
    }
    if (!session) {
        toast('⚠️ 請選擇診次', 'warning');
        return;
    }

    // Build confirm summary
    const apptNum = document.getElementById('modal-appointment-number').value;
    const notify = [
        document.getElementById('notify-20').checked ? '前20號' : '',
        document.getElementById('notify-10').checked ? '前10號' : '',
        document.getElementById('notify-5').checked ? '前5號' : ''
    ].filter(Boolean).join('、');

    const hName = AppState.stepper.hospitalName || '（未知醫院）';
    const dName = AppState.stepper.deptName || '（未知科室）';
    const docName = AppState.stepper.doctorName || '（未知醫師）';

    console.log('[stepperNextFromStep4] 準備進入 Step 5', { hName, dName, docName, date, session });

    document.getElementById('confirm-summary').innerHTML = `
      <div>🏥 <b>醫院：</b>${escHtml(hName)}</div>
      ${AppState.stepper.cat ? `<div>🏷️ <b>類別：</b>${escHtml(AppState.stepper.cat)}</div>` : ''}
      <div>🩺 <b>科室：</b>${escHtml(dName)}</div>
      <div>👨‍⚕️ <b>醫師：</b>${escHtml(docName)}</div>
      <div>📅 <b>日期：</b>${date} ${session}診</div>
      ${apptNum ? `<div>🎫 <b>掛號號碼：</b>${apptNum} 號</div>` : ''}
      <div>🔔 <b>通知門檻：</b>${notify || '（未設定）'}</div>
    `;
    stepperGoTo(5);
}

function stepperGoTo(step) {
    AppState.stepper.step = step;
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

    // Show/hide back button (hide on first step)
    const backBtn = document.getElementById('stepper-back-btn');
    if (backBtn) {
        backBtn.style.display = step > 1 ? '' : 'none';
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function stepperPrevious() {
    if (AppState.stepper.step > 1) {
        // Handle cleanup based on current step
        if (AppState.stepper.step === 3) {
            // Going back from doctor selection
            AppState.stepper.doctorId = '';
            AppState.stepper.doctorName = '';
        } else if (AppState.stepper.step === 4) {
            // Going back from date/settings
            document.getElementById('modal-date').value = '';
            document.getElementById('modal-session').value = '';
            document.getElementById('modal-appointment-number').value = '';
        }
        stepperGoTo(AppState.stepper.step - 1);
    }
}

function _stepperBreadcrumb() {
    const parts = [AppState.stepper.hospitalName, AppState.stepper.category, AppState.stepper.departmentName, AppState.stepper.doctorName].filter(Boolean);
    const el = document.getElementById('stepper-breadcrumb');
    el.innerHTML = parts.map((p, i) => i < parts.length - 1
        ? `<span class="bc-link">${escHtml(p)}</span><span class="bc-sep">›</span>`
        : `<span class="bc-cur">${escHtml(p)}</span>`).join('');
}

function cancelAddTracking() {
    console.log('[cancelAddTracking] 關閉追蹤表單，返回追蹤列表');
    // 重置表單狀態
    Object.assign(AppState.stepper, { step: 1, hospitalId: '', hospitalName: '', cat: '', deptId: '', deptName: '', doctorId: '', doctorName: '' });
    // 導航回追蹤頁面
    navigate(document.querySelector('[data-page=tracking]'), 'tracking');
}

async function quickTrack(doctorId, doctorName) {
    // Fetch doctor info
    const info = await apiFetch(`/api/doctors/${doctorId}/info`);
    if (!info) {
        toast('無法獲取醫生信息', 'error');
        return;
    }

    // If we're in the Add Tracking stepper (Step 3), go to Step 4
    if (AppState.stepper && AppState.stepper.step === 3) {
        console.log('[quickTrack] Stepper mode detected, going to Step 4');
        AppState.stepper.doctorId = doctorId;
        AppState.stepper.doctorName = doctorName;
        AppState.stepper.hospitalId = info.hospital_id;
        AppState.stepper.hospitalName = info.hospital_name;
        AppState.stepper.departmentId = info.department_id;
        AppState.stepper.departmentName = info.department_name;

        document.getElementById('modal-doctor').value = doctorId;
        document.getElementById('modal-dept').value = info.department_id;

        _stepperBreadcrumb();
        await loadModalSchedules(); // Load Step 4 schedules
        stepperGoTo(4);
        return;
    }

    // Otherwise, open standalone Quick Track modal
    const qtState = {
        doctorId: doctorId,
        doctorName: doctorName,
        hospitalId: info.hospital_id,
        hospitalName: info.hospital_name,
        departmentId: info.department_id,
        departmentName: info.department_name
    };
    openQuickTrackModal(qtState);
}

// ── Quick Track Modal ────────────────────────────────────────
let _qtState = null;
let _qtSchedules = [];

async function openQuickTrackModal(qtState) {
    _qtState = qtState;

    // Update modal header and doctor info
    document.getElementById('quick-track-title').textContent = `快速追蹤 - ${escHtml(qtState.doctorName)}`;
    document.getElementById('qt-doctor-name').textContent = escHtml(qtState.doctorName);
    document.getElementById('qt-hospital-dept').textContent = `${escHtml(qtState.hospitalName)} / ${escHtml(qtState.departmentName || '—')}`;

    // Reset form
    document.getElementById('qt-date').value = '';
    document.getElementById('qt-session').value = '';
    document.getElementById('qt-appointment-number').value = '';
    document.getElementById('qt-notify-20').checked = true;
    document.getElementById('qt-notify-10').checked = true;
    document.getElementById('qt-notify-5').checked = true;
    document.getElementById('qt-notify-email').checked = true;
    document.getElementById('qt-notify-line').checked = true;

    // Load schedules
    document.getElementById('qt-date').innerHTML = '<option value="">— 載入中… —</option>';
    document.getElementById('qt-date').disabled = true;
    await loadQuickTrackSchedules();

    // Show modal
    document.getElementById('quick-track-modal').classList.add('open');
}

function closeQuickTrackModal() {
    document.getElementById('quick-track-modal').classList.remove('open');
    _qtState = null;
    _qtSchedules = [];
}

async function loadQuickTrackSchedules() {
    if (!_qtState?.doctorId) return;

    const dateSel = document.getElementById('qt-date');
    const sessionSel = document.getElementById('qt-session');

    _qtSchedules = await apiFetch(`/api/doctors/${_qtState.doctorId}/schedules`) || [];

    if (!_qtSchedules.length) {
        dateSel.innerHTML = '<option value="">— 尚無門診資料 —</option>';
        dateSel.disabled = true;
        return;
    }

    const dates = [...new Set(_qtSchedules.map(s => s.session_date))];
    dateSel.innerHTML = '<option value="">— 選擇就診日期 —</option>' +
        dates.map(d => {
            const label = new Date(d + 'T00:00:00').toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric', weekday: 'short' });
            return `<option value="${d}">${label}</option>`;
        }).join('');
    dateSel.disabled = false;
    dateSel.onchange = loadQuickTrackSessions;
}

function loadQuickTrackSessions() {
    const date = document.getElementById('qt-date').value;
    const sessionSel = document.getElementById('qt-session');
    sessionSel.innerHTML = '<option value="">— 選擇診次 —</option>';
    sessionSel.disabled = true;
    if (!date) return;

    const sessions = _qtSchedules
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

async function submitQuickTrack() {
    const date = document.getElementById('qt-date').value;
    const session = document.getElementById('qt-session').value;

    if (!date) {
        toast('請選擇就診日期', 'warning');
        return;
    }
    if (!session) {
        toast('請選擇診次', 'warning');
        return;
    }

    const apptNum = document.getElementById('qt-appointment-number').value;
    const notify = {
        notify_20: document.getElementById('qt-notify-20').checked,
        notify_10: document.getElementById('qt-notify-10').checked,
        notify_5: document.getElementById('qt-notify-5').checked,
        notify_email: document.getElementById('qt-notify-email').checked,
        notify_line: document.getElementById('qt-notify-line').checked
    };

    // Prepare payload
    const payload = {
        doctor_id: _qtState.doctorId,
        department_id: _qtState.departmentId,
        session_date: date,
        session_type: session,
        appointment_number: apptNum ? parseInt(apptNum) : null,
        notify_at_20: notify.notify_20,
        notify_at_10: notify.notify_10,
        notify_at_5: notify.notify_5,
        notify_email: notify.notify_email,
        notify_line: notify.notify_line,
    };

    try {
        const result = await apiFetch('/api/tracking/', { method: 'POST', body: JSON.stringify(payload) });
        console.log('Tracking response:', result);
        const doctorName = _qtState.doctorName;
        closeQuickTrackModal();
        toast(`成功追蹤 ${escHtml(doctorName)} 的門診`, 'success');
        // Refresh tracking list if on tracking page
        const trackingPage = document.querySelector('[data-page="tracking"]');
        if (trackingPage?.classList.contains('active')) {
            loadTracking();
        }
    } catch (e) {
        console.error('Error creating tracking:', e);
        console.error('Stack:', e.stack);
        // Check for duplicate subscription error (409 Conflict)
        if (e.message && e.message.includes('此門診已在您的追蹤列表中')) {
            toast('此門診已在您的追蹤列表中', 'warning');
        } else {
            toast('追蹤失敗，請重試', 'error');
        }
    }
}

// Keep as noop stubs so old call-sites don't crash
function openTrackingModal() { openAddTracking(); }
function closeTrackingModal() { cancelAddTracking(); }

async function loadModalSchedules() {
    let docId = document.getElementById('modal-doctor').value;
    // 🔴 FIX: Fallback to AppState.stepper.doctorId if element value is empty
    if (!docId && AppState.stepper.doctorId) {
        docId = AppState.stepper.doctorId;
        document.getElementById('modal-doctor').value = docId;
    }

    const dateSel = document.getElementById('modal-date');
    const sessionSel = document.getElementById('modal-session');
    dateSel.innerHTML = '<option value="">— 載入中… —</option>';
    dateSel.disabled = true;
    sessionSel.innerHTML = '<option value="">— 請先選擇日期 —</option>';
    sessionSel.disabled = true;
    if (!docId) return;

    AppState.stepper.doctorSchedules = await apiFetch(`/api/doctors/${docId}/schedules`) || [];

    if (!AppState.stepper.doctorSchedules.length) {
        dateSel.innerHTML = '<option value="">— 尚無門診資料 —</option>';
        return;
    }

    const dates = [...new Set(AppState.stepper.doctorSchedules.map(s => s.session_date))];
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
    const sessions = AppState.stepper.doctorSchedules
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

    const snaps = await apiFetch(`/api/doctors/${doctorId}/snapshots?limit=50`) || [];
    if (!snaps.length) {
        document.getElementById('doctor-modal-body').innerHTML =
            `<div class="empty-state"><div class="empty-icon">📊</div><p>尚無門診資料</p></div>`;
        return;
    }

    const sessionOrder = { "上午": 1, "下午": 2, "晚上": 3 };
    snaps.sort((a, b) => {
        if (a.session_date !== b.session_date) {
            return a.session_date.localeCompare(b.session_date);
        }
        return (sessionOrder[a.session_type] || 99) - (sessionOrder[b.session_type] || 99);
    });

    // Check if we're in stepper mode (adding tracking) or just viewing
    // Show action buttons only if in stepper step 3 (doctor selection)
    const isInStepper = AppState.stepper && AppState.stepper.step === 3;
    const actionButtons = isInStepper
        ? `<div style="display:flex; gap:8px; margin-top:16px; padding-top:16px; border-top:1px solid var(--border-subtle)">
             <button class="btn btn-secondary" onclick="document.getElementById('doctor-modal').classList.remove('open'); stepperGoTo(3)" style="flex:1">取消</button>
             <button class="btn btn-primary" onclick="document.getElementById('doctor-modal').classList.remove('open'); quickTrack('${doctorId}','${escHtml(name)}')" style="flex:1">下一步：設定追蹤日期</button>
           </div>`
        : '';

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
    </div>
    ${actionButtons}`;
}



// ── Tracking list ─────────────────────────────────────────────
let _allTrackingSubs = [];
let _currentTrackingTab = 'current';

async function loadTracking() {
    const subs = await apiFetch('/api/tracking/') || [];
    _allTrackingSubs = subs;

    // Load notification logs to determine which notifications were actually sent
    const logs = await apiFetch('/api/tracking/logs/all').catch(() => []) || [];

    // Build index: sub_id -> {threshold -> [log records]}
    _notificationLogsBySubscription = {};
    for (const log of logs) {
        const subId = log.subscription_id;
        const threshold = log.threshold;
        if (!_notificationLogsBySubscription[subId]) {
            _notificationLogsBySubscription[subId] = {};
        }
        if (!_notificationLogsBySubscription[subId][threshold]) {
            _notificationLogsBySubscription[subId][threshold] = [];
        }
        _notificationLogsBySubscription[subId][threshold].push(log);
    }

    renderTrackingList();
}

function switchTrackingTab(tab) {
    _currentTrackingTab = tab;
    document.getElementById('btn-tab-tracking-current').className = tab === 'current' ? 'btn btn-primary' : 'btn btn-secondary';
    document.getElementById('btn-tab-tracking-past').className = tab === 'past' ? 'btn btn-primary' : 'btn btn-secondary';
    renderTrackingList();
}

function renderTrackingList() {
    const list = document.getElementById('tracking-list');

    if (!_allTrackingSubs.length) {
        list.innerHTML = `<div class="empty-state" style="grid-column:1/-1">
      <div class="empty-icon">🔔</div>
      <p>尚無追蹤設定<br><button class="btn btn-primary" onclick="openTrackingModal()" style="margin-top:12px">新增追蹤</button></p>
    </div>`;
        return;
    }

    const todayStr = new Date().toLocaleString('sv-SE', { timeZone: 'Asia/Taipei' }).substring(0, 10);

    let subs;
    if (_currentTrackingTab === 'current') {
        subs = _allTrackingSubs.filter(s => (s.session_date || '') >= todayStr);
    } else {
        subs = _allTrackingSubs.filter(s => (s.session_date || '') < todayStr);
    }

    const isExpiredTab = _currentTrackingTab === 'past';

    if (!subs.length) {
        list.innerHTML = `<div class="empty-state" style="grid-column:1/-1">
      <div class="empty-icon">${isExpiredTab ? '📁' : '🔔'}</div>
      <p>${isExpiredTab ? '目前沒有過去的追蹤紀錄' : '目前沒有進行中的追蹤<br><button class="btn btn-primary" onclick="openTrackingModal()" style="margin-top:12px">新增追蹤</button>'}</p>
    </div>`;
        return;
    }

    list.innerHTML = subs.map(s => renderTrackingCard(s, isExpiredTab)).join('');
}

function renderTrackingCard(sub, isExpired = false) {
    console.log('renderTrackingCard data - sub room:', sub.clinic_room);

    // Helper to check if notification was actually sent (has success log)
    const hasSuccessfulNotification = (threshold) => {
        if (!_notificationLogsBySubscription || !sub.id) return false;
        const logs = _notificationLogsBySubscription[sub.id]?.[threshold] || [];
        return logs.some(log => log.success === true);
    };

    const pill = (on, notified, label, threshold) => {
        if (!on) return '';

        // Check if actually sent (successful log exists)
        if (hasSuccessfulNotification(threshold)) {
            return `<span class="threshold-pill done">✅${label}</span>`;
        }

        // If marked notified but no successful log, it was skipped
        if (notified) {
            return `<span class="threshold-pill skipped">⏸️${label}</span>`;
        }

        // Otherwise pending
        return `<span class="threshold-pill pending">⏳${label}</span>`;
    };
    const email = sub.notify_email ? '📧 Email' : '';
    const line = sub.notify_line ? '📲 LINE' : '';

    const docName = sub.doctor_name || sub.doctor_id?.slice(0, 8) || '未知';
    const dept = sub.department_name || '';
    const hospital = sub.hospital_name || '';
    const sessionLabel = [sub.session_date, sub.session_type ? sub.session_type + '診' : ''].filter(Boolean).join(' ');
    const apptNo = sub.appointment_number ? `${sub.appointment_number}` : '<span style="opacity:0.6">(未填寫)</span>';

    const emailDisplay = sub.notify_email && AppState.currentUser?.email ? `📧 Email (${AppState.currentUser.email})` : (sub.notify_email ? '📧 Email' : '');
    if (sub.notify_email) {
        console.log('[renderTrackingCard] emailDisplay result:', emailDisplay, 'currentUser:', AppState.currentUser);
    }
    const lineDisplay = sub.notify_line ? '📲 LINE' : '';

    const expiredClass = isExpired ? 'expired' : (sub.is_active ? '' : 'inactive');

    // Handle quota logic with fallback
    const total_quota = sub.total_quota != null ? sub.total_quota : '?';
    const current_registered = sub.current_registered != null ? sub.current_registered : '?';
    const hasBoth = total_quota !== '?' && current_registered !== '?';
    let quotaHtml = '';

    if (hasBoth) {
        quotaHtml = `<div style="font-size:12px; color:var(--text); margin-top:2px">📊 ${current_registered} 已掛號 / ${total_quota} 總號</div>`;
    } else if (total_quota !== '?') {
        quotaHtml = `<div style="font-size:12px; color:var(--text); margin-top:2px">📊 ${total_quota} 總號</div>`;
    } else if (current_registered !== '?') {
        quotaHtml = `<div style="font-size:12px; color:var(--text); margin-top:2px">📊 ${current_registered} 已掛號</div>`;
    }

    return `
  <div class="tracking-card ${expiredClass}" id="sub-${sub.id}">
    <div class="tc-header">
      <div>
        <div style="font-weight:600; font-size:15px">👩‍⚕️ ${escHtml(docName)}</div>
        ${(hospital || dept) ? `<div style="font-size:12px; color:var(--accent); margin-top:2px">🏥 ${escHtml(hospital)} ${dept ? '｜' + escHtml(dept) : ''}</div>` : ''}
        <div style="font-size:13px; color:var(--text-muted); margin-top:4px">📅 ${sessionLabel}${sub.clinic_room ? ` ｜ 🚪 診間：${escHtml(sub.clinic_room)}診` : ''}</div>
        <div style="font-size:12px; color:var(--text-muted)">🎫 我的號碼：${apptNo}</div>
        ${quotaHtml}
        ${sub.current_number ? `<div style="font-size:12px; color:var(--primary); font-weight:bold; margin-top:2px">🔔 目前看診號碼：${sub.current_number}</div>` : ''}
        <div style="font-size:12px; color:var(--text-dim); margin-top:2px">${emailDisplay} ${lineDisplay}</div>
      </div>
      ${isExpired ? '' : `<div class="tc-actions">
        <button class="btn btn-secondary btn-sm" onclick="toggleSubActive('${sub.id}', ${!sub.is_active})">
          ${sub.is_active ? '暫停' : '啟用'}
        </button>
        <button class="btn btn-danger btn-sm" onclick="deleteSub('${sub.id}')">刪除</button>
      </div>`}
    </div>
    <div class="threshold-pills">
      ${pill(sub.notify_at_20, sub.notified_20, '前20', 20)}
      ${pill(sub.notify_at_10, sub.notified_10, '前10', 10)}
      ${pill(sub.notify_at_5, sub.notified_5, '前5', 5)}
    </div>
  </div>`;
}

async function toggleSubActive(subId, isActive) {
    try {
        await apiFetch(`/api/tracking/${subId}`, {
            method: 'PATCH',
            body: JSON.stringify({ is_active: isActive })
        });
        toast(isActive ? '已恢復追蹤' : '已暫停追蹤', 'success');
        setTimeout(() => loadTracking(), 300);
    } catch (e) {
        toast('操作失敗', 'error');
    }
}

async function deleteSub(subId) {
    if (!confirm('確定要刪除這筆追蹤紀錄嗎？')) return;
    try {
        await apiFetch(`/api/tracking/${subId}`, { method: 'DELETE' });
        toast('已刪除紀錄', 'success');
        // 同時更新追蹤清列和儀表板
        setTimeout(() => {
            loadTracking();
            loadDashboard();
        }, 300);
    } catch (e) {
        toast('刪除失敗', 'error');
    }
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
    const originalBtnText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '新增中…';

    const apptNumValue = document.getElementById('modal-appointment-number').value;
    const apptNum = apptNumValue ? parseInt(apptNumValue, 10) : null;

    try {
        console.log('[submitTracking] 正在提交追蹤', {
            doctor_id: docId,
            session_date: sessionDate,
            session_type: sessionType,
        });

        const result = await apiPost('/api/tracking/', {
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

        console.log('[submitTracking] 提交成功', result);
        toast('✅ 追蹤已新增！', 'success');

        // 延遲後重置表單並返回第一步，讓用戶看到成功訊息
        setTimeout(() => {
            // 重置追蹤表單狀態
            Object.assign(AppState.stepper, { step: 1, hospitalId: '', hospitalName: '', cat: '', deptId: '', deptName: '', doctorId: '', doctorName: '' });
            // 重置表單輸入
            document.getElementById('modal-date').value = '';
            document.getElementById('modal-session').value = '';
            document.getElementById('modal-appointment-number').value = '';
            // 返回第一步
            stepperGoTo(1);
            document.getElementById('stepper-breadcrumb').innerHTML = '';
            loadStepperHospitals();
            loadTracking();
        }, 500);
    } catch (e) {
        console.error('[submitTracking] 提交失敗', e);
        toast('❌ 新增失敗：' + e.message, 'error');
    }
    finally {
        btn.disabled = false;
        btn.textContent = originalBtnText;
    }
}

// ── Notifications ─────────────────────────────────────────────


let _allNotificationLogs = [];
let _currentNotifTab = 'current';

async function loadNotifications() {
    const tbody = document.getElementById('notif-table-body');
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--text-muted)"><div class="spinner"></div></td></tr>`;

    console.log('[Notifications] Starting to load notification logs...');
    const startTime = performance.now();

    // Always fetch from the new endpoint
    const logs = await apiFetch('/api/tracking/logs/all').catch(() => []) || [];
    const endTime = performance.now();
    console.log(`[Notifications] Loaded ${logs.length} logs in ${(endTime - startTime).toFixed(0)}ms`);

    _allNotificationLogs = logs;

    // Sort globally by sent_at descending
    _allNotificationLogs.sort((a, b) => new Date(b.sent_at) - new Date(a.sent_at));

    renderNotificationTable();
}

function switchNotifTab(tab) {
    _currentNotifTab = tab;

    // Update button styles
    document.getElementById('btn-tab-notif-current').className = tab === 'current' ? 'btn btn-primary' : 'btn btn-secondary';
    document.getElementById('btn-tab-notif-past').className = tab === 'past' ? 'btn btn-primary' : 'btn btn-secondary';

    renderNotificationTable();
}

function renderNotificationTable() {
    const tbody = document.getElementById('notif-table-body');

    if (!_allNotificationLogs.length) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--text-muted)">尚無通知紀錄</td></tr>`;
        return;
    }

    // Determine the boundary date: today string like 'YYYY-MM-DD'
    const todayStr = new Date().toLocaleString('sv-SE', { timeZone: 'Asia/Taipei' }).substring(0, 10);

    const filteredLogs = _allNotificationLogs.filter(l => {
        const sessionDate = l.session_date || '1970-01-01'; // Fallback
        if (_currentNotifTab === 'current') {
            return sessionDate >= todayStr;
        } else {
            return sessionDate < todayStr;
        }
    });

    if (!filteredLogs.length) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--text-muted)">此分類下尚無紀錄</td></tr>`;
        return;
    }

    tbody.innerHTML = filteredLogs.map(l => `
    <tr>
      <td style="color:var(--text-muted); font-size:13px">${new Date(l.sent_at).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' })}</td>
      <td>
        <div style="font-weight:bold">${l.hospital_name ? escHtml(l.hospital_name) : '—'}</div>
        <div style="font-size:12px;color:var(--text-muted)">${l.department_name ? escHtml(l.department_name) : '—'}</div>
        <div style="font-size:12px;color:var(--text-muted)">${l.session_date || ''} ${l.session_type || ''}</div>
      </td>
      <td>
        <div style="font-weight:bold">${l.doctor_name ? escHtml(l.doctor_name) : '—'}</div>
        <div style="font-size:12px;color:var(--text-muted)">診間: ${l.clinic_room ? escHtml(l.clinic_room) : '—'}</div>
      </td>
      <td><span style="font-size:16px;font-weight:bold;color:var(--primary)">${l.current_number || '—'}</span></td>
      <td><span class="badge badge-warning">前 ${l.threshold} 號</span></td>
      <td>${l.channel === 'email' ? '📧 Email' : '📲 LINE'}</td>
      <td>${l.success
            ? '<span class="badge badge-success">成功</span>'
            : '<span class="badge badge-danger">失敗</span><br><span style="font-size:11px;color:var(--danger)">' + (l.error_message ? escHtml(l.error_message) : '') + '</span>'}
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



async function loadProfile() {
    console.log('[loadProfile] loading...');
    const profile = await apiFetch('/api/users/me');
    console.log('[loadProfile] fetched profile:', profile);
    if (profile) {
        currentUser = profile;
        AppState.currentUser = profile;
        const nameEl = document.getElementById('profile-name');
        const emailEl = document.getElementById('profile-email');

        if (nameEl) nameEl.value = profile.display_name || '';
        if (emailEl) emailEl.value = profile.email || '（未提供）';

        // Start polling to detect when user scans QR code
        startLineConnectionPolling();
    }
}

let _linePollingTimer = null;

function startLineConnectionPolling() {
    // Stop any existing polling
    if (_linePollingTimer) clearInterval(_linePollingTimer);

    // If already linked, don't poll
    if (currentUser && currentUser.line_user_id) return;

    // Poll every 3 seconds to check for pending LINE connection
    _linePollingTimer = setInterval(async () => {
        try {
            const result = await apiPost('/api/users/link-line', {});
            if (result && result.status === 'linked') {
                console.log('[LINE] Successfully linked:', result.line_user_id);
                // Refresh profile
                const profile = await apiFetch('/api/users/me');
                currentUser = profile;
                AppState.currentUser = profile;
                toast('✓ LINE 連接成功！', 'success');
                // Stop polling
                clearInterval(_linePollingTimer);
                _linePollingTimer = null;
            }
        } catch (e) {
            // Polling error, continue silently
        }
    }, 3000);
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
        const isSelf = AppState.currentUser && u.id === AppState.currentUser.id;
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
        // 初始化 QR Code 容器 - 登入頁面默認顯示
        const qrContainer = document.getElementById('line-qr-container');
        if (qrContainer) {
            qrContainer.style.display = 'block';
        }
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

// ── Admin Tabs & Tracking Management ────────────────────────
function switchAdminTab(tabId) {
    // hide all tabs
    document.querySelectorAll('.admin-tab-content').forEach(el => el.style.display = 'none');
    // reset button styles
    document.querySelectorAll('.hs-tabs button').forEach(btn => {
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-secondary');
    });

    // show selected tab
    document.getElementById(`admin-tab-${tabId}`).style.display = 'block';

    // highlight selected button
    const btn = document.getElementById(`admin-tab-btn-${tabId}`);
    if (btn) {
        btn.classList.remove('btn-secondary');
        btn.classList.add('btn-primary');
    }

    // load data for selected tab
    if (tabId === 'users') {
        loadAdminUsers();
    } else if (tabId === 'tracking') {
        loadAdminTracking();
    } else if (tabId === 'system') {
        loadSchedulerStatus();
        loadServerLogs();
    }
}

async function loadAdminTracking() {
    const tbody = document.getElementById('admin-tracking-tbody');
    try {
        tbody.innerHTML = '<tr><td colspan="7" style="padding:20px; text-align:center; color:var(--text-muted)">載入中…</td></tr>';
        const trackings = await apiFetch('/api/admin/tracking');
        if (!trackings || trackings.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="padding:20px; text-align:center; color:var(--text-muted)">目前沒有任何追蹤紀錄。</td></tr>';
            return;
        }

        let html = '';
        for (const t of trackings) {
            const userName = t.user_name ? `${t.user_name} (${t.user_email})` : t.user_email;

            const notifyArr = [];
            if (t.notify_at_20) notifyArr.push('20');
            if (t.notify_at_10) notifyArr.push('10');
            if (t.notify_at_5) notifyArr.push('5');
            const methods = [];
            if (t.notify_email) methods.push('Email');
            if (t.notify_line) methods.push('LINE');

            const notifyStr = `剩 ${notifyArr.join(',')} 號<br><small style="color:var(--text-muted)">${methods.join(', ')}</small>`;

            const statusStr = t.is_active ?
                '<span style="color:var(--success)">✅ 追蹤中</span>' :
                '<span style="color:var(--text-muted)">⏸ 已結束</span>';

            html += `
                <tr style="border-bottom:1px solid var(--border)">
                    <td style="padding:10px 12px">${userName}</td>
                    <td style="padding:10px 12px">${t.session_date}<br><small style="color:var(--text-muted)">${t.session_type || ''}</small></td>
                    <td style="padding:10px 12px">${t.hospital_name || '（未知）'}<br><small style="color:var(--text-muted)">${t.department_name || '（未知）'}</small></td>
                    <td style="padding:10px 12px">${t.doctor_name}<br><small style="color:var(--text-muted)">我的號碼: ${t.appointment_number || '<span style="opacity:0.6">(未填寫)</span>'}</small></td>
                    <td style="padding:10px 12px">${notifyStr}</td>
                    <td style="padding:10px 12px">${statusStr}</td>
                    <td style="padding:10px 12px">
                        <button class="btn btn-secondary btn-sm" style="color:var(--danger)" onclick="deleteAdminTracking('${t.id}')">🗑 刪除</button>
                    </td>
                </tr>
            `;
        }
        tbody.innerHTML = html;
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" style="padding:20px; text-align:center; color:var(--danger)">載入失敗: ${e.message}</td></tr>`;
        toast(e.message, 'error');
    }
}

async function deleteAdminTracking(id) {
    if (!confirm('確定要刪除這筆追蹤紀錄嗎？此操作不可逆。')) return;
    try {
        await apiDelete(`/api/admin/tracking/${id}`);
        toast('追蹤紀錄已刪除', 'success');
        loadAdminTracking();
    } catch (e) {
        toast(e.message, 'error');
    }
}

/* ── Chart Analysis ─────────────────────────────────────────── */

async function switchAnalysisSheet(sheetId) {
    document.querySelectorAll('.analysis-tab-content').forEach(el => el.style.display = 'none');
    document.querySelectorAll('#page-analysis .hs-tabs button').forEach(btn => {
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-secondary');
    });

    document.getElementById(`analysis-${sheetId}`).style.display = 'block';
    const btn = document.getElementById(`btn-tab-${sheetId}`);
    if (btn) {
        btn.classList.remove('btn-secondary');
        btn.classList.add('btn-primary');
    }

    if (sheetId === 'sheet1') {
        loadAnalysisHospitals('analysis-sheet1-hosp-select', true);
        loadAnalysisCategories('analysis-sheet1-cat-select');
        loadDeptComparison();
    } else if (sheetId === 'sheet2') {
        loadAnalysisHospitals('analysis-sheet2-hosp-select');
        loadAnalysisCategories('analysis-sheet2-cat-select');
        refreshDoctorComparison();
    } else if (sheetId === 'sheet3') {
        loadAnalysisHospitals('rank-hosp-filter', true);
        loadRankingTable();
    } else if (sheetId === 'sheet4') {
        loadAnalysisHospitals('analysis-sheet4-hosp-select', true);
        loadAnalysisCategories('analysis-sheet4-cat-select');
        loadDoctorSpeedAnalysis();
    }
}

async function loadDeptComparison() {
    const ctx = document.getElementById('dept-comparison-chart');
    if (!ctx) return;

    const hospId = document.getElementById('analysis-sheet1-hosp-select')?.value || '';
    const cat = document.getElementById('analysis-sheet1-cat-select')?.value || '';

    try {
        const stats = await apiFetch(`/api/stats/dept-comparison?hospital_id=${hospId}&category=${encodeURIComponent(cat)}`);
        if (!stats) return;

        if (AppState.charts.deptComparisonChart) AppState.charts.deptComparisonChart.destroy();
        AppState.charts.deptComparisonChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: stats.labels,
                datasets: [{
                    label: '各科室平均看診人數',
                    data: stats.data,
                    backgroundColor: 'rgba(59, 130, 246, 0.7)',
                    borderColor: 'rgb(59, 130, 246)',
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: {
                        beginAtZero: true,
                        title: { display: true, text: '平均掛號人數 (人)' }
                    }
                }
            }
        });
    } catch (e) { toast(e.message, 'error'); }
}

async function loadAnalysisCategories(selectId) {
    const select = document.getElementById(selectId);
    if (!select || select.dataset.loaded === '1') return;

    try {
        const cats = await apiFetch('/api/stats/categories') || [];
        let html = '<option value="">所有類別</option>';
        html += cats.map(c => `<option value="${c}">${c}</option>`).join('');
        select.innerHTML = html;
        select.dataset.loaded = '1';
    } catch (e) { console.error('Load categories failed', e); }
}

async function loadAnalysisHospitals(selectId, includeAll = false) {
    const select = document.getElementById(selectId);
    if (select.dataset.loaded === '1') return;

    try {
        const hosps = await apiFetch('/api/hospitals') || [];
        let html = includeAll ? '<option value="">所有醫院</option>' : '<option value="">請選擇醫院…</option>';
        html += hosps.map(h => `<option value="${h.id}">${h.name}</option>`).join('');
        select.innerHTML = html;
        select.dataset.loaded = '1';
    } catch (e) { toast(e.message, 'error'); }
}

async function loadAnalysisDepts(hospSelectId, catSelectId, deptSelectId) {
    const hSelect = document.getElementById(hospSelectId || 'analysis-sheet2-hosp-select');
    const cSelect = document.getElementById(catSelectId || 'analysis-sheet2-cat-select');
    const dSelect = document.getElementById(deptSelectId || 'analysis-sheet2-dept-select');
    if (!hSelect || !dSelect) return;

    const hospId = hSelect.value;
    const cat = cSelect?.value || '';
    if (!hospId) {
        dSelect.innerHTML = '<option value="">所有科室</option>';
        return;
    }

    try {
        let url = `/api/hospitals/${hospId}/departments`;
        if (cat) url += `?category=${encodeURIComponent(cat)}`;
        const depts = await apiFetch(url) || [];
        dSelect.innerHTML = '<option value="">所有科室</option>' +
            depts.map(d => `<option value="${d.id}">${d.name}</option>`).join('');
    } catch (e) { toast(e.message, 'error'); }
}

async function refreshDoctorComparison() {
    const hospId = document.getElementById('analysis-sheet2-hosp-select').value;
    const cat = document.getElementById('analysis-sheet2-cat-select').value;
    const deptId = document.getElementById('analysis-sheet2-dept-select').value;
    const ctx = document.getElementById('doctor-comparison-chart');
    if (!ctx) return;

    try {
        let url = `/api/stats/doctor-comparison?`;
        if (hospId) url += `hospital_id=${hospId}&`;
        if (deptId) url += `dept_id=${deptId}&`;
        if (cat) url += `category=${encodeURIComponent(cat)}`;

        const stats = await apiFetch(url);
        if (!stats) return;

        if (AppState.charts.doctorComparisonChart) AppState.charts.doctorComparisonChart.destroy();
        AppState.charts.doctorComparisonChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: stats.labels,
                datasets: [{
                    label: '平均看診人數',
                    data: stats.data,
                    backgroundColor: 'rgba(16, 185, 129, 0.7)',
                    borderColor: 'rgb(16, 185, 129)',
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: { y: { beginAtZero: true } }
            }
        });
    } catch (e) { toast(e.message, 'error'); }
}

async function loadDoctorSpeedAnalysis() {
    const ctx = document.getElementById('doctor-speed-chart');
    if (!ctx) return;

    const hospId = document.getElementById('analysis-sheet4-hosp-select').value;
    const cat = document.getElementById('analysis-sheet4-cat-select').value;
    const deptId = document.getElementById('analysis-sheet4-dept-select')?.value || '';

    try {
        let url = `/api/stats/doctor-speed?`;
        if (hospId) url += `hospital_id=${hospId}&`;
        if (cat) url += `category=${encodeURIComponent(cat)}&`;
        if (deptId) url += `dept_id=${deptId}`;

        const stats = await apiFetch(url);
        if (!stats) return;

        if (AppState.charts.doctorSpeedChart) AppState.charts.doctorSpeedChart.destroy();
        AppState.charts.doctorSpeedChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: stats.labels,
                datasets: [{
                    label: '看診速度 (人/小時)',
                    data: stats.data,
                    backgroundColor: 'rgba(245, 158, 11, 0.7)',
                    borderColor: 'rgb(245, 158, 11)',
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: {
                        beginAtZero: true,
                        title: { display: true, text: '平均每小時看診人數 (人/小時)' }
                    }
                }
            }
        });
    } catch (e) { toast(e.message, 'error'); }
}

async function loadRankingTable() {
    const tbody = document.getElementById('ranking-table-body');
    try {
        AppState.analysis.ranking = await apiFetch('/api/stats/dept-ranking') || [];
        renderRankingTable(AppState.analysis.ranking);
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--danger)">載入失敗: ${e.message}</td></tr>`;
    }
}

function renderRankingTable(data) {
    const tbody = document.getElementById('ranking-table-body');
    if (!data.length) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:32px;">目前無統計數據</td></tr>';
        return;
    }
    tbody.innerHTML = data.map(v => `
        <tr>
            <td>${escHtml(v.hospital_name)}</td>
            <td>${escHtml(v.dept_name)}</td>
            <td>${v.max_registered}</td>
            <td><strong style="color:var(--primary)">${v.avg_registered}</strong></td>
        </tr>
    `).join('');
}

function filterRankingTable() {
    const hospId = document.getElementById('rank-hosp-filter').value;
    const hospSelect = document.getElementById('rank-hosp-filter');
    const hospName = hospId ? hospSelect.options[hospSelect.selectedIndex].text : '';
    const deptQ = document.getElementById('rank-dept-filter').value.toLowerCase();

    const filtered = AppState.analysis.ranking.filter(v => {
        const matchHosp = !hospName || v.hospital_name === hospName;
        const matchDept = !deptQ || v.dept_name.toLowerCase().includes(deptQ);
        return matchHosp && matchDept;
    });
    renderRankingTable(filtered);
}
