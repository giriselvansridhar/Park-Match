"""Generated SVG cover art for parking spots that have no photo.

Each spot gets a scene matching its type (garage, basement, beach, driveway, open lot), with colours,
time of day and cars varied by a seed derived from the spot's id, so the art is stable across runs.
"""
import random

from django.core.files.base import ContentFile

W, H = 1200, 750

PALETTES = {
    "day": {"sky": ("#60a5fa", "#dbeafe"), "sun": "#fde68a", "ground": "#3f4a5c", "wall": "#e2e8f0", "trim": "#94a3b8", "glow": 0},
    "dusk": {"sky": ("#312e81", "#fb923c"), "sun": "#fdba74", "ground": "#2a3140", "wall": "#cbd5e1", "trim": "#64748b", "glow": 0.5},
    "night": {"sky": ("#020617", "#1e3a8a"), "sun": "#f8fafc", "ground": "#1e2533", "wall": "#94a3b8", "trim": "#475569", "glow": 1},
}
CAR_COLORS = ["#ef4444", "#f8fafc", "#0ea5e9", "#facc15", "#22c55e", "#a855f7", "#f97316", "#1f2937", "#94a3b8", "#14b8a6"]


def scene_for(spot):
    t = f"{spot.title} {spot.description}".lower()
    if any(k in t for k in ("beach", "marina", "sea")):
        return "beach"
    if "basement" in t:
        return "basement"
    if any(k in t for k in ("garage", "covered", "stilt", "shaded")) or (spot.is_covered and "driveway" not in t):
        return "garage"
    if any(k in t for k in ("driveway", "residential", "home", "gated")):
        return "driveway"
    return "lot"


# ------------------------------------------------------------------ pieces

def car_side(x, y, w, color, facing=1, lights=0.0):
    """Side-view car; (x, y) is the left end of the wheel baseline."""
    h = w * 0.36
    g = f'<g transform="translate({x + (w if facing < 0 else 0)},{y}) scale({facing},1)">'
    g += f'<ellipse cx="{w/2}" cy="4" rx="{w*0.52}" ry="{h*0.1}" fill="#000" opacity=".35"/>'
    g += (f'<path d="M{w*0.02},{-h*0.18} Q0,{-h*0.55} {w*0.12},{-h*0.6} L{w*0.26},{-h*0.64} '
          f'L{w*0.36},{-h*0.98} Q{w*0.4},{-h*1.04} {w*0.48},{-h*1.04} L{w*0.66},{-h*1.04} '
          f'Q{w*0.72},{-h*1.02} {w*0.76},{-h*0.94} L{w*0.86},{-h*0.66} L{w*0.96},{-h*0.6} '
          f'Q{w*1.01},{-h*0.55} {w},{-h*0.18} Z" fill="{color}"/>')
    g += (f'<path d="M{w*0.3},{-h*0.66} L{w*0.39},{-h*0.93} L{w*0.55},{-h*0.93} L{w*0.55},{-h*0.66} Z" fill="#bfdbfe" opacity=".75"/>'
          f'<path d="M{w*0.58},{-h*0.66} L{w*0.58},{-h*0.93} L{w*0.7},{-h*0.93} L{w*0.8},{-h*0.66} Z" fill="#bfdbfe" opacity=".75"/>')
    g += f'<rect x="{w*0.06}" y="{-h*0.42}" width="{w*0.88}" height="{h*0.05}" fill="#000" opacity=".15"/>'
    g += f'<rect x="{w*0.95}" y="{-h*0.5}" width="{w*0.05}" height="{h*0.1}" rx="3" fill="#fef08a"/>'
    g += f'<rect x="0" y="{-h*0.5}" width="{w*0.035}" height="{h*0.1}" rx="3" fill="#ef4444"/>'
    if lights:
        g += f'<path d="M{w},{-h*0.46} L{w*1.6},{-h*0.8} L{w*1.6},{h*0.1} Z" fill="#fef9c3" opacity="{0.18*lights}"/>'
    for cx in (w * 0.22, w * 0.78):
        g += f'<circle cx="{cx}" cy="{-h*0.16}" r="{h*0.2}" fill="#0b0f17"/><circle cx="{cx}" cy="{-h*0.16}" r="{h*0.09}" fill="#9ca3af"/>'
    return g + "</g>"


