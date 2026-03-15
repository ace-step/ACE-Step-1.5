
function escapeHtml(value) {
  const s = String(value ?? '');
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const el = (id) => document.getElementById(id);


const t = (window && window.t) ? window.t : ((k, vars) => {
  
  if (!vars) return k;
  return String(k).replace(/\{([a-zA-Z0-9_]+)\}/g, (m, kk) => (vars[kk] ?? ''));
});
const applyTranslations = (window && window.applyTranslations) ? window.applyTranslations : (() => {});

const authOverlay = el('auth_overlay');
const authOverlayTitle = el('auth_overlay_title');
const authOverlayHelp = el('auth_overlay_help');
const authOverlayStatus = el('auth_overlay_status');
const authLoginBox = el('auth_login_box');
const authChangeBox = el('auth_change_box');
const authLoginEmail = el('auth_login_email');
const authLoginPassword = el('auth_login_password');
const authLoginForm = el('auth_login_form');
const authLoginSubmit = el('auth_login_submit');
const authChangePassword = el('auth_change_password');
const authChangePasswordConfirm = el('auth_change_password_confirm');
const authChangeSubmit = el('auth_change_submit');
const authBar = el('auth_bar');
const authUserLabel = el('auth_user_label');
const authLogoutBtn = el('auth_logout');
const authAdminToggleBtn = el('auth_admin_toggle');
const authAdminPanel = el('auth_admin_panel');
const authAdminEmail = el('auth_admin_email');
const authAdminRole = el('auth_admin_role');
const authAdminCreate = el('auth_admin_create');
const authAdminStatus = el('auth_admin_status');
const authAdminPasswordBox = el('auth_admin_password_box');
const authAdminPassword = el('auth_admin_password');
const authAdminUsers = el('auth_admin_users');
const authAdminEvents = el('auth_admin_events');

const authState = {
  enabled: false,
  authenticated: false,
  mustChangePassword: false,
  user: null,
  isAdmin: false,
  resolved: false,
};

let protectedBootstrapStarted = false;

function canUseProtectedApi() {
  if (!authState.resolved) return false;
  if (!authState.enabled) return true;
  return !!(authState.authenticated && !authState.mustChangePassword);
}

async function ensureProtectedBootstrap() {
  if (protectedBootstrapStarted) return;
  if (!canUseProtectedApi()) return;
  protectedBootstrapStarted = true;
  await initializeProtectedBootstrap();
}


const __nativeFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const res = await __nativeFetch(...args);
  if (res && (res.status === 401 || res.status === 403)) {
    try {
      const data = await res.clone().json();
      const detail = String((data && data.detail) || '');
      if (detail === 'AUTH_REQUIRED') handleAuthRequirement('login');
      else if (detail === 'PASSWORD_CHANGE_REQUIRED') handleAuthRequirement('change-password');
    } catch (_) {}
  }
  return res;
};

const statusBox = el('status');
const resultBox = el('result');
const resultsList = el('results_list');
const extraPre = el('extra_pre');
const extraSections = el('extra_sections');
const refAudioBox = el('ref_audio_box');
const refAudioInput = el('ref_audio');
const refAudioBtn = el('ref_audio_btn');
const refAudioName = el('ref_audio_name');
const refAudioStatus = el('ref_audio_status');
const lmAudioInput = el('lm_audio');
const lmAudioBtn = el('lm_audio_btn');
const lmAudioName = el('lm_audio_name');
const lmStatus = el('lm_status');
const importJsonFileInput = el('import_json_file');
const importJsonFileBtn = el('import_json_file_btn');
const importJsonFileName = el('import_json_file_name');
const belowSimple = el('below_simple');

const clientIpEl = el('client_ip');
const songCounterEl = el('song_counter');
const gpuInfoEl = el('gpu_info');
const noticeBox = el('notice');

const modelSelect = el('model_select');

const loraSelect = el('lora_select');
const loraWeight = el('lora_weight');
const loraWeightNum = el('lora_weight_num');

const __browserNumberLocale = (() => {
  try {
    const langs = Array.isArray(navigator.languages) ? navigator.languages : [];
    return String(langs[0] || navigator.language || 'en-US');
  } catch (_) {
    return 'en-US';
  }
})();

function readNumericInputValue(node) {
  if (!node) return null;
  try {
    if (node.type === 'number') {
      const viaNumber = node.valueAsNumber;
      if (Number.isFinite(viaNumber)) return viaNumber;
    }
  } catch (_) {}
  const raw = String(node.value ?? '').trim().replace(',', '.');
  if (raw === '' || raw === '-' || raw === '.' || raw === '-.') return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function writeNumericInputValue(node, value, { decimals = null, preferValueAsNumber = true } = {}) {
  if (!node) return;
  const n = Number(value);
  if (!Number.isFinite(n)) return;
  try { node.setAttribute('lang', __browserNumberLocale); } catch (_) {}
  try {
    if (node.type === 'number' && preferValueAsNumber) {
      node.valueAsNumber = n;
      if (node.value !== '') return;
    }
  } catch (_) {}
  if (decimals == null) node.value = String(n);
  else node.value = Number(n).toFixed(decimals);
}

function getNumericDecimals(node) {
  if (!node) return null;
  const stepRaw = String(node.step ?? '').trim().replace(',', '.');
  if (!stepRaw || stepRaw === 'any') return null;
  const idx = stepRaw.indexOf('.');
  return idx >= 0 ? Math.max(0, stepRaw.length - idx - 1) : 0;
}

function clampNumericValueToAttrs(node, value) {
  const parsed = (typeof value === 'number') ? value : readNumericInputValue({ value, type: 'text' });
  if (!Number.isFinite(parsed)) return null;
  const minRaw = String(node?.min ?? '').trim().replace(',', '.');
  const maxRaw = String(node?.max ?? '').trim().replace(',', '.');
  const min = minRaw !== '' ? Number(minRaw) : null;
  const max = maxRaw !== '' ? Number(maxRaw) : null;
  let out = parsed;
  if (Number.isFinite(min)) out = Math.max(min, out);
  if (Number.isFinite(max)) out = Math.min(max, out);
  return out;
}

function commitStandaloneNumericField(node, { decimals = null } = {}) {
  if (!node) return;
  const raw = String(node.value ?? '').trim();
  if (!raw) return;
  const v = clampNumericValueToAttrs(node, readNumericInputValue(node));
  if (v == null) return;
  writeNumericInputValue(node, v, { decimals: (decimals == null ? getNumericDecimals(node) : decimals), preferValueAsNumber: true });
}

function bindStandaloneNumericCommit(node, opts = {}) {
  if (!node || node.dataset.numericCommitBound === '1') return;
  node.dataset.numericCommitBound = '1';
  const commit = () => commitStandaloneNumericField(node, opts);
  node.addEventListener('change', commit);
  node.addEventListener('blur', commit);
  node.addEventListener('keydown', (e) => {
    commitNumericFieldOnEnter(e, node, commit);
  });
}


function __getNumericBlurSink() {
  let sink = document.getElementById('numeric_enter_blur_sink');
  if (sink) return sink;
  try {
    sink = document.createElement('button');
    sink.id = 'numeric_enter_blur_sink';
    sink.type = 'button';
    sink.tabIndex = 0;
    sink.setAttribute('aria-hidden', 'true');
    sink.style.position = 'fixed';
    sink.style.left = '-9999px';
    sink.style.top = '-9999px';
    sink.style.width = '1px';
    sink.style.height = '1px';
    sink.style.opacity = '0';
    sink.style.pointerEvents = 'none';
    document.body.appendChild(sink);
    return sink;
  } catch (_) {
    return null;
  }
}

function __focusAfterNumericEnter(node) {
  const submitBtn = el('submit');
  try {
    if (submitBtn && submitBtn.focus) {
      submitBtn.focus({ preventScroll: true });
      return true;
    }
  } catch (_) {}
  try {
    const sink = __getNumericBlurSink();
    if (sink && sink.focus) {
      sink.focus({ preventScroll: true });
      return true;
    }
  } catch (_) {}
  try {
    if (document.body) {
      if (!document.body.hasAttribute('tabindex')) document.body.setAttribute('tabindex', '-1');
      document.body.focus({ preventScroll: true });
      return true;
    }
  } catch (_) {}
  return false;
}

function commitNumericFieldOnEnter(e, node, commitFn) {
  if (!e || e.key !== 'Enter' || e.repeat) return false;
  e.preventDefault();
  try { e.stopPropagation(); } catch (_) {}

  let didFinalize = false;
  const finalize = () => {
    if (didFinalize) return;
    didFinalize = true;
    try { commitFn && commitFn(); } catch (_) {}
    try { node && node.dispatchEvent && node.dispatchEvent(new Event('change', { bubbles: true })); } catch (_) {}
    try { if (document.activeElement === node && node && node.blur) node.blur(); } catch (_) {}
    const finishFocusExit = () => {
      try {
        if (document.activeElement === node) {
          __focusAfterNumericEnter(node);
          if (document.activeElement === node && node && node.blur) node.blur();
        }
      } catch (_) {}
    };
    try { queueMicrotask(finishFocusExit); } catch (_) {}
    try { requestAnimationFrame(finishFocusExit); } catch (_) { try { setTimeout(finishFocusExit, 0); } catch (_) {} }
    try { setTimeout(finishFocusExit, 24); } catch (_) {}
  };

  finalize();
  return true;
}

function configureNumericInputsForLocale() {
  document.querySelectorAll('input[type="number"]').forEach((node) => {
    try { node.setAttribute('lang', __browserNumberLocale); } catch (_) {}
    try { node.setAttribute('inputmode', 'decimal'); } catch (_) {}
    bindStandaloneNumericCommit(node);
  });
}



let _loraCatalogItems = [];
let _loraLabelToEntry = new Map();
let _loraIdToEntry = new Map();



const __jobRequestSnapshots = new Map();



function setFilePickName(node, file) {
  if (!node) return;
  if (file && file.name) {
    const name = String(file.name);
    node.removeAttribute('data-i18n');
    node.textContent = name;
    node.title = name;
    return;
  }
  node.setAttribute('data-i18n', 'status.no_file_selected');
  node.textContent = t('status.no_file_selected');
  node.title = t('status.no_file_selected');
  applyTranslations();
}

async function getResponseErrorMessage(res, kind) {
  let detail = '';
  try {
    const data = await res.clone().json();
    if (typeof data === 'string') detail = data;
    else if (data && typeof data.detail !== 'undefined') detail = String(data.detail || '').trim();
    else if (data && typeof data.message !== 'undefined') detail = String(data.message || '').trim();
  } catch (_) {
    try {
      detail = String((await res.text()) || '').trim();
    } catch (_) {
      detail = '';
    }
  }
  const lowered = detail.toLowerCase();
  if (kind === 'lm-transcribe' && (res.status === 404 || detail === '{"detail":"Not Found"}' || lowered === 'not found' || lowered.includes('"detail":"not found"') || lowered.includes('upstream llm endpoint returned not found'))) {
    return t('lm.transcribe_not_available');
  }
  if (detail.startsWith('{') && detail.endsWith('}')) {
    try {
      const parsed = JSON.parse(detail);
      if (parsed && typeof parsed.detail !== 'undefined') {
        return localizeApiErrorMessage(String(parsed.detail || '').trim() || detail, kind);
      }
    } catch (_) {}
  }
  return localizeApiErrorMessage(detail || `${res.status} ${res.statusText || ''}`.trim(), kind);
}

function localizeApiErrorMessage(detail, kind) {
  const raw = String(detail || '').trim();
  if (!raw) return raw;
  const map = {
    'Missing email or password.': 'auth.error.missing_email_or_password',
    'Invalid credentials.': 'auth.error.invalid_credentials',
    'New password must be at least 10 characters long.': 'auth.error.password_too_short',
    'User not found.': 'auth.error.user_not_found',
    'Enter a valid email address.': 'auth.error.invalid_email',
    'User already exists.': 'auth.error.user_already_exists',
    'You cannot delete your own account.': 'auth.error.delete_self',
    'You cannot delete the last admin account.': 'auth.error.delete_last_admin',
    'Admin only.': 'auth.error.admin_only',
    'Auth disabled.': 'auth.error.auth_disabled',
    'AUTH_REQUIRED': 'auth.status.session_required',
    'PASSWORD_CHANGE_REQUIRED': 'auth.status.password_required',
  };
  const key = map[raw];
  if (key) return t(key);
  return raw;
}

function formatAuthTime(value) {
  if (!value) return '—';
  try {
    const d = new Date(Number(value) * 1000);
    return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
  } catch (_) {
    return '—';
  }
}

function setAuthOverlayMessage(message) {
  if (!authOverlayStatus) return;
  authOverlayStatus.textContent = message ? String(message) : '';
}

function renderAdminUsers(users) {
  if (!authAdminUsers) return;
  const items = Array.isArray(users) ? users : [];
  if (!items.length) {
    authAdminUsers.textContent = t('auth.admin.no_users');
    authAdminUsers.classList.remove('auth-user-list');
    return;
  }
  const currentEmail = String(authState.user?.email || '').trim().toLowerCase();
  authAdminUsers.classList.add('auth-user-list');
  authAdminUsers.innerHTML = items.map((user) => {
    const email = String(user.email || '');
    const role = String(user.role || 'user').toLowerCase();
    const roleLabel = t(role === 'admin' ? 'auth.role.admin' : 'auth.role.user');
    const must = user.must_change_password ? t('auth.admin.must_change') : '';
    const last = t('auth.admin.last_login') + ': ' + formatAuthTime(user.last_login_at);
    const isSelf = email.trim().toLowerCase() === currentEmail;
    const delLabel = isSelf ? t('auth.admin.delete_self_disabled') : t('auth.admin.delete');
    return `<div class="auth-user-row"><div><strong>${escapeHtml(email)}</strong><div class="muted small">${escapeHtml(roleLabel)}${must ? ' • ' + escapeHtml(must) : ''}</div></div><div class="auth-user-actions"><div class="muted small">${escapeHtml(last)}</div><button class="btn ghost small auth-user-delete" type="button" data-email="${encodeURIComponent(email)}" ${isSelf ? 'disabled' : ''}>${escapeHtml(delLabel)}</button></div></div>`;
  }).join('');
  if (!authAdminUsers.dataset.deleteBound) {
    authAdminUsers.dataset.deleteBound = '1';
    authAdminUsers.addEventListener('click', async (e) => {
      const btn = e.target?.closest?.('.auth-user-delete');
      if (!btn || btn.disabled) return;
      const email = decodeURIComponent(String(btn.getAttribute('data-email') || ''));
      if (!email) return;
      const msg = t('auth.admin.delete_confirm', { email });
      if (!window.confirm(msg)) return;
      const prev = btn.textContent;
      btn.disabled = true;
      btn.textContent = t('auth.admin.deleting');
      try {
        const res = await fetch(`/api/admin/users?email=${encodeURIComponent(email)}`, { method: 'DELETE', cache: 'no-store' });
        if (!res.ok) throw new Error(await getResponseErrorMessage(res, 'admin-delete-user'));
        const data = await res.json();
        const row = btn.closest('.auth-user-row');
        if (Array.isArray(data?.users)) {
          renderAdminUsers(data.users);
        } else if (row) {
          row.remove();
        }
        if (authAdminStatus) authAdminStatus.textContent = t('auth.admin.deleted', { email });
        loadAdminUsers().catch((reloadErr) => {
          console.warn('admin user reload failed after delete', reloadErr);
          if (authAdminStatus) {
            authAdminStatus.textContent = `${t('auth.admin.deleted', { email })} · ${t('auth.admin.reload_warning')}`;
          }
        });
      } catch (err) {
        if (authAdminStatus) authAdminStatus.textContent = t('auth.admin.delete_failed', { msg: err.message || String(err) });
        btn.disabled = false;
        btn.textContent = prev;
      }
    });
  }
}

function renderAdminEvents(events) {
  if (!authAdminEvents) return;
  const items = Array.isArray(events) ? events : [];
  if (!items.length) {
    authAdminEvents.textContent = t('auth.admin.audit_empty');
    authAdminEvents.classList.remove('auth-user-list');
    return;
  }
  authAdminEvents.classList.add('auth-user-list');
  authAdminEvents.innerHTML = items.map((ev) => {
    const when = formatAuthTime(ev.ts);
    const eventName = String(ev.event || 'event');
    const eventKey = `auth.event.${eventName}`;
    const eventLabel = t(eventKey) === eventKey ? eventName : t(eventKey);
    const email = String(ev.email || '—');
    const ip = String(ev.ip || '—');
    const ok = ev.ok ? t('auth.event.ok') : t('auth.event.fail');
    const detail = String(ev.detail || '');
    return `<div class="auth-user-row"><div><strong>${escapeHtml(eventLabel)}</strong><div class="muted small">${escapeHtml(email)} • ${escapeHtml(ip)} • ${escapeHtml(ok)}</div></div><div class="muted small">${escapeHtml(when)}${detail ? `<br />${escapeHtml(detail)}` : ''}</div></div>`;
  }).join('');
}

function updateAuthChrome() {
  document.body.classList.toggle('auth-locked', !!(authState.enabled && (!authState.authenticated || authState.mustChangePassword)));
  if (authBar) authBar.classList.toggle('hidden', !(authState.enabled && authState.authenticated));
  if (authUserLabel) {
    if (authState.authenticated && authState.user) {
      const role = String(authState.user.role || 'user').toLowerCase();
      const roleLabel = t(role === 'admin' ? 'auth.role.admin' : 'auth.role.user');
      authUserLabel.textContent = `${authState.user.email} · ${roleLabel}`;
    } else {
      authUserLabel.textContent = '';
    }
  }
  if (authAdminToggleBtn) authAdminToggleBtn.classList.toggle('hidden', !authState.isAdmin);
  if (authAdminPanel && !authState.isAdmin) authAdminPanel.classList.add('hidden');
}

function setAuthOverlayMode(mode) {
  if (!authOverlay) return;
  const loginMode = mode !== 'change-password';
  authOverlay.classList.toggle('hidden', mode === 'hidden');
  if (authLoginBox) authLoginBox.classList.toggle('hidden', !loginMode);
  if (authChangeBox) authChangeBox.classList.toggle('hidden', loginMode);
  if (authOverlayTitle) authOverlayTitle.textContent = t(loginMode ? 'auth.login.title' : 'auth.change.title');
  if (authOverlayHelp) authOverlayHelp.textContent = t(loginMode ? 'auth.login.help' : 'auth.change.help');
  requestAnimationFrame(() => {
    const target = loginMode ? authLoginEmail : authChangePassword;
    try { target?.focus(); } catch (_) {}
  });
}

function handleAuthRequirement(kind) {
  if (!authState.enabled) return;
  authState.authenticated = false;
  authState.mustChangePassword = kind === 'change-password';
  setAuthOverlayMode(kind === 'change-password' ? 'change-password' : 'login');
  setAuthOverlayMessage(t(kind === 'change-password' ? 'auth.status.password_required' : 'auth.status.session_required'));
  updateAuthChrome();
}

async function loadAdminUsers() {
  if (!authState.isAdmin) return;
  try {
    const [usersRes, eventsRes] = await Promise.all([
      fetch('/api/admin/users', { cache: 'no-store' }),
      fetch('/api/admin/auth-events?limit=100', { cache: 'no-store' }),
    ]);
    if (!usersRes.ok) throw new Error(await getResponseErrorMessage(usersRes, 'admin-users'));
    const usersData = await usersRes.json();
    renderAdminUsers(usersData.users || []);
    if (!eventsRes.ok) throw new Error(await getResponseErrorMessage(eventsRes, 'admin-events'));
    const eventsData = await eventsRes.json();
    renderAdminEvents(eventsData.events || []);
  } catch (e) {
    if (authAdminUsers) authAdminUsers.textContent = t('auth.admin.list_failed', { msg: e.message || String(e) });
    if (authAdminEvents) authAdminEvents.textContent = t('auth.admin.audit_failed', { msg: e.message || String(e) });
  }
}

async function loadAuthStatus() {
  const res = await __nativeFetch('/api/auth/status', { cache: 'no-store' });
  const data = res.ok ? await res.json() : { enabled: false, authenticated: true, must_change_password: false, user: null, is_admin: false };
  authState.enabled = !!data.enabled;
  authState.authenticated = !!data.authenticated;
  authState.mustChangePassword = !!data.must_change_password;
  authState.user = data.user || null;
  authState.isAdmin = !!data.is_admin;
  authState.resolved = true;
  updateAuthChrome();
  if (!authState.enabled) {
    setAuthOverlayMode('hidden');
    return data;
  }
  if (!authState.authenticated) {
    setAuthOverlayMode('login');
    setAuthOverlayMessage('');
  } else if (authState.mustChangePassword) {
    setAuthOverlayMode('change-password');
    setAuthOverlayMessage(t('auth.status.password_required'));
  } else {
    setAuthOverlayMode('hidden');
    setAuthOverlayMessage('');
    if (authState.isAdmin) await loadAdminUsers();
  }
  await ensureProtectedBootstrap();
  return data;
}

async function submitLogin() {
  const email = String(authLoginEmail?.value || '').trim();
  const password = String(authLoginPassword?.value || '');
  try {
    const res = await __nativeFetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error(await getResponseErrorMessage(res, 'auth-login'));
    await loadAuthStatus();
    if (authState.authenticated && !authState.mustChangePassword) window.location.reload();
  } catch (e) {
    setAuthOverlayMessage(t('auth.status.login_failed', { msg: e.message || String(e) }));
  }
}

async function submitPasswordChange() {
  const p1 = String(authChangePassword?.value || '');
  const p2 = String(authChangePasswordConfirm?.value || '');
  if (p1.length < 10) {
    setAuthOverlayMessage(t('auth.status.password_short'));
    return;
  }
  if (p1 !== p2) {
    setAuthOverlayMessage(t('auth.status.password_mismatch'));
    return;
  }
  try {
    const res = await fetch('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_password: p1 }),
    });
    if (!res.ok) throw new Error(await getResponseErrorMessage(res, 'auth-change'));
    if (authChangePassword) authChangePassword.value = '';
    if (authChangePasswordConfirm) authChangePasswordConfirm.value = '';
    setAuthOverlayMessage(t('auth.status.password_changed'));
    await loadAuthStatus();
    if (authState.authenticated && !authState.mustChangePassword) window.location.reload();
  } catch (e) {
    setAuthOverlayMessage(t('auth.status.password_change_failed', { msg: e.message || String(e) }));
  }
}

async function submitCreateUser() {
  const email = String(authAdminEmail?.value || '').trim();
  const role = String(authAdminRole?.value || 'user');
  if (authAdminStatus) authAdminStatus.textContent = '';
  try {
    const res = await fetch('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, role }),
    });
    if (!res.ok) throw new Error(await getResponseErrorMessage(res, 'admin-create'));
    const data = await res.json();
    if (authAdminStatus) authAdminStatus.textContent = t('auth.admin.created', { email: data?.user?.email || email });
    if (authAdminPasswordBox) authAdminPasswordBox.classList.remove('hidden');
    if (authAdminPassword) authAdminPassword.textContent = String(data.temporary_password || '');
    if (authAdminEmail) authAdminEmail.value = '';
    await loadAdminUsers();
  } catch (e) {
    if (authAdminStatus) authAdminStatus.textContent = t('auth.admin.create_failed', { msg: e.message || String(e) });
  }
}

function bindAuthUi() {
  if (authLoginForm && !authLoginForm.dataset.bound) {
    authLoginForm.dataset.bound = '1';
    authLoginForm.addEventListener('submit', (e) => {
      e.preventDefault();
      submitLogin();
    });
  } else if (authLoginSubmit && !authLoginSubmit.dataset.bound) {
    authLoginSubmit.dataset.bound = '1';
    authLoginSubmit.addEventListener('click', submitLogin);
  }
  if (authChangeSubmit && !authChangeSubmit.dataset.bound) {
    authChangeSubmit.dataset.bound = '1';
    authChangeSubmit.addEventListener('click', submitPasswordChange);
  }
  if (authChangePasswordConfirm && !authChangePasswordConfirm.dataset.bound) {
    authChangePasswordConfirm.dataset.bound = '1';
    authChangePasswordConfirm.addEventListener('keydown', (e) => { if (e.key === 'Enter') submitPasswordChange(); });
  }
  if (authLogoutBtn && !authLogoutBtn.dataset.bound) {
    authLogoutBtn.dataset.bound = '1';
    authLogoutBtn.addEventListener('click', async () => {
      try { await fetch('/api/auth/logout', { method: 'POST' }); } catch (_) {}
      await loadAuthStatus();
    });
  }
  if (authAdminToggleBtn && !authAdminToggleBtn.dataset.bound) {
    authAdminToggleBtn.dataset.bound = '1';
    authAdminToggleBtn.addEventListener('click', async () => {
      if (!authAdminPanel) return;
      const willShow = authAdminPanel.classList.contains('hidden');
      authAdminPanel.classList.toggle('hidden', !willShow);
      if (willShow) await loadAdminUsers();
    });
  }
  if (authAdminCreate && !authAdminCreate.dataset.bound) {
    authAdminCreate.dataset.bound = '1';
    authAdminCreate.addEventListener('click', submitCreateUser);
  }
}

function setupFilePickButton(buttonEl, inputEl, nameEl) {
  if (!buttonEl || !inputEl) return;
  buttonEl.addEventListener('click', () => inputEl.click());
  inputEl.addEventListener('change', () => {
    const file = inputEl.files && inputEl.files[0] ? inputEl.files[0] : null;
    setFilePickName(nameEl, file);
  });
  setFilePickName(nameEl, null);
}

const __CHORD_NOTE_INDEX = { C:0, 'B#':0, 'C#':1, Db:1, D:2, 'D#':3, Eb:3, E:4, Fb:4, 'E#':5, F:5, 'F#':6, Gb:6, G:7, 'G#':8, Ab:8, A:9, 'A#':10, Bb:10, B:11, Cb:11 };
const __CHORD_NOTE_NAMES_SHARP = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
const __CHORD_NOTE_NAMES_FLAT = ['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B'];
const __CHORD_ROMAN_BASE_INTERVALS = [0,2,4,5,7,9,11];
const __CHORD_ROMAN_MAP = { I:1, II:2, III:3, IV:4, V:5, VI:6, VII:7 };
const __CHORD_QUALITY_SUFFIX = { major:'', minor:'m', dim:'dim', aug:'aug', maj7:'maj7', min7:'m7', dom7:'7', dim7:'dim7', sus2:'sus2', sus4:'sus4' };

function keyPrefersFlats(rootKey, scale) {
  const root = String(rootKey || 'C').trim();
  const mode = String(scale || 'major').toLowerCase() === 'minor' ? 'minor' : 'major';
  const flatMajor = new Set(['F','Bb','Eb','Ab','Db','Gb','Cb']);
  const flatMinor = new Set(['D','G','C','F','Bb','Eb','Ab']);
  if (root.includes('b')) return true;
  if (root.includes('#')) return false;
  return mode === 'minor' ? flatMinor.has(root) : flatMajor.has(root);
}

function noteNameForSemitone(semitone, rootKey, scale) {
  const idx = ((Number(semitone) % 12) + 12) % 12;
  return (keyPrefersFlats(rootKey, scale) ? __CHORD_NOTE_NAMES_FLAT : __CHORD_NOTE_NAMES_SHARP)[idx];
}

const __KEY_ROOT_OPTIONS = ['C', 'C#', 'Db', 'D', 'D#', 'Eb', 'E', 'F', 'F#', 'Gb', 'G', 'G#', 'Ab', 'A', 'A#', 'Bb', 'B'];
const __KEY_MODE_OPTIONS = ['major', 'minor'];
let __keyScaleControlSync = false;

function normalizeKeyModeToken(value) {
  const raw = String(value || '').trim().toLowerCase();
  if (!raw) return '';
  if (['minor', 'min', 'm'].includes(raw)) return 'minor';
  if (['major', 'maj'].includes(raw)) return 'major';
  return '';
}

