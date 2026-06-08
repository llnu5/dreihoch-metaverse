# -*- coding: utf-8 -*-
# ===========================================================================
#  Prinzenstrasse-Rundgang -- Rhino-6 Publish-Skript (IronPython 2.7)
#  Exportiert das aktive Rhino-Modell direkt nach GLB (mit Texturen + Layer-
#  Metadaten), komprimiert (gzip) und laedt es zu Supabase hoch -- ein Befehl.
#
#  Aufruf in Rhino 6:   _RunPythonScript  ->  diese Datei waehlen
#  (oder als Alias/Toolbar-Button hinterlegen)
#
#  Keine externe DLL, kein Kompilieren -- nutzt nur RhinoCommon + .NET (Windows).
#  v1 -- iterativ; bei Fehlern die Rhino-Befehlszeilen-Meldung zurueckmelden.
# ===========================================================================
import Rhino
import scriptcontext as sc
import rhinoscriptsyntax as rs
import System
import json, uuid, array, struct, os, tempfile

clr_refs = ['System.Drawing', 'System.Net', 'System.IO.Compression', 'System.IO.Compression.FileSystem']
import clr
for r in clr_refs:
    try: clr.AddReference(r)
    except: pass
from System.Drawing import Bitmap, Rectangle, Graphics
from System.Drawing.Imaging import ImageFormat, Encoder, EncoderParameter, EncoderParameters, ImageCodecInfo, PixelFormat
from System.IO import MemoryStream, FileStream, FileMode
from System.IO.Compression import GZipStream, CompressionMode
from System.Net import HttpWebRequest, WebRequestMethods
from System.Text import Encoding

# ---------------------------------------------------------------------------
#  KONFIG  (gleiche oeffentliche Keys wie config.js -- RLS-geschuetzt)
# ---------------------------------------------------------------------------
SUPABASE_URL = 'https://jjeoxzbfsnrnwpooabfw.supabase.co'
SUPABASE_KEY = 'sb_publishable_l4hAdP8VzaJ23vAPnv3BgA_52LkRXta'
STORAGE_BASE = SUPABASE_URL + '/storage/v1/object'
REST_BASE    = SUPABASE_URL + '/rest/v1'
VIEWER_BASE  = 'https://llnu5.github.io/prinzenstrasse-85-rundgang/index.html'
MAX_TEX      = 1024     # Texturkacheln verkleinern (Supabase-Free-Limit 50 MB)
JPEG_QUALITY = 85

def log(msg): print('[publish] ' + msg)

# ---------------------------------------------------------------------------
#  Layer-Logik (identisch zur Web-App)
# ---------------------------------------------------------------------------
import re
def is_scan_layer(name):
    if not name: return False
    n = name.strip().lower()
    return bool(re.search(r'3d[\s_-]?scan', n)) or n == 'scan'
def is_glass_layer(name):
    n = (name or '').lower()
    return ('glas' in n) or (u'gla\xdf' in n)
def is_hide_layer(name):
    return (name or '').strip().lower() == 'hide'

# ---------------------------------------------------------------------------
#  Texturen: Datei -> verkleinertes JPEG (bytes)
# ---------------------------------------------------------------------------
_jpeg_codec = None
def jpeg_codec():
    global _jpeg_codec
    if _jpeg_codec is None:
        for c in ImageCodecInfo.GetImageEncoders():
            if c.FormatID == ImageFormat.Jpeg.Guid: _jpeg_codec = c; break
    return _jpeg_codec

def load_resize_jpeg(path):
    """Bild laden, auf MAX_TEX begrenzen, als JPEG-bytes zurueck. None bei Fehler."""
    try:
        if not path or not os.path.exists(path): return None
        src = Bitmap(path)
        w, h = src.Width, src.Height
        scale = 1.0
        if max(w, h) > MAX_TEX: scale = float(MAX_TEX) / float(max(w, h))
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        dst = Bitmap(nw, nh, PixelFormat.Format24bppRgb)
        g = Graphics.FromImage(dst)
        g.DrawImage(src, Rectangle(0, 0, nw, nh))
        g.Dispose(); src.Dispose()
        ms = MemoryStream()
        eps = EncoderParameters(1)
        eps.Param[0] = EncoderParameter(Encoder.Quality, System.Int64(JPEG_QUALITY))
        dst.Save(ms, jpeg_codec(), eps)
        dst.Dispose()
        b = ms.ToArray(); ms.Dispose()
        return bytes(bytearray(b))
    except Exception as e:
        log('Textur-Fehler %s: %s' % (path, e)); return None

