#!/usr/bin/env python3
"""Vídeo vertical 9:16: globo girando -> Brasil -> Paraná -> Araruna -> cena da cidade.

Uso:  python3 render.py <pasta-geo> <saida.mp4>
Pasta geo precisa de world.json (Natural Earth 50m), states.json (estados BR)
e pr.json (municípios do PR, IBGE via geodata-br). Ver README.md.
"""
import json, math, os, subprocess, sys
import numpy as np
import cairo
from shapely.geometry import shape

W, H, FPS = 1080, 1920, 30
DUR = 37.0
NF = int(DUR * FPS)
GEO = sys.argv[1] if len(sys.argv) > 1 else "geo"
OUT = sys.argv[2] if len(sys.argv) > 2 else "araruna_video_mudo.mp4"
ONLY = os.environ.get("ONLY")  # ex.: "120,480,700" para gerar só stills

# ---------- paleta (arara-azul: cobalto + amarelo-ouro) ----------
NAVY = (0.020, 0.035, 0.085)
OCEAN = (0.035, 0.075, 0.165)
LAND = (0.105, 0.170, 0.300)
BORDER = (0.30, 0.42, 0.62)
COBALT = (0.18, 0.42, 1.00)
GOLD = (1.00, 0.78, 0.22)
WHITE = (1, 1, 1)
RAD = math.pi / 180

# ---------- easing ----------
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def seg(t, a, b): return clamp((t - a) / (b - a))
def ease_io(x): return 4 * x**3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def ease_out(x): return 1 - (1 - x) ** 3
def ease_in(x): return x ** 3
def lerp(a, b, x): return a + (b - a) * x
def back_out(x, s=1.6): return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2

# ---------- geometria ----------
def rings_of(geom):
    gj = geom if isinstance(geom, dict) else geom.__geo_interface__
    polys = gj["coordinates"] if gj["type"] == "MultiPolygon" else [gj["coordinates"]]
    out = []
    for poly in polys:
        out.append([np.radians(np.asarray(r, dtype=np.float64)[:, :2]) for r in poly])
    return out  # list of polygons; each polygon = list of rings (lon,lat rad)

world = json.load(open(os.path.join(GEO, "world.json")))
WORLD = []
BRAZIL = None
for f in world["features"]:
    p = rings_of(f["geometry"])
    if f["properties"]["ADMIN"] == "Brazil":
        BRAZIL = p
    WORLD.append(p)

states = json.load(open(os.path.join(GEO, "states.json")))
STATES, PARANA = [], None
for f in states["features"]:
    p = rings_of(f["geometry"])
    if f["properties"]["sigla"] == "PR":
        PARANA = p
    STATES.append(p)

mun = json.load(open(os.path.join(GEO, "pr.json")))
MUNS, ARARUNA, NEIGH = [], None, []
shp = {f["properties"]["name"]: shape(f["geometry"]) for f in mun["features"]}
ara_shape = shp["Araruna"]
for f in mun["features"]:
    nm = f["properties"]["name"]
    p = rings_of(f["geometry"])
    MUNS.append(p)
    if nm == "Araruna":
        ARARUNA = p
    elif shp[nm].intersects(ara_shape):
        c = shp[nm].representative_point()
        NEIGH.append((nm, c.x, c.y))

ALON, ALAT = -52.576, -23.954       # centróide do município (IBGE)
CITY = (-52.502, -23.931)            # sede urbana aproximada (pin)
PR_C = (-51.55, -24.65)
BR_C = (-53.0, -13.5)

# graticule
GRAT = []
for lon in range(-180, 180, 20):
    GRAT.append(np.radians(np.array([[lon, la] for la in np.linspace(-80, 80, 60)])))
for lat in range(-60, 80, 20):
    GRAT.append(np.radians(np.array([[lo, lat] for lo in np.linspace(-180, 180, 180)])))

# ---------- projeção ortográfica ----------
class Cam:
    def __init__(s, lon0, lat0, R, cx=W / 2, cy=H * 0.52):
        s.l0, s.p0, s.R, s.cx, s.cy = lon0 * RAD, lat0 * RAD, R, cx, cy
        s.sp, s.cp = math.sin(s.p0), math.cos(s.p0)

    def proj(s, ll, clip_horizon=True):
        lam = ll[:, 0] - s.l0
        phi = ll[:, 1]
        cphi = np.cos(phi)
        x = cphi * np.sin(lam)
        y = s.cp * np.sin(phi) - s.sp * cphi * np.cos(lam)
        cosc = s.sp * np.sin(phi) + s.cp * cphi * np.cos(lam)
        if clip_horizon:
            hid = cosc < 0
            if hid.any():
                n = np.hypot(x[hid], y[hid]) + 1e-12
                x[hid] /= n; y[hid] /= n
        return np.stack([s.cx + s.R * x, s.cy - s.R * y], 1), cosc

    def pt(s, lon, lat):
        xy, c = s.proj(np.radians(np.array([[lon, lat]])), False)
        return xy[0][0], xy[0][1], c[0]

