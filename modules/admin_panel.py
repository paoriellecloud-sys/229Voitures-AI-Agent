"""Admin panel router — tableau de bord unifié 229Voitures."""
import os
import sqlite3
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter()

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "admin229voitures2026")
INV_DB = os.environ.get("DB_PATH", "/home/ubuntu/data/229voitures.db")
_HERE = os.path.dirname(os.path.abspath(__file__))
APP_DB = os.path.join(os.path.dirname(_HERE), "vehicles.db")

_PARTNERS = [
    "Honda Donnacona", "Kia Québec", "Kia Val-Bélair", "Kia Ste-Foy", "Ford Donnacona",
]


# ── DB helpers ──────────────────────────────────────────────────

def _verify(token: str):
    if not token or token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Non autorisé")


def _inv_scalar(sql: str, params: tuple = (), default=0):
    conn = sqlite3.connect(INV_DB)
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row and row[0] is not None else default
    except Exception:
        return default
    finally:
        conn.close()


def _inv_fetch(sql: str, params: tuple = ()) -> list:
    conn = sqlite3.connect(INV_DB)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def _app_scalar(sql: str, params: tuple = (), default=0):
    conn = sqlite3.connect(APP_DB)
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row and row[0] is not None else default
    except Exception:
        return default
    finally:
        conn.close()


def _app_fetch(sql: str, params: tuple = ()) -> list:
    conn = sqlite3.connect(APP_DB)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


# ── API endpoints ────────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(token: str = ""):
    _verify(token)
    return _HTML


@router.get("/admin/api/overview")
def api_overview(token: str = ""):
    _verify(token)
    return {
        "total_vehicles": _inv_scalar("SELECT COUNT(*) FROM inventory_cache"),
        "marketplace":    _inv_scalar(
            "SELECT COUNT(*) FROM inventory_cache WHERE marketplace_posted_at IS NOT NULL"
        ),
        "leads":          _app_scalar("SELECT COUNT(*) FROM leads"),
        "sessions":       _inv_scalar("SELECT COUNT(*) FROM sessions"),
    }


@router.get("/admin/api/leads")
def api_leads(token: str = ""):
    _verify(token)
    rows = _app_fetch(
        "SELECT id, name, phone, email, vehicle_title, vehicle_price, "
        "dealer_name, message, created_at FROM leads ORDER BY created_at DESC LIMIT 100"
    )
    return {"leads": rows, "total": len(rows)}


@router.get("/admin/api/marketplace-items")
def api_marketplace_items(token: str = "", q: str = ""):
    _verify(token)
    base_cols = (
        "SELECT vehicle_id, vin, title, price, marketplace_posted_at "
        "FROM inventory_cache WHERE marketplace_posted_at IS NOT NULL"
    )
    if q.strip():
        pattern = f"%{q.strip()}%"
        rows = _inv_fetch(
            base_cols + " AND (title LIKE ? OR vin LIKE ? OR CAST(vehicle_id AS TEXT) LIKE ?)"
            " ORDER BY marketplace_posted_at DESC LIMIT 50",
            (pattern, pattern, pattern),
        )
    else:
        rows = _inv_fetch(base_cols + " ORDER BY marketplace_posted_at DESC LIMIT 100")
    return {"items": rows}


@router.get("/admin/api/partners")
def api_partners(token: str = ""):
    _verify(token)
    last_scrape = _inv_scalar("SELECT MAX(scraped_at) FROM inventory_cache", default=None)
    partners = [
        {
            "dealer": p,
            "count": _inv_scalar(
                "SELECT COUNT(*) FROM inventory_cache WHERE LOWER(dealer_name) = LOWER(?)", (p,)
            ),
        }
        for p in _PARTNERS
    ]
    return {"partners": partners, "last_scrape": last_scrape}


@router.get("/admin/api/bugs")
def api_bugs(token: str = ""):
    _verify(token)
    rows = _app_fetch(
        "SELECT id, user_id, question, response, intent, created_at "
        "FROM bad_responses ORDER BY created_at DESC LIMIT 100"
    )
    return {"bugs": rows, "total": len(rows)}


# ── Embedded HTML ────────────────────────────────────────────────

_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin — 229Voitures</title>
<style>
:root {
  --bg: #0f1117;
  --card: #1a1d27;
  --border: #2d3748;
  --accent: #3b82f6;
  --text: #e2e8f0;
  --muted: #64748b;
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  --radius: 10px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; min-height: 100vh; }
a { color: inherit; text-decoration: none; }

