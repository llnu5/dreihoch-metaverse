# -*- coding: utf-8 -*-
# ===========================================================================
#  Dreihoch Metaverse -- Installer  (run once)
#  Installs the Publisher into Rhino: copies the scripts into Rhino's scripts
#  folder and registers the commands  Publish  and  PublishUpload.
#  Works in Rhino 6, 7 and 8.   Run:  _RunPythonScript  ->  install.py
# ===========================================================================
import Rhino, System, os, shutil
import rhinoscriptsyntax as rs

FILES = ['rhino_publish.py', 'pr85_upload.py']

def scripts_folder():
    appdata = System.Environment.GetFolderPath(System.Environment.SpecialFolder.ApplicationData)
    ver = '%d.0' % Rhino.RhinoApp.ExeVersion
    p = os.path.join(appdata, 'McNeel', 'Rhinoceros', ver, 'scripts')
    try:
        if not os.path.isdir(p): os.makedirs(p)
    except: pass
    return p

RUI_GUIDS = {'file':'d3a10000-0000-4000-8000-000000000001','tbg':'d3a10000-0000-4000-8000-000000000002',
             'tbgi':'d3a10000-0000-4000-8000-000000000003','tb':'d3a10000-0000-4000-8000-000000000004',
             'i1':'d3a10000-0000-4000-8000-000000000005','i2':'d3a10000-0000-4000-8000-000000000006',
             'm1':'d3a10000-0000-4000-8000-000000000007','m2':'d3a10000-0000-4000-8000-000000000008'}

def install_toolbar(dest):
    """Writes a .rui with a 'Dreihoch Metaverse' toolbar (Publisher / 1-Click Update)
    and registers it. It becomes visible after the next Rhino restart."""
    rui = '''<?xml version="1.0" encoding="utf-8"?>
<RhinoUI major_ver="3" minor_ver="0" guid="%(file)s" localize="False" default_language_id="1033" dpi_scale="100">
<extend_rhino_menus /><menus />
<tool_bar_groups>
<tool_bar_group guid="%(tbg)s" dock_bar_guid32="00000000-0000-0000-0000-000000000000" dock_bar_guid64="00000000-0000-0000-0000-000000000000" active_tool_bar_group="%(tbgi)s" single_file="False" hide_single_tab="True" point_floating="400,300">
<text><locale_1033>Dreihoch Metaverse</locale_1033></text>
<tool_bar_group_item guid="%(tbgi)s" major_version="1" minor_version="1">
<text><locale_1033>Dreihoch Metaverse</locale_1033></text>
<tool_bar_id>%(tb)s</tool_bar_id>
<dock_bar_info dpi_scale="100" dock_bar="False" docking="True" horz="True" visible="True" floating="True" mru_float_style="4096" bar_id="59460" mru_width="320" point_pos="-2,-2" float_point="400,300" rect_mru_dock_pos="0,0,0,0" dock_location_u="59419" dock_location="top" float_size="320,64" />
</tool_bar_group_item>
</tool_bar_group>
</tool_bar_groups>
<tool_bars>
<tool_bar guid="%(tb)s" bitmap_id="00000000-0000-0000-0000-000000000000">
<text><locale_1033>Dreihoch Metaverse</locale_1033></text>
<tool_bar_item guid="%(i1)s" button_display_mode="control_and_text" display_style_from_parent="False">
<text><locale_1033>Publisher</locale_1033></text><left_macro_id>%(m1)s</left_macro_id>
</tool_bar_item>
<tool_bar_item guid="%(i2)s" button_display_mode="control_and_text" display_style_from_parent="False">
<text><locale_1033>1-Click Update</locale_1033></text><left_macro_id>%(m2)s</left_macro_id>
</tool_bar_item>
</tool_bar>
</tool_bars>
<macros>
<macro_item guid="%(m1)s"><text><locale_1033>Publisher</locale_1033></text><tooltip><locale_1033>Open the Dreihoch Publisher panel</locale_1033></tooltip><button_text><locale_1033>Publisher</locale_1033></button_text><script>! _Publish</script></macro_item>
<macro_item guid="%(m2)s"><text><locale_1033>1-Click Update</locale_1033></text><tooltip><locale_1033>1-click update of the linked project</locale_1033></tooltip><button_text><locale_1033>1-Click Update</locale_1033></button_text><script>! _PublishUpload</script></macro_item>
</macros>
<bitmaps><small_bitmap item_width="16" item_height="16"><bitmap_items /></small_bitmap><normal_bitmap item_width="24" item_height="24"><bitmap_items /></normal_bitmap><large_bitmap item_width="32" item_height="32"><bitmap_items /></large_bitmap></bitmaps>
<scripts />
</RhinoUI>''' % RUI_GUIDS
    try:
        path = os.path.join(dest, 'Dreihoch_Metaverse.rui')
        fh = open(path, 'w'); fh.write(rui); fh.close()
        tf = Rhino.RhinoApp.ToolbarFiles
        ex = tf.FindByName('Dreihoch_Metaverse', True)
        if ex:
            try: ex.Close(False)
            except: pass
        f = tf.Open(path)
        try:
            if f: f.Save()
        except: pass
        return f is not None
    except Exception as e:
        Rhino.RhinoApp.WriteLine('[install] toolbar failed: %s' % e); return False

def main():
    try: here = os.path.dirname(__file__)
    except: here = None
    if not here or not os.path.exists(os.path.join(here, 'rhino_publish.py')):
        rs.MessageBox('Could not locate the script files.\nPlease keep install.py next to rhino_publish.py and pr85_upload.py, then run it again.', 0, 'Dreihoch Installer'); return

    dest = scripts_folder()
    copied = []
    for f in FILES:
        src = os.path.join(here, f)
        if os.path.exists(src):
            try: shutil.copy2(src, os.path.join(dest, f)); copied.append(f)
            except Exception as e: Rhino.RhinoApp.WriteLine('[install] copy %s failed: %s' % (f, e))

    pub = os.path.join(dest, 'rhino_publish.py')
    upl = os.path.join(dest, 'pr85_upload.py')
    al = Rhino.ApplicationSettings.CommandAliasList
    def set_alias(name, macro):
        try:
            if al.IsAlias(name): al.SetMacro(name, macro)
            else: al.Add(name, macro)
            return True
        except Exception as e:
            Rhino.RhinoApp.WriteLine('[install] alias %s failed: %s' % (name, e)); return False
    set_alias('Publish', '_-RunPythonScript "%s"' % pub)
    set_alias('PublishUpload', '_-RunPythonScript "%s"' % upl)
    tb_ok = install_toolbar(dest)

    Rhino.RhinoApp.WriteLine('[install] copied %d files to %s' % (len(copied), dest))
    msg = ('Installed!\n\n'
           'Commands available now (just type them):\n'
           '   Publish          - open the Publisher panel\n'
           '   PublishUpload    - 1-click update of the linked file\n\n'
           + ('A toolbar "Dreihoch Metaverse" with buttons was added.\n'
              'RESTART RHINO once and the toolbar appears (Publisher / 1-Click Update).'
              if tb_ok else 'Toolbar could not be created - use the typed commands above.'))
    rs.MessageBox(msg, 0, 'Dreihoch Metaverse - installed')

main()
