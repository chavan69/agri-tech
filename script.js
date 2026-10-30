/* 02build AgriTech frontend -> FastAPI + Supabase backend */

/* ------------------------------------------------------------------ */
/* Config & state                                                      */
/* ------------------------------------------------------------------ */

const API_BASE = (() => {
    const saved = localStorage.getItem('agritech_api_base');
    if (saved) return saved.replace(/\/+$/, '');
    // Served by FastAPI (recommended) -> same origin. Opened as a file -> local API.
    return location.protocol === 'file:' ? 'http://127.0.0.1:8000/api' : '/api';
})();

const FALLBACK_IMAGE = 'https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=600&q=80';
const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;

let token = localStorage.getItem('agritech_token') || '';
let user = null;
let isSignup = false;
let bidTarget = null;

try {
    user = JSON.parse(localStorage.getItem('agritech_user') || 'null');
} catch (_) {
    user = null;
}

/** Point the app at another API host, e.g. setApiBase('https://api.example.com/api') */
window.setApiBase = (url) => {
    localStorage.setItem('agritech_api_base', url);
    location.reload();
};

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[char]));
}

const moneyFormat = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });

function money(value) {
    const number = Number(value);
    return Number.isFinite(number) ? `₹${moneyFormat.format(number)}` : '₹—';
}

function formatDate(value) {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

function icons() {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons();
    }
}

function toast(message, type = 'info') {
    const element = document.getElementById('toast');
    if (!element) return;

    const styles = {
        info: 'bg-white border-slate-200 text-slate-800',
        success: 'bg-emerald-600 border-emerald-700 text-white',
        error: 'bg-red-600 border-red-700 text-white'
    };
    element.className = `fixed top-4 right-4 z-[80] max-w-sm rounded-2xl px-4 py-3 text-sm font-bold shadow-xl border ${styles[type] || styles.info}`;
    element.textContent = message;
    element.classList.remove('hidden');

    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => element.classList.add('hidden'), 4500);
}

async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    const hasBody = options.body !== undefined;

    if (hasBody) headers['Content-Type'] = 'application/json';
    if (token && options.auth !== false) headers['Authorization'] = `Bearer ${token}`;

    let response;
    try {
        response = await fetch(`${API_BASE}${path}`, {
            method: options.method || 'GET',
            headers,
            body: hasBody ? JSON.stringify(options.body) : undefined
        });
    } catch (_) {
        throw new Error(`Cannot reach the API at ${API_BASE}. Start the FastAPI server (uvicorn app.main:app) and try again.`);
    }

    const text = await response.text();
    let data = null;
    if (text) {
        try {
            data = JSON.parse(text);
        } catch (_) {
            data = { detail: text };
        }
    }

    if (!response.ok) {
        if (response.status === 401 && options.auth !== false) {
            clearSession();
            showLogin();
        }

        const detail = data && data.detail;
        const message = Array.isArray(detail)
            ? detail.map((item) => item.msg || String(item)).join(', ')
            : (detail || `Request failed (${response.status}).`);

        const error = new Error(message);
        error.status = response.status;
        throw error;
    }

    return data;
}

function setSession(data) {
    token = data.access_token;
    user = data.user;
    localStorage.setItem('agritech_token', token);
    localStorage.setItem('agritech_user', JSON.stringify(user));
}

function clearSession() {
    token = '';
    user = null;
    localStorage.removeItem('agritech_token');
    localStorage.removeItem('agritech_user');
}

function toggleAuthMode() {
    isSignup = !isSignup;

    const title = document.getElementById('auth-title');
    const button = document.getElementById('auth-btn');
    const nameBox = document.getElementById('name-box');
    const extraBox = document.getElementById('extra-box');
    const toggleLabel = document.getElementById('toggle-lbl');
    const nameInput = document.getElementById('u-name');
    const passwordInput = document.getElementById('u-pass');

    title.innerText = isSignup ? 'Create Account' : 'Welcome Back';
    button.innerText = isSignup ? 'Sign Up →' : 'Log In →';
    nameBox.style.display = isSignup ? 'block' : 'none';
    nameInput.required = isSignup;
    extraBox.classList.toggle('hidden', !isSignup);
    passwordInput.setAttribute('autocomplete', isSignup ? 'new-password' : 'current-password');
    toggleLabel.innerText = isSignup ? 'Already have an account? Log In' : "Don't have an account? Sign Up";
}