def material_texture_path(obj):
    """Diffuse-Bitmap-Pfad eines Objekts (best effort) oder None."""
    try:
        mat = obj.GetMaterial(True)
    except:
        mat = None
        try:
            mi = obj.Attributes.MaterialIndex
            if mi >= 0: mat = sc.doc.Materials[mi]
        except: pass
    if not mat: return None
    try:
        bt = mat.GetBitmapTexture()
        if bt and bt.FileName: return bt.FileName
    except: pass
    try:
        tx = mat.GetTexture(Rhino.DocObjects.TextureType.Bitmap)
        if tx and tx.FileName: return tx.FileName
    except: pass
    return None

def material_color(obj):
    try:
        mat = obj.GetMaterial(True)
        if mat: c = mat.DiffuseColor; return [c.R/255.0, c.G/255.0, c.B/255.0]
    except: pass
    return [0.8, 0.8, 0.8]

# ---------------------------------------------------------------------------
#  Geometrie sammeln (Bloecke rekursiv aufloesen)
# ---------------------------------------------------------------------------
def layer_name_of(obj):
    try: return sc.doc.Layers[obj.Attributes.LayerIndex].Name
    except: return ''
def layer_visible_of(obj):
    try:
        l = sc.doc.Layers[obj.Attributes.LayerIndex]
        return l.IsVisible
    except: return True

def meshes_of_geometry(geo):
    """Mesh-Liste aus beliebiger Rhino-Geometrie (Mesh direkt, Brep/Extrusion vernetzt)."""
    out = []
    try:
        if isinstance(geo, Rhino.Geometry.Mesh):
            out.append(geo.DuplicateMesh())
        elif isinstance(geo, Rhino.Geometry.Brep):
            ms = Rhino.Geometry.Mesh.CreateFromBrep(geo, Rhino.Geometry.MeshingParameters.Default)
            if ms:
                for m in ms: out.append(m)
        elif isinstance(geo, Rhino.Geometry.Extrusion):
            br = geo.ToBrep(True)
            if br:
                ms = Rhino.Geometry.Mesh.CreateFromBrep(br, Rhino.Geometry.MeshingParameters.Default)
                if ms:
                    for m in ms: out.append(m)
    except Exception as e:
        log('Mesh-Fehler: %s' % e)
    return out

def collect(renderables, tex_cache):
    """Alle Objekte durchgehen, Bloecke aufloesen, Renderables fuellen."""
    doc = sc.doc
    stats = {'meshes': 0, 'scan': 0, 'glass': 0, 'hidden': 0, 'tex': 0, 'blocks': 0}

    def add_object(obj, xform, inherit_layer):
        # Layer/Material des Objekts (eigene Ebene bevorzugt)
        lname = layer_name_of(obj) or inherit_layer or ''
        lvis  = layer_visible_of(obj)
        if isinstance(obj.Geometry, Rhino.Geometry.InstanceReferenceGeometry):
            return  # wird ueber explode_instance behandelt
        glass = is_glass_layer(lname)
        scan  = is_scan_layer(lname)
        # Scan & Glas immer behalten; sonst ausgeblendete/hide-Layer weglassen
        if not glass and not scan and (not lvis or is_hide_layer(lname)):
            stats['hidden'] += 1; return
        meshes = meshes_of_geometry(obj.Geometry)
        if not meshes: return
        # Textur
        tex_key = None
        if not glass:
            tp = material_texture_path(obj)
            if tp:
                base = os.path.basename(tp).lower()
                if base not in tex_cache:
                    jb = load_resize_jpeg(tp)
                    tex_cache[base] = jb   # bytes oder None
                if tex_cache.get(base): tex_key = base
        col = material_color(obj)
        for m in meshes:
            if xform and xform != Rhino.Geometry.Transform.Identity:
                m.Transform(xform)
            r = mesh_to_renderable(m)
            if not r: continue
            r['grp']  = 'scan' if scan else 'cad'
            r['gmat'] = 'glass' if glass else ''
            r['tex']  = tex_key
            r['color'] = col
            renderables.append(r)
            stats['meshes'] += 1
            if scan: stats['scan'] += 1
            if glass: stats['glass'] += 1
            if tex_key: stats['tex'] += 1

    def explode_instance(iobj, xform, inherit_layer):
        stats['blocks'] += 1
        idef = doc.InstanceDefinitions.FindId(iobj.InstanceDefinition.Id) if hasattr(iobj, 'InstanceDefinition') else None
        try:
            xf = iobj.InstanceXform
        except:
            xf = Rhino.Geometry.Transform.Identity
        comb = Rhino.Geometry.Transform.Multiply(xform, xf) if xform else xf
        try:
            members = iobj.InstanceDefinition.GetObjects()
        except:
            members = []
        for mo in members:
            if isinstance(mo.Geometry, Rhino.Geometry.InstanceReferenceGeometry):
                explode_instance(mo, comb, inherit_layer)
            else:
                add_object(mo, comb, inherit_layer)

    for obj in doc.Objects:
        if not obj.IsValid: continue
        geo = obj.Geometry
        if geo is None: continue
        if isinstance(obj, Rhino.DocObjects.InstanceObject):
            # ausgeblendete Instanz ueberspringen
            lname = layer_name_of(obj)
            if (not layer_visible_of(obj) or is_hide_layer(lname)):
                stats['hidden'] += 1; continue
            explode_instance(obj, Rhino.Geometry.Transform.Identity, lname)
        else:
            add_object(obj, Rhino.Geometry.Transform.Identity, None)
    return stats