def car_top(cx, cy, w, h, color, rot=0):
    """Top-down car centred on (cx, cy), pointing up before rotation."""
    g = f'<g transform="translate({cx},{cy}) rotate({rot})">'
    g += f'<rect x="{-w/2+4}" y="{-h/2+6}" width="{w}" height="{h}" rx="{w*0.3}" fill="#000" opacity=".35"/>'
    g += f'<rect x="{-w/2}" y="{-h/2}" width="{w}" height="{h}" rx="{w*0.3}" fill="{color}"/>'
    g += f'<rect x="{-w*0.38}" y="{-h*0.26}" width="{w*0.76}" height="{h*0.2}" rx="{w*0.1}" fill="#1e293b" opacity=".85"/>'
    g += f'<rect x="{-w*0.36}" y="{h*0.16}" width="{w*0.72}" height="{h*0.14}" rx="{w*0.08}" fill="#1e293b" opacity=".8"/>'
    g += f'<rect x="{-w*0.36}" y="{-h*0.05}" width="{w*0.72}" height="{h*0.2}" rx="{w*0.08}" fill="#fff" opacity=".12"/>'
    g += f'<rect x="{-w*0.42}" y="{-h/2+2}" width="{w*0.2}" height="{h*0.04}" rx="2" fill="#fef08a"/><rect x="{w*0.22}" y="{-h/2+2}" width="{w*0.2}" height="{h*0.04}" rx="2" fill="#fef08a"/>'
    return g + "</g>"


def p_sign(x, y, s=1.0):
    return (f'<g transform="translate({x},{y}) scale({s})"><rect x="-4" y="0" width="8" height="150" fill="#64748b"/>'
            f'<rect x="-42" y="-80" width="84" height="84" rx="14" fill="#14b88a" stroke="#fff" stroke-width="5"/>'
            f'<text x="0" y="-18" text-anchor="middle" font-family="Arial, sans-serif" font-weight="900" font-size="62" fill="#fff">P</text></g>')


def palm(x, y, s=1.0):
    g = f'<g transform="translate({x},{y}) scale({s})">'
    g += '<path d="M0,0 Q-14,-120 12,-250" stroke="#3f2d1d" stroke-width="16" fill="none" stroke-linecap="round"/>'
    for a in (-150, -110, -60, -20, 25, 70):
        g += f'<path d="M12,-250 q60,-30 110,20 q-60,-10 -110,-20" fill="#166534" transform="rotate({a} 12 -250)"/>'
    return g + "</g>"


def plant(x, y, s=1.0, color="#15803d"):
    return (f'<g transform="translate({x},{y}) scale({s})"><rect x="-26" y="-30" width="52" height="34" rx="6" fill="#92400e"/>'
            f'<circle cx="-14" cy="-50" r="26" fill="{color}"/><circle cx="14" cy="-56" r="30" fill="{color}"/><circle cx="0" cy="-78" r="24" fill="{color}"/></g>')


def sky(p, rng):
    top, bottom = p["sky"]
    s = (f'<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient></defs>'
         f'<rect width="{W}" height="{H}" fill="url(#sky)"/>')
    if p["glow"] >= 1:
        s += "".join(f'<circle cx="{rng.randint(0, W)}" cy="{rng.randint(0, 300)}" r="{rng.choice([1.5, 2, 2.5])}" fill="#fff" opacity="{rng.uniform(.4, .9):.2f}"/>' for _ in range(60))
    s += f'<circle cx="{rng.randint(150, 1050)}" cy="{rng.randint(90, 170)}" r="{60 if p["glow"] < 1 else 40}" fill="{p["sun"]}" opacity=".9"/>'
    return s


def skyline(p, rng, base):
    s = ""
    x = -20
    while x < W:
        bw, bh = rng.randint(60, 140), rng.randint(90, 260)
        s += f'<rect x="{x}" y="{base-bh}" width="{bw}" height="{bh}" fill="#0f172a" opacity="{.35 + p["glow"]*.3:.2f}"/>'
        if p["glow"]:
            for wy in range(base - bh + 16, base - 10, 26):
                for wx in range(x + 10, x + bw - 14, 22):
                    if rng.random() < 0.35:
                        s += f'<rect x="{wx}" y="{wy}" width="10" height="12" fill="#fde68a" opacity=".8"/>'
        x += bw + rng.randint(4, 20)
    return s


# ------------------------------------------------------------------ scenes