def path_polys(ctx, cam, polys, margin=200):
    drew = False
    for poly in polys:
        for k, ring in enumerate(poly):
            xy, cosc = cam.proj(ring)
            if (cosc < 0).all():
                continue
            mn, mx = xy.min(0), xy.max(0)
            if mx[0] < -margin or mn[0] > W + margin or mx[1] < -margin or mn[1] > H + margin:
                continue
            if mx[0] - mn[0] < 0.6 and mx[1] - mn[1] < 0.6:
                continue
            ctx.move_to(*xy[0])
            for x, y in xy[1:]:
                ctx.line_to(x, y)
            ctx.close_path()
            drew = True
    return drew

def path_line(ctx, cam, ll):
    xy, cosc = cam.proj(ll, False)
    pen = False
    for (x, y), c in zip(xy, cosc):
        if c < 0.0:
            pen = False; continue
        if pen: ctx.line_to(x, y)
        else: ctx.move_to(x, y); pen = True

# ---------- texto ----------
def font(ctx, size, weight="bold", family="Inter Display", italic=False):
    w = cairo.FONT_WEIGHT_BOLD if weight == "bold" else cairo.FONT_WEIGHT_NORMAL
    sl = cairo.FONT_SLANT_ITALIC if italic else cairo.FONT_SLANT_NORMAL
    fam = {"black": "Inter Display Black", "semi": "Inter Display SemiBold",
           "medium": "Inter Display Medium", "light": "Inter Display Light"}.get(weight, family)
    if weight in ("black", "semi", "medium", "light"):
        w = cairo.FONT_WEIGHT_NORMAL
    ctx.select_font_face(fam, sl, w)
    ctx.set_font_size(size)

def text(ctx, s, x, y, size, color=WHITE, alpha=1.0, weight="bold", align="c",
         track=0.0, family="Inter Display", shadow=True, italic=False):
    if alpha <= 0.003: return
    font(ctx, size, weight, family, italic)
    widths = [ctx.text_extents(ch).x_advance for ch in s]
    tw = sum(widths) + track * size * (len(s) - 1)
    x0 = x - tw / 2 if align == "c" else (x - tw if align == "r" else x)
    def run(dx, dy, col, a):
        ctx.set_source_rgba(*col, a)
        cx = x0
        for ch, wd in zip(s, widths):
            ctx.move_to(cx + dx, y + dy); ctx.show_text(ch)
            cx += wd + track * size
    if shadow:
        run(0, size * 0.04, (0, 0, 0), alpha * 0.55)
    run(0, 0, color, alpha)
    return tw

def reveal(t, a, b, fade=0.45):
    """alpha + deslocamento para um bloco de texto visível entre a e b"""
    i = ease_out(seg(t, a, a + fade)); o = 1 - ease_in(seg(t, b - fade, b))
    al = min(i, o)
    return al, (1 - i) * 40 - (1 - o) * 20

def pill(ctx, x, y, w, h, col, alpha):
    r = h / 2
    ctx.new_path()
    ctx.arc(x + r, y + r, r, math.pi / 2, 3 * math.pi / 2)
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, math.pi / 2)
    ctx.close_path()
    ctx.set_source_rgba(*col, alpha); ctx.fill()

def kicker(ctx, s, x, y, alpha, col=GOLD):
    """etiqueta pequena com bolinha, estilo do guia"""
    if alpha <= 0: return
    font(ctx, 30, "semi")
    tw = sum(ctx.text_extents(ch).x_advance for ch in s) + 0.18 * 30 * (len(s) - 1)
    total = tw + 34
    x0 = x - total / 2
    ctx.set_source_rgba(*col, alpha); ctx.arc(x0 + 9, y - 10, 8, 0, 2 * math.pi); ctx.fill()
    text(ctx, s, x0 + 34, y, 30, col, alpha, "semi", "l", 0.18, shadow=False)

# ---------- câmera do mapa (keyframes) ----------
R_GLOBE = 440
def map_cam(t):
    # 0-7.5s: globo girando e desacelerando até o Brasil
    u = ease_out(seg(t, 0.0, 7.2))
    lon = lerp(BR_C[0] + 420, BR_C[0], u)
    lat = lerp(18, BR_C[1] * 0.75, u)
    R = R_GLOBE * (1 + 0.04 * math.sin(t * 0.8))
    # 6.2-9.2 zoom Brasil
    z = ease_io(seg(t, 6.2, 9.0))
    lat = lerp(lat, BR_C[1], z)
    R = math.exp(lerp(math.log(R), math.log(1250), z))
    # 9.6-12.8 zoom Paraná
    z = ease_io(seg(t, 9.6, 12.6))
    zc = ease_io(seg(t, 9.6, 11.8))
    lon = lerp(lon, PR_C[0], zc); lat = lerp(lat, PR_C[1], zc)
    R = math.exp(lerp(math.log(R), math.log(7600), z))
    # 13.2-16.2 zoom Araruna
    z = ease_io(seg(t, 13.2, 16.2))
    zc = ease_io(seg(t, 13.2, 15.2))
    lon = lerp(lon, ALON, zc); lat = lerp(lat, ALAT, zc)
    R = math.exp(lerp(math.log(R), math.log(105000), z))
    # 16.2-18.0 aproximação lenta centralizando a sede, depois mergulho no pin
    R *= 1 + 0.25 * ease_io(seg(t, 16.2, 18.0))
    c = ease_io(seg(t, 16.0, 17.9))
    lon = lerp(lon, CITY[0], c); lat = lerp(lat, CITY[1], c)
    d = ease_in(seg(t, 17.9, 19.0))
    R *= math.exp(math.log(9) * d)
    return Cam(lon, lat, R)