async function handleAuth(event) {
    event.preventDefault();

    const name = document.getElementById('u-name').value.trim();
    const phone = document.getElementById('u-phone').value.trim();
    const password = document.getElementById('u-pass').value;
    const location = document.getElementById('u-loc').value.trim();
    const role = document.getElementById('u-role').value;

    if (isSignup && name.length < 2) {
        toast('Please enter your full name.', 'error');
        return;
    }
    if (!phone) {
        toast('Please enter your phone number.', 'error');
        return;
    }
    if (password.length < 6) {
        toast('Password must be at least 6 characters.', 'error');
        return;
    }

    const payload = isSignup
        ? { name, phone, password, location: location || 'Karnataka', role }
        : { phone, password };

    const button = document.getElementById('auth-btn');
    const originalLabel = button.textContent;
    button.disabled = true;
    button.textContent = isSignup ? 'Creating account…' : 'Logging in…';

    try {
        const data = await api(isSignup ? '/auth/signup' : '/auth/login', {
            method: 'POST',
            body: payload,
            auth: false
        });
        setSession(data);
        document.getElementById('u-pass').value = '';
        showApp();
        toast(`Welcome, ${data.user.name.split(' ')[0]}!`, 'success');
    } catch (error) {
        toast(error.message, 'error');
    } finally {
        button.disabled = false;
        button.textContent = originalLabel;
    }
}

function showLogin() {
    document.getElementById('login-screen').classList.remove('hidden');
    const app = document.getElementById('main-app');
    app.classList.add('hidden');
    app.classList.remove('flex');
}

function showApp() {
    document.getElementById('login-screen').classList.add('hidden');
    const app = document.getElementById('main-app');
    app.classList.remove('hidden');
    app.classList.add('flex');

    updateIdentity();
    switchTab('doctor');
    checkHealth();
}

function updateIdentity() {
    if (!user) return;

    const initial = (user.name || 'F').trim().charAt(0).toUpperCase();
    document.getElementById('sb-name').textContent = user.name || 'Farmer';
    document.getElementById('sb-role').textContent = user.role || 'Farmer';
    document.getElementById('sb-init').textContent = initial;
    document.getElementById('prof-avatar').textContent = initial;
    document.getElementById('prof-name').textContent = user.name || 'Farmer';
    document.getElementById('prof-info').textContent = `${user.role || 'Farmer'} • ${user.location || 'Karnataka'}`;
    document.getElementById('prof-phone').textContent = user.phone || '—';
    document.getElementById('prof-location').textContent = user.location || '—';
    document.getElementById('prof-role').textContent = user.role || '—';
}

function signOut() {
    clearSession();
    location.reload();
}

async function checkHealth() {
    const badge = document.getElementById('db-badge');

    try {
        const health = await api('/health', { auth: false });
        const database = health.database || {};

        if (database.reachable) {
            const isLocal = database.provider === 'local-sqlite';
            badge.textContent = isLocal ? '● Local Dev DB' : '● Supabase Connected';
            badge.className = isLocal
                ? 'text-xs font-bold px-3 py-1.5 rounded-full bg-sky-100 text-sky-800'
                : 'text-xs font-bold px-3 py-1.5 rounded-full bg-emerald-100 text-emerald-800';
            badge.title = isLocal
                ? `Offline development database (${database.path || 'backend/.local'}). Add SUPABASE_URL and SUPABASE_SERVICE_KEY to use Supabase.`
                : 'Database connection healthy';
        } else if (database.configured) {
            badge.textContent = '● Database Unreachable';
            badge.className = 'text-xs font-bold px-3 py-1.5 rounded-full bg-amber-100 text-amber-900';
            badge.title = database.error || 'Supabase is configured but not reachable';
        } else {
            badge.textContent = '● Supabase Not Configured';
            badge.className = 'text-xs font-bold px-3 py-1.5 rounded-full bg-amber-100 text-amber-900';
            badge.title = 'Set SUPABASE_URL and SUPABASE_SERVICE_KEY in backend/.env';
        }
    } catch (_) {
        badge.textContent = '● Backend Offline';
        badge.className = 'text-xs font-bold px-3 py-1.5 rounded-full bg-red-100 text-red-800';
        badge.title = `Could not reach ${API_BASE}`;
    }
}