# ---------------------------------------------------------------------------
#  Rhino-Mesh -> Renderable (Positionen/Normalen/UVs/Indices, Z-up beibehalten)
# ---------------------------------------------------------------------------
def mesh_to_renderable(m):
    try:
        m.Faces.ConvertQuadsToTriangles()
        if m.Normals.Count != m.Vertices.Count:
            m.Normals.ComputeNormals()
        nv = m.Vertices.Count
        if nv == 0 or m.Faces.Count == 0: return None
        pos = array.array('f'); nor = array.array('f'); uv = array.array('f')
        has_uv = (m.TextureCoordinates.Count == nv)
        for i in range(nv):
            v = m.Vertices[i]
            pos.append(float(v.X)); pos.append(float(v.Y)); pos.append(float(v.Z))   # Z-up (Viewer dreht)
            if m.Normals.Count == nv:
                n = m.Normals[i]; nor.append(float(n.X)); nor.append(float(n.Y)); nor.append(float(n.Z))
            else:
                nor.append(0.0); nor.append(0.0); nor.append(1.0)
            if has_uv:
                t = m.TextureCoordinates[i]; uv.append(float(t.X)); uv.append(1.0 - float(t.Y))
            else:
                uv.append(0.0); uv.append(0.0)
        idx = array.array('I')
        for f in range(m.Faces.Count):
            face = m.Faces[f]
            idx.append(face.A); idx.append(face.B); idx.append(face.C)
            if face.IsQuad:
                idx.append(face.A); idx.append(face.C); idx.append(face.D)
        return {'pos': pos, 'nor': nor, 'uv': uv, 'idx': idx, 'has_uv': has_uv, 'nv': nv}
    except Exception as e:
        log('mesh_to_renderable: %s' % e); return None

# ---------------------------------------------------------------------------
#  GLB von Hand bauen
# ---------------------------------------------------------------------------
def _pad4(b, fill):
    while (len(b) % 4) != 0: b.append(fill)