def draw_bg(ctx, t):
    ctx.set_source_rgb(*NAVY); ctx.paint()
    g = cairo.RadialGradient(W / 2, H * 0.52, 50, W / 2, H * 0.52, 1100)
    g.add_color_stop_rgba(0, 0.10, 0.20, 0.55, 0.55)
    g.add_color_stop_rgba(1, 0, 0, 0, 0)
    ctx.set_source(g); ctx.paint()
    rng = np.random.default_rng(7)
    pts = rng.random((260, 3))
    for x, y, b in pts:
        tw = 0.5 + 0.5 * math.sin(t * 2 + b * 30)
        ctx.set_source_rgba(1, 1, 1, 0.15 + 0.5 * b * tw)
        ctx.arc(x * W + t * 6 * b, y * H, 0.6 + 1.6 * b, 0, 2 * math.pi); ctx.fill()

def draw_map(ctx, t):
    cam = map_cam(t)
    draw_bg(ctx, t)
    globe_a = 1 - seg(cam.R, 1500, 4000)  # disco/atmosfera só no modo globo
    # atmosfera
    if globe_a > 0:
        g = cairo.RadialGradient(cam.cx, cam.cy, cam.R * 0.95, cam.cx, cam.cy, cam.R * 1.25)
        g.add_color_stop_rgba(0, 0.35, 0.6, 1, 0.55 * globe_a)
        g.add_color_stop_rgba(1, 0.35, 0.6, 1, 0)
        ctx.set_source(g); ctx.arc(cam.cx, cam.cy, cam.R * 1.3, 0, 2 * math.pi); ctx.fill()
    # oceano
    ctx.set_source_rgb(*OCEAN)
    if cam.R < 3000:
        ctx.arc(cam.cx, cam.cy, cam.R, 0, 2 * math.pi); ctx.fill()
    else:
        ctx.paint()
    # grade
    ctx.set_line_width(1.0)
    ctx.set_source_rgba(0.5, 0.7, 1, 0.10 * max(globe_a, 0.0))
    if globe_a > 0:
        for ln in GRAT:
            path_line(ctx, cam, ln)
        ctx.stroke()
    # continentes
    ctx.new_path()
    for p in WORLD:
        path_polys(ctx, cam, p)
    ctx.set_fill_rule(cairo.FILL_RULE_WINDING)
    ctx.set_source_rgb(*LAND); ctx.fill_preserve()
    ctx.set_source_rgba(*BORDER, 0.55); ctx.set_line_width(1.1); ctx.stroke()

    br_a = ease_out(seg(t, 6.0, 7.6))
    pr_a = ease_out(seg(t, 10.6, 11.8))
    ar_a = ease_out(seg(t, 14.4, 15.6))
    # Brasil
    ctx.new_path(); path_polys(ctx, cam, BRAZIL)
    ctx.set_source_rgba(*COBALT, 0.55 * br_a * (1 - 0.6 * pr_a)); ctx.fill_preserve()
    ctx.set_source_rgba(*GOLD, br_a * (1 - 0.7 * pr_a)); ctx.set_line_width(2.6); ctx.stroke()
    # estados
    st_a = seg(cam.R, 900, 1600)
    if st_a > 0:
        ctx.new_path()
        for p in STATES: path_polys(ctx, cam, p)
        ctx.set_source_rgba(0.6, 0.75, 1, 0.45 * st_a * (1 - 0.5 * ar_a)); ctx.set_line_width(1.6); ctx.stroke()
    # Paraná
    ctx.new_path(); path_polys(ctx, cam, PARANA)
    ctx.set_source_rgba(*COBALT, 0.6 * pr_a * (1 - 0.92 * ar_a)); ctx.fill_preserve()
    ctx.set_source_rgba(*GOLD, pr_a * (1 - 0.6 * ar_a)); ctx.set_line_width(3); ctx.stroke()
    # municípios
    mu_a = seg(cam.R, 6000, 14000)
    if mu_a > 0:
        ctx.new_path()
        for p in MUNS: path_polys(ctx, cam, p)
        ctx.set_source_rgba(0.6, 0.75, 1, 0.35 * mu_a); ctx.set_line_width(1.4); ctx.stroke()
    # Araruna (glow)
    if ar_a > 0:
        ctx.new_path(); path_polys(ctx, cam, ARARUNA)
        pulse = 0.5 + 0.5 * math.sin(t * 5)
        ctx.set_source_rgba(0.10, 0.30, 0.95, 0.80 * ar_a); ctx.fill_preserve()
        ctx.set_source_rgba(*GOLD, 0.12 * ar_a); ctx.fill_preserve()
        for lw, a in ((26, 0.08), (14, 0.15), (6, 0.5)):
            ctx.set_source_rgba(*GOLD, a * ar_a * (0.7 + 0.3 * pulse)); ctx.set_line_width(lw); ctx.stroke_preserve()
        ctx.set_source_rgba(1, 0.92, 0.6, ar_a); ctx.set_line_width(3.5); ctx.stroke()
        # vizinhos
        nb_a = ar_a * (1 - seg(t, 17.6, 18.2))
        for nm, lo, la in NEIGH:
            x, y, c = cam.pt(lo, la)
            if -100 < x < W + 100 and -50 < y < H + 50:
                text(ctx, nm.upper(), x, y, 24, (0.75, 0.83, 1), 0.75 * nb_a, "semi", track=0.12)
    # pin na sede
    pin_t = seg(t, 15.2, 15.8)
    if pin_t > 0:
        x, y, _ = cam.pt(*CITY)
        drop = (1 - back_out(pin_t)) * -120
        s = 1 + 3 * ease_in(seg(t, 18.2, 19.0))
        # onda
        for k in range(3):
            ph = ((t - 15.6) * 0.9 + k / 3) % 1
            if t > 15.6:
                ctx.set_source_rgba(*GOLD, 0.6 * (1 - ph))
                ctx.set_line_width(3); ctx.arc(x, y, 20 + 140 * ph, 0, 2 * math.pi); ctx.stroke()
        ctx.save(); ctx.translate(x, y + drop); ctx.scale(s, s)
        ctx.move_to(0, 0)
        ctx.curve_to(-14, -26, -34, -40, -34, -64)
        ctx.arc(0, -64, 34, math.pi, 0)
        ctx.curve_to(34, -40, 14, -26, 0, 0)
        ctx.set_source_rgb(*GOLD); ctx.fill()
        ctx.set_source_rgb(*NAVY); ctx.arc(0, -64, 13, 0, 2 * math.pi); ctx.fill()
        ctx.restore()
    return cam