/* ------------------------------------------------------------------ */
/* Navigation                                                          */
/* ------------------------------------------------------------------ */

const TAB_TITLES = {
    doctor: 'AI Plant Doctor & Diagnostics',
    market: 'E-Market & Live Auctions',
    machinery: 'Machinery & Labor Hub',
    profile: 'User Profile'
};

function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('hidden');
}

function switchTab(tab) {
    ['doctor', 'market', 'machinery', 'profile'].forEach((name) => {
        document.getElementById(`tab-${name}`).classList.add('hidden');
        document.getElementById(`btn-${name}`).className = 'w-full flex items-center gap-3 px-4 py-3 rounded-2xl text-sm font-extrabold hover:bg-green-800 text-green-100';
    });

    document.getElementById(`tab-${tab}`).classList.remove('hidden');
    document.getElementById(`btn-${tab}`).className = 'w-full flex items-center gap-3 px-4 py-3 rounded-2xl text-sm font-extrabold bg-yellow-400 text-green-950 shadow';
    document.getElementById('page-title').textContent = TAB_TITLES[tab] || '';

    if (tab === 'market') fetchMarket();
    if (tab === 'machinery') fetchMachinery();
    if (tab === 'profile') {
        updateIdentity();
        fetchScans();
    }
}

function openModal(id) {
    const element = document.getElementById(id);
    element.classList.remove('hidden');
    element.classList.add('flex');
}

function closeModal(id) {
    const element = document.getElementById(id);
    element.classList.remove('flex');
    element.classList.add('hidden');
}

/* ------------------------------------------------------------------ */
/* AI Plant Doctor                                                     */
/* ------------------------------------------------------------------ */

async function handleImageUpload(event) {
    const file = event.target.files && event.target.files[0];
    event.target.value = '';
    if (!file) return;

    if (!file.type.startsWith('image/')) {
        toast('Please choose an image file.', 'error');
        return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
        toast('Image is larger than 8 MB. Please choose a smaller photo.', 'error');
        return;
    }

    document.getElementById('leaf-preview').src = URL.createObjectURL(file);
    document.getElementById('image-preview-container').classList.remove('hidden');

    const output = document.getElementById('diagnostic-output');
    output.innerHTML = `
        <div class="bg-white p-12 rounded-3xl border text-center flex flex-col items-center justify-center h-full min-h-[300px]">
            <i data-lucide="refresh-cw" class="w-10 h-10 text-green-600 animate-spin mb-3"></i>
            <h3 class="text-base font-bold text-slate-800">AI Plant Doctor is inspecting leaf veins...</h3>
            <p class="text-xs text-slate-500 mt-1">Analyzing chlorosis, fungal patterns, and pre-disease stress</p>
        </div>`;
    icons();

    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = async () => {
        const base64String = String(reader.result).split(',')[1];

        try {
            const data = await api('/plant-doctor/analyze', {
                method: 'POST',
                body: { imageBase64: base64String, mimeType: file.type || 'image/jpeg' }
            });
            renderDiagnosticReport(data.report);
            toast('Diagnosis saved to your account.', 'success');
        } catch (error) {
            output.innerHTML = `
                <div class="bg-white p-10 rounded-3xl border text-center flex flex-col items-center justify-center h-full min-h-[300px]">
                    <i data-lucide="alert-triangle" class="w-10 h-10 text-red-500 mb-3"></i>
                    <h3 class="text-base font-bold text-slate-800">Analysis failed</h3>
                    <p class="text-xs text-red-600 mt-1 max-w-sm">${esc(error.message)}</p>
                </div>`;
            icons();
            toast(error.message, 'error');
        }
    };
}

