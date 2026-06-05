// ===========================================================================
//  Admin – Projekte anlegen/aktualisieren (Matterport-ZIP oder Rhino-.3dm)
//  Hinweis: Das Passwort-Gate ist clientseitig und NICHT echt geheim.
// ===========================================================================
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const URL = window.SUPABASE_URL, KEY = window.SUPABASE_ANON_KEY;
const sb = createClient(URL, KEY, { auth: { persistSession: false } });
const ADMIN_PW = 'Berl1nus';

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
//  Login-Gate
// ---------------------------------------------------------------------------
function showPanel() { $('login').classList.add('hidden'); $('panel').classList.remove('hidden'); renderList(); }
function tryLogin() {
  if ($('pw').value === ADMIN_PW) { sessionStorage.setItem('admin_ok', '1'); showPanel(); }
  else { $('login-err').textContent = 'Falsches Passwort.'; }
}
$('login-btn').addEventListener('click', tryLogin);
$('pw').addEventListener('keydown', (e) => { if (e.key === 'Enter') tryLogin(); });
$('logout').addEventListener('click', () => { sessionStorage.removeItem('admin_ok'); location.reload(); });
if (sessionStorage.getItem('admin_ok') === '1') showPanel();
else setTimeout(() => $('pw').focus(), 100);

// ---------------------------------------------------------------------------
//  Datei-Auswahl
// ---------------------------------------------------------------------------
let chosenFile = null;
let editing = null;            // Projekt das aktualisiert wird

const drop = $('drop'), fileInput = $('file');
drop.addEventListener('click', () => fileInput.click());
drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', (e) => {
  e.preventDefault(); drop.classList.remove('over');
  if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files[0]) setFile(fileInput.files[0]); });

function typeOf(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  return ext === '3dm' ? 'rhino' : ext === 'zip' ? 'matterport' : null;
}
function setFile(file) {
  if (!typeOf(file)) { alert('Bitte eine .zip (Matterport) oder .3dm (Rhino) Datei wählen.'); return; }
  chosenFile = file;
  $('fname').textContent = `${file.name} · ${(file.size / 1048576).toFixed(1)} MB · ${typeOf(file) === 'rhino' ? 'Rhino' : 'Matterport'}`;
  $('upload-btn').disabled = false;
}

// ---------------------------------------------------------------------------
//  Rhino: Layer "2D_Scan" erkennen
// ---------------------------------------------------------------------------
let _rhino;
async function rhinoModule() {
  if (!_rhino) { const m = await import('https://cdn.jsdelivr.net/npm/rhino3dm@8.4.0/rhino3dm.module.js'); _rhino = await m.default(); }
  return _rhino;
}
async function detect2DScan(file) {
  try {
    const rhino = await rhinoModule();
    const doc = rhino.File3dm.fromByteArray(new Uint8Array(await file.arrayBuffer()));
    if (!doc) return false;
    const layers = doc.layers(); let found = false;
    for (let i = 0; i < layers.count(); i++) {
      const l = layers.get(i);
      if ((l.name || '').trim().toLowerCase() === '2d_scan') found = true;
      l.delete && l.delete();
    }
    doc.delete && doc.delete();
    return found;
  } catch (e) { console.warn('[admin] Rhino-Layer-Check fehlgeschlagen', e); return false; }
}

// ---------------------------------------------------------------------------
//  Upload / Anlegen / Aktualisieren
// ---------------------------------------------------------------------------
function setStatus(t, ok) { const s = $('status'); s.textContent = t; s.style.color = ok ? 'var(--green)' : 'var(--label2)'; }