def build_glb(renderables, tex_cache):
    buf = bytearray()
    bufferViews = []; accessors = []; images = []; textures = []; materials = []
    meshes = []; nodes = []

    # --- Bilder/Texturen ---
    tex_index = {}  # basename -> material slot info
    img_index = {}  # basename -> texture index
    for base, jb in tex_cache.items():
        if not jb: continue
        off = len(buf); buf.extend(bytearray(jb)); ln = len(jb); _pad4(buf, 0)
        bufferViews.append({'buffer': 0, 'byteOffset': off, 'byteLength': ln})
        images.append({'bufferView': len(bufferViews)-1, 'mimeType': 'image/jpeg'})
        textures.append({'source': len(images)-1})
        img_index[base] = len(textures)-1

    def add_accessor(arr, comp_type, type_str, count, mn=None, mx=None, target=None):
        raw = arr.tostring() if hasattr(arr, 'tostring') else arr.tobytes()
        off = len(buf); buf.extend(bytearray(raw)); _pad4(buf, 0)
        bv = {'buffer': 0, 'byteOffset': off, 'byteLength': len(raw)}
        if target: bv['target'] = target
        bufferViews.append(bv)
        acc = {'bufferView': len(bufferViews)-1, 'componentType': comp_type, 'count': count, 'type': type_str}
        if mn is not None: acc['min'] = mn; acc['max'] = mx
        accessors.append(acc); return len(accessors)-1

    # Material-Slots (dedupe nach tex/color/glass)
    mat_index = {}
    def get_material(r):
        if r['gmat'] == 'glass':
            key = 'glass'
            if key not in mat_index:
                materials.append({'name':'glass','pbrMetallicRoughness':{'baseColorFactor':[0.75,0.88,0.93,0.26],'metallicFactor':0.0,'roughnessFactor':0.06},'alphaMode':'BLEND','doubleSided':True})
                mat_index[key] = len(materials)-1
            return mat_index[key]
        if r['tex']:
            key = 'tex:' + r['tex']
            if key not in mat_index:
                materials.append({'name':r['tex'],'pbrMetallicRoughness':{'baseColorTexture':{'index':img_index[r['tex']]},'baseColorFactor':[1,1,1,1],'metallicFactor':0.0,'roughnessFactor':0.9},'doubleSided':True})
                mat_index[key] = len(materials)-1
            return mat_index[key]
        c = r['color']; key = 'col:%0.2f_%0.2f_%0.2f' % (c[0],c[1],c[2])
        if key not in mat_index:
            materials.append({'name':'col','pbrMetallicRoughness':{'baseColorFactor':[c[0],c[1],c[2],1],'metallicFactor':0.0,'roughnessFactor':0.9},'doubleSided':True})
            mat_index[key] = len(materials)-1
        return mat_index[key]

    COMP_FLOAT=5126; COMP_UINT=5125; ARR_BUF=34962; ELEM_BUF=34963
    node_indices = []
    for r in renderables:
        nv = r['nv']
        # min/max der Positionen
        p = r['pos']; mnx=mny=mnz=1e30; mxx=mxy=mxz=-1e30
        for i in range(0, len(p), 3):
            x,y,z = p[i],p[i+1],p[i+2]
            if x<mnx:mnx=x
            if y<mny:mny=y
            if z<mnz:mnz=z
            if x>mxx:mxx=x
            if y>mxy:mxy=y
            if z>mxz:mxz=z
        a_pos = add_accessor(r['pos'], COMP_FLOAT, 'VEC3', nv, [mnx,mny,mnz], [mxx,mxy,mxz], ARR_BUF)
        a_nor = add_accessor(r['nor'], COMP_FLOAT, 'VEC3', nv, target=ARR_BUF)
        attrs = {'POSITION': a_pos, 'NORMAL': a_nor}
        if r['has_uv']:
            a_uv = add_accessor(r['uv'], COMP_FLOAT, 'VEC2', nv, target=ARR_BUF)
            attrs['TEXCOORD_0'] = a_uv
        a_idx = add_accessor(r['idx'], COMP_UINT, 'SCALAR', len(r['idx']), target=ELEM_BUF)
        prim = {'attributes': attrs, 'indices': a_idx, 'material': get_material(r), 'mode': 4}
        meshes.append({'primitives': [prim]})
        nodes.append({'mesh': len(meshes)-1, 'extras': {'grp': r['grp'], 'gmat': r['gmat']}})
        node_indices.append(len(nodes)-1)

    gltf = {
        'asset': {'version': '2.0', 'generator': 'rhino_publish.py'},
        'scene': 0,
        'scenes': [{'nodes': node_indices}],
        'nodes': nodes, 'meshes': meshes, 'materials': materials,
        'accessors': accessors, 'bufferViews': bufferViews,
        'buffers': [{'byteLength': len(buf)}],
    }
    if images: gltf['images'] = images
    if textures: gltf['textures'] = textures

    json_bytes = bytearray(Encoding.UTF8.GetBytes(json.dumps(gltf)))
    _pad4(json_bytes, 0x20)
    _pad4(buf, 0x00)
    total = 12 + 8 + len(json_bytes) + 8 + len(buf)
    out = bytearray()
    out.extend(struct.pack('<III', 0x46546C67, 2, total))          # Header glTF/2/length
    out.extend(struct.pack('<II', len(json_bytes), 0x4E4F534A))     # JSON-Chunk
    out.extend(json_bytes)
    out.extend(struct.pack('<II', len(buf), 0x004E4942))           # BIN-Chunk
    out.extend(buf)
    return bytes(out)

# ---------------------------------------------------------------------------
#  gzip
# ---------------------------------------------------------------------------
def gzip_bytes(data):
    ms = MemoryStream()
    gz = GZipStream(ms, CompressionMode.Compress, True)
    arr = System.Array[System.Byte](bytearray(data))
    gz.Write(arr, 0, arr.Length); gz.Close()
    out = ms.ToArray(); ms.Dispose()
    return bytes(bytearray(out))

# ---------------------------------------------------------------------------
#  HTTP (Supabase REST + Storage)
# ---------------------------------------------------------------------------
def _read_response(req):
    resp = req.GetResponse()
    s = resp.GetResponseStream()
    sr = System.IO.StreamReader(s)
    txt = sr.ReadToEnd(); sr.Close(); resp.Close()
    return txt