function renderDiagnosticReport(report) {
    if (!report) return;

    const badgeClass = report.badgeColor === 'amber'
        ? 'bg-amber-100 text-amber-900'
        : report.badgeColor === 'red'
            ? 'bg-red-100 text-red-900'
            : 'bg-emerald-100 text-emerald-900';

    const prevention = Array.isArray(report.prevention) ? report.prevention : [];
    const confidence = report.confidence != null
        ? `<span class="text-[10px] font-bold text-slate-500 ml-2">${esc(report.confidence)}% confidence</span>`
        : '';

    const output = document.getElementById('diagnostic-output');
    output.innerHTML = `
        <div class="bg-white p-6 rounded-3xl border space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-2 border-b pb-3">
                <div>
                    <span class="text-[10px] font-extrabold uppercase text-slate-400">Crop: ${esc(report.crop)}</span>
                    <h4 class="text-lg font-black text-slate-900">${esc(report.diagnosis)}${confidence}</h4>
                </div>
                <span class="px-3 py-1 rounded-full text-xs font-extrabold ${badgeClass}">${esc(report.status)}</span>
            </div>
            <div class="bg-amber-50 border border-amber-200 p-3.5 rounded-2xl">
                <h5 class="font-extrabold text-amber-950 text-xs mb-1">⚠️ Pre-Disease Prevention &amp; Immediate Action</h5>
                <ul class="list-disc list-inside text-xs text-amber-900 space-y-1">
                    ${prevention.map((step) => `<li>${esc(step)}</li>`).join('')}
                </ul>
            </div>
            <div class="grid sm:grid-cols-2 gap-3">
                <div class="bg-green-50 border border-green-200 p-3.5 rounded-2xl">
                    <h5 class="font-extrabold text-green-950 text-xs mb-1">🌿 Organic Remedy</h5>
                    <p class="text-xs text-green-900">${esc(report.organicCure || '—')}</p>
                </div>
                <div class="bg-blue-50 border border-blue-200 p-3.5 rounded-2xl">
                    <h5 class="font-extrabold text-blue-950 text-xs mb-1">🧪 Chemical Cure &amp; Dosage</h5>
                    <p class="text-xs text-blue-900">${esc(report.chemicalCure || '—')}</p>
                </div>
            </div>
        </div>`;
    icons();
}

/* ------------------------------------------------------------------ */
/* E-market                                                            */
/* ------------------------------------------------------------------ */

function loadingCard(message) {
    return `<div class="col-span-full bg-white p-10 rounded-3xl border text-center text-slate-500 text-sm">${esc(message)}</div>`;
}

function errorCard(message, retry) {
    return `
        <div class="col-span-full bg-white p-10 rounded-3xl border text-center">
            <i data-lucide="wifi-off" class="w-8 h-8 text-red-500 mx-auto mb-2"></i>
            <p class="text-sm font-bold text-slate-800">Could not load data</p>
            <p class="text-xs text-red-600 mt-1">${esc(message)}</p>
            ${retry ? `<button onclick="${retry}" class="mt-3 text-xs font-extrabold text-green-700 hover:underline">Try again</button>` : ''}
        </div>`;
}