$('upload-btn').addEventListener('click', async () => {
  const name = $('pname').value.trim();
  if (!name) { alert('Bitte Projektnamen eingeben.'); return; }
  if (!chosenFile) { alert('Bitte Datei wählen.'); return; }
  const file = chosenFile, type = typeOf(file);
  $('upload-btn').disabled = true;

  let has2d = false;
  if (type === 'rhino') { setStatus('Prüfe Rhino-Layer …'); has2d = await detect2DScan(file); }

  const id = editing ? editing.id : crypto.randomUUID();
  const ext = file.name.split('.').pop().toLowerCase();
  const path = `projects/${id}/model.${ext}`;

  setStatus(`Lade hoch (${(file.size / 1048576).toFixed(0)} MB) … das kann dauern.`);
  const { error: upErr } = await sb.storage.from('models').upload(path, file, { upsert: true, contentType: file.type || 'application/octet-stream' });
  if (upErr) { setStatus('Upload fehlgeschlagen: ' + upErr.message); $('upload-btn').disabled = false; return; }

  if (editing) {
    const { error } = await sb.from('projects').update({
      type, file_path: path, file_name: file.name, has_2d_scan: has2d, version: (editing.version || 1) + 1,
    }).eq('id', id);
    if (error) { setStatus('Fehler: ' + error.message); $('upload-btn').disabled = false; return; }
    setStatus('Projekt aktualisiert ✓ – Annotationen bleiben erhalten.', true);
  } else {
    const { error } = await sb.from('projects').insert({ id, name, type, file_path: path, file_name: file.name, has_2d_scan: has2d });
    if (error) { setStatus('Fehler: ' + error.message); $('upload-btn').disabled = false; return; }
    setStatus('Projekt angelegt ✓', true);
  }
  resetForm(); renderList();
});

$('cancel-edit').addEventListener('click', resetForm);
function resetForm() {
  editing = null; chosenFile = null; fileInput.value = '';
  $('pname').value = ''; $('fname').textContent = ''; $('upload-btn').disabled = true;
  $('pname').disabled = false;
  $('form-title').textContent = 'Neues Projekt';
  $('upload-btn').textContent = 'Hochladen & anlegen';
  $('cancel-edit').classList.add('hidden');
}
function startEdit(p) {
  editing = p; chosenFile = null; fileInput.value = '';
  $('pname').value = p.name; $('pname').disabled = true;
  $('fname').textContent = 'Neue Datei wählen, um zu überschreiben…';
  $('upload-btn').disabled = true;
  $('form-title').textContent = `„${p.name}" aktualisieren (Annotationen bleiben)`;
  $('upload-btn').textContent = 'Neue Version hochladen';
  $('cancel-edit').classList.remove('hidden');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ---------------------------------------------------------------------------
//  Liste
// ---------------------------------------------------------------------------
async function renderList() {
  const list = $('list');
  const { data, error } = await sb.from('projects').select('*').order('created_at', { ascending: false });
  if (error) { list.innerHTML = `<div class="err">${error.message}</div>`; return; }
  if (!data.length) { list.innerHTML = `<div class="sub">Noch keine Projekte. Lade oben das erste hoch.</div>`; return; }
  list.innerHTML = '';
  for (const p of data) {
    const el = document.createElement('div'); el.className = 'proj';
    const link = `${location.origin}${location.pathname.replace(/admin\.html$/, 'index.html')}?p=${p.id}`;
    el.innerHTML = `
      <div class="ic">${p.type === 'rhino' ? '◳' : '⬢'}</div>
      <div class="meta">
        <div class="nm">${escapeHtml(p.name)}${p.has_2d_scan ? '<span class="tag">2D_Scan</span>' : ''}</div>
        <div class="det">${p.type === 'rhino' ? 'Rhino' : 'Matterport'} · v${p.version} · ${escapeHtml(p.file_name || '')}</div>
        <div class="det"><a href="${link}" target="_blank">${link}</a></div>
      </div>
      <button class="btn sec" data-edit>Update</button>
      <button class="btn danger" data-del>Löschen</button>`;
    el.querySelector('[data-edit]').addEventListener('click', () => startEdit(p));
    el.querySelector('[data-del]').addEventListener('click', () => del(p));
    list.appendChild(el);
  }
}
async function del(p) {
  if (!confirm(`Projekt „${p.name}" inkl. Datei und allen Annotationen löschen?`)) return;
  if (p.file_path) await sb.storage.from('models').remove([p.file_path]);
  for (const t of ['threads', 'comments', 'measurements', 'bookmarks', 'chat_messages'])
    await sb.from(t).delete().eq('project_id', p.id);
  await sb.from('projects').delete().eq('id', p.id);
  renderList();
}
function escapeHtml(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
