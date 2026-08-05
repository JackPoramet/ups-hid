/**
 * UPS Monitor — Enterprise Web UI JavaScript
 * ====================================
 * จัดการ real-time polling, UI updates, tab switching, settings form
 *
 * Architecture:
 *   - polling ทุก 1 วินาทีผ่าน /api/ups + /api/ups/power
 *   - แยก update ตาม tab ที่กำลัง active เพื่อประสิทธิภาพสูงสุด
 *   - Material Symbols icon dynamic rendering
 */

'use strict';

// ── State ──────────────────────────────────────────────────────────────────────
let currentTab = 'dashboard';
let pollTimer = null;
let consecutiveErrors = 0;
const MAX_ERRORS = 5;
const POLL_INTERVAL_MS = 1000;

// ── Theme Management ──────────────────────────────────────────────────────────
function initTheme() {
    const savedTheme = localStorage.getItem('ups_theme') || 'dark';
    setTheme(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('ups_theme', theme);
    const iconEl = document.getElementById('theme-toggle-icon');
    if (iconEl) {
        iconEl.textContent = theme === 'dark' ? 'light_mode' : 'dark_mode';
    }
}

// ── Init ───────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    loadSettings();
    startPolling();
});

// ══════════════════════════════════════════════════════════════════════════════
// Polling
// ══════════════════════════════════════════════════════════════════════════════

/**
 * เริ่ม polling loop
 */
function startPolling() {
    pollOnce();
    pollTimer = setInterval(pollOnce, POLL_INTERVAL_MS);
}

/**
 * poll ครั้งเดียว — ดึงข้อมูลจาก API แล้วอัปเดต UI
 */