function marketCard(listing) {
    const auction = listing.mode === 'auction';
    const currentBid = listing.current_bid != null ? listing.current_bid : listing.price;
    const name = esc(listing.name);
    const image = esc(listing.image || FALLBACK_IMAGE);

    return `
        <div class="bg-white rounded-3xl border overflow-hidden flex flex-col relative shadow-sm">
            <button data-delete-market="${esc(listing.id)}" class="absolute top-3 right-3 bg-white p-2 rounded-xl text-red-600 shadow border hover:bg-red-50" title="Delete listing" aria-label="Delete listing">
                <i data-lucide="trash-2" class="w-4 h-4"></i>
            </button>
            <span class="absolute top-3 left-3 ${auction ? 'bg-yellow-400 text-green-950' : 'bg-emerald-100 text-emerald-800'} text-[10px] font-black uppercase px-2.5 py-1 rounded-full">
                ${auction ? 'Live Auction' : 'Direct Buy'}
            </span>
            <img src="${image}" alt="${name}" class="h-36 w-full object-cover bg-slate-100" onerror="this.onerror=null;this.src='${FALLBACK_IMAGE}'">
            <div class="p-4 space-y-2 flex-1 flex flex-col">
                <div class="flex items-start justify-between gap-2">
                    <h4 class="font-extrabold text-base">${name}</h4>
                    <span class="text-[10px] font-bold uppercase text-slate-400">${esc(listing.category)}</span>
                </div>
                <p class="text-xs text-slate-500">👤 ${esc(listing.seller || 'Verified seller')} • 📍 ${esc(listing.location || 'Karnataka')}</p>
                <p class="font-black text-green-900">${money(listing.price)} <span class="text-xs font-bold text-slate-500">/ kg (${esc(listing.quantity || '—')})</span></p>
                ${auction ? `
                    <p class="text-[11px] text-slate-500">Current bid: <span class="font-extrabold text-green-900">${money(currentBid)}</span></p>
                    <button data-bid="${esc(listing.id)}" data-amount="${esc(currentBid)}" data-name="${name}" class="mt-auto w-full bg-green-700 hover:bg-green-800 text-white text-xs font-extrabold py-2.5 rounded-xl">
                        Place Bid
                    </button>` : `
                    <button data-contact="${esc(listing.phone || '')}" class="mt-auto w-full border border-green-700 text-green-800 hover:bg-green-50 text-xs font-extrabold py-2.5 rounded-xl">
                        Contact Seller
                    </button>`}
            </div>
        </div>`;
}

async function fetchMarket() {
    const grid = document.getElementById('market-grid');
    grid.innerHTML = loadingCard('Loading listings…');

    try {
        const listings = await api('/market');
        grid.innerHTML = listings.length
            ? listings.map(marketCard).join('')
            : loadingCard('No listings yet. Use “+ List Harvest” to add the first one.');
    } catch (error) {
        grid.innerHTML = errorCard(error.message, 'fetchMarket()');
    }

    grid.onclick = (event) => {
        const deleteButton = event.target.closest('[data-delete-market]');
        if (deleteButton) return deleteMarket(deleteButton.dataset.deleteMarket);

        const bidButton = event.target.closest('[data-bid]');
        if (bidButton) return openBidModal(bidButton.dataset.bid, Number(bidButton.dataset.amount), bidButton.dataset.name || '');

        const contactButton = event.target.closest('[data-contact]');
        if (contactButton) return contactSeller(contactButton.dataset.contact);
    };

    icons();
}

async function postCrop() {
    const name = document.getElementById('c-name').value.trim();
    const price = Number(document.getElementById('c-price').value || 30);
    const quantity = document.getElementById('c-qty').value.trim() || '100 kg';

    if (!name) {
        toast('Please enter a product name.', 'error');
        return;
    }
    if (!Number.isFinite(price) || price <= 0) {
        toast('Please enter a valid price.', 'error');
        return;
    }

    try {
        await api('/market', {
            method: 'POST',
            body: {
                name,
                category: document.getElementById('c-cat').value,
                mode: document.getElementById('c-mode').value,
                price,
                quantity
            }
        });
        document.getElementById('c-name').value = '';
        document.getElementById('c-price').value = '';
        document.getElementById('c-qty').value = '';
        closeModal('crop-modal');
        toast('Listing saved to Supabase.', 'success');
        fetchMarket();
    } catch (error) {
        toast(error.message, 'error');
    }
}

async function deleteMarket(id) {
    if (!window.confirm('Delete this listing permanently?')) return;

    try {
        await api(`/market/${encodeURIComponent(id)}`, { method: 'DELETE' });
        toast('Listing deleted.', 'success');
        fetchMarket();
    } catch (error) {
        toast(error.message, 'error');
    }
}

