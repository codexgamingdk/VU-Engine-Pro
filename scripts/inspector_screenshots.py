"""Render the real inspector in an ephemeral WebKit view using synthetic devices."""
import json
from pathlib import Path
import sys
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import GLib, Gtk, WebKit2
root = Path(__file__).resolve().parents[1]
bundle = root / "plugin/org.codex.vuengine.sdPlugin"
sys.path.insert(0, str(bundle))
from appearance import options, render_svg

page = (bundle / "propertyInspector/index.html").read_text()
for approved, filename in [(False, "inspector-approval"), (True, "inspector-approved"), (False, "inspector-offline")]:
    target = dict(node_name="example.channel", description="Studio channel", media_class="Audio/Sink", virtual=True, approved=approved)
    settings = dict(node_name=target["node_name"], control_target=target["node_name"], control_action="volume_up", label="STUDIO", theme="personal", show_vu=False)
    image = render_svg("STUDIO", "live", 0, 0, {"volume":0.75}, "volume_up", options(settings))
    script = "settings=%s;nodes=[%s];controlTargets=nodes;render();$('preview').src=%s;" % (json.dumps(settings),json.dumps(target),json.dumps(image))
    if filename.endswith("offline"):
        script += "nodes=[];controlTargets=[];render();"
        script += "$('preview').src="+json.dumps(render_svg("STUDIO","offline",0,0,None,"volume_up",options(settings)))+";"
    html = page.replace("</body>", "<script>"+script+"</script></body>")
    win = Gtk.OffscreenWindow()
    win.set_default_size(530, 1420)
    view = WebKit2.WebView.new_with_context(WebKit2.WebContext.new_ephemeral())
    win.add(view)
    def save(view, result):
        surface = view.get_snapshot_finish(result)
        surface.write_to_png(str(root / "screenshots" / (filename+".png")))
        Gtk.main_quit()
    def loaded(view, event):
        if event == WebKit2.LoadEvent.FINISHED:
            def snap():
                view.get_snapshot(WebKit2.SnapshotRegion.FULL_DOCUMENT, WebKit2.SnapshotOptions.NONE, None, save)
                return False
            GLib.timeout_add(350, snap)
    view.connect("load-changed", loaded)
    win.show_all()
    view.load_html(html, None)
    Gtk.main()
    win.destroy()
