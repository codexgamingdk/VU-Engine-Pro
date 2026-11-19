"""Pure key-image rendering. Coordinates are in a square 128-unit viewBox."""
import base64
import math
import re
from collections import namedtuple
from functools import lru_cache

THEMES = {"personal": "#4298FF", "stream": "#A578F4", "master": "#FF9F43", "neutral": "#94A3B8"}
RED = "#FF606E"
INK = "#F5F8FC"
# Coordinates are centered on the key's icon origin. The speaker uses a
# six-vertex cone, with a separate right-hand area for the operation mark.
CONE = '<polygon points="-18,-4 -12,-4 -5,-11 -5,11 -12,4 -18,4"/>'
def line(x1, y1, x2, y2):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>'

MINUS = line(2, 0, 17, 0)
PLUS = MINUS + line(9.5, -7.5, 9.5, 7.5)
ICONS = {
    "volume_up": PLUS, "volume_down": MINUS,
    "mute_toggle": CONE + '<path d="M2 -5 Q8 0 2 5 M8 -10 Q20 0 8 10"/>',
    "muted": CONE + line(3,-6,15,6) + line(3,6,15,-6),
    "none": "".join(line(x,-h,x,h) for x,h in zip((-12,-6,0,6,12),(4,8,12,7,3))),
    "set_volume": line(-7,-12,-7,12) + line(7,-12,7,12) + line(-11,-4,-3,-4) + line(3,5,11,5),
    "reset_volume": '<path d="M-10 -5 A11 11 0 1 1 -8 8"/><polyline points="-11,-12 -11,-4 -3,-4"/>',
}

Appearance = namedtuple("Appearance", "accent layout style percentage peak indicator icon vu clean",
                        defaults=(THEMES["personal"], "balanced", "segmented", True, True, True, True, True, False))


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def options(settings):
    node = settings.get("node_name", "")
    default = "stream" if node.endswith("-stream") else "personal" if node.endswith("-personal") else "neutral"
    theme = settings.get("theme", default)
    color = settings.get("custom_color", "")
    accent = color.upper() if theme == "custom" and isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color) else THEMES.get(theme, THEMES[default])
    layout = settings.get("layout", "balanced")
    return Appearance(accent, layout if layout in ("balanced", "meter_focus", "minimal") else "balanced",
                      "continuous" if settings.get("meter_style") == "continuous" else "segmented",
                      *(settings.get(key, True) is not False for key in
                        ("show_percentage", "show_peak", "show_status", "show_icon", "show_vu")), "show_vu" in settings)


def monitor_display_state(props):
    """Reuse the registry's existing SPA Props sample, without another query."""
    for param in props:
        channels = param.get("channelVolumes")
        if channels and all(isinstance(x, (int, float)) and math.isfinite(x) and x >= 0 for x in channels):
            return {"available": True, "muted": bool(param.get("mute")), "volume": max(channels) ** (1/3)}
    return None


def render_svg(label, status, position, peak, control_state=None, action="none", appearance=Appearance()):
    state = control_state or {}
    offline = status != "live" or state.get("available") is False
    muted = bool(state.get("muted"))
    footer = "OFFLINE" if offline else "MUTED" if muted else ""
    if not footer and appearance.percentage and state.get("volume") is not None:
        footer = f'{round(100 * state["volume"])}%'
    quiet = offline or muted or not appearance.vu
    return _frame(label or "Audio", action, appearance, footer,
                  0 if quiet else position, 0 if quiet or not appearance.peak else peak)


def label_lines(label):
    # Keep long names at a readable size by using the two-line title area.
    clean = "".join(c for c in label[:24] if c.isprintable()).strip() or "Audio"
    if len(clean) <= 11:
        return [clean]
    cuts = [i for i,c in enumerate(clean) if c.isspace() and 3 <= i <= len(clean)-3]
    cut = min(cuts, key=lambda i: abs(len(clean)/2-i)) if cuts else (len(clean)+1)//2
    return [clean[:cut].strip(),clean[cut:].strip()]


def title(label, baseline):
    lines = label_lines(label)
    parts = []
    for i, line in enumerate(lines):
        # Approximate bold sans glyph advances conservatively, including wide glyphs.
        width = sum(1.12 if not c.isascii() or c in "MW@%" else
                    .81 if c.isupper() else .68 for c in line) or 1
        size = min(23 if len(lines)==1 else 14, 109/width)
        y = baseline if len(lines)==1 else baseline - 10 + i*14
        parts.append(f'<text x="64" y="{y}" font-size="{size:.1f}">{escape(line)}</text>')
    return ''.join(parts)