function contactSeller(phone) {
    if (!phone) {
        toast('No phone number was provided for this listing.', 'error');
        return;
    }
    toast(`Seller phone: ${phone}`);
    if (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) {
        window.location.href = `tel:${phone.replace(/[^\d+]/g, '')}`;
    }
}

function openBidModal(id, current, name) {
    bidTarget = { id, current: Number(current) || 0 };
    document.getElementById('bid-item').textContent = name;
    document.getElementById('bid-current').textContent = money(bidTarget.current);

    const input = document.getElementById('bid-amount');
    input.min = String(Math.floor(bidTarget.current) + 1);
    input.value = String(Math.ceil(bidTarget.current + 1));

    openModal('bid-modal');
    input.focus();
}

async function submitBid() {
    if (!bidTarget) return;

    const amount = Number(document.getElementById('bid-amount').value);
    if (!Number.isFinite(amount) || amount <= bidTarget.current) {
        toast(`Your bid must be higher than ${money(bidTarget.current)}.`, 'error');
        return;
    }

    try {
        await api(`/market/${encodeURIComponent(bidTarget.id)}/bid`, {
            method: 'POST',
            body: { amount }
        });
        closeModal('bid-modal');
        toast(`Bid placed: ${money(amount)}`, 'success');
        bidTarget = null;
        fetchMarket();
    } catch (error) {
        toast(error.message, 'error');
        if (error.status === 409) fetchMarket();
    }
}

/* ------------------------------------------------------------------ */
/* Machinery                                                           */
/* ------------------------------------------------------------------ */

function machineryCard(machine) {
    const typeLabel = machine.type === 'requirement' ? 'Requirement' : 'For Rent';
    const typeClass = machine.type === 'requirement'
        ? 'bg-blue-100 text-blue-800'
        : 'bg-emerald-100 text-emerald-800';

    return `
        <div class="bg-white p-5 rounded-3xl border space-y-3 shadow-sm relative flex flex-col">
            <button data-delete-machine="${esc(machine.id)}" class="absolute top-3 right-3 text-red-600 hover:text-red-800" title="Delete listing" aria-label="Delete listing">
                <i data-lucide="trash-2" class="w-4 h-4"></i>
            </button>
            <span class="self-start text-[10px] font-black uppercase px-2.5 py-1 rounded-full ${typeClass}">${typeLabel}</span>
            <h4 class="font-extrabold text-base pr-6">${esc(machine.title)}</h4>
            <p class="text-xs text-slate-500">${esc(machine.specs || 'Verified')}</p>
            <p class="text-xs text-slate-500">👤 ${esc(machine.owner || 'Verified owner')} • 📍 ${esc(machine.location || 'Karnataka')}</p>
            <div class="flex items-center justify-between gap-2 mt-auto pt-2">
                <p class="font-black text-green-900">${esc(machine.rate || '₹—')}</p>
                <button data-contact="${esc(machine.phone || '')}" class="border border-green-700 text-green-800 hover:bg-green-50 text-xs font-extrabold px-3 py-2 rounded-xl">Call</button>
            </div>
        </div>`;
}

async function fetchMachinery() {
    const grid = document.getElementById('machinery-grid');
    grid.innerHTML = loadingCard('Loading machinery…');

    try {
        const machines = await api('/machinery');
        grid.innerHTML = machines.length
            ? machines.map(machineryCard).join('')
            : loadingCard('No machinery listed yet. Use “+ List Machine” to add the first one.');
    } catch (error) {
        grid.innerHTML = errorCard(error.message, 'fetchMachinery()');
    }

    grid.onclick = (event) => {
        const deleteButton = event.target.closest('[data-delete-machine]');
        if (deleteButton) return deleteMachine(deleteButton.dataset.deleteMachine);

        const contactButton = event.target.closest('[data-contact]');
        if (contactButton) return contactSeller(contactButton.dataset.contact);
    };

    icons();
}