def map_titles(ctx, t):
    # gancho
    a, dy = reveal(t, 0.3, 5.4)
    text(ctx, "Tem um lugar no mapa", W / 2, 330 + dy, 64, WHITE, a, "bold")
    text(ctx, "que merece a viagem", W / 2, 410 + dy, 64, GOLD, a, "bold")
    # Brasil
    a, dy = reveal(t, 6.4, 9.6)
    kicker(ctx, "AMÉRICA DO SUL", W / 2, 300 + dy, a)
    text(ctx, "BRASIL", W / 2, 400 + dy, 104, WHITE, a, "black", track=0.06)
    # Paraná
    a, dy = reveal(t, 10.8, 13.4)
    kicker(ctx, "REGIÃO SUL", W / 2, 300 + dy, a)
    text(ctx, "PARANÁ", W / 2, 400 + dy, 104, WHITE, a, "black", track=0.06)
    # Araruna
    a, dy = reveal(t, 14.6, 18.3)
    kicker(ctx, "CENTRO-OCIDENTAL PARANAENSE", W / 2, 300 + dy, a)
    text(ctx, "ARARUNA", W / 2, 410 + dy, 120, WHITE, a, "black", track=0.05)
    lat = abs(ALAT); lon = abs(ALON)
    coord = f"{int(lat)}°{int((lat % 1) * 60):02d}′S   {int(lon)}°{int((lon % 1) * 60):02d}′O"
    text(ctx, coord, W / 2, 475 + dy, 30, (0.7, 0.8, 1), a * 0.9, "normal", family="JetBrains Mono", track=0.05)

# ---------- cena ilustrada da cidade ----------
VP = (540, 1080)  # ponto de fuga / horizonte
rng = np.random.default_rng(11)
HOUSES = []
for i in range(46):
    x = rng.uniform(150, 930)
    if 470 < x < 610: continue
    w = rng.uniform(26, 58); h = rng.uniform(22, 70) * (1.2 - abs(x - 540) / 900)
    HOUSES.append((x, w, h, rng.random()))
HOUSES.sort(key=lambda r: -r[2])
TREES = [(rng.uniform(80, 1000), rng.uniform(12, 26)) for _ in range(26)]

def scene_cam(t):
    """(foco_x, foco_y, zoom) da cena ao longo do tempo"""
    keys = [(18.4, 540, 1050, 1.9), (19.6, 540, 900, 1.05), (22.4, 560, 820, 1.0),
            (23.4, 540, 990, 1.75), (26.0, 540, 1000, 1.85), (27.0, 540, 1380, 1.15),
            (29.6, 540, 1400, 1.12), (30.6, 540, 1250, 1.0), (33.0, 540, 1200, 0.98),
            (34.0, 540, 1000, 1.0), (37.0, 540, 980, 1.04)]
    for (t0, x0, y0, z0), (t1, x1, y1, z1) in zip(keys, keys[1:]):
        if t <= t1:
            u = ease_io(seg(t, t0, t1))
            return lerp(x0, x1, u), lerp(y0, y1, u), math.exp(lerp(math.log(z0), math.log(z1), u))
    return keys[-1][1:]