header {
  background: var(--card);
  border-bottom: 1px solid var(--border);
  padding: 14px 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky; top: 0; z-index: 100;
}
.logo { font-size: 17px; font-weight: 700; color: var(--accent); }
.hdr-sub { font-size: 12px; color: var(--muted); }

nav.tabs {
  background: var(--card);
  border-bottom: 1px solid var(--border);
  padding: 0 20px;
  display: flex; gap: 2px;
  overflow-x: auto;
}
.tab {
  background: none; border: none;
  border-bottom: 2px solid transparent;
  color: var(--muted); cursor: pointer;
  font-family: inherit; font-size: 13px; font-weight: 500;
  padding: 12px 18px; white-space: nowrap;
  transition: color .15s, border-color .15s;
}
.tab:hover { color: var(--text); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }

main { padding: 28px; max-width: 1200px; margin: 0 auto; }
.pane { display: none; }
.pane.active { display: block; }

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 16px; margin-bottom: 32px;
}
.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 22px 24px;
}
.stat-val { font-size: 38px; font-weight: 700; color: var(--text); line-height: 1.1; }
.stat-val.blue { color: var(--accent); }
.stat-val.green { color: var(--success); }
.stat-val.orange { color: var(--warning); }
.stat-label { font-size: 11px; color: var(--muted); margin-top: 8px; text-transform: uppercase; letter-spacing: .06em; }

.section-header {
  font-size: 15px; font-weight: 600;
  margin-bottom: 14px;
  display: flex; align-items: center; gap: 10px;
}
.badge {
  background: var(--accent); color: #fff;
  border-radius: 20px; font-size: 11px; font-weight: 700;
  padding: 2px 8px;
}

.table-wrap { border: 1px solid var(--border); border-radius: var(--radius); overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead th {
  background: rgba(45,55,72,.4);
  color: var(--muted); font-size: 11px; font-weight: 600;
  letter-spacing: .06em; padding: 11px 14px;
  text-align: left; text-transform: uppercase;
  white-space: nowrap; border-bottom: 1px solid var(--border);
}
tbody tr { border-bottom: 1px solid rgba(45,55,72,.5); }
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: rgba(59,130,246,.04); }
td { padding: 10px 14px; vertical-align: top; }
td.nowrap { white-space: nowrap; color: var(--muted); font-size: 12px; }
td.mono { font-family: monospace; font-size: 11px; color: var(--muted); }
td.trunc { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
td.msg { max-width: 240px; word-break: break-word; font-size: 12px; color: var(--muted); }

.mkt-cta {
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px 24px;
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; margin-bottom: 24px; flex-wrap: wrap;
}
.mkt-cta-title { font-size: 15px; font-weight: 600; margin-bottom: 4px; }
.mkt-cta-sub { font-size: 13px; color: var(--muted); }
.btn-accent {
  background: var(--accent); color: #fff; border: none;
  border-radius: 8px; font-family: inherit; font-size: 13px; font-weight: 600;
  padding: 10px 20px; cursor: pointer; display: inline-block;
  white-space: nowrap; transition: background .15s;
}
.btn-accent:hover { background: #2563eb; }

.scrape-info {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 18px;
  font-size: 13px; color: var(--muted); margin-bottom: 22px;
}
.scrape-info strong { color: var(--text); }

.partner-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 14px;
}
.partner-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 22px 20px; text-align: center;
}
.partner-name { font-size: 12px; color: var(--muted); margin-bottom: 12px; line-height: 1.5; }
.partner-count { font-size: 40px; font-weight: 700; color: var(--accent); line-height: 1; }
.partner-unit { font-size: 11px; color: var(--muted); margin-top: 5px; }

.loading { text-align: center; padding: 60px 20px; color: var(--muted); font-size: 14px; }
.empty   { text-align: center; padding: 60px 20px; color: var(--muted); font-size: 14px; }
.err     { text-align: center; padding: 40px 20px; color: var(--danger); font-size: 13px; }
</style>
</head>
<body>

<header>
  <div class="logo">229Voitures — Admin</div>
  <div class="hdr-sub" id="hdr-date"></div>
</header>

<nav class="tabs">
  <button class="tab active" data-tab="overview">&#128202; Vue d'ensemble</button>
  <button class="tab" data-tab="leads">&#128197; Leads &amp; RDV</button>
  <button class="tab" data-tab="marketplace">&#128722; Marketplace</button>
  <button class="tab" data-tab="partners">&#127970; Partenaires &amp; Inventaire</button>
  <button class="tab" data-tab="bugs">&#128027; Bugs signalés</button>
</nav>

