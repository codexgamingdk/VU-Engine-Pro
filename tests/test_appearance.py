import base64
import itertools
import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'plugin/org.codex.vuengine.sdPlugin'))
import appearance as ui


def svg(*args):
    return ET.fromstring(base64.b64decode(ui.render_svg(*args).split(",")[1], validate=True))


class VisualTests(unittest.TestCase):
    def test_all_layouts_themes_actions_styles_and_states(self):
        actions = set(ui.ICONS) - {"muted"}
        for theme, layout, action, style in itertools.product(
                [*ui.THEMES, "custom"], ["balanced", "meter_focus", "minimal"],
                actions, ["segmented", "continuous"]):
            opt = ui.options(dict(theme=theme, layout=layout, meter_style=style, custom_color="#55bbaa"))
            for status, muted, level, footer in (("live",False,.81,"85%"), ("live",False,0,"85%"),
                                                  ("live",True,.81,"MUTED"), ("offline",False,.81,"OFFLINE")):
                tree = svg("A<& WW WWWW LONG SOURCE",status,level,level,
                           dict(available=True,muted=muted,volume=.85),action,opt)
                texts = list(tree.itertext())
                self.assertEqual(texts[-1],footer)
                self.assertEqual(''.join(texts[:-1]).replace(' ',''),'A<&WWWWWWLONGSOURCE')
                self.assertNotIn('dB',''.join(texts))
                fills = {e.get("fill") for e in tree.iter("{http://www.w3.org/2000/svg}rect")}
                self.assertEqual("#35D88A" in fills,status=="live" and not muted and level>0)
                expected = ui.RED if muted else ui.THEMES["neutral"] if status=="offline" else opt.accent
                self.assertEqual(tree[0].get("stroke"),expected)

    def test_options_cache_and_visibility(self):
        opt = ui.options(dict(node_name="pwctl.source.psou-example-stream"))
        self.assertEqual(opt.accent,ui.THEMES["stream"])
        hidden = opt._replace(percentage=False,peak=False,indicator=False,icon=False)
        ui._frame.cache_clear()
        for peak in (.6,.9):
            tree=svg("AUX","live",.4,peak,{"available":True,"volume":.75},"volume_up",hidden)
            self.assertEqual(list(tree.itertext()),["AUX"])
            self.assertFalse(tree.findall(".//{*}path") or tree.findall(".//{*}circle"))
        self.assertEqual(ui._frame.cache_info().hits,1)
        self.assertEqual(ui.options({"theme":"custom","custom_color":"bad"}).accent,ui.THEMES["neutral"])

    def test_meter_only_gain_and_mute(self):
        state = ui.monitor_display_state([{"mute":False,"channelVolumes":[.125,.125]}])
        self.assertIn("50%", list(svg("Music","live",0,0,state).itertext()))
        state["muted"]=True
        self.assertIn("MUTED", list(svg("Music","live",1,1,state).itertext()))
        self.assertIsNone(ui.monitor_display_state([]))