async function pollOnce() {
    try {
        const [upsRes, powerRes] = await Promise.all([
            fetch('/api/ups').then(r => r.json()),
            fetch('/api/ups/power').then(r => r.json()),
        ]);

        consecutiveErrors = 0;
        hideBanner();

        updateDashboard(upsRes, powerRes);

        if (currentTab === 'device') {
            updateDeviceInfo(upsRes.device || {}, upsRes.ups || {});
        }
        if (currentTab === 'history') {
            loadHistoryData();
        }

    } catch (err) {
        consecutiveErrors++;
        console.warn(`Poll error (${consecutiveErrors}):`, err);
        if (consecutiveErrors >= MAX_ERRORS) {
            showBanner();
            setStatusDot('disconnected');
        }
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// Dashboard Update
// ══════════════════════════════════════════════════════════════════════════════

/**
 * อัปเดต Dashboard tab ทั้งหมด
 * @param {Object} data - response จาก /api/ups
 * @param {Object} power - response จาก /api/ups/power
 */
function updateDashboard(data, power) {
    const ups = data.ups || {};
    const device = data.device || {};
    const connected = data.connected;

    // Toggle Dashboard Disconnected Card
    const disCard = document.getElementById('dashboard-disconnected-card');
    if (disCard) {
        disCard.style.display = connected ? 'none' : 'block';
    }

    // Update Header Subtitle
    if (connected) {
        const prod = device['product_string'] || device['product'] || 'Innova Unity';
        const mode = ups['ups_mode'] || 'เชื่อมต่อสำเร็จ';
        setText('header-subtitle', `${prod} — ${mode}`);
    } else {
        setText('header-subtitle', 'ไม่ได้เชื่อมต่ออุปกรณ์ UPS');
    }

    // Update timestamp
    setText('last-update', new Date().toLocaleTimeString('th-TH'));

    // ── Hero Cards ────────────────────────────────────────────────────────────
    const acPresent = ups['ac_present'];
    const charging  = ups['charging'];
    const charge    = ups['battery.charge'];
    const runtime   = ups['battery.runtime'];
    const load      = ups['percent_load'];

    // AC Status
    const upsStatus = ups['ups.status'] || '';
    const discharging = ups['discharging'];
    updateAcCard(acPresent, charging, connected, upsStatus, discharging);

    // Battery
    if (connected && charge != null) {
        setText('battery-pct', `${Math.round(charge)}%`);
        setBatteryBar(charge);
    } else if (!connected) {
        setText('battery-pct', 'ไม่ได้เชื่อมต่อ');
        setBatteryBar(0);
    } else {
        setText('battery-pct', '—');
        setBatteryBar(0);
    }

    // Runtime
    if (connected && runtime != null) {
        setText('runtime-val', formatRuntime(runtime));
    } else if (!connected) {
        setText('runtime-val', 'ไม่ได้เชื่อมต่อ');
    } else {
        setText('runtime-val', '—');
    }

    // Load
    if (connected && load != null) {
        setText('load-val', `${Math.round(load)} %`);
    } else if (!connected) {
        setText('load-val', 'ไม่ได้เชื่อมต่อ');
    } else {
        setText('load-val', '—');
    }

    // ── Status Section ────────────────────────────────────────────────────────
    if (!connected) {
        setValWithColor('val-ups-status', 'ไม่ได้เชื่อมต่ออุปกรณ์', 'err');
        setText('val-charging',     'ไม่ได้เชื่อมต่อ');
        setText('val-discharging',  'ไม่ได้เชื่อมต่อ');
        setText('val-status-good',  'ไม่ได้เชื่อมต่อ');
        setText('val-battery-test', 'ไม่ได้เชื่อมต่อ');

        setText('val-batt-charge',   'ไม่ได้เชื่อมต่อ');
        setText('val-batt-capacity', 'ไม่ได้เชื่อมต่อ');
        setText('val-batt-runtime',  'ไม่ได้เชื่อมต่อ');
        setText('val-batt-voltage',  'ไม่ได้เชื่อมต่อ');
        setText('val-batt-low-alert','ไม่ได้เชื่อมต่อ');

        setText('val-internal-failure', 'ไม่ได้เชื่อมต่อ');
        setText('val-need-replacement', 'ไม่ได้เชื่อมต่อ');
        setText('val-overload',         'ไม่ได้เชื่อมต่อ');
        setText('val-shutdown-imminent','ไม่ได้เชื่อมต่อ');
        setText('val-over-temp',        'ไม่ได้เชื่อมต่อ');

        setText('val-input-voltage',   'ไม่ได้เชื่อมต่อ');
        setText('val-input-freq',      'ไม่ได้เชื่อมต่อ');
        setText('val-output-voltage',  'ไม่ได้เชื่อมต่อ');
        setText('val-output-freq',     'ไม่ได้เชื่อมต่อ');
        setText('val-active-power',    'ไม่ได้เชื่อมต่อ');
        setText('val-apparent-power',  'ไม่ได้เชื่อมต่อ');
        setText('val-temperature',     'ไม่ได้เชื่อมต่อ');

        setStatusDot('disconnected');
        return;
    }

    let formattedStatus = upsStatus || '—';
    let statusColor = 'ok';

    if (upsStatus.includes('OFF')) {
        formattedStatus = `Standby / Output Off (${upsStatus})`;
        statusColor = 'dim';
    } else if (upsStatus.includes('BYPASS') || upsStatus.includes('BYP')) {
        formattedStatus = `Bypass Mode (${upsStatus})`;
        statusColor = 'warn';
    } else if (upsStatus.includes('OB') || acPresent === false || discharging === true) {
        formattedStatus = `On Battery (${upsStatus})`;
        statusColor = 'err';
    } else if (upsStatus.includes('OL')) {
        formattedStatus = `Online (${upsStatus})`;
        statusColor = 'ok';
    }

    setValWithColor('val-ups-status', formattedStatus, statusColor);

    setBool('val-charging',     ups['charging'],     true,  'ok',   'dim');
    setBool('val-discharging',  ups['discharging'],  false, 'warn', 'ok');
    setBool('val-status-good',  ups['status_good'],  true,  'ok',   'err');
    setText('val-battery-test', ups['battery_test_status'] || '—');

    // ── Battery Section ───────────────────────────────────────────────────────
    setVal('val-batt-charge',   charge,   '%');
    setVal('val-batt-capacity', ups['battery_capacity_percent'], '%');
    setVal('val-batt-runtime',  formatRuntime(runtime));
    setVal('val-batt-voltage',  ups['battery_voltage_v'],  ' V', 1);
    setVal('val-batt-low-alert',ups['low_batt_alert_limit_percent'], '%');

    // ── Fault Section ─────────────────────────────────────────────────────────
    setFaultBool('val-internal-failure', ups['internal_failure']);
    setFaultBool('val-need-replacement', ups['need_replacement']);
    setFaultBool('val-overload',         ups['overload']);
    setFaultBool('val-shutdown-imminent',ups['shutdown_imminent']);
    setFaultBool('val-over-temp',        ups['over_temperature']);

    // ── Power Section ─────────────────────────────────────────────────────────
    setVal('val-input-voltage',   power['input_voltage_v'],        ' V', 1);
    setVal('val-input-freq',      power['input_frequency_hz'],     ' Hz', 1);
    setVal('val-output-voltage',  power['output_voltage_v'],       ' V', 1);
    setVal('val-output-freq',     power['output_frequency_hz'],    ' Hz', 1);
    setVal('val-active-power',    power['output_active_power_w'],  ' W', 1);
    setVal('val-apparent-power',  power['output_apparent_power_va'],' VA', 0);
    setVal('val-temperature',     power['temperature_c'],          ' °C', 1);

    // Status Dot
    if (!connected) setStatusDot('disconnected');
    else if (upsStatus.includes('OFF')) setStatusDot('disconnected');
    else if (upsStatus.includes('BYPASS') || upsStatus.includes('BYP')) setStatusDot('charging');
    else if (acPresent === false || discharging === true || upsStatus.includes('OB')) setStatusDot('fail');
    else if (charging === true)   setStatusDot('charging');
    else setStatusDot('connected');

    // PC Shutdown & Countdown Status
    updatePcShutdownStatus(data.pc_shutdown || {});
}

/**
 * อัปเดต AC hero card พร้อม Material Symbols icon
 */
function updateAcCard(acPresent, charging, connected, upsStatus, discharging) {
    const card = document.getElementById('card-ac');
    const statusEl = document.getElementById('ac-status');
    const iconEl = document.getElementById('ac-icon');

    card.className = 'hero-card hero-card--ac';

    if (!connected || acPresent == null) {
        statusEl.textContent = 'ไม่ได้เชื่อมต่อ';
        statusEl.style.color = 'var(--color-err)';
        if (iconEl) iconEl.textContent = 'usb_off';
        card.classList.add('status-dim');
    } else if (upsStatus && upsStatus.includes('OFF')) {
        statusEl.textContent = 'Standby (ปิดการจ่ายไฟ)';
        statusEl.style.color = 'var(--color-dim)';
        if (iconEl) iconEl.textContent = 'pause_circle';
        card.classList.add('status-dim');
    } else if (upsStatus && (upsStatus.includes('BYPASS') || upsStatus.includes('BYP'))) {
        statusEl.textContent = 'Bypass Mode';
        statusEl.style.color = 'var(--color-warn)';
        if (iconEl) iconEl.textContent = 'sync';
        card.classList.add('status-charging');
    } else if (acPresent === false || discharging === true || (upsStatus && upsStatus.includes('OB'))) {
        statusEl.textContent = 'On Battery';
        statusEl.style.color = 'var(--color-err)';
        if (iconEl) iconEl.textContent = 'battery_alert';
        card.classList.add('status-fail');
    } else if (charging === true) {
        statusEl.textContent = 'Online (ชาร์จไฟ)';
        statusEl.style.color = 'var(--color-warn)';
        if (iconEl) iconEl.textContent = 'battery_charging_full';
        card.classList.add('status-charging');
    } else {
        statusEl.textContent = 'Online (ปกติ)';
        statusEl.style.color = 'var(--color-ok)';
        if (iconEl) iconEl.textContent = 'bolt';
        card.classList.add('status-ok');
    }
}

/**
 * อัปเดต Device Info tab
 */
function updateDeviceInfo(device, ups) {
    setText('dev-manufacturer', device['manufacturer_string'] || device['manufacturer'] || '—');
    setText('dev-product',      device['product_string']      || device['product']      || '—');
    setText('dev-serial',       device['serial_number']       || device['serial']       || '—');
    setText('dev-firmware',     ups['ups.firmware']           || device['firmware']     || '—');
    setText('dev-release',      device['release_number']      || device['release']      || '—');
    setText('dev-usage-page',   device['usage_page']          || '—');
    setText('dev-usage',        device['usage']               || '—');
}

// ══════════════════════════════════════════════════════════════════════════════
// Tab Switching
// ══════════════════════════════════════════════════════════════════════════════

/**
 * สลับ tab
 * @param {string} name - ชื่อ tab: 'dashboard' | 'device' | 'control' | 'settings'
 */
function switchTab(name) {
    currentTab = name;

    // Update tab buttons
    document.querySelectorAll('.tab').forEach(t => {
        t.classList.remove('tab--active');
        t.setAttribute('aria-selected', 'false');
    });
    const activeTab = document.getElementById(`tab-${name}`);
    if (activeTab) {
        activeTab.classList.add('tab--active');
        activeTab.setAttribute('aria-selected', 'true');
    }

    // Update panels
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('tab-panel--active'));
    document.getElementById(`panel-${name}`)?.classList.add('tab-panel--active');

    if (name === 'device') pollOnce();
    if (name === 'settings') loadSettings();
    if (name === 'history') loadHistoryData();
}

// ══════════════════════════════════════════════════════════════════════════════
// Control Panel
// ══════════════════════════════════════════════════════════════════════════════

/** เริ่ม UPS monitoring */
async function controlMonitor(action) {
    const res = await apiPost(`/api/control/monitor/${action}`);
    showResult('result-monitor',
        res.monitoring !== undefined
            ? (res.monitoring ? '[SUCCESS] Monitoring เริ่มทำงานแล้ว' : '[INFO] Monitoring หยุดทำงาน')
            : `[ERROR] ${res.message || 'Unknown error'}`,
        res.success !== false);
}

/** สั่ง PC Shutdown ด้วยมือพร้อมตั้งเวลานับถอยหลัง */
async function triggerPcShutdown() {
    const inputEl = document.getElementById('manual-pc-shutdown-delay');
    const delay = parseInt(inputEl?.value || '60');
    if (!confirm(`ยืนยันการสั่งปิดเครื่องคอมพิวเตอร์ (PC Shutdown)?\nระบบจะนับถอยหลัง ${delay} วินาทีก่อนปิดเครื่อง!`)) return;

    const res = await apiPost('/api/control/shutdown/trigger', {
        delay_seconds: delay,
        reason: `สั่งปิดเครื่องด้วยมือผ่าน Web Dashboard (นับถอยหลัง ${delay}s)`
    });

    showResult('result-pc-shutdown',
        res.success ? `[SUCCESS] สั่งปิดเครื่องแล้ว! กำลังนับถอยหลัง ${delay} วินาที` : `[ERROR] ${res.message || 'สั่งปิดเครื่องไม่สำเร็จ'}`,
        res.success);

    if (res.success) {
        pollOnce();
    }
}

/** ยกเลิก PC auto-shutdown */
async function cancelShutdown() {
    const res = await apiPost('/api/control/shutdown/cancel');
    showResult('result-pc-shutdown',
        res.success ? '[SUCCESS] ยกเลิก PC Shutdown สำเร็จ' : `[ERROR] ${res.message || 'Error'}`,
        res.success);
    if (res.success) {
        pollOnce();
    }
}

/**
 * อัปเดตสถานะ PC Auto-Shutdown & Live Countdown Timer
 * @param {Object} pcSd - pc_shutdown dict จาก API
 */
function updatePcShutdownStatus(pcSd) {
    const banner = document.getElementById('shutdown-banner');
    const bannerClock = document.getElementById('shutdown-banner-clock');
    const bannerReason = document.getElementById('shutdown-banner-sub');
    const badge = document.getElementById('pc-shutdown-badge');
    const timerDisplay = document.getElementById('pc-shutdown-timer-display');
    const timerDigits = document.getElementById('pc-shutdown-countdown');

    if (pcSd && pcSd.pending && pcSd.remaining_seconds > 0) {
        const secs = pcSd.remaining_seconds;
        const formattedTime = formatCountdownTime(secs);

        // Update Banner
        if (banner) banner.style.display = 'block';
        if (bannerClock) bannerClock.textContent = formattedTime;
        if (bannerReason) bannerReason.textContent = `เหตุผล: ${pcSd.reason || 'UPS Event'}`;

        // Update Card Display Box
        if (badge) {
            badge.textContent = `กำลังนับถอยหลังปิดเครื่อง (${formattedTime})`;
            badge.className = 'countdown-badge pending';
        }
        if (timerDisplay) timerDisplay.style.display = 'flex';
        if (timerDigits) timerDigits.textContent = formattedTime;

    } else {
        // Hide Banner
        if (banner) banner.style.display = 'none';

        // Update Card Display Box
        if (badge) {
            badge.textContent = 'ปกติ (No Pending Shutdown)';
            badge.className = 'countdown-badge';
        }
        if (timerDisplay) timerDisplay.style.display = 'none';
        if (timerDigits) timerDigits.textContent = '00:00';
    }
}

/** Format seconds into MM:SS */
function formatCountdownTime(seconds) {
    if (seconds == null || seconds <= 0) return '00:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    const mm = String(m).padStart(2, '0');
    const ss = String(s).padStart(2, '0');
    return `${mm}:${ss}`;
}

/** UPS Self Test */
async function upsSelfTest(action) {
    const res = await apiPost('/api/ups/control/test', { action });
    showResult('result-selftest',
        res.success ? `[SUCCESS] ${action === 'run' ? 'เริ่ม' : 'ยกเลิก'} Self Test แล้ว` : `[ERROR] ${res.message}`,
        res.success);
}

/** UPS Output Shutdown */
async function upsShutdown() {
    const delay = parseInt(document.getElementById('ups-shutdown-delay')?.value || '60');
    if (!confirm(`ยืนยันดำเนินการ: UPS จะหยุดจ่ายไฟหลังจาก ${delay} วินาที\nอุปกรณ์ต่อพ่วงทั้งหมดจะดับ!`)) return;
    const res = await apiPost('/api/ups/control/shutdown', { delay_seconds: delay });
    showResult('result-ups-shutdown', res.success ? `[SUCCESS] UPS Shutdown scheduled (${delay}s)` : `[ERROR] ${res.message}`, res.success);
}

/** ยกเลิก UPS Output Shutdown */
async function upsShutdownCancel() {
    const res = await apiPost('/api/ups/control/cancel_shutdown');
    showResult('result-ups-shutdown',
        res.success ? '[SUCCESS] ยกเลิก UPS Output Shutdown แล้ว' : `[ERROR] ${res.message}`,
        res.success);
}

/** อ่านเวลานาฬิกา UPS (RID 0x29) */
async function readUpsTime() {
    try {
        const res = await fetch('/api/ups/time').then(r => r.json());
        if (res.success && res.ups_time) {
            setText('val-ups-clock-time', res.ups_time);
            showResult('result-ups-time', `[SUCCESS] อ่านเวลา UPS สำเร็จ: ${res.ups_time}`, true);
        } else {
            showResult('result-ups-time', `[ERROR] ${res.message || 'อ่านไม่สำเร็จ'}`, false);
        }
    } catch (e) {
        showResult('result-ups-time', `[ERROR] ${e.message}`, false);
    }
}

/** ซิงค์เวลานาฬิกา PC ไปยัง UPS (RID 0x29) */
async function syncUpsTime() {
    if (!confirm('ยืนยัน: ต้องการตั้งเวลานาฬิกาภายใน UPS ให้ตรงกับเวลาของเครื่อง PC?')) return;
    const res = await apiPost('/api/ups/time/sync');
    if (res.success) {
        setText('val-ups-clock-time', res.synced_time);
        showResult('result-ups-time', `[SUCCESS] ซิงค์เวลาสำเร็จ: ${res.synced_time}`, true);
    } else {
        showResult('result-ups-time', `[ERROR] ${res.message || 'ตั้งเวลาไม่สำเร็จ'}`, false);
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// Settings
// ══════════════════════════════════════════════════════════════════════════════

/** โหลด config จาก server มาใส่ form */
async function loadSettings() {
    try {
        const cfg = await fetch('/api/config').then(r => r.json());
        setCheck('cfg-auto-shutdown',    cfg['auto_shutdown_enabled']);
        setNumVal('cfg-shutdown-delay',  cfg['shutdown_delay_minutes']);
        setNumVal('cfg-batt-threshold',  cfg['shutdown_battery_threshold']);
        setCheck('cfg-shutdown-ac-fail', cfg['shutdown_on_ac_fail'] !== false);
        setCheck('cfg-shutdown-low-batt',cfg['shutdown_on_low_battery'] !== false);
        setCheck('cfg-notif-enabled',    cfg['notifications_enabled'] !== false);
        setCheck('cfg-notif-ac-fail',    cfg['notify_on_ac_fail'] !== false);
        setCheck('cfg-notif-ac-restore', cfg['notify_on_ac_restore'] !== false);
        setCheck('cfg-notif-low-batt',   cfg['notify_on_low_battery'] !== false);
        setCheck('cfg-db-enabled',       cfg['db_enabled'] !== false);
        setNumVal('cfg-db-telemetry-interval', cfg['db_telemetry_interval_s'] || 10);
        setNumVal('cfg-db-retention',    cfg['db_retention_days'] || 30);
        setCheck('cfg-startup-windows',  cfg['startup_with_windows'] !== false);
        setNumVal('cfg-poll-interval',   cfg['poll_interval_s']);
    } catch (e) {
        console.warn('Failed to load settings:', e);
    }
}

/** บันทึก settings ไปยัง server */
async function saveSettings() {
    const payload = {
        auto_shutdown_enabled:       getCheck('cfg-auto-shutdown'),
        shutdown_delay_minutes:      getNumVal('cfg-shutdown-delay'),
        shutdown_battery_threshold:  getNumVal('cfg-batt-threshold'),
        shutdown_on_ac_fail:         getCheck('cfg-shutdown-ac-fail'),
        shutdown_on_low_battery:     getCheck('cfg-shutdown-low-batt'),
        notifications_enabled:       getCheck('cfg-notif-enabled'),
        notify_on_ac_fail:           getCheck('cfg-notif-ac-fail'),
        notify_on_ac_restore:        getCheck('cfg-notif-ac-restore'),
        notify_on_low_battery:       getCheck('cfg-notif-low-batt'),
        db_enabled:                  getCheck('cfg-db-enabled'),
        db_telemetry_interval_s:     getNumVal('cfg-db-telemetry-interval'),
        db_retention_days:           getNumVal('cfg-db-retention'),
        startup_with_windows:        getCheck('cfg-startup-windows'),
        poll_interval_s:             getNumVal('cfg-poll-interval'),
    };

    const res = await apiPost('/api/config', payload);
    showResult('result-settings',
        res.success ? '[SUCCESS] บันทึกการตั้งค่าสำเร็จ' : `[ERROR] บันทึกไม่สำเร็จ: ${res.message || ''}`,
        res.success);
}

// ══════════════════════════════════════════════════════════════════════════════
// History & Events (Database)
// ══════════════════════════════════════════════════════════════════════════════

async function loadHistoryData() {
    const hours = getNumVal('history-hours') || 24;
    try {
        const [histRes, eventRes] = await Promise.all([
            fetch(`/api/history?hours=${hours}`).then(r => r.json()),
            fetch('/api/events?limit=50').then(r => r.json()),
        ]);

        if (histRes.status === 'ok') {
            updateAllHistoryCharts(histRes.data || []);
        }
        if (eventRes.status === 'ok') {
            renderEventsTable('events-table-body', eventRes.events || []);
        }
    } catch (e) {
        console.error('Failed to load history data:', e);
    }
}

async function clearDatabase() {
    if (!confirm('ยืนยัน: คุณต้องการล้างข้อมูลประวัติและ Event Logs ทั้งหมดใน SQLite ฐานข้อมูลหรือไม่?')) return;
    const res = await apiPost('/api/database/clear');
    if (res.status === 'ok' || res.success) {
        alert(res.message || 'ล้างข้อมูลเรียบร้อยแล้ว');
        loadHistoryData();
    } else {
        alert('เกิดข้อผิดพลาด: ' + (res.message || ''));
    }
}

function renderEventsTable(tbodyId, events) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;

    if (!events || events.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="padding: 20px; text-align: center; color: var(--text-secondary);">ไม่พบประวัติเหตุการณ์ในระบบ</td></tr>`;
        return;
    }

    let html = '';
    events.forEach(e => {
        const timeStr = formatIsoTime(e.timestamp);
        const eventBadge = getEventBadgeHtml(e.event_type);
        const acStr = e.ac_present === true ? '<span style="color:var(--color-ok);">Normal</span>' : (e.ac_present === false ? '<span style="color:var(--color-err);">AC Fail</span>' : '—');
        const battStr = e.battery_level != null ? `${e.battery_level}%` : '—';

        html += `
            <tr style="border-bottom: 1px solid var(--border-color, rgba(255,255,255,0.05));">
                <td style="padding: 10px 16px; color: var(--text-secondary);">${e.id}</td>
                <td style="padding: 10px 16px;">${timeStr}</td>
                <td style="padding: 10px 16px;">${eventBadge}</td>
                <td style="padding: 10px 16px;">${escapeHtml(e.message || '')}</td>
                <td style="padding: 10px 16px; font-weight: 500;">${battStr}</td>
                <td style="padding: 10px 16px;">${acStr}</td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

function getEventBadgeHtml(eventType) {
    let color = '#3B82F6';
    let bg = 'rgba(59, 130, 246, 0.15)';
    if (eventType === 'AC_FAIL') { color = '#EF4444'; bg = 'rgba(239, 68, 68, 0.15)'; }
    else if (eventType === 'AC_RESTORE') { color = '#10B981'; bg = 'rgba(16, 185, 129, 0.15)'; }
    else if (eventType === 'BATTERY_LOW' || eventType === 'BATTERY_CRITICAL') { color = '#F59E0B'; bg = 'rgba(245, 158, 11, 0.15)'; }
    else if (eventType === 'SYSTEM_START') { color = '#8B5CF6'; bg = 'rgba(139, 92, 246, 0.15)'; }

    return `<span style="display:inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 600; color:${color}; background:${bg};">${eventType}</span>`;
}

function formatIsoTime(isoStr) {
    if (!isoStr) return '—';
    try {
        const d = new Date(isoStr);
        return d.toLocaleString('th-TH', { hour12: false });
    } catch (e) {
        return isoStr;
    }
}

function escapeHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ══════════════════════════════════════════════════════════════════════════════
// 3 Separate History Canvas Charts Rendering
// ══════════════════════════════════════════════════════════════════════════════

const chartHoverStates = {};

/**
 * อัปเดตข้อมูลและแสดงผลกราฟแยกทั้ง 3 อัน (Battery, Voltage, Load)
 * @param {Array} data - ข้อมูล telemetry จาก API
 */
function updateAllHistoryCharts(data) {
    if (!data || data.length === 0) {
        setText('chart-val-battery', '—');
        setText('chart-val-voltage', '—');
        setText('chart-val-load', '—');
        renderSingleMetricChart('chart-battery', [], null, 0, 100, '%', '#10B981');
        renderSingleMetricChart('chart-voltage', [], null, 0, 300, 'V', '#3B82F6');
        renderSingleMetricChart('chart-load', [], null, 0, 100, '%', '#F59E0B');
        return;
    }

    const getBatt = (d) => d.battery_charge ?? d.battery_capacity_pct ?? null;
    const getVolt = (d) => d.input_voltage ?? d.input_voltage_v ?? null;
    const getLoad = (d) => d.output_load ?? d.percent_load ?? null;

    // Update Header Value Badges
    const latest = data[data.length - 1];
    const latestBatt = getBatt(latest);
    const latestVolt = getVolt(latest);
    const latestLoad = getLoad(latest);

    setText('chart-val-battery', latestBatt != null ? `${Math.round(latestBatt)}%` : '—');
    setText('chart-val-voltage', latestVolt != null ? `${Number(latestVolt).toFixed(1)} V` : '—');
    setText('chart-val-load', latestLoad != null ? `${Math.round(latestLoad)}%` : '—');

    // Render 3 Individual Charts
    renderSingleMetricChart('chart-battery', data, getBatt, 0, 100, '%', '#10B981');
    renderSingleMetricChart('chart-voltage', data, getVolt, 0, 300, 'V', '#3B82F6');
    renderSingleMetricChart('chart-load', data, getLoad, 0, 100, '%', '#F59E0B');
}

function renderSingleMetricChart(canvasId, data, valExtractor, minVal, maxVal, unit, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // Bind mouse events once per canvas
    if (!canvas.dataset.hoverBound) {
        canvas.dataset.hoverBound = 'true';
        canvas.addEventListener('mousemove', (e) => {
            const rect = canvas.getBoundingClientRect();
            chartHoverStates[canvasId] = {
                x: e.clientX - rect.left,
                y: e.clientY - rect.top
            };
            drawSingleMetricChartContent(canvas, ctx, data, valExtractor, minVal, maxVal, unit, color, chartHoverStates[canvasId]);
        });
        canvas.addEventListener('mouseleave', () => {
            chartHoverStates[canvasId] = null;
            drawSingleMetricChartContent(canvas, ctx, data, valExtractor, minVal, maxVal, unit, color, null);
        });
    }

    drawSingleMetricChartContent(canvas, ctx, data, valExtractor, minVal, maxVal, unit, color, chartHoverStates[canvasId]);
}

function drawSingleMetricChartContent(canvas, ctx, data, valExtractor, minVal, maxVal, unit, color, hoverPos) {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = rect.height;

    ctx.clearRect(0, 0, width, height);

    if (!data || data.length === 0 || !valExtractor) {
        ctx.fillStyle = '#64748B';
        ctx.font = '13px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('ยังไม่มีข้อมูลสำหรับช่วงเวลานี้', width / 2, height / 2);
        return;
    }

    const padding = { top: 15, right: 45, bottom: 25, left: 45 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    // Draw horizontal grid lines & Y labels (4 ticks)
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
    ctx.lineWidth = 1;

    for (let i = 0; i <= 3; i++) {
        const y = padding.top + (chartH / 3) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();

        const stepVal = minVal + ((maxVal - minVal) * (3 - i)) / 3;
        ctx.fillStyle = '#64748B';
        ctx.font = '10px JetBrains Mono, monospace';
        ctx.textAlign = 'right';
        ctx.fillText(`${Math.round(stepVal)}${unit}`, padding.left - 6, y + 3);
    }

    const n = data.length;
    const getX = (idx) => padding.left + (idx / Math.max(1, n - 1)) * chartW;

    // Create Gradient Fill below the line
    const gradient = ctx.createLinearGradient(0, padding.top, 0, height - padding.bottom);
    const alphaColor = color === '#10B981' ? 'rgba(16, 185, 129, 0.2)' : (color === '#3B82F6' ? 'rgba(59, 130, 246, 0.2)' : 'rgba(245, 158, 11, 0.2)');
    gradient.addColorStop(0, alphaColor);
    gradient.addColorStop(1, 'rgba(15, 23, 42, 0.0)');

    ctx.fillStyle = gradient;
    ctx.beginPath();
    let started = false;
    let lastX = padding.left;

    for (let i = 0; i < n; i++) {
        const rawVal = valExtractor(data[i]);
        if (rawVal == null) continue;

        const clamped = Math.max(minVal, Math.min(maxVal, rawVal));
        const norm = (clamped - minVal) / (maxVal - minVal);
        const x = getX(i);
        const y = padding.top + chartH * (1 - norm);

        if (!started) {
            ctx.moveTo(x, padding.top + chartH);
            ctx.lineTo(x, y);
            started = true;
        } else {
            ctx.lineTo(x, y);
        }
        lastX = x;
    }
    if (started) {
        ctx.lineTo(lastX, padding.top + chartH);
        ctx.closePath();
        ctx.fill();
    }

    // Draw Line Series
    drawLineSeries(ctx, data, getX, valExtractor, padding, chartH, minVal, maxVal, color);

    // X Time Labels (Start, Middle, End)
    ctx.fillStyle = '#64748B';
    ctx.font = '10px JetBrains Mono, monospace';
    ctx.textAlign = 'left';
    ctx.fillText(formatTimeShort(data[0].timestamp), padding.left, height - 6);

    ctx.textAlign = 'center';
    ctx.fillText(formatTimeShort(data[Math.floor(n / 2)].timestamp), padding.left + chartW / 2, height - 6);

    ctx.textAlign = 'right';
    ctx.fillText(formatTimeShort(data[n - 1].timestamp), width - padding.right, height - 6);

    // Hover Tooltip & Guideline
    if (hoverPos && hoverPos.x >= padding.left && hoverPos.x <= width - padding.right) {
        const relativeX = (hoverPos.x - padding.left) / chartW;
        const nearestIdx = Math.min(n - 1, Math.max(0, Math.round(relativeX * (n - 1))));
        const item = data[nearestIdx];
        if (item) {
            const pointX = getX(nearestIdx);
            const val = valExtractor(item);

            // Vertical Guide Line
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
            ctx.setLineDash([3, 3]);
            ctx.beginPath();
            ctx.moveTo(pointX, padding.top);
            ctx.lineTo(pointX, height - padding.bottom);
            ctx.stroke();
            ctx.setLineDash([]);

            if (val != null) {
                const clamped = Math.max(minVal, Math.min(maxVal, val));
                const norm = (clamped - minVal) / (maxVal - minVal);
                const py = padding.top + chartH * (1 - norm);

                // Draw Highlight Dot
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(pointX, py, 4, 0, Math.PI * 2);
                ctx.fill();
                ctx.strokeStyle = '#0F172A';
                ctx.lineWidth = 2;
                ctx.stroke();

                // Tooltip Box
                const ttTime = formatIsoTime(item.timestamp);
                const valStr = typeof val === 'number' ? (unit === 'V' ? val.toFixed(1) : Math.round(val)) + ' ' + unit : '—';
                const ttText = `${ttTime} | ${valStr}`;

                ctx.font = '11px Inter, sans-serif';
                const textWidth = ctx.measureText(ttText).width;
                const ttW = textWidth + 16;
                const ttH = 24;

                let ttX = pointX - ttW / 2;
                if (ttX < padding.left) ttX = padding.left;
                if (ttX + ttW > width - padding.right) ttX = width - padding.right - ttW;
                let ttY = py - 32;
                if (ttY < padding.top) ttY = py + 10;

                ctx.fillStyle = 'rgba(15, 23, 42, 0.95)';
                ctx.strokeStyle = color;
                ctx.lineWidth = 1;
                ctx.beginPath();
                if (typeof ctx.roundRect === 'function') {
                    ctx.roundRect(ttX, ttY, ttW, ttH, 4);
                } else {
                    ctx.rect(ttX, ttY, ttW, ttH);
                }
                ctx.fill();
                ctx.stroke();

                ctx.fillStyle = '#F8FAFC';
                ctx.textAlign = 'center';
                ctx.fillText(ttText, ttX + ttW / 2, ttY + 16);
            }
        }
    }
}

function drawLineSeries(ctx, data, getX, valExtractor, padding, chartH, minVal, maxVal, color) {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    let started = false;

    for (let i = 0; i < data.length; i++) {
        const rawVal = valExtractor(data[i]);
        if (rawVal == null) continue;

        const clamped = Math.max(minVal, Math.min(maxVal, rawVal));
        const norm = (clamped - minVal) / (maxVal - minVal);
        const x = getX(i);
        const y = padding.top + chartH * (1 - norm);

        if (!started) {
            ctx.moveTo(x, y);
            started = true;
        } else {
            ctx.lineTo(x, y);
        }
    }
    ctx.stroke();
}

function formatTimeShort(isoStr) {
    if (!isoStr) return '';
    try {
        const d = new Date(isoStr);
        const hh = String(d.getHours()).padStart(2, '0');
        const mm = String(d.getMinutes()).padStart(2, '0');
        return `${hh}:${mm}`;
    } catch (e) {
        return '';
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// UI Helpers
// ══════════════════════════════════════════════════════════════════════════════

/** ตั้ง text content ของ element */
function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value ?? '—';
}

/**
 * ตั้ง value พร้อม unit
 */
function setVal(id, value, unit = '', decimals = 0) {
    const el = document.getElementById(id);
    if (!el) return;
    if (value == null) { el.textContent = '—'; return; }
    const formatted = typeof value === 'number' ? value.toFixed(decimals) : value;
    el.textContent = `${formatted}${unit}`;
}

/**
 * ตั้ง value พร้อม CSS color class
 */
function setValWithColor(id, value, colorClass) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = value ?? '—';
    el.className = `data-row__value ${colorClass ? `val-${colorClass}` : ''}`;
}

/**
 * ตั้ง boolean value พร้อมสีตามผล
 */
function setBool(id, value, trueIsGood, trueClass, falseClass) {
    const el = document.getElementById(id);
    if (!el) return;
    if (value == null) { el.textContent = '—'; el.className = 'data-row__value val-dim'; return; }
    const isTrue = value === true;
    el.textContent = isTrue ? 'Normal' : 'Off';
    el.className = `data-row__value val-${isTrue ? trueClass : falseClass}`;
}

/**
 * ตั้ง fault boolean — True = ผิดปกติ (แดง), False = ปกติ (เขียว)
 */
function setFaultBool(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    if (value == null) { el.textContent = '—'; el.className = 'data-row__value val-dim'; return; }
    const isTrue = value === true;
    el.textContent = isTrue ? 'FAULT' : 'Normal';
    el.className = `data-row__value val-${isTrue ? 'err' : 'ok'}`;
}

/** อัปเดต battery progress bar */
function setBatteryBar(percent) {
    const bar = document.getElementById('battery-bar');
    if (!bar) return;
    const pct = Math.max(0, Math.min(100, percent));
    bar.style.width = `${pct}%`;
    bar.style.background = pct <= 10 ? 'var(--color-critical)' :
                           pct <= 20 ? 'var(--color-err)' :
                           pct <= 40 ? 'var(--color-warn)' : 'var(--color-ok)';
}

/** แปลง runtime วินาที → "Xh Ym" หรือ "Ym Zs" */
function formatRuntime(seconds) {
    if (seconds == null || seconds <= 0) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

/** ตั้งสถานะ dot ใน header */
function setStatusDot(status) {
    const dot = document.getElementById('status-dot');
    if (!dot) return;
    dot.className = `status-dot ${status}`;
}

/** แสดง/ซ่อน disconnect banner */
function showBanner() { const b = document.getElementById('disconnect-banner'); if (b) b.style.display = 'flex'; }
function hideBanner() { const b = document.getElementById('disconnect-banner'); if (b) b.style.display = 'none'; }

/**
 * แสดง result message ใน result-box
 */
function showResult(id, message, success = true) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = message;
    el.style.color = success ? 'var(--color-ok)' : 'var(--color-err)';
    el.style.display = 'block';
    setTimeout(() => { if (el) el.style.color = 'var(--text-secondary)'; }, 4000);
}

// ── Form helpers ──────────────────────────────────────────────────────────────
function setCheck(id, val)   { const el = document.getElementById(id); if (el) el.checked = !!val; }
function setNumVal(id, val)  { const el = document.getElementById(id); if (el && val != null) el.value = val; }
function getCheck(id)        { return document.getElementById(id)?.checked ?? false; }
function getNumVal(id)       { return parseFloat(document.getElementById(id)?.value || '0'); }

// ── API helpers ───────────────────────────────────────────────────────────────
async function apiPost(url, body = {}) {
    try {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        return await res.json();
    } catch (e) {
        console.error(`POST ${url} failed:`, e);
        return { success: false, message: e.message };
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// Device List & Selection Modal Functions
// ══════════════════════════════════════════════════════════════════════════════

function openDeviceModal() {
    const modal = document.getElementById('device-modal');
    if (modal) {
        modal.style.display = 'flex';
        fetchDevices();
    }
}

function closeDeviceModal() {
    const modal = document.getElementById('device-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function handleModalBackdropClick(event) {
    if (event.target && event.target.id === 'device-modal') {
        closeDeviceModal();
    }
}

async function fetchDevices() {
    const statusText = document.getElementById('modal-status-text');
    const spinner = document.getElementById('modal-spinner');
    const listContainer = document.getElementById('modal-device-list');

    if (statusText) statusText.textContent = 'กำลังสแกนหาอุปกรณ์ UPS (VID 0x06DA)...';
    if (spinner) spinner.style.display = 'inline-block';
    if (listContainer) {
        listContainer.innerHTML = '<div class="modal-loading-box"><span class="material-symbols-outlined spin">sync</span><p>กำลังค้นหาอุปกรณ์ UPS ในระบบ...</p></div>';
    }

    try {
        const res = await fetch('/api/ups/devices').then(r => r.json());
        if (spinner) spinner.style.display = 'none';

        if (!res.success || !res.devices || res.devices.length === 0) {
            if (statusText) statusText.textContent = 'ไม่พบอุปกรณ์ UPS (VID 0x06DA) ที่เชื่อมต่ออยู่';
            renderEmptyDeviceList(listContainer);
            return;
        }

        if (statusText) {
            statusText.textContent = `พบอุปกรณ์ UPS (VID 0x06DA) ทั้งหมด ${res.devices.length} รายการ`;
        }

        renderDeviceList(listContainer, res.devices);
    } catch (err) {
        console.error('Failed to fetch devices:', err);
        if (spinner) spinner.style.display = 'none';
        if (statusText) statusText.textContent = 'เกิดข้อผิดพลาดในการดึงรายการอุปกรณ์';
        if (listContainer) {
            listContainer.innerHTML = '<div class="modal-empty-box"><span class="material-symbols-outlined text-danger">error</span><p>ไม่สามารถเชื่อมต่อ API สแกนอุปกรณ์ได้</p></div>';
        }
    }
}

function renderEmptyDeviceList(container) {
    if (!container) return;
    container.innerHTML = `
        <div class="modal-empty-box">
            <span class="material-symbols-outlined modal-empty-icon">usb_off</span>
            <h4>ไม่พบอุปกรณ์ UPS (VID 0x06DA) ที่เชื่อมต่ออยู่</h4>
            <p>กรุณาตรวจสอบว่าได้เสียบสาย USB จากอุปกรณ์ UPS เข้ากับเครื่องคอมพิวเตอร์แล้ว และลองกดปุ่ม "สแกนค้นหาใหม่"</p>
            <button class="btn btn--primary btn--sm" onclick="fetchDevices()" style="margin-top: 12px;">
                <span class="material-symbols-outlined">refresh</span>
                <span>สแกนค้นหาใหม่</span>
            </button>
        </div>
    `;
}

function renderDeviceList(container, devices) {
    if (!container) return;

    let html = '<div class="device-cards-grid">';
    devices.forEach((dev) => {
        const isUps = dev.is_ups;
        const isSelected = dev.is_selected;
        const isActive = dev.is_active;

        const manufacturer = dev.manufacturer_string || 'Generic HID Device';
        const product = dev.product_string || 'USB HID Device';
        const serial = dev.serial_number || 'N/A';
        const vidHex = dev.vendor_id_hex || `0x${(dev.vendor_id || 0).toString(16).padStart(4, '0')}`;
        const pidHex = dev.product_id_hex || `0x${(dev.product_id || 0).toString(16).padStart(4, '0')}`;
        const usagePage = dev.usage_page_hex || '—';
        const pathStr = dev.path_str || dev.path || '';

        let badgeHtml = '';
        if (isActive) {
            badgeHtml = '<span class="badge badge--success" style="display:inline-flex; align-items:center; gap:4px;"><span class="material-symbols-outlined" style="font-size:14px;">check_circle</span> เชื่อมต่อใช้งานอยู่</span>';
        } else if (isSelected) {
            badgeHtml = '<span class="badge badge--primary" style="display:inline-flex; align-items:center; gap:4px;"><span class="material-symbols-outlined" style="font-size:14px;">star</span> อุปกรณ์ที่เลือกไว้</span>';
        } else if (isUps) {
            badgeHtml = '<span class="badge badge--enterprise">อุปกรณ์ UPS</span>';
        } else {
            badgeHtml = '<span class="badge badge--neutral">USB HID</span>';
        }

        const iconName = isUps ? 'battery_charging_full' : 'usb';
        const activeClass = isSelected ? 'device-card--selected' : '';

        const escapedPath = encodeURIComponent(pathStr);
        const escapedVid = encodeURIComponent(vidHex);
        const escapedPid = encodeURIComponent(pidHex);
        const escapedSerial = encodeURIComponent(serial || '');

        html += `
            <div class="device-card ${activeClass}">
                <div class="device-card__header">
                    <div class="device-card__icon-box ${isUps ? 'is-ups' : ''}">
                        <span class="material-symbols-outlined">${iconName}</span>
                    </div>
                    <div class="device-card__title-wrap">
                        <div class="device-card__title">${escapeHtml(manufacturer)} — ${escapeHtml(product)}</div>
                        <div class="device-card__subtitle">${badgeHtml}</div>
                    </div>
                </div>
                <div class="device-card__body">
                    <div class="dev-info-row">
                        <span class="dev-info-label">VID / PID:</span>
                        <span class="dev-info-val mono">${vidHex} : ${pidHex}</span>
                    </div>
                    <div class="dev-info-row">
                        <span class="dev-info-label">Serial Number:</span>
                        <span class="dev-info-val mono">${escapeHtml(serial)}</span>
                    </div>
                    <div class="dev-info-row">
                        <span class="dev-info-label">Usage Page:</span>
                        <span class="dev-info-val mono">${usagePage}</span>
                    </div>
                </div>
                <div class="device-card__footer">
                    ${isActive ? `
                        <button class="btn btn--secondary btn--sm" disabled style="opacity: 0.8;">
                            <span class="material-symbols-outlined">check</span>
                            <span>กำลังใช้งานอยู่</span>
                        </button>
                    ` : `
                        <button class="btn btn--primary btn--sm" onclick="selectDevice('${escapedPath}', '${escapedVid}', '${escapedPid}', '${escapedSerial}')">
                            <span class="material-symbols-outlined">link</span>
                            <span>เลือกเชื่อมต่ออุปกรณ์นี้</span>
                        </button>
                    `}
                </div>
            </div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

async function selectDevice(escapedPath, escapedVid, escapedPid, escapedSerial) {
    const path = decodeURIComponent(escapedPath);
    const vid = decodeURIComponent(escapedVid);
    const pid = decodeURIComponent(escapedPid);
    const serial = escapedSerial ? decodeURIComponent(escapedSerial) : '';

    try {
        const res = await fetch('/api/ups/select_device', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, vid, pid, serial })
        }).then(r => r.json());

        if (res.success) {
            closeDeviceModal();
            pollOnce();
        } else {
            alert(`ไม่สามารถสลับอุปกรณ์ได้: ${res.message}`);
        }
    } catch (err) {
        console.error('Select device error:', err);
        alert('เกิดข้อผิดพลาดในการส่งคำสั่งเลือกอุปกรณ์');
    }
}

function retryConnect() {
    pollOnce();
    fetchDevices();
}