def rest_get(path):
    req = HttpWebRequest(System.Uri(REST_BASE + path))
    req.Method = 'GET'
    req.Headers.Add('apikey', SUPABASE_KEY)
    req.Headers.Add('Authorization', 'Bearer ' + SUPABASE_KEY)
    try: return json.loads(_read_response(req))
    except Exception as e: log('REST GET Fehler: %s' % e); return None

def rest_upsert_project(row):
    body = Encoding.UTF8.GetBytes(json.dumps(row))
    req = HttpWebRequest(System.Uri(REST_BASE + '/projects?on_conflict=id'))
    req.Method = 'POST'
    req.Headers.Add('apikey', SUPABASE_KEY)
    req.Headers.Add('Authorization', 'Bearer ' + SUPABASE_KEY)
    req.ContentType = 'application/json'
    req.Headers.Add('Prefer', 'resolution=merge-duplicates,return=minimal')
    req.ContentLength = body.Length
    st = req.GetRequestStream(); st.Write(body, 0, body.Length); st.Close()
    try: _read_response(req); return True
    except Exception as e: log('REST upsert Fehler: %s' % e); return False

def storage_upload(path, data, content_type):
    """POST nach Storage (x-upsert). Gibt Fehlertext oder None zurueck."""
    body = System.Array[System.Byte](bytearray(data))
    req = HttpWebRequest(System.Uri(STORAGE_BASE + '/models/' + path))
    req.Method = 'POST'
    req.Headers.Add('apikey', SUPABASE_KEY)
    req.Headers.Add('Authorization', 'Bearer ' + SUPABASE_KEY)
    req.Headers.Add('x-upsert', 'true')
    req.ContentType = content_type
    req.ContentLength = body.Length
    try:
        st = req.GetRequestStream(); st.Write(body, 0, body.Length); st.Close()
        _read_response(req); return None
    except System.Net.WebException as we:
        try:
            r = we.Response; sr = System.IO.StreamReader(r.GetResponseStream()); txt = sr.ReadToEnd()
            return txt
        except: return str(we)
    except Exception as e:
        return str(e)

# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------
def main():
    name = rs.GetString('Projektname (neu oder vorhanden zum Aktualisieren)')
    if not name: log('Abgebrochen.'); return
    name = name.strip()

    log('Sammle Geometrie & Texturen ...')
    renderables = []; tex_cache = {}
    stats = collect(renderables, tex_cache)
    if not renderables: log('Keine Geometrie gefunden.'); return
    has_scan = stats['scan'] > 0
    log('Meshes %d | Scan %d | Glas %d | Texturen %d | Bloecke %d | versteckt %d' %
        (stats['meshes'], stats['scan'], stats['glass'], stats['tex'], stats['blocks'], stats['hidden']))

    log('Baue GLB ...')
    glb = build_glb(renderables, tex_cache)
    log('GLB %.1f MB' % (len(glb)/1048576.0))
    log('Komprimiere (gzip) ...')
    gz = gzip_bytes(glb)
    mb = len(gz)/1048576.0
    log('Upload-Groesse %.1f MB' % mb)
    if mb > 50:
        log('WARNUNG: > 50 MB -> Supabase-Free lehnt ab. (Pro noetig oder weiter verkleinern.)')

    # Projekt anlegen/finden
    existing = rest_get('/projects?name=eq.' + System.Uri.EscapeDataString(name) + '&select=id,version')
    if existing and len(existing) > 0:
        pid = existing[0]['id']; version = int(existing[0].get('version', 1)) + 1
        log('Aktualisiere vorhandenes Projekt (v%d).' % version)
    else:
        pid = str(uuid.uuid4()); version = 1
        log('Neues Projekt: %s' % pid)

    path = 'projects/%s/model.glb.gz' % pid
    log('Lade hoch ...')
    err = storage_upload(path, gz, 'application/gzip')
    if err:
        log('UPLOAD FEHLGESCHLAGEN (%.1f MB): %s' % (mb, err)); return

    row = {'id': pid, 'name': name, 'type': 'rhino', 'file_path': path,
           'file_name': os.path.basename(sc.doc.Path or 'rhino.3dm'),
           'has_2d_scan': has_scan, 'version': version}
    if not rest_upsert_project(row):
        log('Projektzeile konnte nicht geschrieben werden (Upload liegt aber im Storage).'); return

    url = VIEWER_BASE + '?p=' + pid
    log('FERTIG  ->  ' + url)
    try: rs.MessageBox('Veroeffentlicht!\n\n' + url, 0, 'Publish')
    except: pass

main()