function normalizeTimeSignatureValue(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const lowered = raw.toLowerCase();
  if (['2', '2/4'].includes(lowered)) return '2/4';
  if (['3', '3/4'].includes(lowered)) return '3/4';
  if (['4', '4/4', 'c'].includes(lowered)) return '4/4';
  if (['6', '6/8'].includes(lowered)) return '6/8';
  return '';
}

function buildLmTranscribeSuccessMessage(data) {
  const labels = [];
  if ((data.caption || '').trim()) labels.push(t('lm.field_caption'));
  if ((data.lyrics || '').trim()) labels.push(t('lm.field_lyrics'));
  if (data.bpm != null && String(data.bpm).trim() !== '') labels.push(t('lm.field_bpm'));
  if (data.duration != null && String(data.duration).trim() !== '') labels.push(t('lm.field_duration'));
  if ((data.keyscale || '').trim()) labels.push(t('lm.field_keyscale'));
  if ((data.vocal_language || '').trim() && String(data.vocal_language).trim().toLowerCase() !== 'unknown') labels.push(t('lm.field_language'));
  const normalizedTS = normalizeTimeSignatureValue(data.timesignature || '');
  if (normalizedTS) labels.push(t('lm.field_timesignature'));
  const fields = labels.join(', ');
  return t('lm.transcribe_success', { fields });
}