def draw_arara(ctx, x, y, s, flap, face=1, alpha=1.0):
    """arara-azul estilizada vista de lado; flap em [-1,1]"""
    ctx.save(); ctx.translate(x, y); ctx.scale(s * face, s)
    ctx.push_group()
    blue, dark, light = (0.12, 0.33, 0.85), (0.05, 0.16, 0.52), (0.30, 0.55, 1.0)
    # cauda
    ctx.move_to(-0.18, 0.02); ctx.curve_to(-0.55, 0.20, -0.95, 0.42, -1.25, 0.62)
    ctx.curve_to(-0.90, 0.30, -0.55, 0.10, -0.12, 0.13); ctx.close_path()
    ctx.set_source_rgb(*dark); ctx.fill()
    ctx.move_to(-0.15, 0.06); ctx.curve_to(-0.5, 0.22, -0.85, 0.42, -1.12, 0.58)
    ctx.curve_to(-0.8, 0.34, -0.5, 0.16, -0.10, 0.14); ctx.close_path()
    ctx.set_source_rgb(*blue); ctx.fill()
    # asa de trás
    ang = flap * 1.0
    ctx.save(); ctx.translate(0.02, -0.05); ctx.rotate(-0.4 - ang * 0.8)
    ctx.move_to(0, 0); ctx.curve_to(-0.15, -0.35, -0.45, -0.75, -0.75, -0.82)
    ctx.curve_to(-0.5, -0.45, -0.3, -0.1, -0.15, 0.05); ctx.close_path()
    ctx.set_source_rgb(*dark); ctx.fill(); ctx.restore()
    # corpo
    ctx.save(); ctx.rotate(-0.35); ctx.scale(0.36, 0.17); ctx.arc(0, 0, 1, 0, 2 * math.pi); ctx.restore()
    g = cairo.LinearGradient(0, -0.2, 0, 0.2); g.add_color_stop_rgb(0, *light); g.add_color_stop_rgb(1, *blue)
    ctx.set_source(g); ctx.fill()
    # cabeça
    ctx.arc(0.30, -0.20, 0.15, 0, 2 * math.pi); ctx.set_source_rgb(*light); ctx.fill()
    # bico (preto, curvo)
    ctx.move_to(0.40, -0.27); ctx.curve_to(0.58, -0.30, 0.62, -0.14, 0.52, -0.06)
    ctx.curve_to(0.50, -0.12, 0.46, -0.14, 0.41, -0.13); ctx.close_path()
    ctx.set_source_rgb(0.06, 0.06, 0.08); ctx.fill()
    # faixa amarela na base do bico + anel do olho (marca da arara-azul)
    ctx.move_to(0.38, -0.12); ctx.curve_to(0.44, -0.10, 0.48, -0.06, 0.46, -0.03)
    ctx.curve_to(0.41, -0.05, 0.37, -0.08, 0.35, -0.11); ctx.close_path()
    ctx.set_source_rgb(*GOLD); ctx.fill()
    ctx.arc(0.33, -0.25, 0.045, 0, 2 * math.pi); ctx.set_source_rgb(*GOLD); ctx.fill()
    ctx.arc(0.335, -0.25, 0.022, 0, 2 * math.pi); ctx.set_source_rgb(0.05, 0.05, 0.05); ctx.fill()
    # asa da frente
    ctx.save(); ctx.translate(0.0, -0.04); ctx.rotate(-0.15 - ang * 1.1)
    ctx.move_to(0.08, 0); ctx.curve_to(-0.10, -0.40, -0.40, -0.85, -0.82, -0.98)
    ctx.curve_to(-0.62, -0.62, -0.45, -0.2, -0.25, 0.08); ctx.close_path()
    g = cairo.LinearGradient(0, 0, -0.8, -0.9); g.add_color_stop_rgb(0, *light); g.add_color_stop_rgb(1, *dark)
    ctx.set_source(g); ctx.fill()
    for k in range(4):  # penas
        ctx.move_to(-0.30 - k * 0.12, -0.35 - k * 0.15); ctx.line_to(-0.55 - k * 0.08, -0.45 - k * 0.12)
    ctx.set_source_rgba(*dark, 0.6); ctx.set_line_width(0.02); ctx.stroke()
    ctx.restore()
    ctx.pop_group_to_source(); ctx.paint_with_alpha(alpha)
    ctx.restore()

def draw_church(ctx, x, base, s, glow):
    ctx.save(); ctx.translate(x, base); ctx.scale(s, s)
    if glow > 0:
        g = cairo.RadialGradient(0, -120, 10, 0, -120, 260)
        g.add_color_stop_rgba(0, *GOLD, 0.45 * glow); g.add_color_stop_rgba(1, *GOLD, 0)
        ctx.set_source(g); ctx.arc(0, -120, 260, 0, 2 * math.pi); ctx.fill()
    body = (0.93, 0.90, 0.84); shade = (0.78, 0.74, 0.68); roof = (0.55, 0.20, 0.15)
    # nave
    ctx.rectangle(-70, -110, 140, 110); ctx.set_source_rgb(*body); ctx.fill()
    ctx.move_to(-82, -110); ctx.line_to(0, -170); ctx.line_to(82, -110); ctx.close_path()
    ctx.set_source_rgb(*roof); ctx.fill()
    # torre
    ctx.rectangle(-26, -270, 52, 170); ctx.set_source_rgb(*body); ctx.fill()
    ctx.rectangle(14, -270, 12, 170); ctx.set_source_rgb(*shade); ctx.fill()
    ctx.move_to(-32, -270); ctx.line_to(0, -340); ctx.line_to(32, -270); ctx.close_path()
    ctx.set_source_rgb(*roof); ctx.fill()
    # cruz
    ctx.set_source_rgb(*GOLD); ctx.rectangle(-3, -390, 6, 52); ctx.fill(); ctx.rectangle(-16, -375, 32, 6); ctx.fill()
    # janelas / sino / porta
    ctx.set_source_rgb(0.25, 0.16, 0.12)
    ctx.arc(0, -225, 12, math.pi, 0); ctx.rectangle(-12, -225, 24, 22); ctx.fill()
    ctx.move_to(-20, 0); ctx.line_to(-20, -50); ctx.arc(0, -50, 20, math.pi, 0); ctx.line_to(20, 0); ctx.close_path(); ctx.fill()
    ctx.set_source_rgba(1, 0.85, 0.45, 0.9)
    for wx in (-50, 50):
        ctx.arc(wx, -70, 9, math.pi, 0); ctx.rectangle(wx - 9, -70, 18, 26); ctx.fill()
    ctx.restore()