<main>
  <div class="pane active" id="pane-overview"><div class="loading">Chargement…</div></div>
  <div class="pane"        id="pane-leads"><div class="loading">Chargement…</div></div>
  <div class="pane"        id="pane-marketplace"><div class="loading">Chargement…</div></div>
  <div class="pane"        id="pane-partners"><div class="loading">Chargement…</div></div>
  <div class="pane"        id="pane-bugs"><div class="loading">Chargement…</div></div>
</main>

<script>
'use strict';
const TOKEN = new URLSearchParams(location.search).get('token') || '';
const loaded = {};

// ── Header date ──────────────────────────────────────────────
document.getElementById('hdr-date').textContent =
  new Date().toLocaleDateString('fr-CA', {weekday:'long',year:'numeric',month:'long',day:'numeric'});

// ── Tab switching ────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const name = btn.dataset.tab;
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.pane').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('pane-' + name).classList.add('active');
    if (!loaded[name]) { loadTab(name); loaded[name] = true; }
  });
});

// Load first tab immediately
loaded['overview'] = true;
loadTab('overview');

// ── Fetch helper ─────────────────────────────────────────────
function api(path) {
  return fetch(path + '?token=' + encodeURIComponent(TOKEN))
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
}

const ENDPOINTS = {
  overview:    '/admin/api/overview',
  leads:       '/admin/api/leads',
  marketplace: '/admin/api/marketplace-items',
  partners:    '/admin/api/partners',
  bugs:        '/admin/api/bugs',
};

function loadTab(name) {
  const pane = document.getElementById('pane-' + name);
  api(ENDPOINTS[name])
    .then(data => RENDERS[name](data, pane))
    .catch(e => { pane.innerHTML = '<div class="err">Erreur : ' + e.message + '</div>'; });
}

// ── Formatters ───────────────────────────────────────────────
const fmt = n => n != null
  ? new Intl.NumberFormat('fr-CA',{style:'currency',currency:'CAD',maximumFractionDigits:0}).format(n)
  : '–';
const esc = s => String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const dt  = s => s ? String(s).replace('T',' ').slice(0,16) : '—';

// ── Renderers ────────────────────────────────────────────────
const RENDERS = {
  overview:    renderOverview,
  leads:       renderLeads,
  marketplace: renderMarketplace,
  partners:    renderPartners,
  bugs:        renderBugs,
};

function renderOverview(d, pane) {
  pane.innerHTML =
    '<div class="stat-grid">' +
      '<div class="stat-card"><div class="stat-val">'       + (d.total_vehicles||0) + '</div><div class="stat-label">Total véhicules</div></div>' +
      '<div class="stat-card"><div class="stat-val blue">'  + (d.marketplace||0)    + '</div><div class="stat-label">Sur Marketplace</div></div>' +
      '<div class="stat-card"><div class="stat-val orange">'+ (d.leads||0)          + '</div><div class="stat-label">Leads en attente</div></div>' +
      '<div class="stat-card"><div class="stat-val green">' + (d.sessions||0)        + '</div><div class="stat-label">Sessions actives</div></div>' +
    '</div>';
}

function renderLeads(d, pane) {
  if (!d.leads || !d.leads.length) { pane.innerHTML = '<div class="empty">Aucun lead enregistré.</div>'; return; }
  let rows = d.leads.map(l =>
    '<tr>' +
      '<td>' + esc(l.name) + '</td>' +
      '<td class="nowrap">' + esc(l.phone) + '</td>' +
      '<td class="trunc" title="' + esc(l.email) + '">' + esc(l.email) + '</td>' +
      '<td class="trunc" title="' + esc(l.vehicle_title) + '">' + esc(l.vehicle_title) + '</td>' +
      '<td class="nowrap">' + fmt(l.vehicle_price) + '</td>' +
      '<td>' + esc(l.dealer_name) + '</td>' +
      '<td class="msg">' + esc(l.message) + '</td>' +
      '<td class="nowrap">' + dt(l.created_at) + '</td>' +
    '</tr>'
  ).join('');
  pane.innerHTML =
    '<div class="section-header">Leads &amp; RDV <span class="badge">' + d.total + '</span></div>' +
    '<div class="table-wrap"><table>' +
      '<thead><tr><th>Nom</th><th>Téléphone</th><th>Email</th><th>Véhicule</th><th>Prix</th><th>Concessionnaire</th><th>Message</th><th>Date</th></tr></thead>' +
      '<tbody>' + rows + '</tbody>' +
    '</table></div>';
}

let _mktItems = [];