async function postMachine() {
    const title = document.getElementById('m-title').value.trim();
    if (!title) {
        toast('Please enter a title for the machine.', 'error');
        return;
    }

    try {
        await api('/machinery', {
            method: 'POST',
            body: {
                title,
                type: document.getElementById('m-type').value,
                category: 'Heavy Machinery',
                rate: document.getElementById('m-rate').value.trim() || '₹500 / hr',
                specs: document.getElementById('m-specs').value.trim() || 'Verified'
            }
        });
        document.getElementById('m-title').value = '';
        document.getElementById('m-rate').value = '';
        document.getElementById('m-specs').value = '';
        closeModal('machine-modal');
        toast('Machinery listing saved to Supabase.', 'success');
        fetchMachinery();
    } catch (error) {
        toast(error.message, 'error');
    }
}

async function deleteMachine(id) {
    if (!window.confirm('Delete this machinery listing permanently?')) return;

    try {
        await api(`/machinery/${encodeURIComponent(id)}`, { method: 'DELETE' });
        toast('Machinery listing deleted.', 'success');
        fetchMachinery();
    } catch (error) {
        toast(error.message, 'error');
    }
}

/* ------------------------------------------------------------------ */
/* Scan history                                                        */
/* ------------------------------------------------------------------ */

function scanCard(scan) {
    const badgeClass = scan.badge_color === 'red'
        ? 'bg-red-100 text-red-900'
        : scan.badge_color === 'amber'
            ? 'bg-amber-100 text-amber-900'
            : 'bg-emerald-100 text-emerald-900';

    const confidence = scan.confidence != null ? `${scan.confidence}%` : '—';

    return `
        <div class="border rounded-2xl p-3.5 space-y-1.5">
            <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                    <p class="text-[10px] font-extrabold uppercase text-slate-400 truncate">${esc(scan.crop || 'Unknown crop')}</p>
                    <p class="text-sm font-bold text-slate-900 truncate">${esc(scan.diagnosis || 'Diagnosis')}</p>
                </div>
                <button data-scan-delete="${esc(scan.id)}" class="text-red-600 hover:text-red-800 shrink-0" title="Delete scan" aria-label="Delete scan">
                    <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
                </button>
            </div>
            <div class="flex flex-wrap items-center gap-2 text-[10px]">
                <span class="px-2 py-0.5 rounded-full font-extrabold ${badgeClass}">${esc(scan.status || 'Saved')}</span>
                <span class="text-slate-500">Confidence: ${esc(confidence)}</span>
                <span class="text-slate-400">${esc(formatDate(scan.created_at))}</span>
            </div>
        </div>`;
}

async function fetchScans() {
    const list = document.getElementById('scan-list');
    list.innerHTML = '<p class="text-xs text-slate-500">Loading diagnostics…</p>';

    try {
        const scans = await api('/scans');
        list.innerHTML = scans.length
            ? scans.map(scanCard).join('')
            : '<p class="text-xs text-slate-500">No scans yet. Analyze a leaf photo to build your history.</p>';

        list.querySelectorAll('[data-scan-delete]').forEach((button) => {
            button.addEventListener('click', () => deleteScan(button.dataset.scanDelete));
        });
    } catch (error) {
        list.innerHTML = `<p class="text-xs text-red-600">${esc(error.message)}</p>`;
    }

    icons();
}

async function deleteScan(id) {
    if (!window.confirm('Delete this diagnostic report?')) return;

    try {
        await api(`/scans/${encodeURIComponent(id)}`, { method: 'DELETE' });
        toast('Diagnostic report deleted.', 'success');
        fetchScans();
    } catch (error) {
        toast(error.message, 'error');
    }
}

/* ------------------------------------------------------------------ */
/* Boot                                                                */
/* ------------------------------------------------------------------ */

async function boot() {
    icons();
    document.getElementById('name-box').style.display = 'none';

    if (!token) {
        showLogin();
        return;
    }

    try {
        user = await api('/auth/me');
        localStorage.setItem('agritech_user', JSON.stringify(user));
        showApp();
    } catch (_) {
        clearSession();
        showLogin();
    }
}

boot();