def draw_fields(ctx, t, hi):
    # campo em perspectiva: faixas convergindo ao ponto de fuga
    hx, hy = VP
    ctx.rectangle(-400, hy, W + 800, 2000)
    g = cairo.LinearGradient(0, hy, 0, H + 400)
    g.add_color_stop_rgb(0, 0.20, 0.36, 0.20); g.add_color_stop_rgb(1, 0.10, 0.30, 0.12)
    ctx.set_source(g); ctx.fill()
    N = 34
    for i in range(N):
        x0 = -2600 + i * (W + 5200) / N
        x1 = -2600 + (i + 0.5) * (W + 5200) / N
        ctx.move_to(hx, hy); ctx.line_to(x0, H + 600); ctx.line_to(x1, H + 600); ctx.close_path()
        # quadras de milho (douradas) à direita, soja (verde) à esquerda
        if i > N * 0.62:
            ctx.set_source_rgba(0.85, 0.68, 0.22, 0.55 + 0.25 * hi)
        else:
            ctx.set_source_rgba(0.30, 0.58, 0.24, 0.45 + 0.25 * hi)
        ctx.fill()
    # névoa no horizonte
    g = cairo.LinearGradient(0, hy - 10, 0, hy + 160)
    g.add_color_stop_rgba(0, 0.98, 0.80, 0.55, 0.65); g.add_color_stop_rgba(1, 0.98, 0.80, 0.55, 0)
    ctx.set_source(g); ctx.rectangle(-400, hy - 10, W + 800, 170); ctx.fill()
    # pés de soja em primeiro plano (brotos)
    if hi > 0:
        r2 = np.random.default_rng(3)
        for k in range(70):
            px = r2.uniform(-100, W + 100); py = r2.uniform(hy + 300, H + 300)
            sc = (py - hy) / 700
            sway = math.sin(t * 2 + k) * 4 * sc
            ctx.set_source_rgba(0.45, 0.78, 0.30, 0.9 * hi)
            for d in (-1, 1):
                ctx.save(); ctx.translate(px + sway, py); ctx.scale(sc, sc); ctx.rotate(d * 0.6)
                ctx.scale(1, 0.45); ctx.arc(0, -22, 18, 0, 2 * math.pi); ctx.restore(); ctx.fill()

def peabiru_pts():
    pts = []
    for i in range(120):
        u = i / 119
        y = lerp(H + 500, VP[1] + 6, u ** 0.55)
        amp = 260 * (1 - u) ** 1.2
        x = VP[0] + 90 * (1 - u) + amp * math.sin(u * 9.5)
        pts.append((x, y))
    return pts
PEA = peabiru_pts()