function renderMarketplace(d, pane) {
  const mktUrl = '/admin/marketplace?token=' + encodeURIComponent(TOKEN);
  _mktItems = d.items || [];

  pane.innerHTML =
    '<div class="mkt-cta">' +
      '<div><div class="mkt-cta-title">Générer un lien Marketplace Facebook</div>' +
      '<div class="mkt-cta-sub">Cherchez par modèle ou VIN, générez et copiez le lien en 2 clics.</div></div>' +
      '<a href="' + mktUrl + '" class="btn-accent" target="_blank">Ouvrir le générateur &#8594;</a>' +
    '</div>' +
    '<div style="margin:20px 0 14px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;">' +
      '<div class="section-header" style="margin:0">Annonces actives <span class="badge" id="mkt-count">' + _mktItems.length + '</span></div>' +
      '<input id="mkt-search" type="text" placeholder="Chercher par stock, VIN ou modèle..."' +
        ' oninput="filterMkt(this.value)"' +
        ' style="flex:1;min-width:220px;max-width:360px;background:#1a1d27;border:1px solid #2d3748;' +
        'border-radius:8px;color:#e2e8f0;font-family:inherit;font-size:13px;padding:8px 14px;outline:none;">' +
    '</div>' +
    '<div class="table-wrap"><table>' +
      '<thead><tr><th>Stock #</th><th>VIN</th><th>Titre</th><th>Prix</th><th>Posté le</th></tr></thead>' +
      '<tbody id="mkt-tbody">' + _mktRows(_mktItems) + '</tbody>' +
    '</table></div>';

  const inp = document.getElementById('mkt-search');
  inp.addEventListener('focus', () => inp.style.borderColor = '#3b82f6');
  inp.addEventListener('blur',  () => inp.style.borderColor = '#2d3748');
}

function _mktRows(items) {
  if (!items.length) return '<tr><td colspan="5" style="text-align:center;padding:32px;color:#64748b">Aucun résultat.</td></tr>';
  return items.map(i =>
    '<tr>' +
      '<td class="mono">' + esc(i.vehicle_id || '–') + '</td>' +
      '<td class="mono">' + esc(i.vin) + '</td>' +
      '<td class="trunc" title="' + esc(i.title) + '">' + esc(i.title) + '</td>' +
      '<td class="nowrap">' + fmt(i.price) + '</td>' +
      '<td class="nowrap">' + dt(i.marketplace_posted_at) + '</td>' +
    '</tr>'
  ).join('');
}

function filterMkt(q) {
  const lower = q.toLowerCase().trim();
  const filtered = lower
    ? _mktItems.filter(i =>
        (i.title      || '').toLowerCase().includes(lower) ||
        (i.vin        || '').toLowerCase().includes(lower) ||
        String(i.vehicle_id || '').toLowerCase().includes(lower)
      )
    : _mktItems;
  document.getElementById('mkt-tbody').innerHTML = _mktRows(filtered);
  document.getElementById('mkt-count').textContent = filtered.length;
}

function renderPartners(d, pane) {
  const last = d.last_scrape ? dt(d.last_scrape) : 'inconnue';
  const cards = (d.partners||[]).map(p =>
    '<div class="partner-card">' +
      '<div class="partner-name">' + esc(p.dealer) + '</div>' +
      '<div class="partner-count">' + p.count + '</div>' +
      '<div class="partner-unit">véhicules</div>' +
    '</div>'
  ).join('');
  pane.innerHTML =
    '<div class="scrape-info">Dernière mise à jour du scraper : <strong>' + last + '</strong></div>' +
    '<div class="partner-grid">' + cards + '</div>';
}

function renderBugs(d, pane) {
  if (!d.bugs || !d.bugs.length) { pane.innerHTML = '<div class="empty">Aucun bug signalé.</div>'; return; }
  let rows = d.bugs.map(b =>
    '<tr>' +
      '<td class="mono">' + esc(b.user_id) + '</td>' +
      '<td class="msg">' + esc(b.question) + '</td>' +
      '<td>' + esc(b.intent) + '</td>' +
      '<td class="nowrap">' + dt(b.created_at) + '</td>' +
    '</tr>'
  ).join('');
  pane.innerHTML =
    '<div class="section-header">Bugs signalés <span class="badge">' + d.total + '</span></div>' +
    '<div class="table-wrap"><table>' +
      '<thead><tr><th>Utilisateur</th><th>Question</th><th>Intent</th><th>Date</th></tr></thead>' +
      '<tbody>' + rows + '</tbody>' +
    '</table></div>';
}
</script>
</body>
</html>"""