function parseKeyScaleValue(value) {
  const raw = String(value || '').trim();
  if (!raw) return { root: '', mode: '' };
  const m = raw.match(/^([A-Ga-g])([#b]?)(?:\s+|-|\/)?(major|minor|maj|min|m)$/i);
  if (m) {
    const root = (m[1].toUpperCase() + (m[2] || '')).trim();
    const mode = normalizeKeyModeToken(m[3]);
    if (__KEY_ROOT_OPTIONS.includes(root) && __KEY_MODE_OPTIONS.includes(mode)) return { root, mode };
  }
  const parts = raw.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    const root = (parts[0][0] || '').toUpperCase() + (parts[0].slice(1) || '');
    const mode = normalizeKeyModeToken(parts[parts.length - 1]);
    if (__KEY_ROOT_OPTIONS.includes(root) && __KEY_MODE_OPTIONS.includes(mode)) return { root, mode };
  }
  return { root: '', mode: '' };
}

function formatKeyScaleValue(root, mode) {
  const cleanRoot = String(root || '').trim();
  const cleanMode = normalizeKeyModeToken(mode);
  if (!cleanRoot || !cleanMode) return '';
  return `${cleanRoot} ${cleanMode}`;
}

function getKeyScaleFromControls() {
  const hidden = el('keyscale');
  const rootEl = el('key_root');
  const modeEl = el('key_mode');
  if (rootEl && modeEl) {
    return formatKeyScaleValue(rootEl.value, modeEl.value);
  }
  return hidden?.value || '';
}

function setKeyScaleValue(value, { dispatch = true } = {}) {
  const hidden = el('keyscale');
  const rootEl = el('key_root');
  const modeEl = el('key_mode');
  const parsed = parseKeyScaleValue(value);
  const rawValue = String(value || '').trim();
  const hasParsedValue = !!(parsed.root && parsed.mode);
  const finalValue = hasParsedValue ? formatKeyScaleValue(parsed.root, parsed.mode) : rawValue;

  __keyScaleControlSync = true;
  try {
    if (rootEl) rootEl.value = parsed.root || 'C';
    if (modeEl) modeEl.value = parsed.mode || 'major';
    if (hidden) hidden.value = finalValue;
  } finally {
    __keyScaleControlSync = false;
  }

  if (dispatch && hidden) {
    hidden.dispatchEvent(new Event('input', { bubbles: true }));
    hidden.dispatchEvent(new Event('change', { bubbles: true }));
  }
  return finalValue;
}

function syncKeyScaleHiddenFromControls({ dispatch = true } = {}) {
  const hidden = el('keyscale');
  const root = el('key_root')?.value || '';
  const mode = normalizeKeyModeToken(el('key_mode')?.value || '') || 'major';
  const finalValue = root ? formatKeyScaleValue(root, mode) : '';
  if (hidden) hidden.value = finalValue;
  if (dispatch && hidden) {
    hidden.dispatchEvent(new Event('input', { bubbles: true }));
    hidden.dispatchEvent(new Event('change', { bubbles: true }));
  }
  return finalValue;
}

function fillSelectOptions(selectEl, values, labelFn) {
  if (!selectEl) return;
  selectEl.innerHTML = '';
  values.forEach((value) => {
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = labelFn(value);
    selectEl.appendChild(opt);
  });
}

function setupKeyScaleControls() {
  const hidden = el('keyscale');
  const rootEl = el('key_root');
  const modeEl = el('key_mode');
  if (!hidden || !rootEl || !modeEl) return;

  fillSelectOptions(rootEl, __KEY_ROOT_OPTIONS, (value) => value);
  fillSelectOptions(modeEl, __KEY_MODE_OPTIONS, (value) => (
    value === 'minor' ? t('opt.key_mode_minor') : t('opt.key_mode_major')
  ));
  if (!rootEl.value) rootEl.value = 'C';
  if (!modeEl.value) modeEl.value = 'major';

  const onControlChange = () => {
    if (__keyScaleControlSync) return;
    syncKeyScaleHiddenFromControls({ dispatch: true });
  };
  if (!rootEl.dataset.boundKeyScale) {
    rootEl.addEventListener('change', onControlChange);
    rootEl.addEventListener('input', onControlChange);
    modeEl.addEventListener('change', onControlChange);
    modeEl.addEventListener('input', onControlChange);
    hidden.addEventListener('change', () => {
      if (__keyScaleControlSync) return;
      setKeyScaleValue(hidden.value, { dispatch: false });
    });
    hidden.addEventListener('input', () => {
      if (__keyScaleControlSync) return;
      setKeyScaleValue(hidden.value, { dispatch: false });
    });
    rootEl.dataset.boundKeyScale = '1';
  }

  setKeyScaleValue(hidden.value, { dispatch: false });
}

function refreshKeyScaleControlLabels() {
  const rootEl = el('key_root');
  const modeEl = el('key_mode');
  if (!rootEl || !modeEl) return;
  Array.from(modeEl.options || []).forEach((opt) => {
    if (opt.value === 'major') opt.textContent = t('opt.key_mode_major');
    else if (opt.value === 'minor') opt.textContent = t('opt.key_mode_minor');
  });
}

function parseRomanChordToken(token) {
  let rest = String(token || '').trim();
  if (!rest) return null;
  let modifier = '';
  if (/^[#b♯♭]/.test(rest)) {
    modifier = rest[0] === '♯' ? '#' : (rest[0] === '♭' ? 'b' : rest[0]);
    rest = rest.slice(1);
  }
  const m = rest.match(/^(VII|VI|IV|III|II|V|I|vii|vi|iv|iii|ii|v|i)/);
  if (!m) return null;
  const romanPart = m[0];
  const suffix = rest.slice(romanPart.length).toLowerCase();
  const isMinor = romanPart === romanPart.toLowerCase();
  const degree = __CHORD_ROMAN_MAP[romanPart.toUpperCase()] || 1;
  let quality = isMinor ? 'minor' : 'major';
  if (suffix.includes('maj7')) quality = 'maj7';
  else if (suffix.includes('dim7')) quality = 'dim7';
  else if (suffix.includes('dim') || suffix === '°' || suffix === 'o') quality = 'dim';
  else if (suffix.includes('aug') || suffix === '+') quality = 'aug';
  else if (suffix === '7' || suffix === 'dom7' || suffix === '9') quality = isMinor ? 'min7' : 'dom7';
  else if (suffix === 'm7') quality = 'min7';
  else if (suffix === 'sus2') quality = 'sus2';
  else if (suffix === 'sus4') quality = 'sus4';
  return { degree, quality, modifier, roman: token };
}

function resolveChordProgression(romanStr, key, scale) {
  const rootKey = String(key || 'C').trim();
  const rootIndex = __CHORD_NOTE_INDEX[rootKey];
  if (rootIndex == null) throw new Error(t('error.chord_key_invalid'));
  const tokens = String(romanStr || '').split(/[\s,\-–—]+/).filter(Boolean);
  if (!tokens.length) throw new Error(t('error.chord_empty'));
  return tokens.map((tok) => {
    const parsed = parseRomanChordToken(tok);
    if (!parsed) throw new Error(t('error.chord_token_invalid', { token: tok }));
    // Resolve roman degrees against the tonic-major degree grid. Lowercase still controls
    // chord quality, while accidentals alter the degree itself. That keeps minor progressions
    // like A minor: i - iv - bVII - iv at Am - Dm - G - Dm instead of the nonsense F#.
    let semitone = (rootIndex + __CHORD_ROMAN_BASE_INTERVALS[(parsed.degree - 1) % 7]) % 12;
    if (parsed.modifier === '#') semitone = (semitone + 1) % 12;
    if (parsed.modifier === 'b') semitone = (semitone + 11) % 12;
    return `${noteNameForSemitone(semitone, rootKey, scale)}${__CHORD_QUALITY_SUFFIX[parsed.quality] || ''}`;
  });
}

function formatChordProgressionForGeneration(romanStr, key, scale) {
  const chords = resolveChordProgression(romanStr, key, scale);
  const scaleLabel = String(scale || 'major').toLowerCase() === 'minor' ? 'Minor' : 'Major';
  const chordNamesDash = chords.join(' - ');
  const chordNamesInline = chords.join(' ');
  return {
    roman: String(romanStr || "").trim(),
    chords,
    styleTag: `${key} ${scaleLabel} key, chord progression ${chordNamesDash}, harmonic structure, ${scaleLabel.toLowerCase()} tonality`,
    lyricsTag: `[Chord Progression: ${chordNamesDash}]`,
    sectionChordTag: `Chords: ${chordNamesInline}`,
    keyScaleTag: `${key} ${scaleLabel}`,
    description: `${key} ${scaleLabel}: ${romanStr} → ${chordNamesDash}`,
  };
}


function normalizeMinorRomanDisplay(romanStr) {
  const scaleName = String(el('chord_scale')?.value || '').toLowerCase();
  if (scaleName !== 'minor') return String(romanStr || '').trim();
  return String(romanStr || '')
    .replace(/(^|\s|[-,–—])VI(?=$|\s|[-,–—])/g, '$1bVI')
    .replace(/(^|\s|[-,–—])VII(?=$|\s|[-,–—])/g, '$1bVII')
    .trim();
}

function inferChordProgressionFamily(scale, contextText = '') {
  const lowerScale = String(scale || 'major').toLowerCase() === 'minor' ? 'minor' : 'major';
  const text = String(contextText || '').toLowerCase();
  const hasAny = (items) => items.some((item) => text.includes(item));
  const families = lowerScale === 'minor'
    ? [
      ['dark', ['dark', 'sad', 'melanch', 'brood', 'night', 'shadow', 'doom', 'goth', 'trap', 'drama', 'tension', 'pain']],
      ['cinematic', ['cinematic', 'epic', 'score', 'soundtrack', 'trailer', 'orches', 'heroic', 'battle', 'movie']],
      ['ballad', ['ballad', 'piano', 'acoustic', 'love', 'heart', 'emotional', 'romance', 'singer', 'songwriter']],
      ['dance', ['dance', 'edm', 'house', 'club', 'techno', 'disco', 'festival', 'drop']],
      ['pop', ['pop', 'indie', 'alt', 'electro', 'synth', 'radio']],
      ['modal', ['folk', 'modal', 'world', 'celtic', 'medieval', 'ambient']],
      ['dominant', ['dominant', 'phrygian', 'flamenco', 'dramatic cadence', 'cadence']],
    ]
    : [
      ['dance', ['dance', 'edm', 'house', 'club', 'future bass', 'festival', 'drop', 'disco']],
      ['ballad', ['ballad', 'piano', 'acoustic', 'love', 'romance', 'heart', 'emotional', 'wedding']],
      ['cinematic', ['cinematic', 'epic', 'score', 'soundtrack', 'trailer', 'orches', 'heroic', 'movie']],
      ['rock', ['rock', 'guitar', 'band', 'anthem', 'punk', 'garage']],
      ['jazz_light', ['jazz', 'neo soul', 'soul', 'r&b', 'swing', 'bossa', 'lounge']],
      ['pop', ['pop', 'indie', 'uplift', 'happy', 'bright', 'summer', 'radio']],
      ['modal', ['folk', 'modal', 'world', 'ambient', 'dream', 'cinema']],
    ];
  for (const [family, keywords] of families) {
    if (hasAny(keywords)) return family;
  }
  return lowerScale === 'minor' ? 'dark' : 'pop';
}

function inferMinorProfile(contextText = '', family = '') {
  const text = String(contextText || '').toLowerCase();
  const familyName = String(family || '').toLowerCase();
  const hasAny = (items) => items.some((item) => text.includes(item));
  if (familyName === 'cinematic' || hasAny(['cinematic', 'epic', 'score', 'soundtrack', 'trailer', 'orches', 'heroic', 'battle', 'movie'])) return 'cinematic';
  if (familyName === 'modal' || hasAny(['modal', 'folk', 'celtic', 'medieval', 'drone', 'world'])) return 'modal';
  if (familyName === 'dance' || familyName === 'pop' || hasAny(['pop', 'indie', 'alt', 'electro', 'synth', 'radio', 'dance', 'edm', 'club', 'techno'])) return 'pop';
  if (familyName === 'dominant' || hasAny(['dominant', 'harmonic minor', 'phrygian', 'flamenco', 'cadence', 'dramatic'])) return 'dominant';
  if (familyName === 'ballad' || hasAny(['ballad', 'acoustic', 'piano', 'heart', 'romance', 'singer', 'songwriter'])) return 'natural';
  if (familyName === 'dark' || hasAny(['dark', 'sad', 'melanch', 'brood', 'night', 'shadow', 'doom', 'goth', 'trap', 'tension', 'pain'])) return 'dark';
  return 'natural';
}

function inferMinorProfileFromTokens(tokens, family = '') {
  const arr = (Array.isArray(tokens) ? tokens : []).map((tok) => String(tok || '').trim()).filter(Boolean);
  if (!arr.length) return inferMinorProfile('', family);
  const bases = arr.map((tok) => tok.replace(/7|maj7|dim7|dim|aug|sus2|sus4/gi, ''));
  const hasUpperDominant = bases.some((tok) => tok === 'V' || tok === 'V7');
  const hasModal = bases.some((tok) => /^(bVI|bVII|bIII|III)$/i.test(tok));
  const modalCount = bases.filter((tok) => /^(bVI|bVII|bIII|III)$/i.test(tok)).length;
  const hasSubdom = bases.some((tok) => /^iv$/i.test(tok));
  const hasLeading = bases.some((tok) => /^ii°$/i.test(tok));
  if (hasUpperDominant && (hasLeading || modalCount <= 1)) return 'dominant';
  if (modalCount >= 2 && hasSubdom) return 'dark';
  if (hasModal && !hasSubdom) return 'modal';
  if (modalCount >= 2) return 'pop';
  return inferMinorProfile('', family);
}

function buildProgressionPatternBank() {
  return {
    major: {
      pop: [
        ['I', 'V', 'vi', 'IV'],
        ['vi', 'IV', 'I', 'V'],
        ['I', 'vi', 'IV', 'V'],
        ['I', 'IV', 'vi', 'V'],
        ['I', 'V', 'IV', 'I'],
      ],
      dance: [
        ['vi', 'IV', 'I', 'V'],
        ['I', 'V', 'vi', 'IV'],
        ['I', 'iii', 'vi', 'IV'],
        ['I', 'V', 'ii', 'IV'],
      ],
      ballad: [
        ['Imaj7', 'V', 'vi7', 'IVmaj7'],
        ['I', 'vi', 'ii', 'V'],
        ['Imaj7', 'iii7', 'vi7', 'IVmaj7'],
        ['IV', 'I', 'ii', 'V'],
      ],
      cinematic: [
        ['I', 'V', 'vi', 'iii'],
        ['I', 'IV', 'I', 'V'],
        ['vi', 'I', 'V', 'IV'],
        ['I', 'ii', 'IV', 'V'],
      ],
      rock: [
        ['I', 'IV', 'V'],
        ['I', 'V', 'IV'],
        ['I', 'bVII', 'IV', 'I'],
        ['I', 'IV', 'I', 'V'],
      ],
      jazz_light: [
        ['ii7', 'V7', 'Imaj7', 'Imaj7'],
        ['Imaj7', 'vi7', 'ii7', 'V7'],
        ['iii7', 'vi7', 'ii7', 'V7'],
        ['Imaj7', 'IVmaj7', 'ii7', 'V7'],
      ],
      modal: [
        ['I', 'bVII', 'IV', 'I'],
        ['I', 'IV', 'bVII', 'IV'],
        ['I', 'ii', 'bVII', 'IV'],
      ],
    },
    minor: {
      natural: [
        ['i', 'iv', 'v', 'i'],
        ['i7', 'iv7', 'v', 'i'],
        ['i', 'ii°', 'v', 'i'],
        ['i', 'iv', 'i', 'v'],
        ['i', 'v', 'iv', 'i'],
      ],
      dark: [
        ['i', 'iv', 'v', 'i'],
        ['i', 'iv', 'bVI', 'v'],
        ['i', 'bVI', 'iv', 'v'],
        ['i', 'ii°', 'v', 'i'],
        ['i', 'bVII', 'iv', 'v'],
      ],
      cinematic: [
        ['i', 'iv', 'bVI', 'v'],
        ['i', 'bVI', 'iv', 'i'],
        ['i', 'bIII', 'iv', 'v'],
        ['i', 'ii°', 'V', 'i'],
      ],
      dominant: [
        ['i', 'iv', 'V', 'i'],
        ['i', 'ii°', 'V', 'i'],
        ['i', 'bVI', 'V', 'i'],
        ['i7', 'iv', 'V7', 'i'],
      ],
      ballad: [
        ['i7', 'iv7', 'v', 'i'],
        ['i', 'iv', 'V', 'i'],
        ['i', 'bVI', 'iv', 'i'],
        ['i', 'ii°', 'V', 'i'],
      ],
      dance: [
        ['i', 'bVI', 'bIII', 'v'],
        ['i', 'iv', 'bVI', 'v'],
        ['i', 'bVII', 'bVI', 'v'],
      ],
      pop: [
        ['i', 'iv', 'bVI', 'v'],
        ['i', 'bVI', 'bIII', 'v'],
        ['i', 'bVII', 'iv', 'v'],
      ],
      modal: [
        ['i', 'bVII', 'iv', 'i'],
        ['i', 'bIII', 'bVII', 'i'],
        ['i', 'iv', 'bVII', 'iv'],
      ],
    },
  };
}

function varyRomanProgression(tokens, scale, family) {
  const out = Array.isArray(tokens) ? tokens.slice() : [];
  if (!out.length) return out;
  const lowerScale = String(scale || 'major').toLowerCase() === 'minor' ? 'minor' : 'major';
  const tonic = lowerScale === 'minor' ? 'i' : 'I';
  if (lowerScale === 'minor') {
    if (out.length >= 4 && !/^i/i.test(String(out[0] || ''))) out[0] = 'i';
    if (family !== 'modal' && out.length >= 4 && Math.random() < 0.18) out[out.length - 1] = Math.random() < 0.58 ? 'v' : 'V';
  } else if (out.length >= 4 && Math.random() < 0.28) {
    out[out.length - 1] = 'V';
  }
  if (family === 'ballad' && out[0] && !/7|maj7/i.test(out[0]) && Math.random() < 0.42) out[0] = lowerScale === 'minor' ? 'i7' : 'Imaj7';
  if (family === 'jazz_light' && out.length >= 4 && Math.random() < 0.48) {
    out[1] = lowerScale === 'minor' ? 'ii°' : 'ii7';
    out[2] = 'V7';
    out[3] = lowerScale === 'minor' ? tonic : 'Imaj7';
  }
  if (family === 'cinematic' && Math.random() < 0.25) out.push(tonic);
  if (out.length >= 4 && Math.random() < 0.24) {
    const rotated = out.slice(1).concat(out[0]);
    if (rotated.join(' ') !== out.join(' ')) return rotated;
  }
  return out;
}

function generateSensibleRomanProgression(scale, contextText = '') {
  const normalizedScale = String(scale || 'major').toLowerCase() === 'minor' ? 'minor' : 'major';
  const family = inferChordProgressionFamily(normalizedScale, contextText);
  generatedChordFamily = family;
  const bank = buildProgressionPatternBank();
  const minorProfile = normalizedScale === 'minor' ? inferMinorProfile(contextText, family) : '';
  const preferredKey = normalizedScale === 'minor' ? minorProfile : family;
  const familyBank = (((bank[normalizedScale] || {})[preferredKey]) || ((bank[normalizedScale] || {})[family]) || ((bank[normalizedScale] || {}).pop) || []);
  const fallbackBank = Object.values(bank[normalizedScale] || {}).flat();
  const source = familyBank.length ? familyBank : fallbackBank;
  const base = source[Math.floor(Math.random() * source.length)] || (normalizedScale === 'minor' ? ['i', 'iv', 'v', 'i'] : ['I', 'V', 'vi', 'IV']);
  const varied = varyRomanProgression(base, normalizedScale, family);
  return varied.join(' - ');
}

function sanitizeSectionChordTokens(tokens, maxLen = 4) {
  const playable = filterPlayableChordTokens(tokens);
  if (!playable.length) return [];
  const capped = playable.slice(0, Math.max(1, Number(maxLen) || 4));
  return dedupeChordTokens(capped);
}

function summarizeSectionChordTokens(tokens, maxLen = 4) {
  return sanitizeSectionChordTokens(tokens, maxLen);
}

function sanitizeResolvedChordNames(chords, maxLen = 4) {
  const out = [];
  (Array.isArray(chords) ? chords : []).forEach((name) => {
    const trimmed = String(name || '').trim();
    if (!trimmed) return;
    if (!/^([A-G](?:#|b)?)(maj7|m7|dim7|dim|aug|sus2|sus4|m|7)?$/i.test(trimmed)) return;
    if (!out.length || out[out.length - 1] !== trimmed) out.push(trimmed);
  });
  return out.slice(0, Math.max(1, Number(maxLen) || 4));
}


// ─── Rich section-aware harmonic planner ────────────────────────────────────
// Instead of deriving everything from the (often tiny) user input pool,
// we keep a large library of per-section Roman-numeral templates and pick
// one at generation time.  The input pool is still used as the PRIMARY
// source when a token from it matches — this preserves the user's key choice
// — but we no longer collapse to 2-3 chords just because the pool is small.

const _MINOR_SECTION_BANKS = {
  intro: [
    ['i', 'iv', 'bVI', 'i'],
    ['i', 'bVI', 'iv', 'i'],
    ['i7', 'iv7', 'i', 'v'],
    ['i', 'iv', 'bVII', 'i'],
    ['i', 'bIII', 'iv', 'i'],
    ['i', 'ii°', 'v', 'i'],
  ],
  verse: [
    ['i', 'iv', 'v', 'i'],
    ['i', 'bVI', 'iv', 'v'],
    ['i', 'iv', 'bVII', 'v'],
    ['i7', 'iv7', 'v', 'i'],
    ['i', 'bIII', 'iv', 'v'],
    ['i', 'ii°', 'V', 'i'],
    ['i', 'bVI', 'v', 'i'],
    ['i', 'iv', 'V', 'bVI'],
  ],
  'verse 2': [
    ['i', 'bVI', 'iv', 'i'],
    ['i', 'bIII', 'iv', 'V'],
    ['i7', 'iv7', 'V', 'i'],
    ['i', 'bVI', 'iv', 'bVII'],
    ['i', 'iv', 'bIII', 'bVI'],
    ['i', 'v', 'iv', 'i'],
  ],
  'verse 3': [
    ['i', 'iv', 'bVI', 'iv'],
    ['i7', 'bIII', 'iv', 'v'],
    ['i', 'iv', 'bIII', 'v'],
    ['i', 'ii°', 'V7', 'i'],
  ],
  'pre-chorus': [
    ['bVI', 'iv', 'V', 'i'],
    ['iv', 'V', 'i', 'iv'],
    ['bVI', 'iv', 'bVII', 'V'],
    ['iv', 'bVI', 'V', 'i'],
    ['ii°', 'V', 'i', 'bVI'],
    ['iv7', 'bVII', 'V7', 'i'],
    ['bVI', 'bIII', 'iv', 'V'],
    ['ii°', 'v', 'iv', 'V'],
  ],
  chorus: [
    ['i', 'iv', 'bVI', 'v'],
    ['i', 'bVI', 'bIII', 'v'],
    ['bVI', 'iv', 'i', 'v'],
    ['i', 'iv', 'bVII', 'V'],
    ['bVI', 'bIII', 'iv', 'i'],
    ['i', 'V', 'bVI', 'iv'],
    ['i7', 'bVI', 'iv', 'V'],
    ['i', 'bIII', 'iv', 'V'],
  ],
  'final chorus': [
    ['i', 'iv', 'bVI', 'v', 'i'],
    ['i', 'bVI', 'iv', 'V', 'i'],
    ['bVI', 'iv', 'i', 'bVI', 'V'],
    ['i', 'iv', 'V', 'bVI', 'i'],
    ['i', 'ii°', 'V7', 'bVI', 'i'],
  ],
  bridge: [
    ['bIII', 'iv', 'bVI', 'V'],
    ['bVI', 'V', 'iv', 'i'],
    ['iv', 'bVI', 'V7', 'i'],
    ['bIII', 'bVI', 'iv', 'V'],
    ['bVI', 'bIII', 'V', 'i'],
    ['iv', 'V', 'bIII', 'bVI'],
    ['i', 'V7', 'iv', 'bVI'],
    ['bVI', 'iv', 'V', 'i'],
  ],
  instrumental: [
    ['i', 'bIII', 'iv', 'bVI'],
    ['i', 'iv', 'bVII', 'bVI'],
    ['bVI', 'iv', 'i', 'bIII'],
    ['i7', 'bVI', 'iv', 'v'],
  ],
  outro: [
    ['i', 'iv', 'bVI', 'i'],
    ['i7', 'iv', 'v', 'i'],
    ['i', 'bIII', 'iv', 'i'],
    ['bVI', 'iv', 'i', 'i'],
    ['i', 'v', 'i', 'i'],
  ],
  solo: [
    ['i', 'bVI', 'bIII', 'v'],
    ['i', 'V', 'iv', 'bVI'],
    ['iv', 'bVII', 'i', 'bVI'],
  ],
  interlude: [
    ['i', 'iv', 'bVI', 'iv'],
    ['bVI', 'bIII', 'iv', 'i'],
    ['i7', 'bVI', 'iv', 'bVI'],
  ],
  'post-chorus': [
    ['i', 'iv', 'bVI', 'bVI'],
    ['bVI', 'iv', 'i', 'iv'],
    ['i', 'bIII', 'iv', 'bVI'],
  ],
};



const _MINOR_SECTION_PROFILE_BANKS = {
  natural: {
    intro: [
      ['i', 'iv', 'v', 'i'],
      ['i7', 'iv7', 'v', 'i'],
      ['i', 'ii°', 'v', 'i'],
    ],
    verse: [
      ['i', 'iv', 'v', 'i'],
      ['i7', 'iv7', 'v', 'i'],
      ['i', 'v', 'iv', 'i'],
    ],
    'verse 2': [
      ['i', 'v', 'iv', 'i'],
      ['i7', 'iv7', 'v', 'i'],
      ['i', 'ii°', 'v', 'i'],
    ],
    chorus: [
      ['i', 'iv', 'i', 'v'],
      ['i', 'iv', 'v', 'i'],
      ['i7', 'iv7', 'v', 'i'],
    ],
    'final chorus': [
      ['i', 'iv', 'v', 'i', 'i'],
      ['i7', 'iv7', 'v', 'i', 'i'],
    ],
    outro: [
      ['i', 'v', 'i', 'i'],
      ['i', 'iv', 'v', 'i'],
    ],
  },
  dark: {
    intro: [
      ['i', 'iv', 'bVI', 'i'],
      ['i', 'bVI', 'iv', 'i'],
    ],
    verse: [
      ['i', 'iv', 'bVI', 'v'],
      ['i', 'bVI', 'iv', 'v'],
    ],
    chorus: [
      ['i', 'iv', 'bVI', 'v'],
      ['i', 'bVI', 'iv', 'V'],
    ],
    bridge: [
      ['bVI', 'iv', 'V', 'i'],
      ['bIII', 'iv', 'bVI', 'V'],
    ],
  },
  cinematic: {
    intro: [
      ['i', 'bVI', 'iv', 'i'],
      ['i', 'iv', 'bVI', 'i'],
    ],
    verse: [
      ['i', 'bVI', 'iv', 'v'],
      ['i', 'bIII', 'iv', 'v'],
    ],
    'pre-chorus': [
      ['bVI', 'iv', 'V', 'i'],
      ['ii°', 'V', 'i', 'bVI'],
    ],
    chorus: [
      ['i', 'bIII', 'iv', 'V'],
      ['i', 'ii°', 'V', 'i'],
    ],
    bridge: [
      ['bIII', 'iv', 'bVI', 'V'],
      ['bVI', 'V', 'iv', 'i'],
    ],
  },
  pop: {
    verse: [
      ['i', 'iv', 'bVI', 'v'],
      ['i', 'bVII', 'iv', 'v'],
    ],
    chorus: [
      ['i', 'bVI', 'bIII', 'v'],
      ['i', 'iv', 'bVI', 'v'],
      ['bVI', 'iv', 'i', 'v'],
    ],
    'post-chorus': [
      ['i', 'bIII', 'iv', 'bVI'],
      ['i', 'iv', 'bVI', 'bVI'],
    ],
  },
  modal: {
    verse: [
      ['i', 'bVII', 'iv', 'i'],
      ['i', 'iv', 'bVII', 'iv'],
    ],
    chorus: [
      ['i', 'bVII', 'iv', 'V'],
      ['i', 'bIII', 'bVII', 'i'],
    ],
    instrumental: [
      ['i', 'iv', 'bVII', 'bVI'],
      ['bVI', 'iv', 'i', 'bIII'],
    ],
  },
  dominant: {
    verse: [
      ['i', 'iv', 'V', 'i'],
      ['i', 'ii°', 'V', 'i'],
    ],
    'pre-chorus': [
      ['ii°', 'V', 'i', 'bVI'],
      ['iv', 'V', 'i', 'iv'],
    ],
    chorus: [
      ['i', 'V', 'bVI', 'iv'],
      ['i', 'ii°', 'V7', 'i'],
      ['i7', 'bVI', 'iv', 'V'],
    ],
    outro: [
      ['i', 'iv', 'V', 'i'],
      ['i', 'ii°', 'V7', 'i'],
    ],
  },
};

const _MAJOR_SECTION_BANKS = {
  intro: [
    ['I', 'V', 'vi', 'IV'],
    ['I', 'IV', 'I', 'V'],
    ['Imaj7', 'IV', 'ii', 'V'],
    ['I', 'bVII', 'IV', 'I'],
    ['I', 'vi', 'ii', 'V'],
    ['IV', 'I', 'V', 'vi'],
  ],
  verse: [
    ['I', 'V', 'vi', 'IV'],
    ['I', 'IV', 'V', 'IV'],
    ['I', 'vi', 'IV', 'V'],
    ['I', 'ii', 'V', 'I'],
    ['I', 'iii', 'IV', 'V'],
    ['I', 'bVII', 'IV', 'V'],
    ['vi', 'IV', 'I', 'V'],
    ['I', 'IV', 'vi', 'V'],
  ],
  'verse 2': [
    ['I', 'iii', 'vi', 'IV'],
    ['Imaj7', 'IV', 'V', 'vi'],
    ['I', 'vi', 'ii7', 'V'],
    ['I', 'bVII', 'IV', 'I'],
    ['IV', 'I', 'ii', 'V'],
    ['I', 'V7', 'vi', 'IV'],
  ],
  'verse 3': [
    ['I', 'iii', 'IV', 'ii'],
    ['Imaj7', 'vi7', 'ii7', 'V7'],
    ['I', 'IV', 'bVII', 'IV'],
    ['I', 'vi', 'IV', 'ii'],
  ],
  'pre-chorus': [
    ['ii', 'V', 'I', 'V'],
    ['IV', 'V', 'vi', 'V'],
    ['ii7', 'V7', 'I', 'IV'],
    ['IV', 'I', 'V', 'V'],
    ['vi', 'ii', 'IV', 'V'],
    ['ii', 'IV', 'V', 'V'],
    ['IV', 'iii', 'ii', 'V'],
    ['vi', 'IV', 'ii', 'V'],
  ],
  chorus: [
    ['I', 'V', 'vi', 'IV'],
    ['IV', 'I', 'V', 'vi'],
    ['I', 'IV', 'I', 'V'],
    ['vi', 'IV', 'I', 'V'],
    ['I', 'iii', 'IV', 'V'],
    ['I', 'bVII', 'IV', 'V'],
    ['IV', 'V', 'I', 'vi'],
    ['I', 'V', 'IV', 'I'],
  ],
  'final chorus': [
    ['I', 'V', 'vi', 'IV', 'I'],
    ['IV', 'I', 'V', 'vi', 'I'],
    ['I', 'IV', 'V', 'vi', 'I'],
    ['I', 'bVII', 'IV', 'V', 'I'],
    ['I', 'V7', 'IV', 'I', 'I'],
  ],
  bridge: [
    ['vi', 'ii', 'V', 'I'],
    ['IV', 'iii', 'vi', 'V'],
    ['ii7', 'V7', 'Imaj7', 'IV'],
    ['vi', 'IV', 'ii', 'V'],
    ['bVII', 'IV', 'I', 'V'],
    ['IV', 'V', 'iii', 'vi'],
    ['ii', 'V', 'vi', 'IV'],
    ['iii', 'vi', 'IV', 'V'],
  ],
  instrumental: [
    ['I', 'iii', 'IV', 'V'],
    ['I', 'vi', 'ii', 'V'],
    ['IV', 'I', 'V', 'IV'],
    ['Imaj7', 'vi7', 'ii7', 'V7'],
  ],
  outro: [
    ['I', 'IV', 'I', 'I'],
    ['Imaj7', 'IV', 'I', 'I'],
    ['I', 'V', 'I', 'I'],
    ['IV', 'I', 'IV', 'I'],
    ['I', 'vi', 'IV', 'I'],
  ],
  solo: [
    ['I', 'V', 'vi', 'IV'],
    ['I', 'IV', 'V', 'IV'],
    ['vi', 'IV', 'I', 'V'],
  ],
  interlude: [
    ['I', 'IV', 'I', 'IV'],
    ['I', 'bVII', 'IV', 'I'],
    ['Imaj7', 'IV', 'vi', 'V'],
  ],
  'post-chorus': [
    ['I', 'V', 'IV', 'IV'],
    ['IV', 'V', 'I', 'I'],
    ['I', 'IV', 'V', 'V'],
  ],
};

function _shuffleDeterministic(arr, seed) {
  // Fisher-Yates with a simple LCG so results are deterministic per seed
  const a = arr.slice();
  let s = Math.abs(seed | 0) || 1;
  for (let i = a.length - 1; i > 0; i--) {
    s = (s * 1664525 + 1013904223) & 0xffffffff;
    const j = Math.abs(s) % (i + 1);
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function _getSectionPatternPool(scale, kind, profile = '') {
  const lowerScale = String(scale || 'major').toLowerCase() === 'minor' ? 'minor' : 'major';
  const canonicalKind = canonicalChordSectionName(kind) || 'verse';
  if (lowerScale !== 'minor') {
    return Array.isArray(_MAJOR_SECTION_BANKS[canonicalKind]) ? _MAJOR_SECTION_BANKS[canonicalKind] : (Array.isArray(_MAJOR_SECTION_BANKS.verse) ? _MAJOR_SECTION_BANKS.verse : []);
  }
  const generic = Array.isArray(_MINOR_SECTION_BANKS[canonicalKind]) ? _MINOR_SECTION_BANKS[canonicalKind] : (Array.isArray(_MINOR_SECTION_BANKS.verse) ? _MINOR_SECTION_BANKS.verse : []);
  const profileBanks = _MINOR_SECTION_PROFILE_BANKS[String(profile || '').toLowerCase()] || null;
  const specific = profileBanks && Array.isArray(profileBanks[canonicalKind]) ? profileBanks[canonicalKind] : [];
  return specific.concat(generic);
}

function _baseSectionToken(tok) {
  return String(tok || '').replace(/7|maj7|dim7|dim|aug|sus2|sus4/gi, '');
}

function _sectionNarrativeScore(arr, lowerScale, canonicalKind, profile) {
  if (!arr.length) return 0;
  const bases = arr.map(_baseSectionToken);
  const first = bases[0] || '';
  const last = bases[bases.length - 1] || '';
  const tonicRe = lowerScale === 'minor' ? /^i(?!i)/i : /^I$/;
  const subdomRe = lowerScale === 'minor' ? /^iv$/i : /^IV$/i;
  const domRe = lowerScale === 'minor' ? /^(v|V)$/ : /^V$/;
  let score = 0;
  if (canonicalKind === 'intro') {
    if (tonicRe.test(first)) score += 2.3;
    if (tonicRe.test(last)) score += 1.4;
  } else if (canonicalKind === 'verse' || /^verse\b/i.test(canonicalKind)) {
    if (tonicRe.test(first)) score += 1.8;
    if (subdomRe.test(bases[1] || '')) score += 0.9;
    if (domRe.test(last)) score += 1.0;
    if (tonicRe.test(last)) score += 0.4;
  } else if (canonicalKind === 'pre-chorus') {
    if (subdomRe.test(first) || /^(ii|ii°|bVI)$/i.test(first)) score += 1.5;
    if (domRe.test(last)) score += 2.8;
    if (tonicRe.test(last)) score -= 1.4;
  } else if (canonicalKind === 'chorus' || canonicalKind === 'final chorus') {
    if (tonicRe.test(first)) score += 1.2;
    if (domRe.test(bases[Math.max(0, bases.length - 2)] || '')) score += 1.5;
    if (tonicRe.test(last)) score += canonicalKind === 'final chorus' ? 2.8 : 2.0;
    if (subdomRe.test(bases[1] || '')) score += 0.8;
  } else if (canonicalKind === 'bridge' || canonicalKind === 'solo' || canonicalKind === 'guitar solo' || canonicalKind === 'instrumental' || canonicalKind === 'interlude') {
    const uniqueCount = new Set(bases).size;
    score += uniqueCount * 0.35;
    if (!tonicRe.test(first)) score += 0.7;
    if (domRe.test(last)) score += 0.7;
  } else if (canonicalKind === 'post-chorus') {
    if (tonicRe.test(first) || subdomRe.test(first)) score += 0.8;
    if (tonicRe.test(last)) score += 0.9;
  } else if (canonicalKind === 'outro') {
    if (tonicRe.test(first)) score += 1.3;
    if (tonicRe.test(last)) score += 3.2;
    if (bases.slice(-2).every((tok) => tonicRe.test(tok))) score += 1.1;
  }
  if (lowerScale === 'minor') {
    if (profile === 'natural') {
      if (bases.some((tok) => /^V$/i.test(tok))) score -= 0.4;
      if (bases.filter((tok) => /^(bVI|bVII|bIII)$/i.test(tok)).length >= 2) score -= 1.2;
    } else if (profile === 'dark') {
      if (bases.some((tok) => /^bVI$/i.test(tok))) score += 0.8;
    } else if (profile === 'cinematic') {
      if (bases.some((tok) => /^V$/i.test(tok))) score += 0.7;
      if (bases.some((tok) => /^(bVI|bIII)$/i.test(tok))) score += 0.6;
    } else if (profile === 'pop') {
      if (bases.some((tok) => /^(bVI|bVII|bIII)$/i.test(tok))) score += 0.5;
    } else if (profile === 'modal') {
      if (bases.some((tok) => /^bVII$/i.test(tok))) score += 0.8;
      if (bases.some((tok) => /^V$/i.test(tok))) score -= 0.6;
    } else if (profile === 'dominant') {
      if (bases.some((tok) => /^V$/i.test(tok))) score += 1.4;
      if (bases.some((tok) => /^ii°$/i.test(tok))) score += 0.8;
    }
  } else {
    if (canonicalKind === 'chorus' || canonicalKind === 'final chorus') {
      if (bases.some((tok) => /^vi$/i.test(tok))) score += 0.5;
      if (bases.some((tok) => /^IV$/i.test(tok))) score += 0.6;
    }
    if (canonicalKind === 'pre-chorus' && bases.some((tok) => /^ii/i.test(tok))) score += 0.8;
    if ((canonicalKind === 'bridge' || canonicalKind === 'instrumental') && bases.some((tok) => /^iii$/i.test(tok))) score += 0.4;
  }
  return score;
}

function _scoreSectionPattern(tokens, scale, poolSet, kind = 'verse', profile = '') {
  const lowerScale = String(scale || 'major').toLowerCase() === 'minor' ? 'minor' : 'major';
  const canonicalKind = canonicalChordSectionName(kind) || 'verse';
  const arr = Array.isArray(tokens) ? tokens.map((tok) => String(tok || '').trim()).filter(Boolean) : [];
  if (!arr.length) return -999;
  let score = 0;
  const seen = new Set();
  for (const tok of arr) {
    const baseTok = _baseSectionToken(tok);
    if (!seen.has(baseTok)) score += 0.45;
    seen.add(baseTok);
    if (poolSet && poolSet.has(tok)) score += 1.2;
    if (poolSet && poolSet.has(baseTok)) score += 0.8;
    if (lowerScale === 'minor') {
      if (/^i(?!i)/i.test(baseTok)) score += 4.0;
      if (/^iv$/i.test(baseTok)) score += 2.8;
      if (/^v$/i.test(baseTok)) score += 2.4;
      if (/^V$/i.test(baseTok)) score += profile === 'dominant' || profile === 'cinematic' ? 2.2 : 1.3;
      if (/^ii°$/i.test(baseTok)) score += profile === 'dominant' ? 3.0 : 2.4;
      if (/^bVI$/i.test(baseTok)) score += ['dark', 'cinematic', 'pop'].includes(profile) ? 1.1 : 0.5;
      if (/^bVII$/i.test(baseTok)) score += ['modal', 'pop', 'dark'].includes(profile) ? 0.9 : 0.2;
      if (/^bIII$/i.test(baseTok) || /^III$/i.test(baseTok)) score += ['cinematic', 'pop', 'modal'].includes(profile) ? 0.3 : -0.6;
    } else {
      if (/^I$/i.test(baseTok)) score += 3.6;
      if (/^IV$/i.test(baseTok)) score += 2.1;
      if (/^V$/i.test(baseTok)) score += 2.5;
      if (/^vi$/i.test(baseTok)) score += canonicalKind.includes('chorus') ? 1.4 : 0.9;
      if (/^ii/i.test(baseTok)) score += canonicalKind === 'pre-chorus' ? 1.8 : 0.8;
      if (/^iii$/i.test(baseTok)) score += canonicalKind === 'bridge' || canonicalKind === 'instrumental' ? 0.8 : 0.2;
      if (/^bVII$/i.test(baseTok)) score += canonicalKind === 'rock' ? 0.6 : 0.1;
    }
  }
  if (lowerScale === 'minor') {
    const tonicCount = arr.filter((tok) => /^i(?!i)/i.test(_baseSectionToken(tok))).length;
    const subdomCount = arr.filter((tok) => /^iv$/i.test(_baseSectionToken(tok))).length;
    const modalCount = arr.filter((tok) => /^(bVI|bVII|bIII|III|VII)$/i.test(_baseSectionToken(tok))).length;
    const dominantCount = arr.filter((tok) => /^(v|V)$/i.test(_baseSectionToken(tok))).length;
    if (tonicCount) score += 2.2;
    if (subdomCount) score += 1.4;
    if (dominantCount) score += profile === 'dominant' ? 1.8 : 1.0;
    if (profile === 'natural' && modalCount >= 2) score -= 2.8;
    if (profile === 'modal' && modalCount >= 2) score += 1.5;
    if (profile === 'dark' && modalCount >= 1) score += 0.6;
    if (modalCount >= 3 && profile !== 'modal') score -= 1.8;
    if (modalCount >= 2 && !subdomCount) score -= 1.4;
    if (!dominantCount && arr.length >= 4 && !['modal', 'natural'].includes(profile)) score -= 0.9;
  } else {
    const tonicCount = arr.filter((tok) => /^I$/i.test(_baseSectionToken(tok))).length;
    const dominantCount = arr.filter((tok) => /^V$/i.test(_baseSectionToken(tok))).length;
    const subdomCount = arr.filter((tok) => /^IV$/i.test(_baseSectionToken(tok))).length;
    if (tonicCount) score += 1.8;
    if (dominantCount) score += 1.4;
    if (subdomCount) score += 1.0;
    if (!dominantCount && /chorus|pre-chorus|outro/i.test(canonicalKind)) score -= 0.8;
  }
  score += _sectionNarrativeScore(arr, lowerScale, canonicalKind, profile);
  return score;
}


function _countIntroducedSectionBases(tokens, poolSet) {
  const arr = Array.isArray(tokens) ? tokens.map(_baseSectionToken).filter(Boolean) : [];
  if (!arr.length) return 0;
  return arr.filter((tok) => !(poolSet && poolSet.has(tok))).length;
}

function _isConservativeMinorVariant(tokens, poolSet, canonicalKind, profile) {
  const arr = Array.isArray(tokens) ? tokens.map((tok) => String(tok || '').trim()).filter(Boolean) : [];
  if (!arr.length) return false;
  const bases = arr.map(_baseSectionToken);
  const introduced = bases.filter((tok) => !(poolSet && poolSet.has(tok)));
  if (!introduced.length) return true;
  const uniqueIntroduced = Array.from(new Set(introduced));
  const allowDominantColor = ['dominant', 'cinematic'].includes(String(profile || '').toLowerCase());
  const allowBridgeColor = /^(bridge|solo|guitar solo|instrumental|interlude)$/i.test(String(canonicalKind || ''));
  for (const tok of uniqueIntroduced) {
    if (/^V$/i.test(tok) || /^ii°$/i.test(tok)) {
      if (!(allowDominantColor || allowBridgeColor)) return false;
      continue;
    }
    if (/^bVI$/i.test(tok) || /^bVII$/i.test(tok) || /^bIII$/i.test(tok) || /^III$/i.test(tok) || /^VII$/i.test(tok)) {
      return false;
    }
    return false;
  }
  return uniqueIntroduced.length <= 1;
}

function chooseNarrativeChordTokens(scale, kind, baseTokens, variantIndex = 0) {
  const pool = filterPlayableChordTokens(baseTokens);
  const canonicalKind = canonicalChordSectionName(kind) || 'verse';
  const maxLen = (canonicalKind === 'final chorus' || canonicalKind === 'outro') ? 5 : 4;
  if (!pool.length) return [];

  const lowerScale = String(scale || 'major').toLowerCase() === 'minor' ? 'minor' : 'major';
  const minorProfile = lowerScale === 'minor' ? inferMinorProfileFromTokens(pool, generatedChordFamily || '') : '';
  const poolSet = new Set(pool.concat(pool.map((tok) => String(tok || '').replace(/7|maj7|dim7|dim|aug|sus2|sus4/gi, ''))));
  const base = sanitizeSectionChordTokens(pool, maxLen);
  if (base.length <= 1) return base;

  const variants = [];
  const pushVariant = (tokens) => {
    const clean = sanitizeSectionChordTokens(tokens, maxLen);
    if (!clean.length) return;
    if (!variants.some((existing) => tokensEqual(existing, clean))) variants.push(clean);
  };
  const byPattern = (pattern) => pattern
    .map((idx) => base[((idx % base.length) + base.length) % base.length])
    .filter(Boolean);

  const sectionPatterns = _getSectionPatternPool(lowerScale, canonicalKind, minorProfile)
    .slice()
    .filter((tokens) => lowerScale !== 'minor' || _isConservativeMinorVariant(tokens, poolSet, canonicalKind, minorProfile))
    .sort((left, right) => _scoreSectionPattern(right, lowerScale, poolSet, canonicalKind, minorProfile) - _scoreSectionPattern(left, lowerScale, poolSet, canonicalKind, minorProfile));
  sectionPatterns.forEach(pushVariant);

  const rotations = Array.from({ length: Math.min(base.length, maxLen) }, (_, idx) => rotateChordTokens(base, idx));
  rotations.forEach(pushVariant);
  rotations.forEach((tokens) => pushVariant(tokens.slice().reverse()));

  const tonicish = base.find((tok) => /^i(?!v)|^I(?!V)/.test(String(tok || '')) || String(tok || '').toLowerCase().startsWith('i')) || base[0];
  const dominantish = base.find((tok) => /^(v|V)/.test(String(tok || '')) || /^b?v/i.test(String(tok || ''))) || base[base.length - 1];
  const preDominantish = base.find((tok) => /^iv/i.test(String(tok || '')) || /^b?vi/i.test(String(tok || '')) || /^ii/i.test(String(tok || ''))) || base[1] || base[0];

  pushVariant(byPattern([0, 1, base.length - 1, 0]));
  pushVariant(byPattern([0, 2, 1, base.length - 1]));
  pushVariant(byPattern([base.length - 1, 1, 0, 2]));
  if (base.length >= 4) {
    pushVariant(byPattern([0, 1, 2, 3, 0]));
    pushVariant(byPattern([0, 2, 3, 1]));
  }

  switch (canonicalKind) {
    case 'intro':
      pushVariant(byPattern([1, 2, 0, base.length - 1]));
      pushVariant(byPattern([base.length - 2, base.length - 1, 0, 1]));
      pushVariant([tonicish, ...rotateChordTokens(base, 1).slice(0, Math.max(0, maxLen - 1))]);
      break;
    case 'verse':
      pushVariant(base);
      pushVariant(byPattern([0, 2, 1, base.length - 1]));
      pushVariant(byPattern([0, 1, 0, base.length - 1]));
      break;
    case 'chorus':
    case 'final chorus':
      pushVariant(byPattern([1, 2, base.length - 1, 0]));
      pushVariant(byPattern([0, 1, base.length - 1, 0]));
      pushVariant([preDominantish, dominantish, tonicish, dominantish, tonicish]);
      break;
    case 'bridge':
    case 'solo':
    case 'guitar solo':
    case 'instrumental':
      pushVariant(byPattern([2, 1, base.length - 1, 0]));
      pushVariant([tonicish, preDominantish, dominantish, tonicish]);
      pushVariant([tonicish, base[Math.min(2, base.length - 1)] || tonicish, tonicish]);
      break;
    case 'outro':
      pushVariant(byPattern([0, 1, 2, base.length - 1, 0]));
      pushVariant([tonicish, preDominantish, dominantish, tonicish, tonicish]);
      pushVariant([tonicish, ...rotateChordTokens(base, 1).slice(0, Math.max(0, maxLen - 2)), tonicish]);
      break;
    default:
      pushVariant(base);
      break;
  }

  const scored = variants.slice().sort((left, right) => {
    const rightIntroduced = _countIntroducedSectionBases(right, poolSet);
    const leftIntroduced = _countIntroducedSectionBases(left, poolSet);
    if (rightIntroduced !== leftIntroduced) return leftIntroduced - rightIntroduced;
    return _scoreSectionPattern(right, lowerScale, poolSet, canonicalKind, minorProfile) - _scoreSectionPattern(left, lowerScale, poolSet, canonicalKind, minorProfile);
  });
  const top = scored.slice(0, Math.max(1, Math.min(6, scored.length)));
  const ordered = _shuffleDeterministic(top, (variantIndex * 31) + top.length * 7 + canonicalKind.length * 11);
  return ordered[Math.abs(variantIndex) % ordered.length] || scored[0] || base;
}


function getRomanTokens(romanStr) {
  return String(romanStr || '').split(/[\s,\-]+/).filter(Boolean);
}

function titleCaseChordSectionName(name) {
  const n = canonicalChordSectionName(name);
  if (!n) return '';
  return n.split(' ').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
}

function parseExplicitChordNames(text, maxLen = 5) {
  const tokens = String(text || '').split(/[\s,\/|]+/).filter(Boolean);
  return sanitizeResolvedChordNames(tokens, maxLen);
}

function parseChordSectionHeaderLine(line) {
  const m = String(line || '').match(/^\s*\[([^\]]+)\]\s*$/);
  if (!m) return null;
  const inner = String(m[1] || '').trim();
  if (!inner) return null;
  const parts = inner.split(/\|\s*chords\s*:/i);
  const rawLabel = String(parts[0] || '').trim().replace(/\s+/g, ' ');
  const canonical = canonicalChordSectionName(rawLabel);
  const normalized = normalizeChordSectionName(rawLabel);
  const isKnown = chordSectionCanonicalPatterns.some((entry) => entry.re.test(normalized));
  if (!isKnown || !canonical) return null;
  return {
    raw: rawLabel,
    canonical,
    inlineChords: parseExplicitChordNames(parts.slice(1).join(' | ') || '', canonical === 'final chorus' || canonical === 'outro' ? 5 : 4),
  };
}

function parseLyricsSectionHeaders(text) {
  const lines = String(text || '').split(/\r?\n/);
  const out = [];
  for (const line of lines) {
    const parsed = parseChordSectionHeaderLine(line);
    if (parsed) out.push(parsed);
  }
  return out;
}

function listChordSectionsFromLyrics(text) {
  return parseLyricsSectionHeaders(text).map((item) => ({ raw: item.raw, canonical: item.canonical }));
}


function rotateChordTokens(tokens, shift) {
  const arr = Array.isArray(tokens) ? tokens.slice() : [];
  if (!arr.length) return [];
  const n = ((shift % arr.length) + arr.length) % arr.length;
  return arr.slice(n).concat(arr.slice(0, n));
}

function dedupeChordTokens(tokens) {
  const out = [];
  tokens.forEach((tok) => {
    if (!tok) return;
    if (!out.length || out[out.length - 1] !== tok) out.push(tok);
  });
  return out;
}

function tokensEqual(a, b) {
  const left = Array.isArray(a) ? a.map((x) => String(x || '').trim()).filter(Boolean) : [];
  const right = Array.isArray(b) ? b.map((x) => String(x || '').trim()).filter(Boolean) : [];
  if (left.length != right.length) return false;
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] !== right[i]) return false;
  }
  return true;
}

function filterPlayableChordTokens(tokens) {
  return dedupeChordTokens((tokens || []).filter((tok) => {
    try {
      return !!parseRomanChordToken(tok);
    } catch (e) {
      return false;
    }
  }));
}

function pickChordTemplate(scale, kind, baseTokens, variantIndex = 0) {
  const picked = chooseNarrativeChordTokens(scale, kind, baseTokens, variantIndex);
  if (picked.length) return picked;
  const fallback = sanitizeSectionChordTokens(baseTokens, 4);
  return fallback.length ? fallback : filterPlayableChordTokens(baseTokens);
}

function buildAutoChordSectionMap(lyricsText, baseRoman, scale) {
  const sections = listChordSectionsFromLyrics(lyricsText || '');
  if (!sections.length) return '';
  const baseTokens = getRomanTokens(baseRoman);
  if (!baseTokens.length) throw new Error(t('error.chord_empty'));
  const lines = [];
  let previousTokens = [];
  sections.forEach((section, sectionIndex) => {
    const rawName = section.raw;
    const canonical = section.canonical;
    const allowRepeat = ['chorus', 'final chorus', 'outro'].includes(canonical || '');
    let tokens = [];
    for (let attempt = 0; attempt < 6; attempt += 1) {
      tokens = pickChordTemplate(scale, canonical || rawName, baseTokens, (sectionIndex * 13) + attempt * 7);
      if (!tokens.length) continue;
      if (allowRepeat || !tokensEqual(tokens, previousTokens)) break;
    }
    if (!tokens.length) tokens = sanitizeSectionChordTokens(baseTokens, 4);
    previousTokens = tokens.slice();
    lines.push(`${titleCaseChordSectionName(rawName)}=${tokens.join(' - ')}`);
  });
  return lines.join('\n');
}


function autoGenerateChordSectionOverrides() {
  const lyricsText = el('lyrics')?.value || '';
  const roman = el('chord_roman')?.value || '';
  const scale = el('chord_scale')?.value || 'major';
  const status = el('chord_status');
  try {
    const mapText = buildAutoChordSectionMap(lyricsText, roman, scale);
    if (!mapText.trim()) throw new Error(t('error.chord_sections_missing'));
    if (el('chord_section_map')) el('chord_section_map').value = mapText;
    refreshChordPreview();
    if (status) status.textContent = t('status.chord_sections_generated');
    return true;
  } catch (err) {
    if (status) status.textContent = err && err.message ? err.message : String(err);
    return false;
  }
}

const chordSectionCanonicalPatterns = [
  { canonical: 'final chorus', re: /^final\s+chorus\b/i },
  { canonical: 'post-chorus', re: /^post\s*-?\s*chorus\b/i },
  { canonical: 'pre-chorus', re: /^pre\s*-?\s*chorus\b/i },
  { canonical: 'guitar solo', re: /^guitar\s+solo\b/i },
  { canonical: 'instrumental', re: /^instrumental\b/i },
  { canonical: 'intro', re: /^intro\b/i },
  { canonical: 'verse', re: /^verse\b/i },
  { canonical: 'chorus', re: /^chorus\b/i },
  { canonical: 'bridge', re: /^bridge\b/i },
  { canonical: 'outro', re: /^outro\b/i },
  { canonical: 'solo', re: /^solo\b/i },
  { canonical: 'interlude', re: /^interlude\b/i },
];

function normalizeChordSectionName(name) {
  return String(name || '')
    .toLowerCase()
    .replace(/[–—]/g, '-')
    .replace(/\s+/g, ' ')
    .trim();
}

function canonicalChordSectionName(name) {
  const normalized = normalizeChordSectionName(name);
  if (!normalized) return '';
  for (const entry of chordSectionCanonicalPatterns) {
    const m = normalized.match(entry.re);
    if (!m) continue;
    if (entry.canonical === 'verse') {
      const num = normalized.slice(m[0].length).match(/^\s*(\d+)\b/);
      return num ? `verse ${num[1]}` : 'verse';
    }
    return entry.canonical;
  }
  return normalized;
}

function getChordSectionMapText() {
  return String(el('chord_section_map')?.value || '');
}

function parseChordSectionMap(text, key, scale) {
  const raw = String(text || '').trim();
  if (!raw) return [];
  const lines = raw.split(/\r?\n/);
  const out = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || /^#/.test(trimmed)) continue;
    const parts = trimmed.split(/\s*(?:=|:)\s*/);
    if (parts.length < 2) throw new Error(t('error.chord_section_line_invalid', { line: trimmed }));
    const sectionName = canonicalChordSectionName(parts.shift());
    const roman = parts.join(' = ').trim();
    if (!sectionName || !roman) throw new Error(t('error.chord_section_line_invalid', { line: trimmed }));
    const escapedSection = sectionName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\-/g, '[-\\s]?');
    const data = formatChordProgressionForGeneration(roman, key, scale);
    const displayChords = sanitizeResolvedChordNames(data.chords, sectionName === 'final chorus' || sectionName === 'outro' ? 5 : 4);
    out.push({
      section: sectionName,
      roman,
      matcher: new RegExp(`^${escapedSection}(?:\\s+\\d+)?$`, 'i'),
      data: {
        ...data,
        sectionChordTag: `Chords: ${displayChords.join(' ')}`,
      },
      summary: `${sectionName}: ${displayChords.join(' - ')}`,
    });
  }
  return out;
}

function findChordSectionRule(sectionLabel, sectionRules) {
  const normalized = canonicalChordSectionName(sectionLabel);
  if (!normalized) return null;
  return sectionRules.find((rule) => rule.matcher.test(normalized) || normalized === rule.section) || null;
}

function getChordReferenceSequence(baseData, sectionRules, lyricsText) {
  const headers = parseLyricsSectionHeaders(lyricsText || '');
  const baseChords = ((baseData && Array.isArray(baseData.chords) && baseData.chords.length) ? baseData.chords : []);
  if (!headers.length) return baseChords;
  const sequence = [];
  headers.forEach((header) => {
    const rule = findChordSectionRule(header.raw, sectionRules || []);
    if (rule && rule.data && Array.isArray(rule.data.chords) && rule.data.chords.length) {
      sequence.push(...rule.data.chords);
      return;
    }
    if (baseChords.length) {
      sequence.push(...baseChords);
      return;
    }
    if (header.inlineChords && header.inlineChords.length) {
      sequence.push(...header.inlineChords);
    }
  });
  return sequence.length ? sequence : baseChords;
}


function buildChordReferencePlan(baseData, sectionRules, lyricsText) {
  const headers = parseLyricsSectionHeaders(lyricsText || '');
  const plan = [];
  headers.forEach((header) => {
    const rawLabel = header.raw;
    const canonical = header.canonical;
    const rule = findChordSectionRule(rawLabel, sectionRules || []);
    let chords = ((rule && rule.data && rule.data.chords) ? rule.data.chords : []).slice();
    let source = rule ? 'override' : 'base';
    if (!chords.length) {
      chords = sanitizeResolvedChordNames((baseData && baseData.chords) ? baseData.chords : [], canonical === 'final chorus' || canonical === 'outro' ? 5 : 4);
    }
    if (!chords.length && header.inlineChords && header.inlineChords.length) {
      chords = header.inlineChords.slice();
      source = 'lyrics';
    }
    const displayChords = sanitizeResolvedChordNames(chords, canonical === 'final chorus' || canonical === 'outro' ? 5 : 4);
    plan.push({
      label: rawLabel,
      section: canonical,
      source,
      roman: (rule && rule.roman) ? rule.roman : (source === 'lyrics' ? '' : (el('chord_roman')?.value || '')),
      chords,
      displayChords,
    });
  });
  if (!plan.length) {
    const globalChords = sanitizeResolvedChordNames((baseData && baseData.chords) ? baseData.chords : [], 4);
    plan.push({
      label: 'global',
      section: 'global',
      source: 'global',
      roman: el('chord_roman')?.value || '',
      chords: globalChords,
      displayChords: globalChords,
    });
  }
  return plan;
}


function formatChordReferencePlan(plan) {
  return (plan || []).map((item) => `${item.label} [${item.source}] => ${Array.isArray(item.chords) ? item.chords.join(' - ') : ''}`).join(' || ');
}

let chordStatusLock = false;
let chordReferenceSoundfontAvailable = false;
let chordReferenceSoundfontName = '';

function setChordStatusMessage(msg, options = {}) {
  const status = el('chord_status');
  if (!status) return;
  if (chordStatusLock && !options.force) return;
  status.textContent = String(msg ?? '');
}

async function applyChordProgressionFullConditioning() {
  const originalLyrics = el('lyrics')?.value || '';
  try {
    syncChordSectionOverridesFromCurrentProgression();
  } catch (err) {
    setChordStatusMessage(err && err.message ? err.message : String(err), { force: true });
    return false;
  }
  const data = refreshChordPreview();
  if (!data) return false;
  const status = el('chord_status');
  chordStatusLock = true;
  try {
    setChordStatusMessage(__tr('status.chord_full_uploading', 'Reference audio generation in progress…', 'Generazione audio di riferimento in corso…'), { force: true });
    await new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve, 0)));
    const bpmVal = Number(el('bpm')?.value || 120) || 120;
    const targetDuration = Math.max(10, Number(el('duration')?.value || 180) || 180);
    const appliedLyrics = el('chord_apply_lyrics')?.checked
      ? injectChordTagsIntoLyrics(originalLyrics, data.sectionChordTag, data.lyricsTag, data.sectionRules || [])
      : originalLyrics;
    const sectionPlan = buildChordReferencePlan(data, data.sectionRules || [], appliedLyrics);
    applyChordProgressionToUi({ suppressStatus: true });
    const sequenceChords = sectionPlan.flatMap((item) => Array.isArray(item.chords) ? item.chords : []);
    generatedChordReferenceSequence = sequenceChords.slice();
    generatedChordSectionPlan = sectionPlan.slice();
    generatedChordReferenceBpm = bpmVal;
    generatedChordReferenceTargetDuration = targetDuration;
    console.log('[aceflow] chord full reference plan', { bpm: bpmVal, targetDuration, sectionPlan, sequenceChords });
    const chordReferenceRenderer = String(el('chord_reference_renderer')?.value || 'soundfont').trim().toLowerCase() || 'soundfont';
    const renderRes = await fetch('/api/chords/render-reference', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chords: sequenceChords,
        bpm: bpmVal,
        beats_per_chord: 4,
        target_duration: targetDuration,
        chord_reference_renderer: chordReferenceRenderer,
      }),
    });
    if (!renderRes.ok) {
      const errTxt = await renderRes.text();
      throw new Error(errTxt || 'Chord reference render failed');
    }
    const up = await renderRes.json();
    generatedChordReferenceMeta = up.meta || null;
    if (generatedChordReferenceMeta && Array.isArray(generatedChordReferenceMeta.warning_debug) && generatedChordReferenceMeta.warning_debug.length) {
      console.warn('[aceflow] chord reference warning_debug', generatedChordReferenceMeta.warning_debug);
    }
    generatedChordConditioningPath = up.path;
    generatedChordConditioningName = up.filename || `chord_progression_${Date.now()}.wav`;
    setChordStatusMessage(__tr('status.chord_full_extracting', 'Extracting audio codes from reference…', 'Estrazione codici audio dal reference…'), { force: true });
    const codesRes = await fetch('/api/chords/extract-codes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: up.path }),
    });
    if (!codesRes.ok) {
      const errTxt = await codesRes.text();
      throw new Error(errTxt || 'Chord audio-code extraction failed');
    }
    const codesData = await codesRes.json();
    generatedChordAudioCodes = String(codesData && codesData.codes ? codesData.codes : '').trim();
    if (!generatedChordAudioCodes) throw new Error('Empty chord audio codes');
    chordConditioningMode = 'full';
    if (refAudioStatus) {
      const warningCount = Number((generatedChordReferenceMeta && generatedChordReferenceMeta.warning_count) || 0);
      const warningSuffix = warningCount > 0 ? ` | warning_debug=${warningCount}` : '';
      refAudioStatus.textContent = `${t('upload.done', { name: up.filename || fileName })}${warningSuffix}`;
    }
    if (el('audio_codes')) el('audio_codes').value = generatedChordAudioCodes;
    if (el('cover_noise_strength')) el('cover_noise_strength').value = '0';
    if (el('cover_noise_strength_range')) el('cover_noise_strength_range').value = '0';
    setChordStatusMessage(t('status.chord_full_ready', { duration: String(Math.round(targetDuration)) }), { force: true });
    return true;
  } catch (err) {
    chordConditioningMode = 'none';
    generatedChordConditioningPath = '';
    generatedChordConditioningName = '';
    generatedChordReferenceSequence = [];
    generatedChordSectionPlan = [];
    generatedChordReferenceBpm = null;
    generatedChordReferenceTargetDuration = null;
    generatedChordAudioCodes = '';
    generatedChordReferenceMeta = null;
    setChordStatusMessage(t('error.chord_full_failed', { msg: err && err.message ? err.message : String(err) }), { force: true });
    return false;
  } finally {
    chordStatusLock = false;
  }
}