def draw_city(ctx, t):
    fx, fy, z = scene_cam(t)
    ctx.save()
    ctx.translate(W / 2, H / 2); ctx.scale(z, z); ctx.translate(-fx, -fy)
    hx, hy = VP
    # céu fim de tarde
    g = cairo.LinearGradient(0, -400, 0, hy)
    g.add_color_stop_rgb(0, 0.03, 0.07, 0.20); g.add_color_stop_rgb(0.55, 0.13, 0.30, 0.68)
    g.add_color_stop_rgb(0.85, 0.85, 0.55, 0.45); g.add_color_stop_rgb(1, 1.0, 0.78, 0.45)
    ctx.set_source(g); ctx.rectangle(-500, -500, W + 1000, hy + 520); ctx.fill()
    sun = cairo.RadialGradient(760, hy - 70, 10, 760, hy - 70, 420)
    sun.add_color_stop_rgba(0, 1, 0.92, 0.65, 1); sun.add_color_stop_rgba(0.12, 1, 0.85, 0.45, 0.9)
    sun.add_color_stop_rgba(1, 1, 0.7, 0.3, 0)
    ctx.set_source(sun); ctx.arc(760, hy - 70, 420, 0, 2 * math.pi); ctx.fill()
    # nuvens
    for k, (cx, cy, s) in enumerate([(200, 420, 1.0), (820, 300, 0.8), (520, 600, 0.7)]):
        cx += (t - 18) * (6 + 3 * k)
        ctx.set_source_rgba(1, 0.9, 0.85, 0.22)
        for dx, dy, r in ((0, 0, 50), (45, -18, 40), (90, 0, 45), (40, 15, 45)):
            ctx.arc(cx + dx * s, cy + dy * s, r * s, 0, 2 * math.pi); ctx.fill()
    # colinas
    for k, (yy, col) in enumerate([(hy - 40, (0.22, 0.28, 0.48)), (hy - 15, (0.16, 0.22, 0.38))]):
        ctx.move_to(-500, hy + 5)
        for x in range(-500, W + 520, 40):
            ctx.line_to(x, yy + 18 * math.sin(x * 0.006 + k * 2) + 10 * math.sin(x * 0.017))
        ctx.line_to(W + 500, hy + 5); ctx.close_path(); ctx.set_source_rgb(*col); ctx.fill()
    fields_hi = ease_out(seg(t, 26.2, 27.2)) * (1 - 0.6 * seg(t, 33.0, 34.0))
    draw_fields(ctx, t, fields_hi)
    # Caminho de Peabiru
    pea = ease_io(seg(t, 29.8, 32.0))
    if pea > 0:
        n = max(2, int(len(PEA) * pea))
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        for lw, a in ((60, 0.10), (34, 0.20), (16, 0.95)):
            ctx.move_to(*PEA[0])
            for p in PEA[1:n]: ctx.line_to(*p)
            ctx.set_source_rgba(0.85, 0.62, 0.35, a); ctx.set_line_width(lw); ctx.stroke()
        ctx.set_dash([2, 26], -(t * 60) % 28)
        ctx.move_to(*PEA[0])
        for p in PEA[1:n]: ctx.line_to(*p)
        ctx.set_source_rgba(1, 0.95, 0.75, 0.95); ctx.set_line_width(7); ctx.stroke()
        ctx.set_dash([])
        hxp, hyp = PEA[n - 1]
        ctx.set_source_rgba(*GOLD, 1); ctx.arc(hxp, hyp, 10, 0, 2 * math.pi); ctx.fill()
    # cidade no horizonte
    ch_glow = ease_out(seg(t, 22.8, 23.8)) * (1 - seg(t, 26.0, 26.8))
    for x, w, h, r in HOUSES:
        base = hy + 6
        ctx.set_source_rgb(0.88 - 0.25 * r, 0.80 - 0.2 * r, 0.75 - 0.15 * r)
        ctx.rectangle(x - w / 2, base - h, w, h); ctx.fill()
        ctx.move_to(x - w / 2 - 4, base - h); ctx.line_to(x, base - h - w * 0.35); ctx.line_to(x + w / 2 + 4, base - h)
        ctx.close_path(); ctx.set_source_rgb(0.55 + 0.1 * r, 0.22, 0.17); ctx.fill()
        if h > 30:
            ctx.set_source_rgba(1, 0.86, 0.45, 0.85)
            ctx.rectangle(x - w / 4, base - h * 0.6, 5, 7); ctx.rectangle(x + w / 6, base - h * 0.6, 5, 7); ctx.fill()
    draw_church(ctx, 540, hy + 8, 0.62, ch_glow)
    # árvores (ipês) entre a cidade e o campo
    for k, (x, r) in enumerate(TREES):
        col = (0.95, 0.75, 0.15) if k % 4 == 0 else ((0.80, 0.35, 0.65) if k % 7 == 0 else (0.16, 0.38, 0.22))
        ctx.set_source_rgb(0.25, 0.18, 0.12); ctx.rectangle(x - 2, hy - 4, 4, 22); ctx.fill()
        ctx.set_source_rgb(*col); ctx.arc(x, hy - 10, r, 0, 2 * math.pi); ctx.fill()
    # arara-azul voando (19.2 -> 23.0) e voltando no final
    fl = math.sin(t * 9.0)
    if 18.6 < t < 23.4:
        u = seg(t, 18.6, 23.4)
        ax = lerp(-260, 1350, ease_io(u) * 0.5 + u * 0.5)
        ay = 760 - 160 * math.sin(u * math.pi) + 18 * fl
        sc = 260 if t < 22.0 else lerp(260, 200, seg(t, 22, 23.4))
        draw_arara(ctx, ax, ay, sc, fl, 1)
    ctx.restore()
    # degradê no topo para os títulos
    g = cairo.LinearGradient(0, 0, 0, 760)
    g.add_color_stop_rgba(0, *NAVY, 0.80); g.add_color_stop_rgba(0.6, *NAVY, 0.45); g.add_color_stop_rgba(1, *NAVY, 0)
    ctx.set_source(g); ctx.rectangle(0, 0, W, 760); ctx.fill()

