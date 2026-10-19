// ===========================================================================
//  Supabase-Zugangsdaten (selbst gehostet auf Hetzner / dreihoch-ops)
//  Diese Werte sind ÖFFENTLICH und durch Row-Level-Security geschützt –
//  sie dürfen im Quelltext stehen.
//  Backend: Supabase self-hosted (Docker) hinter Caddy, HTTPS via Let's Encrypt.
// ===========================================================================
window.SUPABASE_URL = 'https://static.63.89.13.49.clients.your-server.de';
window.SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiIsImlzcyI6InN1cGFiYXNlIiwiaWF0IjoxNzkyNDA2NDM4LCJleHAiOjE5NTAwODY0Mzh9.Muyz13I6F-ZRs3Waez3lGAEqtBjM41QZhumgr5A-CSY';

// Current project from the URL (?p=…). NULL = default project.
window.PROJECT_ID = new URLSearchParams(location.search).get('p') || null;
// Base URL for public storage files
window.STORAGE_BASE = window.SUPABASE_URL + '/storage/v1/object/public/models/';