function stripChordCaptionTag(text) {
  return String(text || '')
    .replace(/,?\s*[A-G][#b]?\s*(Major|Minor)\s+key,?\s*chord progression\s*[^,]+,\s*harmonic structure,\s*(major|minor)\s+tonality/gi, '')
    .replace(/,?\s*chord progression\s*[^,]+,\s*harmonic structure,\s*(major|minor)\s+tonality/gi, '')
    .replace(/,?\s*harmonic structure,\s*(major|minor)\s+tonality/gi, '')
    .replace(/\s+,/g, ',')
    .replace(/,\s*,+/g, ',')
    .replace(/^\s*,\s*|\s*,\s*$/g, '')
    .trim();
}

function stripChordLyricsTag(text) {
  const src = String(text || '');
  return src
    .replace(/^\s*\[Chord Progression:[^\n]*\]\s*\n?/i, '')
    .split(/\r?\n/)
    .map((line) => {
      const m = line.match(/^\s*\[(.+)\]\s*$/);
      if (!m) return line;
      const inner = m[1].replace(/\s*\|\s*Chords:\s*[^\]]*$/i, '').trim();
      return `[${inner}]`;
    })
    .join('\n')
    .trimStart();
}

function stripChordTagsForModelInput(text) {
  return stripChordLyricsTag(text);
}

function injectChordTagsIntoLyrics(text, sectionChordTag, progressionTag, sectionRules = []) {
  const srcLines = String(text || '').split(/\r?\n/);
  let touched = 0;
  const out = srcLines.map((line) => {
    const parsed = parseChordSectionHeaderLine(line);
    if (!parsed) return line;
    touched += 1;
    const base = parsed.raw;
    const canonical = parsed.canonical;
    const rule = findChordSectionRule(base, sectionRules);
    let effectiveTag = (rule && rule.data && rule.data.sectionChordTag) ? rule.data.sectionChordTag : '';
    if (!effectiveTag) effectiveTag = sectionChordTag;
    if (!effectiveTag) {
      const inlineChords = Array.isArray(parsed.inlineChords) ? parsed.inlineChords : [];
      if (inlineChords.length) effectiveTag = `Chords: ${inlineChords.join(' ')}`;
    }
    const tagBody = String(effectiveTag || '').replace(/^Chords:\s*/i, '').trim();
    const compactTag = sanitizeResolvedChordNames(tagBody.split(/[\s,\-–—]+/).filter(Boolean), canonical === 'final chorus' || canonical === 'outro' ? 5 : 4);
    effectiveTag = compactTag.length ? `Chords: ${compactTag.join(' ')}` : '';
    return effectiveTag ? `[${base} | ${effectiveTag}]` : `[${base}]`;
  });
  const clean = stripChordLyricsTag(out.join('\n'));
  if (!touched) {
    return progressionTag ? `${progressionTag}\n${clean}`.trim() : clean;
  }
  return out.join('\n');
}



function syncChordSectionOverridesFromCurrentProgression() {
  const mapEl = el('chord_section_map');
  if (!mapEl) return '';
  const roman = String(el('chord_roman')?.value || '').trim();
  if (!roman) {
    mapEl.value = '';
    return '';
  }
  const lyricsText = stripChordLyricsTag(el('lyrics')?.value || '');
  const scale = el('chord_scale')?.value || 'major';
  const mapText = buildAutoChordSectionMap(lyricsText, roman, scale);
  mapEl.value = mapText;
  return mapText;
}

function resetChordPreviewUi() {
  const ids = ['chord_resolved_preview', 'chord_caption_preview', 'chord_keyscale_preview', 'chord_sections_preview'];
  ids.forEach((id) => {
    const node = el(id);
    if (node) node.textContent = '—';
  });
}

function refreshChordPreview() {
  const status = el('chord_status');
  const resolvedEl = el('chord_resolved_preview');
  const capEl = el('chord_caption_preview');
  const keyEl = el('chord_keyscale_preview');
  const sectionsEl = el('chord_sections_preview');
  try {
    const data = formatChordProgressionForGeneration(el('chord_roman')?.value || '', el('chord_key')?.value || 'C', el('chord_scale')?.value || 'major');
    const sectionRules = parseChordSectionMap(getChordSectionMapText(), el('chord_key')?.value || 'C', el('chord_scale')?.value || 'major');
    data.sectionRules = sectionRules;
    data.sectionSummary = sectionRules.length ? sectionRules.map((rule) => rule.summary).join(' • ') : t('status.chord_sections_none');
    if (resolvedEl) resolvedEl.textContent = data.description;
    if (capEl) capEl.textContent = data.styleTag;
    if (keyEl) keyEl.textContent = data.keyScaleTag;
    if (sectionsEl) sectionsEl.textContent = data.sectionSummary;
    setChordStatusMessage('');
    return data;
  } catch (err) {
    if (resolvedEl) resolvedEl.textContent = '—';
    if (capEl) capEl.textContent = '—';
    if (keyEl) keyEl.textContent = '—';
    if (sectionsEl) sectionsEl.textContent = '—';
    setChordStatusMessage(err && err.message ? err.message : String(err), { force: true });
    return null;
  }
}

function applyChordProgressionToUi(options = {}) {
  try {
    syncChordSectionOverridesFromCurrentProgression();
  } catch (err) {
    setChordStatusMessage(err && err.message ? err.message : String(err), { force: true });
    return false;
  }
  const data = refreshChordPreview();
  if (!data) return false;
  const captionEl = el('caption');
  const lyricsEl = el('lyrics');
  const keyscaleEl = el('keyscale');
  const bpmEl = el('bpm');
  const chordStatus = el('chord_status');
  const cleanCaption = stripChordCaptionTag(captionEl ? captionEl.value : '');
  if (captionEl) captionEl.value = cleanCaption ? `${cleanCaption}, ${data.styleTag}` : data.styleTag;
  if (el('chord_apply_lyrics')?.checked) {
    const currentLyrics = lyricsEl ? lyricsEl.value : '';
    if (lyricsEl) lyricsEl.value = injectChordTagsIntoLyrics(currentLyrics, data.sectionChordTag, data.lyricsTag, data.sectionRules || []);
  }
  if (el('chord_apply_keyscale')?.checked && keyscaleEl) {
    setKeyScaleValue(data.keyScaleTag, { dispatch: true });
    if (el('key_auto')) el('key_auto').checked = false;
  }
  if (el('chord_apply_bpm')?.checked && bpmEl) {
    const chordBpm = Number(el('bpm')?.value || '');
    if (Number.isFinite(chordBpm) && chordBpm > 0) {
      bpmEl.value = String(Math.round(chordBpm));
      if (el('bpm_auto')) el('bpm_auto').checked = false;
      bpmEl.dispatchEvent(new Event('input', { bubbles: true }));
      bpmEl.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }
  if (!options || !options.suppressStatus) {
    setChordStatusMessage(t('status.chord_applied', { desc: data.description }) + ((data.sectionRules && data.sectionRules.length) ? (' ' + t('status.chord_sections_applied', { count: String(data.sectionRules.length) })) : ''));
  }
  return true;
}

function removeChordProgressionFromUi() {
  const captionEl = el('caption');
  const lyricsEl = el('lyrics');
  if (captionEl) captionEl.value = stripChordCaptionTag(captionEl.value || '');
  if (lyricsEl) lyricsEl.value = stripChordLyricsTag(lyricsEl.value || '');
  if (el('chord_roman')) el('chord_roman').value = '';
  if (el('chord_section_map')) el('chord_section_map').value = '';
  resetChordPreviewUi();
  let msg = t('status.chord_removed');
  const hadChordConditioning = !!generatedChordConditioningPath;
  if (uploadedRefAudioPath === generatedChordConditioningPath) uploadedRefAudioPath = '';
  generatedChordConditioningPath = '';
  generatedChordConditioningName = '';
  chordConditioningMode = 'none';
  generatedChordReferenceSequence = [];
  generatedChordSectionPlan = [];
  generatedChordReferenceBpm = null;
  generatedChordReferenceTargetDuration = null;
  generatedChordAudioCodes = '';
  generatedChordReferenceMeta = null;
  if (el('audio_codes')) el('audio_codes').value = '';
  if (refAudioStatus) refAudioStatus.textContent = '';
  if (hadChordConditioning) msg += ' ' + t('status.chord_full_cleared');
  const status = el('chord_status');
  if (status) status.textContent = msg;
}

function __getJobIdFromUrl(u) {
  const m = String(u || '').match(/\/download\/([^\/]+)\//);
  return m ? m[1] : '';
}

function __safeOptText(selEl) {
  try {
    const opt = selEl && selEl.options ? selEl.options[selEl.selectedIndex] : null;
    return opt ? (opt.textContent || '').trim() : '';
  } catch (e) {
    return '';
  }
}

function __snapshotUiForExport(payload) {
  
  
  const ui = {
    model: payload?.model ?? null,
    model_label: __safeOptText(el('model_select')),

    lora_id: payload?.lora_id ?? null,
    lora_trigger: payload?.lora_trigger ?? payload?.lora_tag ?? null,
    lora_weight: (payload?.lora_weight != null) ? payload.lora_weight : null,
    lora_label: __safeOptText(el('lora_select')),

    caption: payload?.caption ?? (el('caption') ? el('caption').value : null),
    lyrics: (el('lyrics') ? el('lyrics').value : (payload?.lyrics_export ?? payload?.lyrics ?? null)),
    lyrics_export: (el('lyrics') ? el('lyrics').value : (payload?.lyrics_export ?? payload?.lyrics ?? null)),
    lyrics_model_input: payload?.lyrics_model_input ?? payload?.lyrics ?? null,
    generation_mode: payload?.generation_mode ?? null,
    task_type: payload?.task_type ?? null,

    
    inference_steps: payload?.inference_steps ?? null,
    infer_method: payload?.infer_method ?? (el('infer_method') ? el('infer_method').value : null),
    timesteps: (payload?.timesteps != null) ? payload.timesteps : (el('timesteps') ? el('timesteps').value : null),
    source_start: (payload?.source_start != null) ? payload.source_start : (el('source_start') ? Number(el('source_start').value || '') : null),
    source_end: (payload?.source_end != null) ? payload.source_end : (el('source_end') ? Number(el('source_end').value || '') : null),
    guidance_scale: payload?.guidance_scale ?? null,
    shift: payload?.shift ?? null,

    
    score_scale: (payload?.score_scale != null) ? payload.score_scale : (el('score_scale') ? Number(el('score_scale').value || '') : null),
    auto_score: !!payload?.auto_score,
    audio_codes: payload?.audio_codes ?? (el('audio_codes') ? el('audio_codes').value : null),
    audio_cover_strength: (payload?.audio_cover_strength != null) ? payload.audio_cover_strength : (el('audio_cover_strength') ? Number(el('audio_cover_strength').value || '') : null),
    cover_noise_strength: (payload?.cover_noise_strength != null) ? payload.cover_noise_strength : (el('cover_noise_strength') ? Number(el('cover_noise_strength').value || '') : null),
    cover_conditioning_balance: (payload?.cover_conditioning_balance != null) ? payload.cover_conditioning_balance : (el('cover_conditioning_balance') ? Number(el('cover_conditioning_balance').value || '') : null),
    chord_reference_renderer: payload?.chord_reference_renderer ?? (el('chord_reference_renderer') ? el('chord_reference_renderer').value : 'soundfont'),
    reference_audio: payload?.reference_audio ?? null,
    src_audio: payload?.src_audio ?? null,
    batch_size: payload?.batch_size ?? (el('batch_size') ? Number(el('batch_size').value || '') : null),
    audio_format: payload?.audio_format ?? (el('audio_format') ? el('audio_format').value : null),

    
    duration_auto: !!payload?.duration_auto,
    bpm_auto: !!payload?.bpm_auto,
    key_auto: !!payload?.key_auto,
    timesig_auto: !!payload?.timesig_auto,
    language_auto: !!payload?.language_auto,
    duration: (payload?.duration != null) ? payload.duration : (el('duration') ? Number(el('duration').value || '') : null),
    bpm: (payload?.bpm != null) ? payload.bpm : (el('bpm') ? Number(el('bpm').value || '') : null),
    keyscale: (payload?.keyscale != null) ? payload.keyscale : (el('keyscale') ? el('keyscale').value : null),
    timesignature: (payload?.timesignature != null) ? payload.timesignature : (el('timesignature') ? el('timesignature').value : null),
    vocal_language: (payload?.vocal_language != null) ? payload.vocal_language : (el('vocal_language') ? el('vocal_language').value : null),

    
    seed: payload?.seed ?? null,
    seed_random: !!(el('seed_random')?.checked),
    instrumental: !!payload?.instrumental,
    thinking: !!payload?.thinking,
    use_cot_metas: !!payload?.use_cot_metas,
    use_cot_caption: !!payload?.use_cot_caption,
    use_cot_language: !!payload?.use_cot_language,
    parallel_thinking: !!payload?.parallel_thinking,
    constrained_decoding_debug: !!payload?.constrained_decoding_debug,

    
    chord_key: (el('chord_key') ? el('chord_key').value : null),
    chord_scale: (el('chord_scale') ? el('chord_scale').value : null),
    chord_roman: (el('chord_roman') ? el('chord_roman').value : null),
    chord_section_map: (el('chord_section_map') ? el('chord_section_map').value : null),
    chord_apply_keyscale: !!(el('chord_apply_keyscale')?.checked),
    chord_apply_bpm: !!(el('chord_apply_bpm')?.checked),
    chord_apply_lyrics: !!(el('chord_apply_lyrics')?.checked),
    chord_conditioning_mode: chordConditioningMode,
    chord_conditioning_path: generatedChordConditioningPath || uploadedRefAudioPath || null,
    chord_conditioning_name: generatedChordConditioningName || null,
    uploaded_reference_audio_path: uploadedRefAudioPath || null,
    uploaded_lm_audio_path: uploadedLmAudioPath || null,
    chord_debug_reference_sequence: (generatedChordReferenceSequence || []).join(' - '),
    chord_debug_section_plan: formatChordReferencePlan(generatedChordSectionPlan || []),
    chord_debug_reference_bpm: generatedChordReferenceBpm,
    chord_debug_reference_target_duration: generatedChordReferenceTargetDuration,
    chord_audio_codes: generatedChordAudioCodes || null,
    chord_family: generatedChordFamily || null,

    
    ui_lang: (document.getElementById('ui_lang_select')?.value || 'auto'),
  };
  return ui;
}

function __stripExtension(filename) {
  const name = String(filename || '').trim();
  return name.replace(/\.[^.]+$/, '');
}

function __filenameFromContentDisposition(cd) {
  const raw = String(cd || '').trim();
  if (!raw) return '';
  const star = raw.match(/filename\*=UTF-8''([^;]+)/i);
  if (star && star[1]) {
    try { return decodeURIComponent(star[1].replace(/^"|"$/g, '')); } catch (e) {}
    return star[1].replace(/^"|"$/g, '');
  }
  const plain = raw.match(/filename=([^;]+)/i);
  if (plain && plain[1]) return plain[1].trim().replace(/^"|"$/g, '');
  return '';
}

async function __resolveDownloadFilename(url) {
  const target = String(url || '').trim();
  if (!target) return '';
  try {
    const res = await fetch(target, { method: 'HEAD', cache: 'no-store' });
    if (res.ok) {
      const cd = res.headers.get('Content-Disposition') || res.headers.get('content-disposition') || '';
      const fn = __filenameFromContentDisposition(cd);
      if (fn) return fn;
    }
  } catch (e) {}
  try {
    const u = new URL(target, window.location.href);
    const pathname = u.pathname || '';
    return decodeURIComponent(pathname.split('/').pop() || '');
  } catch (e) {
    return '';
  }
}

async function downloadMergedJobJson(jsonUrl, jobId, audioUrl, explicitAudioFilename) {
  const jid = String(jobId || __getJobIdFromUrl(jsonUrl) || '').trim();
  const snap = jid ? __jobRequestSnapshots.get(jid) : null;

  let backend = null;
  try {
    const res = await fetch(jsonUrl, { cache: 'no-store' });
    if (!res.ok) throw new Error('fetch failed');
    backend = await res.json();
  } catch (e) {
    
    backend = { error: 'backend_json_unavailable' };
  }

  const merged = (backend && typeof backend === 'object') ? { ...backend } : { backend };
  if (snap) {
    merged.ui_state = snap.ui_state;
    merged.request_sent = snap.request;
    if (merged.request == null) merged.request = snap.request;
    
    if (merged.model == null && snap.ui_state?.model != null) merged.model = snap.ui_state.model;
    if (merged.lora_id == null && snap.ui_state?.lora_id != null) merged.lora_id = snap.ui_state.lora_id;
    if (merged.lora_trigger == null) {
      if (snap.ui_state?.lora_trigger != null) merged.lora_trigger = snap.ui_state.lora_trigger;
      else if (snap.ui_state?.lora_tag != null) merged.lora_trigger = snap.ui_state.lora_tag;
    }
    if (merged.lora_weight == null && snap.ui_state?.lora_weight != null) merged.lora_weight = snap.ui_state.lora_weight;
  }

  const audioFilename = String(explicitAudioFilename || '').trim() || await __resolveDownloadFilename(audioUrl);
  const audioBaseName = __stripExtension(audioFilename);
  const jsonFilename = audioBaseName ? `${audioBaseName}.json` : (jid ? `acestep_${jid}.json` : 'acestep_export.json');

  const blob = new Blob([JSON.stringify(merged, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = jsonFilename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2500);
}


async function refreshFooterStats() {
  if (!canUseProtectedApi()) return;
  try {
    const r = await fetch(`/api/stats?ts=${Date.now()}`);
    const data = await r.json();
    if (clientIpEl && data && data.ip) clientIpEl.textContent = data.ip;
    if (songCounterEl && data && (data.songs_generated != null)) songCounterEl.textContent = String(data.songs_generated);


    
    try {
      const rs = await fetch(`/api/system?ts=${Date.now()}`);
      const sys = await rs.json();
      const gpu = sys || null;
      if (gpuInfoEl) {
        if (gpu && gpu.gpu_name && (gpu.vram_total_mb != null)) {
          const usedGb = (gpu.vram_used_mb != null) ? (Number(gpu.vram_used_mb) / 1024) : null;
          const totGb = Number(gpu.vram_total_mb) / 1024;
          const usedTxt = (usedGb != null && Number.isFinite(usedGb)) ? usedGb.toFixed(1) : 'n/a';
          const totTxt = (Number.isFinite(totGb)) ? totGb.toFixed(1) : 'n/a';
          const tempTxt = (gpu.gpu_temp_c != null && Number.isFinite(Number(gpu.gpu_temp_c))) ? String(Math.round(Number(gpu.gpu_temp_c))) : 'n/a';
          gpuInfoEl.textContent = window.i18n ? window.i18n.t('footer.gpu_line', { name: gpu.gpu_name, used: usedTxt, total: totTxt, temp: tempTxt }) : `GPU: ${gpu.gpu_name} — VRAM: ${usedTxt}/${totTxt} GB — Temp: ${tempTxt}°C`;
          gpuInfoEl.style.display = '';
        } else {
          gpuInfoEl.style.display = 'none';
          gpuInfoEl.textContent = '';
        }
      }
    } catch (e2) {
      if (gpuInfoEl) {
        gpuInfoEl.style.display = 'none';
        gpuInfoEl.textContent = '';
      }
    }
  } catch (e) {
    
  }
}


function getSelectedModel() {
  const v = modelSelect ? String(modelSelect.value || '').trim() : '';
  return v || 'acestep-v15-turbo';
}

function updateReadyStatus(maxDuration) {
  const max = (maxDuration != null) ? Number(maxDuration) : null;
  const maxTxt = (max != null && Number.isFinite(max)) ? max : 600;
  setStatusT('status.ready', { model: getSelectedModel(), max: maxTxt });
}


async function loadLoraCatalog() {
  if (!loraSelect) return;
  try {
    const r = await fetch(`/api/lora_catalog?ts=${Date.now()}`);
    const items = await r.json();
    

    _loraCatalogItems = Array.isArray(items) ? items : [];
    _loraLabelToEntry = new Map();
    _loraIdToEntry = new Map();
    
    window.__ACE_LORA_TRIGGERS = new Set();
    for (const it of _loraCatalogItems) {
      const _id = String((it && it.id) ? it.id : '').trim();
      const _trigger = String((it && (it.trigger ?? it.tag)) ? (it.trigger ?? it.tag) : '').trim();
      const _label = String((it && it.label) ? it.label : (_id || '')).trim();
      const entry = { id: _id, trigger: _trigger, label: _label };
      if (_id) _loraIdToEntry.set(_id, entry);
      if (_label) _loraLabelToEntry.set(_label, entry);
      if (_trigger) window.__ACE_LORA_TRIGGERS.add(_trigger);
    }

    loraSelect.innerHTML = '';
    for (const it of (items || [])) {
      const opt = document.createElement('option');
      const _id = (it && it.id) ? String(it.id) : '';
      const _trigger = (it && (it.trigger ?? it.tag)) ? String(it.trigger ?? it.tag) : '';
      const _label = (it && it.label) ? String(it.label) : String(it.id || '');
      opt.value = _id;
      opt.dataset.id = _id;
      opt.dataset.trigger = _trigger;
      opt.textContent = _label;
      if (!opt.value) opt.selected = true; 
      loraSelect.appendChild(opt);
    }
    
    if (!loraSelect.querySelector('option[value=""]')) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.dataset.id = '';
      opt.dataset.trigger = '';
      opt.textContent = t('lora.none');
      opt.selected = true;
      loraSelect.insertBefore(opt, loraSelect.firstChild);
    }

    
    try {
      const last = String(localStorage.getItem('ace_lora_id') || '').trim();
      if (last) loraSelect.value = last;
    } catch (e) {}

    
    try {
      loraSelect.addEventListener('change', () => {
        try { localStorage.setItem('ace_lora_id', String(loraSelect.value || '').trim()); } catch (e) {}
      });
    } catch (e) {}
  } catch (e) {
    
    loraSelect.innerHTML = `<option value="" selected>${t('lora.none')}</option>`;
  }
}

function getSelectedLora() {
  const sel = document.getElementById('lora_select');
  if (!sel) return { id: '', trigger: '', label: '' };
  const v = String(sel.value || '').trim();
  const opt = sel.selectedOptions ? sel.selectedOptions[0] : null;
  const dsId = opt && opt.dataset ? String(opt.dataset.id || '').trim() : '';
  const dsTrigger = opt && opt.dataset ? String((opt.dataset.trigger || opt.dataset.tag || '')).trim() : '';
  const label = opt ? String(opt.textContent || '').trim() : '';

  const id = v || dsId || '';
  let entry = null;
  if (id && _loraIdToEntry && _loraIdToEntry.has(id)) entry = _loraIdToEntry.get(id);
  if (!entry && label && _loraLabelToEntry && _loraLabelToEntry.has(label)) entry = _loraLabelToEntry.get(label);

  return {
    id: String((entry && entry.id) ? entry.id : id).trim(),
    trigger: String((entry && entry.trigger) ? entry.trigger : dsTrigger).trim(),
    label: String((entry && entry.label) ? entry.label : label).trim(),
  };
}

function getSelectedLoraWeight() {
  const nEl = document.getElementById('lora_weight_num');
  const rEl = document.getElementById('lora_weight');
  const n = nEl ? readNumericInputValue(nEl) : null;
  if (Number.isFinite(n)) return Math.max(0, Math.min(1, n));
  const r = rEl ? readNumericInputValue(rEl) : null;
  if (Number.isFinite(r)) return Math.max(0, Math.min(1, r));
  return 0.5;
}

function clamp01(v) {
  const n = (typeof v === 'number') ? v : readNumericInputValue({ value: v, type: 'text' });
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}
function isAbCompareEnabled() {
  return !!el('ab_compare_enabled')?.checked;
}

function updateAbCompareBatchUi() {
  const batchSel = el('batch_size');
  const abToggle = el('ab_compare_enabled');
  if (!batchSel || !abToggle) return;

  if (!batchSel.dataset.abPrevValue) {
    batchSel.dataset.abPrevValue = String(batchSel.value || '1');
  }

  if (abToggle.checked) {
    if (String(batchSel.value || '1') !== '1') {
      batchSel.dataset.abPrevValue = String(batchSel.value || '1');
    }
    batchSel.value = '1';
    batchSel.disabled = true;
    batchSel.classList.add('ro');
    batchSel.setAttribute('aria-disabled', 'true');
    batchSel.title = __tr('ab.batch_locked', 'Batch size is locked to 1 while compare mode is active.', 'Il batch size è bloccato a 1 mentre la modalità confronto è attiva.');
    return;
  }

  batchSel.disabled = false;
  batchSel.classList.remove('ro');
  batchSel.removeAttribute('aria-disabled');
  batchSel.title = '';
  const prev = String(batchSel.dataset.abPrevValue || '').trim();
  if (prev && prev !== '1' && String(batchSel.value || '1') === '1') {
    batchSel.value = prev;
  }
}

function __makeStableAbSeed(seedRandom, seedRaw) {
  if (!seedRandom) {
    const parsed = Number(seedRaw);
    return Number.isFinite(parsed) ? parsed : -1;
  }
  const max = 2147483646;
  return 1 + Math.floor(Math.random() * max);
}

function __makeAbCompareKey() {
  return `ab-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function __normalizeCustomModeConditioning(payload) {
  if (!payload || String(payload.generation_mode || '').trim() !== 'Custom') return payload;
  const hasAudioCodes = !!String(payload.audio_codes || '').trim();
  const usesLmThinking = !!payload.thinking;
  if (!hasAudioCodes && !usesLmThinking) return payload;
  return {
    ...payload,
    task_type: 'text2music',
    reference_audio: '',
    src_audio: '',
    audio_cover_strength: 1.0,
    cover_noise_strength: 0.0,
  };
}

function __setPlayerVolume(player, value) {
  if (!player || !player.audio || !player.vol) return;
  const v = Math.max(0, Math.min(1, Number(value) || 0));
  player.audio.volume = v;
  player.audio.muted = (v === 0);
  player.vol.value = String(v);
  if (typeof player._syncMuteIcon === 'function') player._syncMuteIcon();
}
function formatLoraWeight(v) {
  const n = clamp01(v);
  return n.toFixed(2).replace(/\.0+$/, '').replace(/(\.\d*[1-9])0+$/, '$1');
}
function syncLoraWeight(from, commit = false) {
  if (!loraWeight || !loraWeightNum) return;
  if (from === 'range') {
    const v = clamp01(readNumericInputValue(loraWeight));
    writeNumericInputValue(loraWeight, v, { preferValueAsNumber: true });
    writeNumericInputValue(loraWeightNum, v, { preferValueAsNumber: true });
  } else if (from === 'num') {
    const raw = readNumericInputValue(loraWeightNum);
    if (!Number.isFinite(raw)) return;
    const snapped = Math.round(clamp01(raw) / 0.05) * 0.05;
    writeNumericInputValue(loraWeight, snapped, { preferValueAsNumber: true });
    if (commit) writeNumericInputValue(loraWeightNum, snapped, { preferValueAsNumber: true });
  }
  try { localStorage.setItem('ace_lora_weight', String(formatLoraWeight(getSelectedLoraWeight()))); } catch (e) {}
}


let currentJobId = null;
let pollTimer = null;

let uploadedRefAudioPath = '';
let uploadedLmAudioPath = '';
let generatedChordConditioningPath = '';
let generatedChordConditioningName = '';
let chordConditioningMode = 'none';
let generatedChordReferenceSequence = [];
let generatedChordSectionPlan = [];
let generatedChordReferenceBpm = null;
let generatedChordReferenceTargetDuration = null;
let generatedChordAudioCodes = '';
let generatedChordFamily = '';
let generatedChordReferenceMeta = null;

function getGenerationMode() {
  const radios = document.querySelectorAll('input[name="generation_mode"]');
  for (const r of radios) {
    if (r.checked) return r.value;
  }
  return 'Custom';
}

function setGenerationMode(mode) {
  const radios = document.querySelectorAll('input[name="generation_mode"]');
  for (const r of radios) {
    r.checked = (r.value === mode);
  }
  updateModeVisibility();
}

function updateModeVisibility() {
  const mode = getGenerationMode();
  const needsAudio = (mode === 'Cover' || mode === 'Remix');
  const coverBalanceRow = el('cover_conditioning_balance_row');
  if (refAudioBox) {
    refAudioBox.classList.toggle('hidden', !needsAudio);
  }
  if (coverBalanceRow) {
    coverBalanceRow.classList.toggle('hidden', mode !== 'Cover');
  }

  
  if (belowSimple) {
    belowSimple.classList.toggle('hidden', mode === 'Simple');
  }

  
  const refLabel = document.getElementById('ref_audio_label');
  const refHelp = document.getElementById('ref_audio_help');
  if (refLabel && refHelp) {
    if (mode === 'Cover') {
      refLabel.textContent = t('label.ref_song_cover');
      refHelp.textContent = t('help.ref_song_cover');
    } else if (mode === 'Remix') {
      refLabel.textContent = t('label.ref_song_remix');
      refHelp.textContent = t('help.ref_song_remix');
    } else {
      refLabel.textContent = t('label.ref_song');
      refHelp.textContent = t('help.ref_song_upload');
    }
  }

  updateRefAudioVisibility();
  updateRemixSourceWindowVisibility();
}

function updateRemixSourceWindowVisibility() {
  const mode = getGenerationMode();
  const show = (mode === 'Remix');
  const startRow = document.getElementById('remix_source_window_start_row');
  const endRow = document.getElementById('remix_source_window_end_row');
  if (startRow) startRow.classList.toggle('hidden', !show);
  if (endRow) endRow.classList.toggle('hidden', !show);
}

function updateRefAudioVisibility() {
  const box = refAudioBox || document.getElementById('ref_audio_box');
  const status = refAudioStatus || document.getElementById('ref_audio_status');
  const nameNode = refAudioName || document.getElementById('ref_audio_name');
  const mode = getGenerationMode();
  const needsAudio = (mode === 'Cover' || mode === 'Remix');
  const effectivePath = String(((mode === 'Cover' || mode === 'Remix')
    ? (uploadedRefAudioPath || generatedChordConditioningPath)
    : (generatedChordConditioningPath || uploadedRefAudioPath)) || '').trim();
  const effectiveName = String((effectivePath && effectivePath === String(uploadedRefAudioPath || '').trim() ? '' : generatedChordConditioningName) || (effectivePath ? effectivePath.split(/[\/]/).pop() : '') || '').trim();

  if (box) box.classList.toggle('hidden', !needsAudio);
  if (!status) return;

  if (!needsAudio) {
    status.textContent = '';
    status.classList.add('hidden');
    return;
  }

  if (effectivePath) {
    status.textContent = `✅ ${effectiveName || effectivePath}`;
    status.title = effectivePath;
    status.classList.remove('hidden');
    if (nameNode && (!nameNode.textContent || nameNode.dataset.i18n === 'status.no_file_selected')) {
      nameNode.textContent = effectiveName || effectivePath;
      nameNode.title = effectivePath;
      nameNode.removeAttribute('data-i18n');
    }
    return;
  }

  status.textContent = '';
  status.title = '';
  status.classList.add('hidden');
  if (nameNode && !(refAudioInput && refAudioInput.files && refAudioInput.files[0])) {
    setFilePickName(nameNode, null);
  }
}

function numOrNull(v) {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}


function num(id, defVal) {
  const e = el(id);
  const v = e ? e.value : null;
  const n = numOrNull(v);
  return (n === null) ? defVal : n;
}


function intNum(id, defVal) {
  const e = el(id);
  const v = e ? e.value : null;
  const n = numOrNull(v);
  if (n === null) return defVal;
  const i = parseInt(String(n), 10);
  return Number.isFinite(i) ? i : defVal;
}


function strVal(id, defVal) {
  const e = el(id);
  if (!e) return defVal;
  const v = (e.value !== undefined && e.value !== null) ? String(e.value) : '';
  return v.trim().length ? v : defVal;
}


function boolVal(id, defVal) {
  const e = el(id);
  if (!e) return defVal;
  if (e.type === 'checkbox') return !!e.checked;
  
  const v = (e.value !== undefined && e.value !== null) ? String(e.value).trim().toLowerCase() : '';
  if (!v.length) return defVal;
  if (['1','true','yes','on'].includes(v)) return true;
  if (['0','false','no','off'].includes(v)) return false;
  return defVal;
}

function boolEl(id) {
  const e = el(id);
  return !!(e && e.checked);
}

function setDisabled(id, disabled) {
  const e = el(id);
  if (!e) return;
  e.disabled = !!disabled;
  e.classList.toggle('ro', !!disabled);
}

function setupAutoToggles() {
  const pairs = [
    { autoId: 'duration_auto', fieldId: 'duration' },
    { autoId: 'bpm_auto', fieldId: 'bpm' },
    { autoId: 'key_auto', fieldId: 'key_root' },
    { autoId: 'key_auto', fieldId: 'key_mode' },
    { autoId: 'timesig_auto', fieldId: 'timesignature' },
    { autoId: 'language_auto', fieldId: 'vocal_language' },
  ];

  const apply = () => {
    for (const p of pairs) {
      const on = boolEl(p.autoId);
      setDisabled(p.fieldId, on);

      
      const f = el(p.fieldId);
      if (f) {
        f.setAttribute('aria-disabled', on ? 'true' : 'false');
        
        if (on) {
          f.dataset.prevTabIndex = (f.getAttribute('tabindex') ?? '');
          f.setAttribute('tabindex', '-1');
        } else {
          const prev = (f.dataset.prevTabIndex ?? '');
          if (prev === '') f.removeAttribute('tabindex');
          else f.setAttribute('tabindex', prev);
          delete f.dataset.prevTabIndex;
        }
      }
    }
  };

  for (const p of pairs) {
    const a = el(p.autoId);
    if (a && !a.dataset.bound) {
      a.addEventListener('change', apply);
      a.dataset.bound = '1';
    }
    const f = el(p.fieldId);
    
    if (f && !f.dataset.boundAuto) {
      const forceManual = () => {
        const a2 = el(p.autoId);
        if (a2 && a2.checked) {
          a2.checked = false;
          apply();
        }
      };
      f.addEventListener('pointerdown', forceManual);
      f.addEventListener('focus', forceManual);
      f.dataset.boundAuto = '1';
    }
  }
  apply();
}

function setAutoOffForMusicMeta() {
  const ids = ['duration_auto','bpm_auto','key_auto','timesig_auto','language_auto'];
  for (const id of ids) {
    const e = el(id);
    if (e) { e.checked = false; e.dispatchEvent(new Event("change", { bubbles: true })); }
  }
  
  setDisabled('duration', false);
  setDisabled('bpm', false);
  setDisabled('key_root', false);
  setDisabled('key_mode', false);
  setDisabled('timesignature', false);
  setDisabled('vocal_language', false);
}

function syncRangeNumber(rangeId, numId, { decimals = null } = {}) {
  const r = el(rangeId);
  const n = el(numId);
  if (!r || !n) return;
  if (n.dataset.syncBound === '1') return;
  n.dataset.syncBound = '1';
  n.dataset.numericCommitBound = '1';

  const clampToAttrs = (val) => {
    const parsed = (typeof val === 'number') ? val : readNumericInputValue({ value: val, type: 'text' });
    if (!Number.isFinite(parsed)) return null;
    const min = (n.min !== '') ? Number(n.min) : ((r.min !== '') ? Number(r.min) : null);
    const max = (n.max !== '') ? Number(n.max) : ((r.max !== '') ? Number(r.max) : null);
    let out = parsed;
    if (Number.isFinite(min)) out = Math.max(min, out);
    if (Number.isFinite(max)) out = Math.min(max, out);
    return out;
  };

  const fromRange = () => {
    const v = clampToAttrs(r.value);
    if (v == null) return;
    writeNumericInputValue(n, v, { decimals, preferValueAsNumber: true });
    try { n.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
  };
  const fromNumInput = () => {
    const v = clampToAttrs(readNumericInputValue(n));
    if (v == null) return;
    r.value = String(v);
  };
  const fromNumCommit = () => {
    const v = clampToAttrs(readNumericInputValue(n));
    if (v == null) return;
    r.value = String(v);
    writeNumericInputValue(n, v, { decimals, preferValueAsNumber: true });
    try { n.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
  };

  r.addEventListener('input', fromRange);
  r.addEventListener('change', fromRange);
  n.addEventListener('input', fromNumInput);
  n.addEventListener('change', fromNumCommit);
  n.addEventListener('blur', fromNumCommit);
  n.addEventListener('keydown', (e) => {
    commitNumericFieldOnEnter(e, n, fromNumCommit);
  });

  if (String(n.value || '').trim() !== '') fromNumCommit();
  else fromRange();
}



let __ACE_STEP_LIMITS = {
  max_inference_steps_turbo: 20,
  max_inference_steps_base: 200,
  max_inference_steps_current_model: 20,
};

function isSftModelName(modelName) {
  const v = String(modelName || '').trim().toLowerCase();
  return v.startsWith('sft') || v.includes('sft');
}

function isTurboModelName(modelName) {
  const v = String(modelName || '').trim().toLowerCase();
  return v.includes('turbo') && !isSftModelName(v);
}

function getCurrentStepLimit(modelName) {
  if (isTurboModelName(modelName)) return Number(__ACE_STEP_LIMITS.max_inference_steps_turbo || 20);
  return Number(__ACE_STEP_LIMITS.max_inference_steps_base || 200);
}

function getDefaultInferenceStepsForModel(modelName) {
  if (isSftModelName(modelName)) return 50;
  if (isTurboModelName(modelName)) return 8;
  return 20;
}

function applyInferenceStepLimit(modelName, options = {}) {
  const st = el('steps') || el('inference_steps');
  const stR = el('steps_range') || el('inference_steps_range');
  if (!st || !stR) return;
  const maxSteps = Math.max(1, getCurrentStepLimit(modelName));
  const minSteps = 1;
  const preserveValue = options.preserveValue !== false;
  const desiredValue = options.desiredValue;
  st.min = String(minSteps);
  st.max = String(maxSteps);
  stR.min = String(minSteps);
  stR.max = String(maxSteps);
  let nextValue = desiredValue;
  if (nextValue == null && preserveValue) {
    const current = Number((st.value ?? stR.value ?? '').toString().trim());
    if (!Number.isNaN(current)) nextValue = current;
  }
  if (nextValue == null) nextValue = maxSteps;
  nextValue = Math.max(minSteps, Math.min(maxSteps, Math.round(Number(nextValue) || minSteps)));
  writeNumericInputValue(st, nextValue, { decimals: 0, preferValueAsNumber: true });
  stR.value = String(nextValue);
}

function syncStepsPair() {
  const st = el('steps');
  const stR = el('steps_range');
  if (!st || !stR) return;
  const clamp = (v) => {
    const parsed = (typeof v === 'number') ? v : readNumericInputValue({ value: v, type: 'text' });
    if (!Number.isFinite(parsed)) return null;
    const min = (st.min !== '') ? Number(st.min) : 1;
    const max = (st.max !== '') ? Number(st.max) : 200;
    return Math.max(min, Math.min(max, Math.round(parsed)));
  };
  const fromRange = () => {
    const v = clamp(stR.value);
    if (v == null) return;
    writeNumericInputValue(st, v, { decimals: 0, preferValueAsNumber: true });
    __stepsTouched = true;
  };
  const fromNumInput = () => {
    const v = clamp(readNumericInputValue(st));
    if (v == null) return;
    stR.value = String(v);
    __stepsTouched = true;
  };
  const fromNumCommit = () => {
    const v = clamp(readNumericInputValue(st));
    if (v == null) return;
    writeNumericInputValue(st, v, { decimals: 0, preferValueAsNumber: true });
    stR.value = String(v);
    __stepsTouched = true;
  };
  if (!st.dataset.bound) {
    st.dataset.bound = '1';
    st.dataset.numericCommitBound = '1';
    st.addEventListener('input', fromNumInput);
    st.addEventListener('change', fromNumCommit);
    st.addEventListener('blur', fromNumCommit);
    st.addEventListener('keydown', (e) => {
      commitNumericFieldOnEnter(e, st, fromNumCommit);
    });
  }
  if (!stR.dataset.bound) {
    stR.dataset.bound = '1';
    stR.addEventListener('input', fromRange);
    stR.addEventListener('change', fromRange);
  }
  fromNumCommit();
}





let _lastStatus = { kind: 'raw', msg: '' };


let _lastNotice = { kind: 'raw', msg: '' };

function setStatusRaw(msg) {
  _lastStatus = { kind: 'raw', msg: String(msg ?? '') };
  statusBox.textContent = _lastStatus.msg;
}

function setStatusT(key, vars) {
  _lastStatus = { kind: 'i18n', key: String(key || ''), vars: (vars || null) };
  statusBox.textContent = t(_lastStatus.key, _lastStatus.vars);
}

function rerenderStatusForLangChange() {
  if (!_lastStatus || !statusBox) return;
  if (_lastStatus.kind === 'i18n' && _lastStatus.key) {
    statusBox.textContent = t(_lastStatus.key, _lastStatus.vars);
  }
}

function setNoticeRaw(msg) {
  if (!noticeBox) return;
  const s = String(msg ?? '').trim();
  _lastNotice = { kind: 'raw', msg: s };
  if (!s) {
    noticeBox.textContent = '';
    noticeBox.classList.add('hidden');
    return;
  }
  noticeBox.textContent = s;
  noticeBox.classList.remove('hidden');
}

function setNoticeT(key, vars) {
  if (!noticeBox) return;
  const kk = String(key || '').trim();
  _lastNotice = { kind: 'i18n', key: kk, vars: (vars || null) };
  const s = kk ? t(kk, vars) : '';
  if (!s) {
    noticeBox.textContent = '';
    noticeBox.classList.add('hidden');
    return;
  }
  noticeBox.textContent = s;
  noticeBox.classList.remove('hidden');
}

function clearNotice() {
  setNoticeRaw('');
}

function rerenderNoticeForLangChange() {
  if (!_lastNotice || !noticeBox) return;
  if (_lastNotice.kind === 'i18n' && _lastNotice.key) {
    const s = t(_lastNotice.key, _lastNotice.vars);
    if (s) {
      noticeBox.textContent = s;
      noticeBox.classList.remove('hidden');
    }
  }
}










const __activePlayers = new Set();


let __stepsTouched = false;

let __sharedDecodeCtx = null;

function __getDecodeCtx() {
  if (__sharedDecodeCtx) return __sharedDecodeCtx;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return null;
  __sharedDecodeCtx = new AC({ sampleRate: 48000 });
  return __sharedDecodeCtx;
}

function __tr(key, fallbackEn, fallbackIt) {
  const _t = (typeof window.t === "function") ? window.t : t;
  const r = _t(key);
  if (r && r !== key) return r;
  const lang = (typeof window.getUiLang === "function") ? window.getUiLang() : (document.documentElement.lang || "en");
  if (lang === "it") return (fallbackIt != null) ? fallbackIt : (fallbackEn != null ? fallbackEn : key);
  return (fallbackEn != null) ? fallbackEn : (fallbackIt != null ? fallbackIt : key);
}

function __fmtTime(sec) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  sec = Math.floor(sec);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function __extToMime(url) {
  const q = url.split('?')[0];
  const ext = (q.split('.').pop() || '').toLowerCase();
  switch (ext) {
    case 'flac': return 'audio/flac';
    case 'wav': return 'audio/wav';
    case 'mp3': return 'audio/mpeg';
    case 'ogg': return 'audio/ogg';
    case 'opus': return 'audio/opus';
    case 'm4a': return 'audio/mp4';
    case 'aac': return 'audio/aac';
    default: return '';
  }
}

function __hashStr(s) {
  
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function __seededRand(seed) {
  
  let x = seed >>> 0;
  return () => {
    x ^= x << 13; x >>>= 0;
    x ^= x >> 17; x >>>= 0;
    x ^= x << 5;  x >>>= 0;
    return (x >>> 0) / 4294967296;
  };
}

function __makeBtn(label, aria, onClick, cls = '') {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = `pbtn ${cls}`.trim();
  b.textContent = label;
  b.setAttribute('aria-label', aria);
  b.addEventListener('click', onClick);
  return b;
}

function destroyAllPlayers() {
  for (const p of Array.from(__activePlayers)) {
    try { p.destroy(); } catch (e) {  }
  }
  __activePlayers.clear();
}

class GradioLikePlayer {
  constructor({ url, index, jsonUrl, audioFilename, resolvedSeed }) {
    this.url = url;
    this.index = index;
    this.jsonUrl = jsonUrl;
    this.audioFilename = String(audioFilename || "").trim();
    this.resolvedSeed = (resolvedSeed != null) ? resolvedSeed : null;

    this.abort = new AbortController();
    this.raf = 0;
    this.audioBlobUrl = null;
    this.audioBuffer = null;
    this.peaks = null;
    this.zoom = 1; 
    this._dragging = false;

    this.root = document.createElement('div');
    this.root.className = 'gplayer';

    
    const head = document.createElement('div');
    head.className = 'gplayerHead';

    const title = document.createElement('div');
    title.className = 'gplayerTitle';
    title.textContent = t('result.audio_n', { n: index + 1 });

    this.msg = document.createElement('div');
    this.msg.className = 'gplayerMsg muted';
    this.msg.textContent = '';

    head.appendChild(title);
    head.appendChild(this.msg);

    const meta = document.createElement('div');
    meta.className = 'gplayerMeta';
    this.fileSpan = null;
    if (this.audioFilename) {
      const fSpan = document.createElement('span');
      fSpan.className = 'gplayerMetaItem';
      this.fileSpan = fSpan;
      meta.appendChild(fSpan);
    }
    this.seedSpan = document.createElement('span');
    this.seedSpan.className = 'gplayerMetaItem';
    meta.appendChild(this.seedSpan);
    this._metaEl = meta;

    
    const waveWrap = document.createElement('div');
    waveWrap.className = 'waveWrap';

    this.waveScroller = document.createElement('div');
    this.waveScroller.className = 'waveScroller';
    this.waveScroller.tabIndex = 0;
    this.waveScroller.setAttribute('aria-label', 'Waveform timeline');

    this.baseCanvas = document.createElement('canvas');
    this.baseCanvas.className = 'waveCanvas base';

    this.overlayCanvas = document.createElement('canvas');
    this.overlayCanvas.className = 'waveCanvas overlay';

    this.waveScroller.appendChild(this.baseCanvas);
    this.waveScroller.appendChild(this.overlayCanvas);

    this.loader = document.createElement('div');
    this.loader.className = 'waveLoader';
    this.loader.textContent = __tr('player.analyzing', 'Analyzing audio…', 'Analizzo audio…');
    this.loader.setAttribute('role', 'status');
    this.loader.setAttribute('aria-live', 'polite');

    waveWrap.appendChild(this.waveScroller);
    waveWrap.appendChild(this.loader);

    
    const controls = document.createElement('div');
    controls.className = 'gcontrols';

    this.playBtn = __makeBtn('▶', 'Play/Pause', () => this.togglePlay());
    this.stopBtn = __makeBtn('⏹', __tr('player.stop', 'Stop'), () => this.stop());
    this.backBtn = __makeBtn('⟲', __tr('player.skip_back', 'Back 5s', 'Indietro 5s'), () => this.skip(-5));
    this.fwdBtn  = __makeBtn('⟳', __tr('player.skip_fwd', 'Forward 5s', 'Avanti 5s'), () => this.skip(5));

    this.timeLbl = document.createElement('div');
    this.timeLbl.className = 'ptime';
    this.timeLbl.textContent = '0:00 / --:--';

    const volBox = document.createElement('div');
    volBox.className = 'pvol';

    this.muteBtn = __makeBtn('🔊', __tr('player.mute', 'Mute', 'Muto'), () => this.toggleMute(), 'mute');

    this.vol = document.createElement('input');
    this.vol.type = 'range';
    this.vol.min = '0';
    this.vol.max = '1';
    this.vol.step = '0.01';
    this.vol.value = '1';
    this.vol.className = 'vol';
    this.vol.setAttribute('aria-label', 'Volume');

    volBox.appendChild(this.muteBtn);
    volBox.appendChild(this.vol);

    
    const actions = document.createElement('div');
    actions.className = 'pactions';

    this.dlA = document.createElement('a');
    this.dlA.href = url;
    this.dlA.className = 'paction';
    this.dlA.setAttribute('aria-label', __tr('player.download', 'Download audio', 'Scarica audio'));
    
    this.dlA.setAttribute('download', this.audioFilename || '');
    this.dlA.textContent = __tr('player.download', 'Download audio', 'Scarica audio');

    this.jsonA = document.createElement('a');
    this.jsonA.href = jsonUrl || '#';
    this.jsonA.className = 'paction secondary';
    this.jsonA.setAttribute('aria-label', __tr('player.json', 'Download JSON', 'Scarica JSON'));
    this.jsonA.textContent = __tr('player.json', 'Download JSON', 'Scarica JSON');
    if (jsonUrl) {
      const jobId = __getJobIdFromUrl(jsonUrl) || __getJobIdFromUrl(url);
      
      
      this.jsonA.addEventListener('click', (ev) => {
        const isNewTabIntent = !!(ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button === 1);
        if (isNewTabIntent) return;
        ev.preventDefault();
        downloadMergedJobJson(jsonUrl, jobId, url, this.audioFilename);
      });
      this.jsonA.target = '_blank';
      this.jsonA.rel = 'noopener';
    } else {
      this.jsonA.classList.add('disabled');
      this.jsonA.setAttribute('aria-disabled', 'true');
      this.jsonA.addEventListener('click', (e) => e.preventDefault());
    }

    actions.appendChild(this.dlA);
    actions.appendChild(this.jsonA);

    controls.appendChild(this.playBtn);
    controls.appendChild(this.stopBtn);
    controls.appendChild(this.backBtn);
    controls.appendChild(this.fwdBtn);
    controls.appendChild(this.timeLbl);
    controls.appendChild(volBox);
    controls.appendChild(actions);

    
    this.audio = document.createElement('audio');
    this.audio.preload = 'metadata';
    this.audio.className = 'nativeAudioHidden';

    
    this.root.appendChild(head);
    this.root.appendChild(meta);
    this.root.appendChild(waveWrap);
    this.root.appendChild(controls);
    this.root.appendChild(this.audio);

    
    this._wire();

    __activePlayers.add(this);
  }

  mount(parent) {
    parent.appendChild(this.root);
    this._updateMetaLang();
    this._langHandler = () => this._updateMetaLang();
    window.addEventListener('ace_ui_lang_changed', this._langHandler);
    window.addEventListener('ace:ui_lang_changed', this._langHandler);
    this.init();
  }

  _updateMetaLang() {
    const seedVal = (this.resolvedSeed != null && this.resolvedSeed >= 0) ? String(this.resolvedSeed) : '—';
    if (this.fileSpan) this.fileSpan.textContent = __tr('player.file', 'File', 'File') + ': ' + this.audioFilename;
    this.seedSpan.textContent = __tr('player.resolved_seed', 'Resolved seed', 'Seed risolto') + ': ' + seedVal;
  }


  _wire() {
    
    this.audio.addEventListener('loadedmetadata', () => {
      this._updateTime();
      this._ensureCanvasSize();
      this._drawBaseIfNeeded();
    });

    this.audio.addEventListener('timeupdate', () => this._updateTime());
    this.audio.addEventListener('play', () => this._onPlayState(true));
    this.audio.addEventListener('pause', () => this._onPlayState(false));
    this.audio.addEventListener('ended', () => this._onPlayState(false));
    this.audio.addEventListener('error', () => {
      this._showUnsupported();
    });

    
    this.vol.addEventListener('input', () => {
      this.audio.volume = parseFloat(this.vol.value);
      if (this.audio.volume === 0) this.audio.muted = true;
      this._syncMuteIcon();
    });

    
    const seekFromEvent = (ev) => {
      const rect = this.waveScroller.getBoundingClientRect();
      const x = ev.clientX - rect.left + this.waveScroller.scrollLeft;
      const w = Math.max(1, this.baseCanvas.width);
      const p = Math.max(0, Math.min(1, x / w));
      const dur = this.audio.duration;
      if (isFinite(dur) && dur > 0) this.audio.currentTime = dur * p;
      this._drawOverlay();
    };

    this.waveScroller.addEventListener('mousedown', (ev) => {
      if (ev.button !== 0) return;
      this._dragging = true;
      seekFromEvent(ev);
    });
    window.addEventListener('mousemove', (ev) => {
      if (!this._dragging) return;
      seekFromEvent(ev);
    });
    window.addEventListener('mouseup', () => {
      this._dragging = false;
    });

    this.waveScroller.addEventListener('click', (ev) => {
      seekFromEvent(ev);
    });

    
    this.waveScroller.addEventListener('keydown', (ev) => {
      if (ev.key === 'ArrowLeft') { ev.preventDefault(); this.skip(-5); }
      if (ev.key === 'ArrowRight') { ev.preventDefault(); this.skip(5); }
      if (ev.key === ' ') { ev.preventDefault(); this.togglePlay(); }
    });

    
    this.waveScroller.addEventListener('wheel', (ev) => {
      if (!(ev.ctrlKey || ev.metaKey)) return;
      ev.preventDefault();
      const delta = Math.sign(ev.deltaY);
      const before = this.zoom;
      this.zoom = Math.max(1, Math.min(8, this.zoom + (delta > 0 ? -1 : 1)));
      if (this.zoom !== before) {
        this._ensureCanvasSize(true);
        this._drawBaseIfNeeded(true);
        this._drawOverlay();
      }
    }, { passive: false });
  }

  async init() {
    this._setMsg(__tr('player.analyzing', 'Analyzing audio…', 'Analizzo audio…'), 'muted');
    this._setLoader(true);

    
    
    const ctx = __getDecodeCtx();
    if (!ctx) {
      this._setMsg(__tr('player.web_audio_unavailable', 'WebAudio unavailable: using native player.', 'WebAudio non disponibile: uso player nativo.'), 'muted');
      this._fallbackStreaming();
      return;
    }

    try {
      const res = await fetch(this.url, { signal: this.abort.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const buf = await res.arrayBuffer();

      
      const ab = buf.slice(0); 
      const audioBuffer = await new Promise((resolve, reject) => {
        
        const p = ctx.decodeAudioData(ab);
        if (p && typeof p.then === 'function') {
          p.then(resolve).catch(reject);
        } else {
          ctx.decodeAudioData(ab, resolve, reject);
        }
      });

      this.audioBuffer = audioBuffer;
      this._buildPeaksFromBuffer(audioBuffer);

      
      const mime = __extToMime(this.url) || 'application/octet-stream';
      const blob = new Blob([buf], { type: mime });
      this.audioBlobUrl = URL.createObjectURL(blob);
      this.audio.src = this.audioBlobUrl;

      this._setMsg('', 'muted');
      this._setLoader(false);
      this._ensureCanvasSize(true);
      this._drawBaseIfNeeded(true);
      this._drawOverlay();
    } catch (err) {
      
      const msg = __tr('player.web_audio_decode_failed', 'Waveform analysis failed in this browser. Using native playback.', 'Impossibile analizzare la waveform in questo browser. Uso riproduzione nativa.');
      this._setMsg(msg, 'warn');
      this._fallbackStreaming();
    }
  }

  _fallbackStreaming() {
    
    this._setLoader(false);
    this.audio.src = this.url;

    
    this._buildPlaceholderPeaks();
    this._ensureCanvasSize(true);
    this._drawBaseIfNeeded(true);
    this._drawOverlay();
  }

  _showUnsupported() {
    this._setLoader(false);
    this._setMsg(__tr('player.format_unsupported', 'Format not supported by this browser. Use Download to open it with an external player.', 'Formato non supportato dal browser. Usa Download per aprirlo con un player esterno.'), 'err');

    
    for (const b of [this.playBtn, this.stopBtn, this.backBtn, this.fwdBtn, this.muteBtn, this.vol]) {
      b.disabled = true;
    }
    this.waveScroller.classList.add('disabled');
  }

  togglePlay() {
    if (this.audio.paused) {
      this.audio.play().catch(() => {
        
      });
    } else {
      this.audio.pause();
    }
  }

  stop() {
    this.audio.pause();
    try { this.audio.currentTime = 0; } catch (e) {  }
    this._drawOverlay();
    this._updateTime();
  }

  skip(delta) {
    const dur = this.audio.duration;
    let tcur = this.audio.currentTime || 0;
    let next = tcur + delta;
    if (isFinite(dur) && dur > 0) next = Math.max(0, Math.min(dur, next));
    else next = Math.max(0, next);
    try { this.audio.currentTime = next; } catch (e) {  }
    this._drawOverlay();
    this._updateTime();
  }

  toggleMute() {
    this.audio.muted = !this.audio.muted;
    if (this.audio.muted) {
      this.muteBtn.textContent = '🔇';
      this.muteBtn.setAttribute('aria-label', __tr('player.unmute', 'Unmute', 'Audio'));
    } else {
      this.muteBtn.textContent = '🔊';
      this.muteBtn.setAttribute('aria-label', __tr('player.mute', 'Mute', 'Muto'));
    }
  }

  _syncMuteIcon() {
    if (this.audio.muted || this.audio.volume === 0) {
      this.muteBtn.textContent = '🔇';
    } else {
      this.muteBtn.textContent = '🔊';
    }
  }

  _onPlayState(isPlaying) {
    this.playBtn.textContent = isPlaying ? '⏸' : '▶';
    if (isPlaying) this._startRAF();
    else this._stopRAF();
  }

  _startRAF() {
    if (this.raf) return;
    const tick = () => {
      this._drawOverlay();
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  _stopRAF() {
    if (!this.raf) return;
    cancelAnimationFrame(this.raf);
    this.raf = 0;
    this._drawOverlay();
  }

  _setMsg(text, kind) {
    this.msg.textContent = text || '';
    this.msg.classList.remove('muted', 'warn', 'err');
    this.msg.classList.add(kind || 'muted');
  }

  _setLoader(on) {
    this.loader.style.display = on ? 'flex' : 'none';
    this.waveScroller.classList.toggle('loading', !!on);
  }

  _updateTime() {
    const cur = this.audio.currentTime || 0;
    const dur = this.audio.duration;
    const durStr = (isFinite(dur) && dur > 0) ? __fmtTime(dur) : '--:--';
    this.timeLbl.textContent = `${__fmtTime(cur)} / ${durStr}`;
  }

  _ensureCanvasSize(force = false) {
    const h = 72; 
    const viewportW = Math.max(280, Math.floor(this.waveScroller.clientWidth || 600));
    const w = Math.floor(viewportW * this.zoom);

    const resize = (c) => {
      if (force || c.width !== w || c.height !== h) {
        c.width = w;
        c.height = h;
        c.style.width = `${w}px`;
        c.style.height = `${h}px`;
      }
    };
    resize(this.baseCanvas);
    resize(this.overlayCanvas);
  }

  _buildPeaksFromBuffer(buf) {
    
    const ch0 = buf.getChannelData(0);
    const ch1 = buf.numberOfChannels > 1 ? buf.getChannelData(1) : null;

    
    
    const buckets = 4096;
    const step = Math.max(1, Math.floor(ch0.length / buckets));
    const peaks = new Float32Array(buckets);

    for (let i = 0; i < buckets; i++) {
      const start = i * step;
      const end = Math.min(ch0.length, start + step);
      let max = 0;
      for (let j = start; j < end; j++) {
        const v0 = Math.abs(ch0[j]);
        const v = ch1 ? Math.max(v0, Math.abs(ch1[j])) : v0;
        if (v > max) max = v;
      }
      peaks[i] = max;
    }
    this.peaks = peaks;
  }

  _buildPlaceholderPeaks() {
    const seed = __hashStr(this.url);
    const rnd = __seededRand(seed);
    const buckets = 4096;
    const peaks = new Float32Array(buckets);
    
    let env = 0.3 + rnd() * 0.4;
    for (let i = 0; i < buckets; i++) {
      if (i % 128 === 0) env = 0.2 + rnd() * 0.8;
      const noise = rnd();
      const v = Math.min(1, (noise * noise) * env);
      peaks[i] = v;
    }
    this.peaks = peaks;
  }

  _drawBaseIfNeeded(force = false) {
    if (!this.peaks) return;
    const c = this.baseCanvas;
    const ctx = c.getContext('2d');
    if (!ctx) return;

    
    ctx.clearRect(0, 0, c.width, c.height);

    const mid = Math.floor(c.height / 2);
    const len = this.peaks.length;
    const pixels = c.width;
    for (let x = 0; x < pixels; x++) {
      const i = Math.floor((x / pixels) * len);
      const p = this.peaks[i] || 0;
      const amp = Math.floor(p * (c.height * 0.48));
      
      ctx.fillStyle = 'rgba(255,255,255,0.18)';
      ctx.fillRect(x, mid - amp, 1, amp * 2);
    }

    
    ctx.fillStyle = 'rgba(255,255,255,0.08)';
    ctx.fillRect(0, mid, c.width, 1);
  }

  _drawOverlay() {
    const c = this.overlayCanvas;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, c.width, c.height);

    const dur = this.audio.duration;
    const cur = this.audio.currentTime || 0;
    if (!isFinite(dur) || dur <= 0) return;

    const p = Math.max(0, Math.min(1, cur / dur));
    const x = Math.floor(p * c.width);

    
    ctx.fillStyle = 'rgba(255,255,255,0.08)';
    ctx.fillRect(0, 0, x, c.height);

    
    ctx.fillStyle = 'rgba(255,255,255,0.65)';
    ctx.fillRect(x, 0, 2, c.height);

    
    const left = this.waveScroller.scrollLeft;
    const view = this.waveScroller.clientWidth;
    if (x < left + 24 || x > left + view - 24) {
      const target = Math.max(0, x - Math.floor(view / 2));
      this.waveScroller.scrollLeft = target;
    }
  }

  destroy() {
    try { this.abort.abort(); } catch (e) {  }
    this._stopRAF();
    if (this.audio) {
      try { this.audio.pause(); } catch (e) {  }
      this.audio.src = '';
    }
    if (this.audioBlobUrl) {
      try { URL.revokeObjectURL(this.audioBlobUrl); } catch (e) {  }
      this.audioBlobUrl = null;
    }
    __activePlayers.delete(this);
    if (this._langHandler) {
      window.removeEventListener('ace_ui_lang_changed', this._langHandler);
      window.removeEventListener('ace:ui_lang_changed', this._langHandler);
    }
    if (this.root && this.root.parentNode) this.root.parentNode.removeChild(this.root);
  }
}

class AbCompareBridge {
  constructor(aPlayer, bPlayer, labels = {}) {
    this.a = aPlayer;
    this.b = bPlayer;
    this.labels = {
      a: String(labels.a || __tr('ab.audio1', 'Audio 1', 'Audio 1')),
      b: String(labels.b || __tr('ab.audio2', 'Audio 2', 'Audio 2')),
    };
    this.syncing = false;
    this.root = document.createElement('div');
    this.root.className = 'abCompareBridge';

    const title = document.createElement('div');
    title.className = 'abCompareTitle';
    title.textContent = __tr('ab.compare_title', 'Audio 1 / Audio 2 Controls', 'Controlli Audio 1 / Audio 2');
    this.titleNode = title;

    const desc = document.createElement('div');
    desc.className = 'abCompareDesc muted';
    desc.textContent = __tr('ab.compare_desc', 'The normal players stay untouched. These controls act on both together.', 'I player normali restano intatti. Questi controlli agiscono su entrambi insieme.');
    this.descNode = desc;

    const controls = document.createElement('div');
    controls.className = 'abCompareControls';

    const leftControls = document.createElement('div');
    leftControls.className = 'abCompareControlsLeft';

    this.playBtn = __makeBtn('▶', __tr('ab.play_pause', 'Play/Pause both', 'Play/Pausa entrambi'), () => this.togglePlayBoth());
    this.stopBtn = __makeBtn('⏹', __tr('ab.stop', 'Stop both', 'Stop entrambi'), () => this.stopBoth());

    this.timeLbl = document.createElement('div');
    this.timeLbl.className = 'ptime';
    this.timeLbl.textContent = '0:00 / --:--';

    leftControls.appendChild(this.playBtn);
    leftControls.appendChild(this.stopBtn);
    leftControls.appendChild(this.timeLbl);

    const fadeWrap = document.createElement('div');
    fadeWrap.className = 'abFadeWrap';

    const labelsRow = document.createElement('div');
    labelsRow.className = 'abFadeLabels';
    this.leftLabel = document.createElement('span');
    this.leftLabel.textContent = this.labels.a;
    this.rightLabel = document.createElement('span');
    this.rightLabel.textContent = this.labels.b;
    labelsRow.appendChild(this.leftLabel);
    labelsRow.appendChild(this.rightLabel);

    this.fade = document.createElement('input');
    this.fade.type = 'range';
    this.fade.min = '0';
    this.fade.max = '100';
    this.fade.step = '1';
    this.fade.value = '0';
    this.fade.className = 'abFadeSlider';
    this.fade.setAttribute('aria-label', __tr('ab.crossfade', 'Crossfade', 'Crossfade'));

    fadeWrap.appendChild(labelsRow);
    fadeWrap.appendChild(this.fade);

    controls.appendChild(leftControls);
    controls.appendChild(fadeWrap);

    this.root.appendChild(title);
    this.root.appendChild(desc);
    this.root.appendChild(controls);

    this._wire();
    this.applyCrossfade();
    this._updateTime();
  }

  mount(parent) {
    parent.appendChild(this.root);
    this._langHandler = () => this.updateLang();
    window.addEventListener('ace_ui_lang_changed', this._langHandler);
    window.addEventListener('ace:ui_lang_changed', this._langHandler);
    this.updateLang();
  }

  updateLang() {
    this.labels.a = __tr('ab.audio1', 'Audio 1', 'Audio 1');
    this.labels.b = __tr('ab.audio2', 'Audio 2', 'Audio 2');
    if (this.titleNode) this.titleNode.textContent = __tr('ab.compare_title', 'Audio 1 / Audio 2 Controls', 'Controlli Audio 1 / Audio 2');
    if (this.descNode) this.descNode.textContent = __tr('ab.compare_desc', 'The normal players stay untouched. These controls act on both together.', 'I player normali restano intatti. Questi controlli agiscono su entrambi insieme.');
    if (this.leftLabel) this.leftLabel.textContent = this.labels.a;
    if (this.rightLabel) this.rightLabel.textContent = this.labels.b;
    if (this.playBtn) {
      this.playBtn.title = __tr('ab.play_pause', 'Play/Pause both', 'Play/Pausa entrambi');
      this.playBtn.setAttribute('aria-label', __tr('ab.play_pause', 'Play/Pause both', 'Play/Pausa entrambi'));
    }
    if (this.stopBtn) {
      this.stopBtn.title = __tr('ab.stop', 'Stop both', 'Stop entrambi');
      this.stopBtn.setAttribute('aria-label', __tr('ab.stop', 'Stop both', 'Stop entrambi'));
    }
    if (this.fade) {
      this.fade.title = __tr('ab.crossfade', 'Crossfade', 'Crossfade');
      this.fade.setAttribute('aria-label', __tr('ab.crossfade', 'Crossfade', 'Crossfade'));
    }
  }

  _wire() {
    this.fade.addEventListener('input', () => this.applyCrossfade());
    const syncTime = (source, target) => {
      if (this.syncing) return;
      this.syncing = true;
      try {
        const t = Number(source?.audio?.currentTime || 0);
        if (target?.audio && Number.isFinite(t) && Math.abs((target.audio.currentTime || 0) - t) > 0.12) target.audio.currentTime = t;
      } catch (e) {}
      this.syncing = false;
      this._updateTime();
    };
    const syncState = () => {
      const playing = !this.a.audio.paused || !this.b.audio.paused;
      this.playBtn.textContent = playing ? '⏸' : '▶';
      this._updateTime();
    };
    [this.a.audio, this.b.audio].forEach((audio) => {
      audio.addEventListener('timeupdate', () => this._updateTime());
      audio.addEventListener('play', syncState);
      audio.addEventListener('pause', syncState);
      audio.addEventListener('ended', syncState);
    });
    this.a.audio.addEventListener('seeked', () => syncTime(this.a, this.b));
    this.b.audio.addEventListener('seeked', () => syncTime(this.b, this.a));
  }

  applyCrossfade() {
    const ratio = Math.max(0, Math.min(1, Number(this.fade.value || 0) / 100));
    __setPlayerVolume(this.a, 1 - ratio);
    __setPlayerVolume(this.b, ratio);
  }

  async togglePlayBoth() {
    const playing = !this.a.audio.paused || !this.b.audio.paused;
    if (playing) {
      this.a.audio.pause();
      this.b.audio.pause();
      return;
    }
    const targetTime = Math.max(Number(this.a.audio.currentTime || 0), Number(this.b.audio.currentTime || 0));
    try { this.a.audio.currentTime = targetTime; } catch (e) {}
    try { this.b.audio.currentTime = targetTime; } catch (e) {}
    const plays = [];
    try { plays.push(this.a.audio.play()); } catch (e) {}
    try { plays.push(this.b.audio.play()); } catch (e) {}
    try { await Promise.allSettled(plays); } catch (e) {}
    this._updateTime();
  }

  stopBoth() {
    [this.a, this.b].forEach((player) => {
      try { player.audio.pause(); } catch (e) {}
      try { player.audio.currentTime = 0; } catch (e) {}
      if (typeof player._drawOverlay === 'function') player._drawOverlay();
      if (typeof player._updateTime === 'function') player._updateTime();
    });
    this._updateTime();
  }

  _updateTime() {
    const cur = Math.max(Number(this.a.audio.currentTime || 0), Number(this.b.audio.currentTime || 0));
    const durA = Number(this.a.audio.duration || 0);
    const durB = Number(this.b.audio.duration || 0);
    const dur = Math.max(durA, durB);
    const durStr = (Number.isFinite(dur) && dur > 0) ? __fmtTime(dur) : '--:--';
    this.timeLbl.textContent = `${__fmtTime(cur)} / ${durStr}`;
  }
}

function createGradioLikePlayerCard(url, idx, jsonUrl, audioFilename, resolvedSeed) {
  const p = new GradioLikePlayer({ url, index: idx, jsonUrl, audioFilename, resolvedSeed });
  const wrap = document.createElement('div');
  wrap.className = 'resultItem';
  p.mount(wrap);
  
  wrap.__player = p;
  return wrap;
}


function showResult(audioUrls, jsonUrls, audioFilenames, resolvedSeeds, compareMeta = null) {
  
  try { destroyAllPlayers(); } catch (e) {  }

  resultBox.classList.remove('hidden');
  resultsList.innerHTML = '';
  if (extraSections) extraSections.open = false;
  if (extraPre) extraPre.textContent = '';

  const list = Array.isArray(audioUrls) ? audioUrls : (audioUrls ? [audioUrls] : []);

  if (!list.length) {
    const warn = document.createElement('div');
    warn.className = 'muted';
    warn.textContent = t('result.no_audio_found');
    resultsList.appendChild(warn);
  }

  const names = Array.isArray(audioFilenames) ? audioFilenames : [];
  const seeds = Array.isArray(resolvedSeeds) ? resolvedSeeds : [];
  const createdCards = [];
  list.forEach((url, i) => {
    const jsonUrl = Array.isArray(jsonUrls) ? (jsonUrls[i] || '') : (jsonUrls || '');
    const card = createGradioLikePlayerCard(url, i, jsonUrl, names[i] || "", seeds[i] != null ? seeds[i] : null);
    createdCards.push(card);
    resultsList.appendChild(card);
  });

  if (compareMeta && createdCards.length >= 2) {
    const bridge = new AbCompareBridge(createdCards[0].__player, createdCards[1].__player, compareMeta);
    bridge.mount(resultsList);
  }

  
  (async () => {
    try {
      const metaUrl = Array.isArray(jsonUrls) ? (jsonUrls[0] || jsonUrls[1] || '') : jsonUrls;
      if (!metaUrl) return;
      const r = await fetch(metaUrl);
      if (!r.ok) return;
      const meta = await r.json();

      const extra = {};
      if (meta && meta.result) {
        if (meta.result.extra_outputs) extra.extra_outputs = meta.result.extra_outputs;
        if (meta.result.audios) extra.audios = meta.result.audios;
        if (meta.result.status_message) extra.status_message = meta.result.status_message;
      }
      
      if (meta && meta.request) extra.request = meta.request;

      if (extraPre) extraPre.textContent = JSON.stringify(extra, null, 2);
    } catch (e) {
      
    }
  })();
}

async function __submitSingleJob(payload) {
  const res = await fetch('/api/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    let detail = null;
    try {
      const j = await res.json();
      detail = (j && (j.detail != null)) ? j.detail : j;
    } catch (e) {}

    if (detail && typeof detail === 'object' && detail.error_code) {
      const code = String(detail.error_code || '').trim();
      if (code === 'rate_limited') {
        const ra = (detail.retry_after_s != null) ? Number(detail.retry_after_s) : null;
        const sec = (ra != null && Number.isFinite(ra)) ? Math.max(0.0, ra) : 5.0;
        setNoticeT('limit.rate_limited', { sec: sec.toFixed(1) });
        throw new Error(__tr('error.request_failed', 'Request failed', 'Richiesta fallita'));
      }
      if (code === 'queue_full') {
        const cap = (detail.cap != null) ? Number(detail.cap) : 30;
        const capTxt = (Number.isFinite(cap) ? String(Math.max(0, Math.floor(cap))) : '30');
        setNoticeT('limit.queue_full', { cap: capTxt });
        throw new Error(__tr('error.request_failed', 'Request failed', 'Richiesta fallita'));
      }
    }

    let txt = '';
    try { txt = await res.text(); } catch (e) {}
    throw new Error((txt || '').trim() || t('error.request_failed'));
  }

  const data = await res.json();
  const jid = String(data.job_id || '').trim();
  if (jid) {
    __jobRequestSnapshots.set(jid, {
      ui_state: __snapshotUiForExport(payload),
      request: payload,
      created_at_ms: Date.now(),
    });
  }
  clearNotice();
  return data;
}

async function __waitForJobDone(jobId, onProgress) {
  while (true) {
    const res = await fetch(`/api/jobs/${jobId}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(__tr('status.cant_read_job', 'Cannot read job status', 'Impossibile leggere lo stato del job'));
    const st = await res.json();
    if (typeof onProgress === 'function') onProgress(st);
    if (st.status === 'done') return st;
    if (st.status === 'error') throw new Error(st.error || t('error.unknown'));
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
}

function buildPayloadForCurrentUi() {
  const generation_mode = getGenerationMode();
  const caption = el('caption').value;
  const lyrics = el('lyrics').value;
  const lyricsExport = String(lyrics || '');
  const instrumental = el('instrumental').checked;
  const thinking = el('thinking') ? el('thinking').checked : true;

  
  const duration_auto = boolEl('duration_auto');
  const bpm_auto = boolEl('bpm_auto');
  const key_auto = boolEl('key_auto');
  const timesig_auto = boolEl('timesig_auto');
  const language_auto = boolEl('language_auto');

  const duration = Number(el('duration').value || 180);
  const seedRandom = !!el('seed_random')?.checked;
  const seedRaw = el('seed').value;
  const seed = seedRandom ? -1 : (seedRaw === '' ? -1 : Number(seedRaw));

  
  const batch_size = Number(el('batch_size')?.value || 1);
  const audio_format = el('audio_format')?.value || 'flac';
  let inference_steps = numOrNull((el('inference_steps')?.value ?? el('steps')?.value));
  try {
    const maxSteps = getCurrentStepLimit(modelSelect?.value || '');
    if (inference_steps !== null) inference_steps = Math.max(1, Math.min(inference_steps, maxSteps));
  } catch (e) {}
  const infer_method = (el('infer_method')?.value || 'ode').trim().toLowerCase() || 'ode';
  const timesteps = strVal('timesteps', '');
  const source_start = numOrNull(el('source_start')?.value);
  const source_end = numOrNull(el('source_end')?.value);
  const guidance_scale = numOrNull((el('guidance_scale')?.value ?? el('cfg')?.value));
  const shift = numOrNull(el('shift')?.value);
  const use_adg = !!el('use_adg')?.checked;
  const cfg_interval_start = numOrNull(el('cfg_interval_start')?.value);
  const cfg_interval_end = numOrNull(el('cfg_interval_end')?.value);
  const enable_normalization = !!el('enable_normalization')?.checked;
  const normalization_db = numOrNull(el('normalization_db')?.value);
  const score_scale = numOrNull(el('score_scale')?.value);
  const auto_score = !!el('auto_score')?.checked;
  const latent_shift = numOrNull(el('latent_shift')?.value);
  const latent_rescale = numOrNull(el('latent_rescale')?.value);
  const bpm = numOrNull(el('bpm')?.value);
  const keyscale = getKeyScaleFromControls();
  const timesignature = el('timesignature')?.value || '';
  let vocal_language = el('vocal_language')?.value || 'unknown';

  const audio_cover_strength = numOrNull(el('audio_cover_strength')?.value);
  const cover_noise_strength = numOrNull(el('cover_noise_strength')?.value);
  const cover_conditioning_balance = numOrNull(el('cover_conditioning_balance')?.value);
  const chord_reference_renderer = String(el('chord_reference_renderer')?.value || 'soundfont').trim().toLowerCase() || 'soundfont';

  
  const generatedReferencePath = generatedChordConditioningPath || '';
  const uploadedReferencePath = uploadedRefAudioPath || '';
  let reference_audio = '';
  let src_audio = '';
  let audio_codes = (chordConditioningMode === 'full') ? (generatedChordAudioCodes || el('audio_codes')?.value || '') : (el('audio_codes')?.value || '');
  let conditioningRouteDebug = 'none';
  let conditioningSourceDebug = 'none';
  if (generation_mode === 'Cover') {
    const coverSourcePath = uploadedReferencePath || generatedReferencePath;
    const coverCodesRaw = String(audio_codes || '').trim();
    const coverBalanceRaw = (cover_conditioning_balance == null) ? 0.5 : cover_conditioning_balance;
    const coverBalance = Math.max(0, Math.min(1, coverBalanceRaw));
    const preferCodesOnly = (coverBalance <= 0.001);
    const preferSrcOnly = (coverBalance >= 0.999);
    const hasSource = !!String(coverSourcePath || '').trim();
    const hasCodes = !!coverCodesRaw;
    reference_audio = '';
    src_audio = hasSource ? coverSourcePath : '';
    audio_codes = coverCodesRaw;
    if (preferCodesOnly) {
      src_audio = '';
    } else if (preferSrcOnly) {
      audio_codes = '';
    }
    if (src_audio && audio_codes) {
      conditioningRouteDebug = 'hybrid_src_audio_and_audio_codes';
      conditioningSourceDebug = uploadedReferencePath ? 'uploaded_source_audio+audio_codes' : (generatedReferencePath ? 'generated_chord_reference+audio_codes' : 'hybrid');
    } else if (src_audio) {
      conditioningRouteDebug = 'src_audio_wav';
      conditioningSourceDebug = uploadedReferencePath ? 'uploaded_source_audio' : (generatedReferencePath ? 'generated_chord_reference_wav' : 'src_audio_wav');
    } else if (audio_codes) {
      conditioningRouteDebug = 'audio_codes';
      conditioningSourceDebug = 'audio_codes';
    }
  } else if (generation_mode === 'Remix') {
    src_audio = uploadedReferencePath;
    audio_codes = '';
    conditioningRouteDebug = src_audio ? 'src_audio_wav' : 'none';
    conditioningSourceDebug = src_audio ? 'uploaded_source_audio' : 'none';
  } else {
    reference_audio = '';
    conditioningRouteDebug = String(audio_codes || '').trim() ? 'audio_codes' : 'none';
    conditioningSourceDebug = String(audio_codes || '').trim() ? 'generated_chord_reference' : 'none';
  }

  
  
  
  let lyricsPayload = stripChordTagsForModelInput(lyricsExport);
  if (instrumental) {
    vocal_language = 'unknown';
    if (!String(lyricsPayload || '').trim()) {
      lyricsPayload = '[Instrumental]';
    }
  }

  
  const loraSel = getSelectedLora();
  const lora_id = String(loraSel.id || '').trim();
  const lora_trigger = String(loraSel.trigger || '').trim();
  const lora_weight = getSelectedLoraWeight();

  

  
  const captionPayload = stripChordCaptionTag(String(caption || '').trim());
  const loraShow = lora_id ? (String(loraSel.label || lora_id) + ' @ ' + lora_weight.toFixed(2)) : t('lora.none_short');
  setStatusT('status.sending_request', { lora: loraShow });
  resultBox.classList.add('hidden');

    const payload = {
      model: getSelectedModel(),
      generation_mode,
      caption: captionPayload,
      lyrics: lyricsPayload,
      lyrics_model_input: lyricsPayload,
      lyrics_export: lyricsExport,
      instrumental,
      thinking,

      use_cot_metas: (thinking && boolVal('use_cot_metas', true)),
      use_cot_caption: (thinking && boolVal('use_cot_caption', true)),
      use_cot_language: (thinking && boolVal('use_cot_language', true)),
      parallel_thinking: (thinking && boolVal('parallel_thinking', false)),
      constrained_decoding_debug: (thinking && boolVal('constrained_decoding_debug', false)),

      lm_temperature: num('lm_temperature', 0.85),
      lm_cfg_scale: num('lm_cfg_scale', 2.0),
      lm_top_k: intNum('lm_top_k', 0),
      lm_top_p: num('lm_top_p', 0.9),
      lm_negative_prompt: strVal('lm_negative_prompt', 'NO USER INPUT'),
      use_constrained_decoding: boolVal('use_constrained_decoding', true),

      duration_auto,
      bpm_auto,
      key_auto,
      timesig_auto,
      language_auto,

      seed,

      lora_id,
      lora_trigger,
      lora_weight,

      chord_key: el('chord_key')?.value || '',
      chord_scale: el('chord_scale')?.value || 'major',
      chord_roman: el('chord_roman')?.value || '',
      chord_section_map: el('chord_section_map')?.value || '',
      chord_apply_keyscale: !!(el('chord_apply_keyscale')?.checked),
      chord_apply_bpm: !!(el('chord_apply_bpm')?.checked),
      chord_apply_lyrics: !!(el('chord_apply_lyrics')?.checked),
      chord_family: generatedChordFamily || '',

      reference_audio,
      src_audio,
      audio_codes,
      audio_cover_strength,
      cover_noise_strength,
      cover_conditioning_balance,
      chord_reference_renderer,
      conditioning_route_debug: conditioningRouteDebug,
      conditioning_source_debug: conditioningSourceDebug,
      chord_debug_mode: chordConditioningMode,
      chord_debug_reference_only: !!(conditioningRouteDebug === 'reference_audio_wav' && reference_audio && !src_audio && !String(audio_codes || '').trim()),
      chord_debug_reference_sequence: (generatedChordReferenceSequence || []).join(' - '),
      chord_debug_section_plan: formatChordReferencePlan(generatedChordSectionPlan || []),
      chord_debug_reference_bpm: generatedChordReferenceBpm,
      chord_debug_reference_target_duration: generatedChordReferenceTargetDuration,
      chord_reference_renderer,

      batch_size,
      audio_format,
      inference_steps,
      infer_method,
      timesteps,
      ...(generation_mode === 'Remix' ? { source_start, source_end } : {}),
      guidance_scale,
      shift,
      use_adg,
      cfg_interval_start,
      cfg_interval_end,
      enable_normalization,
      normalization_db,
      score_scale,
      auto_score,
      latent_shift,
      latent_rescale,

      
      ...(duration_auto ? {} : { duration }),
      ...(bpm_auto ? {} : { bpm }),
      ...(key_auto ? {} : { keyscale }),
      ...(timesig_auto ? {} : { timesignature }),
      ...(language_auto ? {} : { vocal_language }),
    };

    return __normalizeCustomModeConditioning(payload);
}

async function postJob() {
  const payload = buildPayloadForCurrentUi();

    console.log('[aceflow] /api/jobs payload', payload);
    console.log('[aceflow] chord conditioning summary', {
      mode: chordConditioningMode,
      generation_mode: payload.generation_mode,
      conditioning_route: payload.conditioning_route_debug,
      conditioning_source: payload.conditioning_source_debug,
      reference_audio: payload.reference_audio,
      src_audio: payload.src_audio,
      audio_codes_len: String(payload.audio_codes || '').trim().length,
      audio_cover_strength: payload.audio_cover_strength,
      cover_noise_strength: payload.cover_noise_strength,
      cover_conditioning_balance: payload.cover_conditioning_balance,
      chord_reference_renderer: payload.chord_reference_renderer,
      reference_only: !!(payload.conditioning_route_debug === 'reference_audio_wav' && payload.reference_audio && !payload.src_audio && !String(payload.audio_codes || '').trim()),
      reference_sequence: payload.chord_debug_reference_sequence || '',
      section_plan: payload.chord_debug_section_plan || '',
      target_duration: payload.chord_debug_reference_target_duration,
      bpm: payload.chord_debug_reference_bpm,
    });
    try { console.log('[aceflow] /api/jobs payload json', JSON.stringify(payload)); } catch(e) {}
    const data = await __submitSingleJob(payload);
  currentJobId = data.job_id;
  setStatusT('status.request_queued', { pos: data.position });
  startPolling();
}

function setupSeedUI() {
  const seed = el('seed');
  const seedRandom = el('seed_random');
  if (!seed || !seedRandom) return;

  const sync = () => {
    if (seedRandom.checked) {
      seed.value = '-1';
      seed.readOnly = true;
      seed.classList.add('ro');
    } else {
      seed.readOnly = false;
      seed.classList.remove('ro');
      if ((seed.value || '').trim() === '-1') seed.value = '';
    }
  };

  seedRandom.addEventListener('change', sync);
  seed.addEventListener('input', () => {
    if (seed.readOnly) return;
    const v = (seed.value || '').trim();
    seedRandom.checked = (v === '' || v === '-1');
    sync();
  });
  
  
  const forceEnable = () => {
    if (!seed.readOnly) return;
    seedRandom.checked = false;
    sync();
  };
  seed.addEventListener('pointerdown', forceEnable);
  seed.addEventListener('focus', forceEnable);
  seed.addEventListener('keydown', forceEnable);

  sync();
}

async function pollJob() {
  if (!currentJobId) return;

  const res = await fetch(`/api/jobs/${currentJobId}`);
  if (!res.ok) {
    setStatusT('status.cant_read_job');
    stopPolling();
    return;
  }

  const st = await res.json();

  if (st.status === 'queued') {
    setStatusT('status.queued_ahead', { pos: st.position });
    return;
  }

  if (st.status === 'running') {
    setStatusT('status.running');
    return;
  }

  if (st.status === 'error') {
    setStatusT('status.error', { msg: st.error || t('error.unknown') });
    stopPolling();
    return;
  }

  if (st.status === 'done') {
    const r = st.result;
    setStatusT('status.done_in', { sec: (Math.round((r.seconds || 0) * 10) / 10) });
    const urls = Array.isArray(r.audio_urls) ? r.audio_urls : (r.audio_url ? [r.audio_url] : []);
    const jsons = urls.map(() => r.json_url || '');
    showResult(urls, jsons, r.audio_filenames, r.audio_resolved_seeds);
    stopPolling();
    refreshFooterStats();
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(pollJob, 1200);
  pollJob();
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

async function triggerGenerateFromUi() {
  try {
    updateAbCompareBatchUi();
    if (!isAbCompareEnabled()) {
      await postJob();
      return;
    }

    const loraSel = getSelectedLora();
    const loraId = String(loraSel.id || '').trim();
    if (!loraId) throw new Error(__tr('ab.need_lora', 'Select a LoRA before using A/B compare.', 'Seleziona una LoRA prima di usare il confronto A/B.'));

    const seedRandom = !!el('seed_random')?.checked;
    const seedRaw = el('seed')?.value;
    const stableSeed = __makeStableAbSeed(seedRandom, seedRaw);
    const compareKey = __makeAbCompareKey();

    const basePayload = buildPayloadForCurrentUi();
    const payloadA = __normalizeCustomModeConditioning({ ...basePayload, seed: stableSeed, batch_size: 1, lora_id: '', lora_trigger: '', lora_weight: basePayload.lora_weight, _aceflow_compare_key: compareKey, _aceflow_compare_step: 'A' });
    const payloadB = __normalizeCustomModeConditioning({ ...basePayload, seed: stableSeed, batch_size: 1, lora_id: basePayload.lora_id, lora_trigger: basePayload.lora_trigger, lora_weight: basePayload.lora_weight, _aceflow_compare_key: compareKey, _aceflow_compare_step: 'B' });

    resultBox.classList.add('hidden');
    stopPolling();
    currentJobId = null;

    setStatusT('status.sending_request', { lora: __tr('ab.phase_a', 'A: base model (no LoRA)', 'A: modello base (senza LoRA)') });
    const first = await __submitSingleJob(payloadA);
    setStatusT('status.request_queued', { pos: first.position });
    const stA = await __waitForJobDone(first.job_id, (st) => {
      if (st.status === 'queued') setStatusT('status.queued_ahead', { pos: st.position });
      else if (st.status === 'running') setStatusT('status.running');
    });

    setStatusT('status.sending_request', { lora: __tr('ab.phase_b', 'B: selected LoRA', 'B: LoRA selezionata') });
    const second = await __submitSingleJob(payloadB);
    setStatusT('status.request_queued', { pos: second.position });
    const stB = await __waitForJobDone(second.job_id, (st) => {
      if (st.status === 'queued') setStatusT('status.queued_ahead', { pos: st.position });
      else if (st.status === 'running') setStatusT('status.running');
    });

    const rA = stA.result || {};
    const rB = stB.result || {};
    const audioUrls = [];
    const audioNames = [];
    const resolvedSeeds = [];
    const pushOne = (r) => {
      const urls = Array.isArray(r.audio_urls) ? r.audio_urls : (r.audio_url ? [r.audio_url] : []);
      const names = Array.isArray(r.audio_filenames) ? r.audio_filenames : [];
      const seeds = Array.isArray(r.audio_resolved_seeds) ? r.audio_resolved_seeds : [];
      if (urls[0]) {
        audioUrls.push(urls[0]);
        audioNames.push(names[0] || '');
        resolvedSeeds.push(seeds[0] != null ? seeds[0] : stableSeed);
      }
    };
    pushOne(rA);
    pushOne(rB);

    setStatusT('status.done_in', { sec: (Math.round((((rA.seconds || 0) + (rB.seconds || 0)) * 10)) / 10) });
    showResult(audioUrls, [rA.json_url || '', rB.json_url || ''], audioNames, resolvedSeeds, {
      a: __tr('ab.audio1', 'Audio 1', 'Audio 1'),
      b: __tr('ab.audio2', 'Audio 2', 'Audio 2'),
    });
    refreshFooterStats();
  } catch (e) {
    setStatusT('status.error', { msg: e.message });
  }
}

el('submit').addEventListener('click', async () => {
  await triggerGenerateFromUi();
});

document.addEventListener('keydown', async (ev) => {
  if (!(ev.ctrlKey && ev.key === 'Enter')) return;
  if (ev.defaultPrevented || ev.repeat) return;
  ev.preventDefault();
  await triggerGenerateFromUi();
});


document.querySelectorAll('input[name="generation_mode"]').forEach((r) => {
  r.addEventListener('change', updateModeVisibility);
});
updateModeVisibility();

async function uploadAudioFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/uploads/audio', { method: 'POST', body: fd });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || t('upload.failed'));
  }
  return await res.json();
}


if (refAudioInput) {
  refAudioInput.addEventListener('change', async () => {
    const f = refAudioInput.files && refAudioInput.files[0];
    if (!f) return;
    refAudioStatus.textContent = t('upload.in_progress');
    try {
      const up = await uploadAudioFile(f);
      uploadedRefAudioPath = up.path;
      if (!generatedChordConditioningPath || up.path !== generatedChordConditioningPath) {
        generatedChordConditioningPath = '';
        generatedChordConditioningName = '';
        generatedChordAudioCodes = '';
        chordConditioningMode = 'none';
      }
      refAudioStatus.textContent = t('upload.done', { name: up.filename });
      updateRefAudioVisibility();
    } catch (e) {
      uploadedRefAudioPath = '';
      refAudioStatus.textContent = t('upload.error', { msg: e.message });
      updateRefAudioVisibility();
    }
  });
}


if (lmAudioInput) {
  lmAudioInput.addEventListener('change', async () => {
    const f = lmAudioInput.files && lmAudioInput.files[0];
    if (!f) return;
    if (lmStatus) lmStatus.textContent = t('upload.in_progress');
    try {
      const up = await uploadAudioFile(f);
      uploadedLmAudioPath = up.path;
      if (lmStatus) lmStatus.textContent = t('upload.done', { name: up.filename });
    } catch (e) {
      uploadedLmAudioPath = '';
      if (lmStatus) lmStatus.textContent = t('upload.error', { msg: e.message });
    }
  });
}


const btnConvert = el('btn_convert_codes');
if (btnConvert) {
  btnConvert.addEventListener('click', async () => {
    try {
      if (!uploadedLmAudioPath) throw new Error(t('lm.need_audio_first'));
      if (lmStatus) lmStatus.textContent = t('lm.converting');
      const res = await fetch('/api/chords/extract-codes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: uploadedLmAudioPath }),
      });
      if (!res.ok) throw new Error(await getResponseErrorMessage(res, 'extract-codes'));
      const data = await res.json();
      if (el('audio_codes')) el('audio_codes').value = data.codes || '';
      if (lmStatus) lmStatus.textContent = t('lm.codes_generated');
    } catch (e) {
      if (lmStatus) lmStatus.textContent = t('status.error', { msg: e.message });
    }
  });
}


const btnTranscribe = el('btn_transcribe_codes');
if (btnTranscribe) {
  btnTranscribe.addEventListener('click', async () => {
    try {
      const codes = (el('audio_codes')?.value || '').trim();
      if (!codes) throw new Error(t('lm.paste_codes_first'));
      if (lmStatus) lmStatus.textContent = t('lm.transcribing');
      const res = await fetch('/api/lm/transcribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codes }),
      });
      if (!res.ok) throw new Error(await getResponseErrorMessage(res, 'lm-transcribe'));
      const data = await res.json();

      
      if (el('caption')) el('caption').value = data.caption || '';
      if (el('lyrics')) el('lyrics').value = data.lyrics || '';
      if (el('bpm')) el('bpm').value = (data.bpm != null) ? data.bpm : '';
      if (el('duration') && data.duration != null) el('duration').value = data.duration;
      setKeyScaleValue(data.keyscale || '', { dispatch: false });
      if (el('vocal_language')) el('vocal_language').value = data.vocal_language || 'unknown';
      const normalizedTranscribedTS = normalizeTimeSignatureValue(data.timesignature || '');
      if (el('timesignature')) el('timesignature').value = normalizedTranscribedTS;

      
      if (data.bpm != null && String(data.bpm).trim() !== '' && el('bpm_auto')) el('bpm_auto').checked = false;
      if (data.duration != null && String(data.duration).trim() !== '' && el('duration_auto')) el('duration_auto').checked = false;
      if ((data.keyscale || '').trim() && el('key_auto')) el('key_auto').checked = false;
      if (normalizedTranscribedTS && el('timesig_auto')) el('timesig_auto').checked = false;
      if ((data.vocal_language || '').trim()) {
        const normalizedLang = String(data.vocal_language).trim().toLowerCase();
        if (normalizedLang !== 'unknown' && el('language_auto')) el('language_auto').checked = false;
      }

      if (lmStatus) lmStatus.textContent = buildLmTranscribeSuccessMessage({ ...data, timesignature: normalizedTranscribedTS });
    } catch (e) {
      if (lmStatus) lmStatus.textContent = t('status.error', { msg: e.message });
    }
  });
}


async function initializeProtectedBootstrap() {
  if (!canUseProtectedApi()) return;
  refreshFooterStats();
  try {
    let opt = null;
    const optRes = await fetch('/api/options');
    if (optRes.ok) {
      opt = await optRes.json();
      __ACE_STEP_LIMITS = {
        ...__ACE_STEP_LIMITS,
        ...(opt && opt.limits ? opt.limits : {}),
      };
      const langs = Array.isArray(opt.valid_languages) ? opt.valid_languages : [];
      const sel = el('vocal_language');
      if (sel && langs.length) {
        sel.innerHTML = '';
        langs.forEach((code) => {
          const o = document.createElement('option');
          o.value = code;
          o.textContent = code;
          sel.appendChild(o);
        });
        sel.value = langs.includes('it') ? 'it' : (langs.includes('unknown') ? 'unknown' : langs[0]);
      }

      chordReferenceSoundfontAvailable = !!opt.soundfont_available;
      chordReferenceSoundfontName = String(opt.soundfont_name || '');
      updateChordReferenceRendererUi();

      const tsSel = el('timesignature');
      const tss = Array.isArray(opt.time_signatures) ? opt.time_signatures : ['','2/4','3/4','4/4','6/8'];
      if (tsSel) {
        tsSel.innerHTML = '';
        tss.forEach((v) => {
          const o = document.createElement('option');
          o.value = v;
          o.textContent = v || t('ph.auto');
          tsSel.appendChild(o);
        });
        tsSel.value = '';
      }

      
      const think = el('thinking');
      if (think) {
        think.disabled = !opt.lm_ready;
        
        if (!think.dataset.touched) {
          think.checked = !!(opt.lm_ready && (opt.think_default ?? true));
        }
        think.addEventListener('change', () => {
          think.dataset.touched = '1';
        }, { once: false });
      }

function _setLmSubFeaturesEnabled(on) {
  const ids = ['use_constrained_decoding','use_cot_metas','use_cot_caption','use_cot_language','parallel_thinking','constrained_decoding_debug','lm_temperature','lm_cfg_scale','lm_top_k','lm_top_p','lm_negative_prompt'];
  ids.forEach((id) => {
    const e = el(id);
    if (e) e.disabled = !on;
  });
  
  document.querySelectorAll('.lm-dep').forEach((node) => {
    node.classList.toggle('lm-off', !on);
  });
  
  const hint = el('lm_inactive_hint');
  if (hint) hint.classList.toggle('hidden', !!on);
}
_setLmSubFeaturesEnabled(!!think.checked);

think.addEventListener('change', () => {
  try { _setLmSubFeaturesEnabled(!!think.checked); } catch (e) {}
}, { once: false });
    }

    
    try {
      const activeModel = (modelSelect && modelSelect.value) ? modelSelect.value : '';
      applyInferenceStepLimit(activeModel, {
        preserveValue: __stepsTouched,
        desiredValue: __stepsTouched ? undefined : getDefaultInferenceStepsForModel(activeModel),
      });
    } catch (e) {}

    if (!canUseProtectedApi()) return;
    const res = await fetch('/api/health');
    if (res.ok) {
      const h = await res.json();
      __ACE_STEP_LIMITS = {
        ...__ACE_STEP_LIMITS,
        ...(h && h.limits ? h.limits : {}),
      };
      window.__ACE_MAX_DURATION = h.max_duration;
      updateReadyStatus(h.max_duration);
      const dur = el('duration');
      if (dur) {
        dur.max = String(h.max_duration);
        if (!dur.value) dur.value = 180;
      }

      try {
        const uiModel = modelSelect?.value || h.model || '';
        applyInferenceStepLimit(uiModel, {
          preserveValue: __stepsTouched,
          desiredValue: __stepsTouched ? undefined : getDefaultInferenceStepsForModel(uiModel),
        });
      } catch (e) {}

      
      if (modelSelect && !modelSelect.dataset.bound) {
        modelSelect.dataset.bound = '1';
        modelSelect.addEventListener('change', () => {
  
  
  
  try {
    const v = String(modelSelect.value || '').toLowerCase();
    const shiftEl = el('shift');
    if (shiftEl) {
      shiftEl.value = v.includes('sft') ? '1' : '3';
      shiftEl.dispatchEvent(new Event('input', { bubbles: true }));
      shiftEl.dispatchEvent(new Event('change', { bubbles: true }));
    }
  } catch (e) {}
  
  
  
  try {
    const v = String(modelSelect.value || '');
    const desiredSteps = getDefaultInferenceStepsForModel(v);
    applyInferenceStepLimit(v, {
      preserveValue: __stepsTouched,
      desiredValue: __stepsTouched ? undefined : desiredSteps,
    });

    if (!__stepsTouched) {
      __stepsTouched = false;
    }
  } catch (e) {}

  
  try { syncStepsPair(); } catch (e) {}
  updateReadyStatus(window.__ACE_MAX_DURATION);
});
      }
    } else {
      setStatusT('status.server_not_ready');
    }
  } catch {
    setStatusT('status.server_unreachable');
  }
}

setupSeedUI();



async function loadOptions() {
  if (!canUseProtectedApi()) return;
  try {
    const r = await fetch("/api/options");
    const data = await r.json();
    __ACE_STEP_LIMITS = {
      ...__ACE_STEP_LIMITS,
      ...(data && data.limits ? data.limits : {}),
    };
    const langs = (data && data.valid_languages) ? data.valid_languages : ["unknown","it","en","es","fr","de","pt","ja","ko","zh","ru"];
    chordReferenceSoundfontAvailable = !!(data && data.soundfont_available);
    chordReferenceSoundfontName = String((data && data.soundfont_name) || '');
    updateChordReferenceRendererUi();
    const sel = document.getElementById("vocal_language");
    if (sel && sel.options.length === 0) {
      langs.forEach((l) => {
        const opt = document.createElement("option");
        opt.value = l;
        opt.textContent = l;
        sel.appendChild(opt);
      });
      
      sel.value = langs.includes("it") ? "it" : (langs.includes("unknown") ? "unknown" : langs[0]);
    }

    
    const inst = document.getElementById('instrumental');
    if (inst) inst.checked = false;

    
    const norm = document.getElementById('enable_normalization');
    if (norm) norm.checked = true;

  } catch (e) {}
}

async function loadRandomExample() {
  const btn = document.getElementById("dice");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    try {
      const r = await fetch("/api/examples/random");
      const ex = await r.json();
      if (!ex || !ex.style) return;
      
      const caption = document.getElementById("caption");
      const lyrics = document.getElementById("lyrics");
      if (caption) caption.value = ex.style || "";
      if (lyrics) lyrics.value = ex.lyrics || "";
      const bpm = document.getElementById("bpm");
      if (bpm) bpm.value = (ex.bpm != null) ? ex.bpm : "";
      setKeyScaleValue(ex.keyscale || '', { dispatch: false });
      const ts = document.getElementById("timesignature");
      if (ts) {
        const allowedTS = new Set(["2/4","3/4","4/4","6/8"]);
        const v = (ex.timesignature != null) ? String(ex.timesignature).trim() : "";
        ts.value = allowedTS.has(v) ? v : (v ? "4/4" : "");
      }
      const vl = document.getElementById("vocal_language");
      if (vl) vl.value = ex.vocal_language || (vl.value || "unknown");
      const dur = document.getElementById("duration");
      if (dur) dur.value = (ex.duration != null) ? ex.duration : dur.value;

      
      setAutoOffForMusicMeta();

      
      const inst = document.getElementById('instrumental');
      const isInst = !!(ex.instrumental || (String(ex.lyrics || '').trim().toLowerCase() === '[instrumental]') || (String(ex.lyrics || '').trim().toLowerCase() === '[inst]'));
      if (inst) inst.checked = isInst;
      if (isInst) {
        const vl2 = document.getElementById('vocal_language');
        if (vl2) vl2.value = 'unknown';
      }
      
      const seed = document.getElementById("seed");
      if (seed) seed.value = -1;
      
    } catch (e) {
      console.error(e);
    }
  });
}