def city_titles(ctx, t):
    a, dy = reveal(t, 19.6, 22.7)
    kicker(ctx, "DO TUPI", W / 2, 290 + dy, a)
    text(ctx, "ARARUNA", W / 2, 400 + dy, 110, WHITE, a, "black", track=0.05)
    text(ctx, "quer dizer arara-azul", W / 2, 480 + dy, 52, GOLD, a, "semi")
    a, dy = reveal(t, 23.2, 26.3)
    kicker(ctx, "FÉ E TRADIÇÃO", W / 2, 290 + dy, a)
    text(ctx, "Igreja Matriz", W / 2, 390 + dy, 88, WHITE, a, "black")
    text(ctx, "Santo Antônio", W / 2, 480 + dy, 88, WHITE, a, "black")
    text(ctx, "festa do padroeiro todo mês de junho", W / 2, 555 + dy, 40, GOLD, a, "semi")
    a, dy = reveal(t, 26.8, 29.9)
    kicker(ctx, "O CAMPO QUE MOVE A CIDADE", W / 2, 290 + dy, a)
    text(ctx, "Soja, milho", W / 2, 390 + dy, 92, WHITE, a, "black")
    text(ctx, "e mandioca", W / 2, 485 + dy, 92, GOLD, a, "black")
    a, dy = reveal(t, 30.3, 33.4)
    kicker(ctx, "HISTÓRIA", W / 2, 290 + dy, a)
    text(ctx, "Caminho de Peabiru", W / 2, 390 + dy, 80, WHITE, a, "black")
    text(ctx, "a trilha indígena que cortava a região", W / 2, 460 + dy, 40, GOLD, a, "semi")

def end_card(ctx, t):
    a = ease_out(seg(t, 33.4, 34.2))
    if a <= 0: return
    g = cairo.LinearGradient(0, 0, 0, H)
    g.add_color_stop_rgba(0, *NAVY, 0.88 * a); g.add_color_stop_rgba(0.55, *NAVY, 0.55 * a); g.add_color_stop_rgba(1, *NAVY, 0.92 * a)
    ctx.set_source(g); ctx.paint()
    dy = (1 - a) * 40
    kicker(ctx, "PARANÁ · BRASIL", W / 2, 640 + dy, a)
    text(ctx, "ARARUNA", W / 2, 780 + dy, 150, WHITE, a, "black", track=0.04)
    b = ease_out(seg(t, 34.0, 34.6))
    text(ctx, "14.485 habitantes", W / 2, 880 + dy, 54, GOLD, b, "semi")
    text(ctx, "Censo IBGE 2022", W / 2, 930 + dy, 30, (0.75, 0.82, 1), b * 0.9, "medium", track=0.08)
    c = ease_out(seg(t, 34.6, 35.2))
    text(ctx, "29 de novembro", W / 2, 1060 + dy, 62, WHITE, c, "black")
    text(ctx, "aniversário da cidade", W / 2, 1115 + dy, 38, (0.85, 0.9, 1), c, "medium")
    d = back_out(seg(t, 35.3, 35.9)) if t > 35.3 else 0
    if d > 0:
        ctx.save(); ctx.translate(W / 2, 1290); ctx.scale(d, d)
        pill(ctx, -380, -58, 760, 104, GOLD, 1)
        text(ctx, "Comenta ARARUNA se você é daqui", 0, 12, 40, NAVY, 1, "black", shadow=False)
        ctx.restore()
    u = seg(t, 33.4, 37.2)
    fl = math.sin(t * 9.0)
    draw_arara(ctx, lerp(1300, 760, ease_out(u)), lerp(470, 420, u) + 10 * fl, 140, fl, -1, a)

def vignette(ctx):
    g = cairo.RadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.75)
    g.add_color_stop_rgba(0, 0, 0, 0, 0); g.add_color_stop_rgba(1, 0, 0, 0, 0.55)
    ctx.set_source(g); ctx.paint()

def frame(t):
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    ctx = cairo.Context(surf)
    ctx.set_antialias(cairo.ANTIALIAS_GOOD)
    T0, T1 = 18.2, 19.2  # transição portal
    if t < T1:
        draw_map(ctx, t)
        map_titles(ctx, t)
    if t >= T0:
        u = ease_in(seg(t, T0, T1))
        ctx.save()
        if u < 1:
            ctx.arc(W / 2, H * 0.52 - 64, 1 + u * 1300, 0, 2 * math.pi); ctx.clip()
        draw_city(ctx, t)
        city_titles(ctx, t)
        end_card(ctx, t)
        ctx.restore()
        if u < 1:  # anel dourado do portal
            ctx.set_source_rgba(*GOLD, 1 - u); ctx.set_line_width(14 * (1 - u) + 2)
            ctx.arc(W / 2, H * 0.52 - 64, 1 + u * 1300, 0, 2 * math.pi); ctx.stroke()
        fl = 1 - seg(t, T1, T1 + 0.35)
        if t >= T1 and fl > 0:
            ctx.set_source_rgba(1, 0.95, 0.8, 0.5 * fl); ctx.paint()
    vignette(ctx)
    # fade in/out
    fade = min(seg(t, 0, 0.5), 1 - seg(t, DUR - 0.6, DUR))
    if fade < 1:
        ctx.set_source_rgba(0, 0, 0, 1 - fade); ctx.paint()
    surf.flush()
    return surf

def main():
    if ONLY:
        os.makedirs("stills", exist_ok=True)
        for f in ONLY.split(","):
            t = float(f)
            frame(t).write_to_png(f"stills/t{t:05.1f}.png")
        return
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
                           "-b:v", "18M", "-maxrate", "24M", "-bufsize", "36M", OUT], stdin=subprocess.PIPE)
    for i in range(NF):
        s = frame(i / FPS)
        ff.stdin.write(bytes(s.get_data()))
        if i % 60 == 0: print(f"frame {i}/{NF}", flush=True)
    ff.stdin.close(); ff.wait()

if __name__ == "__main__":
    main()
