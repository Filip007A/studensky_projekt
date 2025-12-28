// Simple signage client: WS realtime + HTTP fallback
const statusEl = document.getElementById('status');
const depsEl = document.getElementById('departures');

// replace relative WS path with absolute backend URL for local dev:
const WS_PATH = 'ws://localhost:8000/ws/updates';
const API_BASE = 'http://localhost:8000'; // <-- backend base for REST calls
const STATUS_PATH = `${API_BASE}/api/status`;
const FALLBACK_PATH = `${API_BASE}/api/fallback`;

let ws = null;
let reconnectTimeout = 2000;
let reconnectHandle = null;

function renderDepartures(list) {
  depsEl.innerHTML = '';
  if (!list || list.length === 0) {
    depsEl.innerHTML = `<div class="departure empty">Žádné odjezdy</div>`;
    return;
  }
  list.forEach(d => {
    const el = document.createElement('div');
    el.className = 'departure';
    el.innerHTML = `<div class="line">${escapeHtml(d.line)}</div>
                    <div class="dest">${escapeHtml(d.dest)}</div>
                    <div class="time">${escapeHtml(String(d.in_min))} min</div>`;
    depsEl.appendChild(el);
  });
}

function escapeHtml(s){ return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}[c])); }

async function setOfflineView() {
  statusEl.textContent = 'OFFLINE — zobrazuji lokální data';
  try {
    const r = await fetch(FALLBACK_PATH);
    const data = await r.json();
    renderDepartures((data.departures || []).slice(0, 10));
  } catch (e) {
    depsEl.innerHTML = `<div class="departure empty">Žádná fallback data</div>`;
  }
}

function getWebSocketUrl() {
  // pokud WS_PATH je absolutní (ws:// nebo wss://), použij ho přímo
  if (WS_PATH.startsWith('ws://') || WS_PATH.startsWith('wss://')) return WS_PATH;
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${location.host}${WS_PATH}`;
}

function connect() {
  const wsUrl = getWebSocketUrl();
  try {
    ws = new WebSocket(wsUrl);
  } catch (err) {
    console.error('WS construction error', err);
    setOfflineView();
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    statusEl.textContent = 'ONLINE — přijímám data';
    console.log('WS connected to', wsUrl);
    if (reconnectHandle) { clearTimeout(reconnectHandle); reconnectHandle = null; reconnectTimeout = 2000; }
  };

  ws.onmessage = ev => {
    try {
      const data = JSON.parse(ev.data);
      renderDepartures(data.departures || []);
    } catch (e) {
      console.warn('Invalid WS payload', e);
    }
  };

  ws.onclose = (ev) => {
    console.warn('WS closed', ev);
    statusEl.textContent = 'Přerušeno — přepínám na offline';
    setOfflineView();
    scheduleReconnect();
  };

  ws.onerror = (err) => {
    console.error('WS error', err);
    // zavři spojení, onclose provede přepnutí do offline a reconnect
    try { ws.close(); } catch(e){}
  };
}

function scheduleReconnect(){
  if (reconnectHandle) return;
  reconnectHandle = setTimeout(() => {
    reconnectHandle = null;
    reconnectTimeout = Math.min(30000, reconnectTimeout * 1.5);
    connect();
  }, reconnectTimeout);
}

// periodic REST health check, fallback to offline on failure
setInterval(async () => {
  try {
    await fetch(STATUS_PATH, {cache: 'no-store'});
    // pokud byl offline a WS se nepřipojí, connect se stále snaží
  } catch {
    setOfflineView();
  }
}, 10000);

// start
connect();