function setupImportJson() {
  const btn = document.getElementById('btn_import_apply');
  const txt = document.getElementById('import_json_text');
  const file = document.getElementById('import_json_file');
  const status = document.getElementById('import_status');

  if (!btn || !txt || !file || !status) return;

  const setImportStatus = (ok, msgKeyOrText) => {
    status.textContent = '';
    status.classList.remove('ok', 'err');
    if (!msgKeyOrText) return;
    const msg = (typeof msgKeyOrText === 'string' && msgKeyOrText.startsWith('status.')) ? t(msgKeyOrText) : String(msgKeyOrText);
    status.textContent = msg;
    status.classList.add(ok ? 'ok' : 'err');
  };

  const safeBool = (v) => {
    if (typeof v === 'boolean') return v;
    if (typeof v === 'number') return v !== 0;
    if (typeof v === 'string') {
      const s = v.trim().toLowerCase();
      if (['true','1','yes','y','on'].includes(s)) return true;
      if (['false','0','no','n','off'].includes(s)) return false;
    }
    return null;
  };

  const safeNum = (v) => {
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    if (typeof v === 'string' && v.trim() !== '') {
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    }
    return null;
  };

  const safeInt = (v) => {
    const n = safeNum(v);
    return (n === null) ? null : (Math.trunc(n));
  };

  const pick = (obj, keys) => {
    for (const k of keys) {
      if (obj && Object.prototype.hasOwnProperty.call(obj, k)) return obj[k];
    }
    return undefined;
  };

  const extractRequest = (root) => {
    if (!root || typeof root !== 'object') return null;
    
    
    const direct = pick(root, ['request', 'payload']);
    if (direct && typeof direct === 'object') return direct;
    const res = root.result;
    if (res && typeof res === 'object') {
      const nested = pick(res, ['request', 'payload']);
      if (nested && typeof nested === 'object') return nested;
      if (pick(res, ['caption','lyrics','generation_mode','task_type']) !== undefined) return res;
      if (res.result && typeof res.result === 'object') {
        const r2 = pick(res.result, ['request','payload']);
        if (r2 && typeof r2 === 'object') return r2;
      }
    }
    if (pick(root, ['caption','lyrics','generation_mode','task_type']) !== undefined) return root;
    return null;
  };

  const extractMergedImportState = (root) => {
    const base = extractRequest(root) || {};
    const sent = (root && typeof root.request_sent === 'object') ? root.request_sent : {};
    const uiState = (root && typeof root.ui_state === 'object') ? root.ui_state : {};
    return { ...uiState, ...sent, ...base };
  };

  const setVal = (id, v) => {
    const e = document.getElementById(id);
    if (!e) return;
    if (e.tagName === 'SELECT' || e.tagName === 'TEXTAREA' || e.tagName === 'INPUT') {
      e.value = (v == null) ? '' : String(v);
      e.dispatchEvent(new Event('input', { bubbles: true }));
      e.dispatchEvent(new Event('change', { bubbles: true }));
    }
  };

  const setChecked = (id, v) => {
    const e = document.getElementById(id);
    if (!e) return;
    const b = safeBool(v);
    if (b === null) return;
    e.checked = b;
    e.dispatchEvent(new Event('change', { bubbles: true }));
  };

  const applyRequestToUI = (req) => {
    
    const modeRaw = pick(req, ['generation_mode', 'mode', 'generationMode', 'task_type', 'taskType']);
    if (modeRaw != null) {
      const m = String(modeRaw).toLowerCase();
      let uiMode = null;
      if (m === 'simple') uiMode = 'Simple';
      else if (m === 'custom') uiMode = 'Custom';
      else if (m === 'cover') uiMode = 'Cover';
      else if (m === 'remix') uiMode = 'Remix';
      if (uiMode) setGenerationMode(uiMode);
    }

    
    const importedModel = (req.model != null) ? req.model : ((req.model_used != null) ? req.model_used : null);
    if (importedModel != null) {
      setVal('model_select', importedModel);
      const modelSelectEl = el('model_select');
      if (modelSelectEl) {
        modelSelectEl.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }

    
    if (req.caption != null) setVal('caption', req.caption);
    if (req.style != null && req.caption == null) setVal('caption', req.style);
    if (req.lyrics != null) setVal('lyrics', req.lyrics);

    
    if (req.duration != null) {
      const n = safeInt(req.duration);
      if (n !== null) setVal('duration', n);
    }
    if (req.bpm != null) {
      const n = safeInt(req.bpm);
      if (n !== null) setVal('bpm', n);
    }
    if (req.keyscale != null) setKeyScaleValue(req.keyscale, { dispatch: true });
    if (req.timesignature != null) setVal('timesignature', req.timesignature);
    if (req.vocal_language != null) setVal('vocal_language', req.vocal_language);

    
    
    
    const has = (k) => Object.prototype.hasOwnProperty.call(req || {}, k);
    if (req.duration != null && !has('duration_auto')) setChecked('duration_auto', false);
    if (req.bpm != null && !has('bpm_auto')) setChecked('bpm_auto', false);
    if (req.keyscale != null && !has('key_auto')) setChecked('key_auto', false);
    if (req.timesignature != null && !has('timesig_auto')) setChecked('timesig_auto', false);
    if (req.vocal_language != null && !has('language_auto')) setChecked('language_auto', false);

    
    setChecked('duration_auto', req.duration_auto);
    setChecked('bpm_auto', req.bpm_auto);
    setChecked('key_auto', req.key_auto);
    setChecked('timesig_auto', req.timesig_auto);
    setChecked('language_auto', req.language_auto);

    
    if (req.seed != null) {
      const n = safeInt(req.seed);
      if (n !== null) {
        setVal('seed', n);
        if (n >= 0) setChecked('seed_random', false);
      }
    }
    if (!(req.seed != null && safeInt(req.seed) !== null && safeInt(req.seed) >= 0)) {
      setChecked('seed_random', req.seed_random);
    }

    
    setChecked('instrumental', req.instrumental);
    setChecked('thinking', req.thinking);

    
    if (req.lora_id != null) setVal('lora_select', req.lora_id);
    if (req.lora_weight != null) {
      const n = safeNum(req.lora_weight);
      if (n !== null) {
        const clamped = Math.max(0, Math.min(1, n));
        setVal('lora_weight', clamped);
        setVal('lora_weight_num', clamped);
      }
    }

    
    if (req.lm_temperature != null) setVal('lm_temperature', safeNum(req.lm_temperature) ?? req.lm_temperature);
    if (req.lm_cfg_scale != null) setVal('lm_cfg_scale', safeNum(req.lm_cfg_scale) ?? req.lm_cfg_scale);
    if (req.lm_top_k != null) setVal('lm_top_k', safeInt(req.lm_top_k) ?? req.lm_top_k);
    if (req.lm_top_p != null) setVal('lm_top_p', safeNum(req.lm_top_p) ?? req.lm_top_p);
    if (req.lm_negative_prompt != null) setVal('lm_negative_prompt', req.lm_negative_prompt);
    setChecked('use_constrained_decoding', req.use_constrained_decoding);
    setChecked('use_cot_metas', req.use_cot_metas);
    setChecked('use_cot_caption', req.use_cot_caption);
    setChecked('use_cot_language', req.use_cot_language);
    setChecked('parallel_thinking', req.parallel_thinking);
    setChecked('constrained_decoding_debug', req.constrained_decoding_debug);

    
    if (req.batch_size != null) setVal('batch_size', safeInt(req.batch_size) ?? req.batch_size);
    try {
      const batchSel = el('batch_size');
      if (batchSel && !isAbCompareEnabled()) batchSel.dataset.abPrevValue = String(batchSel.value || '1');
    } catch (e) {}
    if (req.audio_format != null) setVal('audio_format', req.audio_format);
    if (req.inference_steps != null) setVal('steps', safeInt(req.inference_steps) ?? req.inference_steps);
    if (req.infer_method != null) setVal('infer_method', String(req.infer_method).toLowerCase());
    if (req.timesteps != null) setVal('timesteps', Array.isArray(req.timesteps) ? req.timesteps.join(',') : req.timesteps);
    if (req.source_start != null) setVal('source_start', safeNum(req.source_start) ?? req.source_start);
    if (req.source_end != null) setVal('source_end', safeNum(req.source_end) ?? req.source_end);
    if (req.guidance_scale != null) setVal('guidance_scale', safeNum(req.guidance_scale) ?? req.guidance_scale);
    if (req.shift != null) setVal('shift', safeNum(req.shift) ?? req.shift);
    setChecked('use_adg', req.use_adg);
    if (req.cfg_interval_start != null) setVal('cfg_interval_start', safeNum(req.cfg_interval_start) ?? req.cfg_interval_start);
    if (req.cfg_interval_end != null) setVal('cfg_interval_end', safeNum(req.cfg_interval_end) ?? req.cfg_interval_end);
    setChecked('enable_normalization', req.enable_normalization);
    if (req.normalization_db != null) setVal('normalization_db', safeNum(req.normalization_db) ?? req.normalization_db);
    if (req.score_scale != null) setVal('score_scale', safeNum(req.score_scale) ?? req.score_scale);
    setChecked('auto_score', req.auto_score);
    if (req.latent_shift != null) setVal('latent_shift', safeNum(req.latent_shift) ?? req.latent_shift);
    if (req.latent_rescale != null) setVal('latent_rescale', safeNum(req.latent_rescale) ?? req.latent_rescale);
    if (req.audio_cover_strength != null) setVal('audio_cover_strength', safeNum(req.audio_cover_strength) ?? req.audio_cover_strength);
    if (req.cover_noise_strength != null) setVal('cover_noise_strength', safeNum(req.cover_noise_strength) ?? req.cover_noise_strength);
    if (req.cover_conditioning_balance != null) setVal('cover_conditioning_balance', safeNum(req.cover_conditioning_balance) ?? req.cover_conditioning_balance);
    if (req.chord_reference_renderer != null) setVal('chord_reference_renderer', String(req.chord_reference_renderer));
    if (req.audio_codes != null) setVal('audio_codes', req.audio_codes);

    
    if (req.chord_key != null) setVal('chord_key', req.chord_key);
    if (req.chord_scale != null) setVal('chord_scale', req.chord_scale);
    if (req.chord_roman != null) setVal('chord_roman', req.chord_roman);
    if (req.chord_section_map != null) setVal('chord_section_map', req.chord_section_map);
    setChecked('chord_apply_keyscale', req.chord_apply_keyscale);
    setChecked('chord_apply_bpm', req.chord_apply_bpm);
    setChecked('chord_apply_lyrics', req.chord_apply_lyrics);
    chordConditioningMode = String(req.chord_conditioning_mode || chordConditioningMode || 'none');
    generatedChordConditioningPath = String(req.chord_conditioning_path || generatedChordConditioningPath || '');
    generatedChordConditioningName = String(req.chord_conditioning_name || generatedChordConditioningName || '');
    generatedChordAudioCodes = String(req.chord_audio_codes || req.audio_codes || generatedChordAudioCodes || '');
    generatedChordFamily = String(req.chord_family || generatedChordFamily || '');
    refreshChordPreview();

    
    const ref = (req.reference_audio != null) ? String(req.reference_audio) : '';
    const src = (req.src_audio != null) ? String(req.src_audio) : '';
    const uiRef = (req.uploaded_reference_audio_path != null) ? String(req.uploaded_reference_audio_path) : '';
    const uiLm = (req.uploaded_lm_audio_path != null) ? String(req.uploaded_lm_audio_path) : '';
    uploadedRefAudioPath = uiRef || ref || src || uploadedRefAudioPath || '';
    uploadedLmAudioPath = uiLm || uploadedLmAudioPath || '';
    if (chordConditioningMode === 'full' && uploadedRefAudioPath && !generatedChordConditioningPath) {
      generatedChordConditioningPath = uploadedRefAudioPath;
    }
    updateRefAudioVisibility();
    try {
      applyInferenceStepLimit(el('model_select')?.value || '', { preserveValue: true });
    } catch (e) {}
  };

  const parseAndApply = async (raw) => {
    try {
      const root = JSON.parse(raw);
      const req = extractMergedImportState(root);
      if (!req || !Object.keys(req).length) throw new Error(t('error.import_no_request'));

      applyRequestToUI(req);

      
      try { syncRangeNumber('lm_temperature_range', 'lm_temperature', { decimals: 2 }); } catch (e) {}
      try { syncRangeNumber('lm_cfg_scale_range', 'lm_cfg_scale', { decimals: 1 }); } catch (e) {}
      try { syncRangeNumber('lm_top_p_range', 'lm_top_p', { decimals: 2 });   syncRangeNumber('lm_top_k_range', 'lm_top_k', { decimals: 0 });
} catch (e) {}
      try { syncRangeNumber('lm_top_k_range', 'lm_top_k', { decimals: 0 }); } catch (e) {}
      try { syncRangeNumber('inference_steps_range', 'inference_steps', { decimals: 0 }); } catch (e) {}
      try { syncRangeNumber('steps_range', 'steps', { decimals: 0 }); } catch (e) {}
      try { syncRangeNumber('source_start_range', 'source_start', { decimals: 1 }); } catch (e) {}
      try { syncRangeNumber('source_end_range', 'source_end', { decimals: 1 }); } catch (e) {}
      try { syncRangeNumber('guidance_scale_range', 'guidance_scale', { decimals: 1 }); } catch (e) {}
      try { syncRangeNumber('shift_range', 'shift', { decimals: 1 }); } catch (e) {}
      try { syncRangeNumber('audio_cover_strength_range', 'audio_cover_strength', { decimals: 2 }); } catch (e) {}
      try { syncRangeNumber('cover_noise_strength_range', 'cover_noise_strength', { decimals: 2 }); } catch (e) {}
      try { syncRangeNumber('cover_conditioning_balance_range', 'cover_conditioning_balance', { decimals: 2 }); } catch (e) {}
      try { updateChordReferenceRendererUi(); } catch (e) {}
      try { syncRangeNumber('score_scale_range', 'score_scale', { decimals: 2 }); } catch (e) {}
      try { syncRangeNumber('latent_shift_range', 'latent_shift', { decimals: 2 }); } catch (e) {}
      try { syncRangeNumber('latent_rescale_range', 'latent_rescale', { decimals: 2 }); } catch (e) {}

      setImportStatus(true, 'status.import_ok');
    } catch (e) {
      const msg = (e && e.message) ? e.message : String(e);
      setImportStatus(false, t('status.import_error', { err: msg }));
    }
  };

  btn.addEventListener('click', async () => {
    setImportStatus(true, '');
    const fileObj = (file.files && file.files[0]) ? file.files[0] : null;
    const textVal = String(txt.value || '').trim();

    if (!textVal && !fileObj) {
      setImportStatus(false, t('error.import_empty'));
      return;
    }

    if (textVal) {
      await parseAndApply(textVal);
      return;
    }

    
    try {
      const content = await fileObj.text();
      await parseAndApply(content);
    } catch (e) {
      const msg = (e && e.message) ? e.message : String(e);
      setImportStatus(false, t('status.import_error', { err: msg }));
    }
  });
}




window.addEventListener('ace:ui_lang_changed', () => {
  try { refreshDynamicI18n(); } catch (e) {}
  try { refreshKeyScaleControlLabels(); } catch (e) {}
  try { updateModeVisibility(); } catch (e) {}
  try {
    if (refAudioInput && !(refAudioInput.files && refAudioInput.files[0])) setFilePickName(refAudioName, null);
    if (lmAudioInput && !(lmAudioInput.files && lmAudioInput.files[0])) setFilePickName(lmAudioName, null);
    if (importJsonFileInput && !(importJsonFileInput.files && importJsonFileInput.files[0])) setFilePickName(importJsonFileName, null);
  } catch (e) {}
});

window.addEventListener('load', async () => {
  
  applyTranslations();
  bindAuthUi();
  await loadAuthStatus();
  if (authState.enabled && (!authState.authenticated || authState.mustChangePassword)) return;
  setupFilePickButton(refAudioBtn, refAudioInput, refAudioName);
  setupFilePickButton(lmAudioBtn, lmAudioInput, lmAudioName);
  setupFilePickButton(importJsonFileBtn, importJsonFileInput, importJsonFileName);

  await loadOptions();
  await loadLoraCatalog();
  refreshDynamicI18n();
  setupKeyScaleControls();

  setupAutoToggles();
  configureNumericInputsForLocale();
  
  syncRangeNumber('lm_temperature_range', 'lm_temperature', { decimals: 2 });
  syncRangeNumber('lm_cfg_scale_range', 'lm_cfg_scale', { decimals: 1 });
  syncRangeNumber('lm_top_p_range', 'lm_top_p', { decimals: 2 });
  syncRangeNumber('lm_top_k_range', 'lm_top_k', { decimals: 0 });


  
  syncRangeNumber('steps_range', 'steps', { decimals: 0 });
  syncStepsPair();
  syncRangeNumber('inference_steps_range', 'inference_steps', { decimals: 0 });
  syncRangeNumber('source_start_range', 'source_start', { decimals: 1 });
  syncRangeNumber('source_end_range', 'source_end', { decimals: 1 });
  syncRangeNumber('guidance_scale_range', 'guidance_scale', { decimals: 1 });
  syncRangeNumber('shift_range', 'shift', { decimals: 1 });
  syncRangeNumber('cfg_interval_start_range', 'cfg_interval_start', { decimals: 2 });
  syncRangeNumber('cfg_interval_end_range', 'cfg_interval_end', { decimals: 2 });
  syncRangeNumber('normalization_db_range', 'normalization_db', { decimals: 1 });
  syncRangeNumber('score_scale_range', 'score_scale', { decimals: 2 });
  syncRangeNumber('latent_shift_range', 'latent_shift', { decimals: 2 });
  syncRangeNumber('latent_rescale_range', 'latent_rescale', { decimals: 2 });

  ['chord_key','chord_scale','chord_roman','chord_section_map'].forEach((id) => {
    const node = el(id);
    if (node) {
      node.addEventListener('input', refreshChordPreview);
      node.addEventListener('change', refreshChordPreview);
    }
  });
  ['chord_apply_keyscale','chord_apply_bpm','chord_apply_lyrics'].forEach((id) => {
    const node = el(id);
    if (node) node.addEventListener('change', refreshChordPreview);
  });
  if (el('btn_chord_generate')) el('btn_chord_generate').addEventListener('click', () => {
    const chordContext = `${el('caption')?.value || ''}
${el('lyrics')?.value || ''}`;
    const roman = generateSensibleRomanProgression(el('chord_scale')?.value || 'major', chordContext);
    if (el('chord_roman')) el('chord_roman').value = roman;
    refreshChordPreview();
    setChordStatusMessage(t('status.chord_generated', { roman }));
  });
  if (el('btn_chord_auto_sections')) el('btn_chord_auto_sections').addEventListener('click', autoGenerateChordSectionOverrides);
  if (el('btn_chord_apply')) el('btn_chord_apply').addEventListener('click', applyChordProgressionToUi);
  if (el('btn_chord_apply_full')) el('btn_chord_apply_full').addEventListener('click', applyChordProgressionFullConditioning);
  if (el('btn_chord_remove')) el('btn_chord_remove').addEventListener('click', removeChordProgressionFromUi);
  refreshChordPreview();
  syncRangeNumber('audio_cover_strength_range', 'audio_cover_strength', { decimals: 2 });
  syncRangeNumber('cover_noise_strength_range', 'cover_noise_strength', { decimals: 2 });
  syncRangeNumber('cover_conditioning_balance_range', 'cover_conditioning_balance', { decimals: 2 });
  updateChordReferenceRendererUi();

  
  try {
    const st = el('steps');
    const stR = el('steps_range');
    const mark = () => { __stepsTouched = true; };
    if (st) { st.addEventListener('input', mark); st.addEventListener('change', mark); }
    if (stR) { stR.addEventListener('input', mark); stR.addEventListener('change', mark); }
  } catch (e) {}

  try {
    if (modelSelect) {
      modelSelect.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      const initialModel = el('model_select')?.value || '';
      applyInferenceStepLimit(initialModel, {
        preserveValue: __stepsTouched,
        desiredValue: __stepsTouched ? undefined : getDefaultInferenceStepsForModel(initialModel),
      });
    }
  } catch (e) {}

  
  try {
    const savedW = String(localStorage.getItem('ace_lora_weight') || '').trim().replace(',', '.');
    const n = savedW === '' ? NaN : Number(savedW);
    if (Number.isFinite(n)) {
      const v = Math.max(0, Math.min(1, n));
      const formatted = formatLoraWeight(v);
      if (loraWeight) writeNumericInputValue(loraWeight, v, { preferValueAsNumber: true });
      if (loraWeightNum) writeNumericInputValue(loraWeightNum, v, { preferValueAsNumber: true });
    }
  } catch (e) {}

  const abCompareToggle = el('ab_compare_enabled');
  const batchSizeSel = el('batch_size');
  if (abCompareToggle) abCompareToggle.addEventListener('change', updateAbCompareBatchUi);
  if (batchSizeSel) batchSizeSel.addEventListener('change', () => {
    if (!isAbCompareEnabled()) batchSizeSel.dataset.abPrevValue = String(batchSizeSel.value || '1');
  });
  updateAbCompareBatchUi();

  if (loraWeight) loraWeight.addEventListener('input', () => syncLoraWeight('range'));
  if (loraWeightNum) {
    loraWeightNum.dataset.numericCommitBound = '1';
    loraWeightNum.addEventListener('input', () => syncLoraWeight('num', false));
    loraWeightNum.addEventListener('change', () => syncLoraWeight('num', true));
    loraWeightNum.addEventListener('blur', () => syncLoraWeight('num', true));
    loraWeightNum.addEventListener('keydown', (e) => {
      commitNumericFieldOnEnter(e, loraWeightNum, () => syncLoraWeight('num', true));
    });
  }

  
  setupImportJson();
  await loadRandomExample();
});



function updateChordReferenceRendererUi() {
  const sel = el('chord_reference_renderer');
  const help = el('chord_reference_renderer_help');
  if (!sel || !help) return;
  const soundfontOpt = sel.querySelector('option[value="soundfont"]');
  if (soundfontOpt) {
    soundfontOpt.disabled = !chordReferenceSoundfontAvailable;
    if (chordReferenceSoundfontAvailable) {
      soundfontOpt.textContent = chordReferenceSoundfontName
        ? t('opt.chord_reference_renderer_soundfont_named', { name: chordReferenceSoundfontName })
        : t('opt.chord_reference_renderer_soundfont');
    } else {
      soundfontOpt.textContent = t('opt.chord_reference_renderer_soundfont_unavailable');
    }
  }
  const preferred = String(sel.value || 'soundfont').trim().toLowerCase();
  if ((!chordReferenceSoundfontAvailable && preferred === 'soundfont') || (preferred !== 'soundfont' && preferred !== 'internal')) {
    sel.value = chordReferenceSoundfontAvailable ? 'soundfont' : 'internal';
  }
  help.textContent = chordReferenceSoundfontAvailable
    ? (chordReferenceSoundfontName
        ? t('help.chord_reference_renderer_available_named', { name: chordReferenceSoundfontName })
        : t('help.chord_reference_renderer_available'))
    : t('help.chord_reference_renderer_unavailable');
}

function refreshDynamicI18n() {
  try {
    
    const sel = el('lora_select');
    if (sel) {
      const noneOpt = sel.querySelector('option[value=""]');
      if (noneOpt) noneOpt.textContent = t('lora.none');
    }

    
    const ts = el('timesignature');
    if (ts) {
      const opt = ts.querySelector('option[value=""]');
      if (opt) opt.textContent = t('ph.auto');
    }
  } catch (e) {}
}

window.addEventListener('ace_ui_lang_changed', () => {
  refreshDynamicI18n();
  updateChordReferenceRendererUi();
  rerenderStatusForLangChange();
  rerenderNoticeForLangChange();
});