def scene_lot(p, rng):
    s = f'<rect width="{W}" height="{H}" fill="{p["ground"]}"/>'
    s += "".join(f'<circle cx="{rng.randint(0, W)}" cy="{rng.randint(0, H)}" r="{rng.randint(1, 3)}" fill="#fff" opacity=".04"/>' for _ in range(260))
    # two rows of bays with a driving lane between
    bay_w, bay_h = 150, 230
    for row, top in enumerate((40, H - 40 - bay_h)):
        for i in range(9):
            x = -30 + i * bay_w
            s += f'<rect x="{x}" y="{top}" width="6" height="{bay_h}" fill="#f8fafc" opacity=".85"/>'
            if rng.random() < 0.62:
                s += car_top(x + bay_w / 2 + 3, top + bay_h / 2, 96, 190, rng.choice(CAR_COLORS), 0 if row else 180)
        s += f'<rect x="-30" y="{top + (bay_h if row == 0 else 0) - 3}" width="{W+60}" height="6" fill="#f8fafc" opacity=".85"/>'
    lane = H / 2
    s += "".join(f'<rect x="{x}" y="{lane-4}" width="60" height="8" rx="3" fill="#facc15" opacity=".8"/>' for x in range(20, W, 120))
    s += f'<path d="M{W*0.52},{lane-40} l40,40 l-40,40" stroke="#f8fafc" stroke-width="10" fill="none" opacity=".6" stroke-linecap="round"/>'
    s += car_top(W * 0.3, lane, 100, 196, rng.choice(CAR_COLORS), 90)
    # trees along the edge and a big painted P
    for x in (60, 1140):
        s += f'<circle cx="{x}" cy="{lane}" r="70" fill="#166534" opacity=".9"/><circle cx="{x+20}" cy="{lane-20}" r="40" fill="#22c55e" opacity=".5"/>'
    s += f'<rect x="{W*0.72}" y="{lane-58}" width="116" height="116" rx="22" fill="#14b88a" opacity=".92"/>'
    s += f'<text x="{W*0.72+58}" y="{lane+36}" text-anchor="middle" font-family="Arial, sans-serif" font-weight="900" font-size="96" fill="#fff">P</text>'
    if p["glow"]:
        s += f'<rect width="{W}" height="{H}" fill="#020617" opacity="{.35*p["glow"]:.2f}"/>'
    return s


def scene_garage(p, rng):
    s = sky(p, rng) + skyline(p, rng, 430)
    s += f'<rect y="430" width="{W}" height="{H-430}" fill="{p["ground"]}"/>'
    s += f'<rect x="60" y="170" width="{W-120}" height="44" fill="{p["trim"]}"/><rect x="40" y="150" width="{W-80}" height="26" rx="6" fill="{p["wall"]}"/>'
    s += f'<rect x="60" y="214" width="{W-120}" height="460" fill="#0f172a" opacity=".55"/>'
    for i in range(4):
        x = 90 + i * 340
        s += f'<rect x="{x}" y="214" width="34" height="460" fill="{p["wall"]}" opacity=".9"/>'
        s += f'<ellipse cx="{x+180}" cy="232" rx="44" ry="8" fill="#fef9c3"/><path d="M{x+136},236 L{x+80},560 L{x+280},560 L{x+224},236 Z" fill="#fef9c3" opacity=".08"/>'
    for i in range(3):
        if rng.random() < 0.85:
            s += car_side(150 + i * 340, 640, 260, rng.choice(CAR_COLORS), rng.choice([1, -1]))
    s += f'<rect y="674" width="{W}" height="{H-674}" fill="{p["ground"]}"/>'
    s += "".join(f'<rect x="{x}" y="700" width="70" height="8" fill="#f8fafc" opacity=".5"/>' for x in range(20, W, 140))
    s += p_sign(1110, 520, .8)
    return s


def scene_basement(p, rng):
    s = f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#111827"/><stop offset="1" stop-color="#1f2937"/></linearGradient></defs>'
    s += f'<rect width="{W}" height="{H}" fill="url(#bg)"/>'
    s += f'<path d="M0,{H} L{W*0.38},330 L{W*0.62},330 L{W},{H} Z" fill="#374151"/>'
    s += f'<rect y="0" width="{W}" height="120" fill="#0b1220"/>'
    for x in (0.2, 0.5, 0.8):
        s += f'<rect x="{W*x-60}" y="112" width="120" height="14" rx="6" fill="#f8fafc"/><path d="M{W*x-60},126 L{W*x-200},{H} L{W*x+200},{H} L{W*x+60},126 Z" fill="#f8fafc" opacity=".05"/>'
    for i, x in enumerate((140, 1060)):
        s += f'<rect x="{x-45}" y="120" width="90" height="{H-120}" fill="#9ca3af"/>'
        s += "".join(f'<path d="M{x-45},{y} l90,-40 v24 l-90,40 Z" fill="#facc15"/>' for y in range(H - 150, H + 40, 60))
        s += "".join(f'<path d="M{x-45},{y+30} l90,-40 v24 l-90,40 Z" fill="#111827"/>' for y in range(H - 150, H + 40, 60))
    for y in (470, 560, 660):
        s += f'<rect x="{W*0.5-3}" y="{y}" width="6" height="40" fill="#facc15" opacity=".8"/>'
    s += car_side(230, 640, 300, rng.choice(CAR_COLORS), 1, 1)
    s += car_side(680, 600, 240, rng.choice(CAR_COLORS), -1)
    s += (f'<g transform="translate({W/2},180)"><rect x="-110" y="-34" width="220" height="68" rx="10" fill="#14b88a"/>'
          f'<text x="0" y="16" text-anchor="middle" font-family="Arial, sans-serif" font-weight="900" font-size="44" fill="#fff">P ➜</text></g>')
    return s