@lru_cache(maxsize=256)
def bar(style, y, height, level):
    # Fixed scale: yellow and red appear only when the signal reaches those zones.
    count = 14
    sections = []
    if style == "segmented":
        lit = round(level * count)
        for i in range(count):
            color = "#303A49" if i >= lit else "#35D88A" if i < 10 else "#FFCF58" if i < 13 else RED
            sections.append(f'<rect x="{7+i*8.2:.1f}" y="{y}" width="6.7" height="{height}" rx="1.6" fill="{color}"/>')
    else:
        sections.append(f'<rect x="7" y="{y}" width="114" height="{height}" rx="3" fill="#303A49"/>')
        for start,end,color in [(0,10/14,"#35D88A"),(10/14,13/14,"#FFCF58"),(13/14,1,RED)]:
            width = (min(level,end)-start)*114
            if width>0:
                sections.append(f'<rect x="{7+114*start:.1f}" y="{y}" width="{width:.1f}" height="{height}" fill="{color}"/>')
    return ''.join(sections)


@lru_cache(maxsize=128)
def _frame(label, action, opt, footer, level, peak):
    muted, offline = footer == "MUTED", footer == "OFFLINE"
    accent = THEMES["neutral"] if offline else RED if muted else opt.accent
    minimal = opt.layout == "minimal"
    icon = opt.icon and not minimal
    focus = opt.layout == "meter_focus"
    y, height = (59,32) if focus else (73,20)
    if not icon:
        y, height = (55,36) if focus else (56,28)
    if not footer:
        y += 9
    body = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="144" height="144" viewBox="0 0 128 128">',
        f'<rect x="2" y="2" width="124" height="124" rx="14" fill="#191E27" stroke="{accent}" stroke-width="2.5"/>',
        f'<rect x="21" y="7" width="86" height="3" rx="1.5" fill="{accent}"/>',
        f'<g font-family="DejaVu Sans,sans-serif" font-weight="bold" text-anchor="middle" fill="{INK}">',
        title(label, 34 if icon else 39)]
    clean = opt.clean and not (opt.vu and opt.percentage)
    status = muted or offline
    if clean:
        y, height = (88, 29) if focus else (94, 23)
        if not icon:
            y, height = 65, 48
        if status and opt.vu and not icon:
            y, height = 86, 30
        if not opt.vu and not opt.percentage and not status and not icon:
            body[-1] = title(label, 70)
    if icon:
        path = ICONS["muted"] if muted else ICONS.get(action, ICONS["none"])
        icon_y, scale = (48, .60) if focus else (54, .96)
        if clean:
            icon_y, scale = (57, 1.22) if status and opt.vu else (62, 1.52)
            if not opt.vu and not opt.percentage and not status:
                icon_y, scale = 77, 1.85
            if action in ("volume_up", "volume_down") and not muted:
                path = CONE + path
        body.append(f'<g transform="translate(64 {icon_y}) scale({scale})" fill="none" stroke="{RED if muted else INK}" stroke-width="3.7" stroke-linecap="round" stroke-linejoin="round">{path}</g>')
    if opt.indicator and not minimal:
        light = accent if muted or offline else "#35D88A"
        body.append(f'<circle cx="115" cy="9" r="2.4" fill="{light}"/>')
    if opt.vu:
        body.append(bar(opt.style, y, height, level))
    if peak > 0:
        x = 7+113*peak
        body.append(f'<path d="M{x:.1f} {y-1}v{height+2}" stroke="#10151D" stroke-width="4"/><path d="M{x:.1f} {y-1}v{height+2}" stroke="white" stroke-width="2"/>')
    if clean and opt.vu and status and not opt.indicator:
        footer = ""
    if footer:
        baseline = 86 if clean and opt.vu else 115 if clean else 119
        size = 17 if clean and opt.vu else min(39, 142 / len(footer)) if clean else 21 if status else 26
        body.append(f'<text x="64" y="{baseline}" font-size="{size}" fill="{accent if muted or offline else INK}">{footer}</text>')
    body.append('</g></svg>')
    return 'data:image/svg+xml;base64,' + base64.b64encode(''.join(body).encode()).decode('ascii')
