// ===========================================================================
//  Supabase-Zugangsdaten
//  Diese Werte sind ÖFFENTLICH und durch Row-Level-Security geschützt –
//  sie dürfen im Quelltext stehen.
//  Eintragen aus: Supabase -> Project Settings -> API
//    • Project URL    -> SUPABASE_URL
//    • anon public Key -> SUPABASE_ANON_KEY
// ===========================================================================
window.SUPABASE_URL = 'https://jjeoxzbfsnrnwpooabfw.supabase.co';
window.SUPABASE_ANON_KEY = 'sb_publishable_l4hAdP8VzaJ23vAPnv3BgA_52LkRXta';

// Aktuelles Projekt aus der URL (?p=…). NULL = Standard-/Prinzenstrasse-Projekt.
window.PROJECT_ID = new URLSearchParams(location.search).get('p') || null;
// Basis-URL fuer oeffentliche Storage-Dateien
window.STORAGE_BASE = window.SUPABASE_URL + '/storage/v1/object/public/models/';