def scene_beach(p, rng):
    s = sky(p, rng)
    s += f'<rect y="330" width="{W}" height="130" fill="#0e7490"/>'
    s += "".join(f'<path d="M{x},{y} q30,-10 60,0" stroke="#e0f2fe" stroke-width="4" fill="none" opacity=".45"/>' for x, y in ((rng.randint(0, W), rng.randint(350, 440)) for _ in range(18)))
    s += f'<path d="M0,460 Q{W/2},420 {W},460 L{W},540 L0,540 Z" fill="#fcd9a4"/>'
    s += palm(160, 530, .9) + palm(1030, 540, 1.05) + palm(1120, 520, .7)
    s += f'<rect y="540" width="{W}" height="{H-540}" fill="{p["ground"]}"/><rect y="540" width="{W}" height="10" fill="#e2e8f0"/>'
    s += "".join(f'<rect x="{x}" y="{620}" width="80" height="8" fill="#f8fafc" opacity=".6"/>' for x in range(30, W, 160))
    for i in range(3):
        s += car_side(80 + i * 360, 700, 250, rng.choice(CAR_COLORS), 1, p["glow"])
    s += p_sign(1150, 400, .7)
    return s


def scene_driveway(p, rng):
    s = sky(p, rng)
    wall = rng.choice(["#fde68a", "#fecaca", "#bfdbfe", "#bbf7d0", "#e9d5ff", "#fed7aa"])
    s += f'<path d="M180,260 L600,90 L1020,260 Z" fill="#7c2d12"/>'
    s += f'<rect x="220" y="258" width="760" height="330" fill="{wall}"/>'
    for x in (270, 820):
        glow = "#fde68a" if p["glow"] else "#bae6fd"
        s += f'<rect x="{x}" y="310" width="110" height="100" rx="6" fill="{glow}" stroke="#78350f" stroke-width="8"/><rect x="{x+51}" y="310" width="8" height="100" fill="#78350f"/>'
    s += f'<rect x="420" y="330" width="360" height="258" fill="#475569"/>'
    s += "".join(f'<rect x="420" y="{y}" width="360" height="4" fill="#334155"/>' for y in range(350, 588, 26))
    s += f'<rect y="588" width="{W}" height="{H-588}" fill="#6b7280"/><path d="M420,588 L780,588 L900,{H} L300,{H} Z" fill="#9ca3af"/>'
    s += car_side(450, 700, 300, rng.choice(CAR_COLORS), rng.choice([1, -1]))
    s += "".join(f'<rect x="{x}" y="520" width="10" height="120" fill="#1f2937"/>' for x in range(20, 300, 32))
    s += f'<rect x="10" y="520" width="290" height="10" fill="#1f2937"/><rect x="10" y="600" width="290" height="8" fill="#1f2937"/>'
    s += plant(1000, 640, 1.1) + plant(1110, 650, .9, "#16a34a") + plant(180, 660, .8, "#16a34a")
    s += p_sign(1150, 470, .6)
    return s


SCENES = {"lot": scene_lot, "garage": scene_garage, "basement": scene_basement, "beach": scene_beach, "driveway": scene_driveway}


def render_spot_svg(spot):
    rng = random.Random(spot.pk * 7919 + 17)
    kind = scene_for(spot)
    mood = rng.choice(["day", "dusk", "night"] if kind != "basement" else ["night"])
    body = SCENES[kind](PALETTES[mood], rng)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice" '
            f'role="img" aria-label="Illustration of {kind} parking">{body}</svg>')


def ensure_photo(spot, force=False):
    """Give the spot generated cover art if it has no photo (or regenerate art we made before, with force)."""
    generated = bool(spot.photo) and spot.photo.name.endswith(".svg") and "/generated-" in spot.photo.name
    if spot.photo and not (force and generated):
        return False
    if generated:
        spot.photo.delete(save=False)
    spot.photo.save(f"generated-{spot.pk}.svg", ContentFile(render_spot_svg(spot).encode()), save=True)
    return True
