# Origami Crane demo clip for X (4:3 1920×1440, 60 fps): a titanium iPhone 17 Pro Max mockup playing the app recording.
# Ported from ../soap-bubbles/blender/scripts/promo.py (same rules): the PHONE STAYS STILL in the centre for the whole demo
# (no pan / zoom / shake / tilt), then ONE straight cut to the end card (phone on the right, still playing, text on the left).
# Frame 1 = the app's first frame (never black). No status bar overlay, nothing over the screen.
#
# Background (matches the app's anime house at golden hour): the app's painted sunset sky (app/assets/scene/anime/sky.jpg)
# heavily blurred and drifting slowly (two layers at different speeds = soft painterly clouds), mixed with a dusty-blue →
# peach gradient whose colours shift per beat-sheet section (warm in the house, sky blue when the crane flies out), a warm sun
# glow, soft bokeh, slow falling sakura petals (behind the phone only). Soft contact shadow behind the phone.
# End card: "Origami Crane" (letters fade and rise in softly), stack, author, studio.
#
# All timings live in the beat sheet JSON (blender/scripts/beats/v0.json…).
#
# Run: Blender -b --factory-startup -P blender/scripts/promo.py -- --beats blender/scripts/beats/v0.json \
#         --screen render/promo/v0/screen.mp4 --film-start 1.2 --out render/promo/frames [--pct 100] [--stills 0,8,16]
#   --film-start: second in screen.mp4 showing app t = 0 (promo.sh gets it from tools/filmstart.sh)
import bpy, bmesh, json, math, os, random, sys

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BEATS_PATH = os.path.abspath(arg("--beats", os.path.join(HERE, "beats", "v0.json")))
BEATS = json.load(open(BEATS_PATH))
SCREEN = os.path.abspath(arg("--screen", "render/promo/v0/screen.mp4"))
FILM0 = float(arg("--film-start", "0"))        # second in the recording at app t = 0
OUT = os.path.abspath(arg("--out", "render/promo/frames"))
PCT = int(arg("--pct", "100"))
LABEL = arg("--label", "")                     # small bottom-left label (e.g. "v2") to compare versions
FPS = 60
APP0 = float(arg("--app-start", BEATS["app_start"]))   # app second on the first clip frame (promo.sh may raise it)
APP_END = float(BEATS["app_end"])              # app second of the cut to the end card
CARD = float(BEATS.get("card", 3.0))           # end card length
DUR = APP_END - APP0 + CARD
FR = lambda sec: round(sec * FPS)              # clip second → frame
A = lambda t: FR(t - APP0)                     # app second → clip frame
rad = math.radians
rng = random.Random(BEATS.get("seed", 31))
C_CARD = APP_END - APP0                        # clip second of the cut
F_CARD = FR(C_CARD)
NF = FR(DUR)
EV = BEATS.get("events", {})


def TT(v):
    """Beat sheet timing → clip frame: number = app second; "start"; "card" / "card+0.9"; "end"; or an event name
    ("climb", "vanish+0.2")."""
    if isinstance(v, (int, float)):
        return A(v)
    if v == "start":
        return 0
    if v == "end":
        return NF
    if v.startswith("card"):
        return F_CARD + FR(float(v[4:] or 0))
    name, _, off = v.partition("+")
    if name in EV and isinstance(EV[name], (int, float)):
        return A(float(EV[name]) + float(off or 0))
    raise ValueError(f"unknown timing: {v}")


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1440, PCT
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 0, NF - 1
sc.view_settings.view_transform = "Standard"
sc.eevee.taa_render_samples = 16
sc.eevee.use_fast_gi = False
sc.render.film_transparent = False
sc.render.use_motion_blur = False              # the phone is still; the sprites drift slowly


def hexc(h):
    h = h.lstrip("#")
    lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return tuple(lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4)) + (1.0,)


def link(ob):
    sc.collection.objects.link(ob)
    return ob


def fcurves(idb):
    # Blender 5.x: layered/slotted Actions → go through the slot's channelbag
    ad = idb.animation_data
    if ad is None or ad.action is None:
        return []
    if hasattr(ad.action, "fcurves"):
        return ad.action.fcurves
    from bpy_extras.anim_utils import action_get_channelbag_for_slot
    cb = action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return cb.fcurves if cb else []


def key(idb, path, f, value):
    setattr(idb, path, value)
    idb.keyframe_insert(path, frame=f)


def key_sock(sock, f, value):
    sock.default_value = value
    sock.keyframe_insert("default_value", frame=f)


def sock_in(node, name, typ):
    return [s for s in node.inputs if s.name == name and s.type == typ][0]


def sock_out(node, typ):
    return [s for s in node.outputs if s.type == typ][0]


def interp(idb, kind):
    for fc in fcurves(idb):
        for k in fc.keyframe_points:
            k.interpolation = kind


def constant_hide(ob):
    for fc in fcurves(ob):
        if fc.data_path == "hide_render":
            for k in fc.keyframe_points:
                k.interpolation = "CONSTANT"


def math_node(N, op, a=None, b=None, L=None, clamp=False):
    m = N.new("ShaderNodeMath"); m.operation = op; m.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = v
        else:
            L.new(v, m.inputs[i])
    return m


def mix_rgb(N, Lk, a, b, fac, blend="MIX"):
    m = N.new("ShaderNodeMix"); m.data_type = "RGBA"; m.blend_type = blend
    for sock, v in ((m.inputs["Factor"], fac), (sock_in(m, "A", "RGBA"), a), (sock_in(m, "B", "RGBA"), b)):
        if isinstance(v, (int, float)):
            sock.default_value = v
        elif isinstance(v, tuple):
            sock.default_value = v
        else:
            Lk.new(v, sock)
    return m


def mat_emit(name, color, strength=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n = m.node_tree.nodes
    n.clear()
    e = n.new("ShaderNodeEmission"); e.inputs["Color"].default_value = hexc(color); e.inputs["Strength"].default_value = strength
    o = n.new("ShaderNodeOutputMaterial")
    m.node_tree.links.new(e.outputs[0], o.inputs[0])
    return m, e


def blended(m):
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    if hasattr(m, "use_transparency_overlap"):
        m.use_transparency_overlap = True


def quad(name, uv=True):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1)
    if uv:
        uvl = bm.loops.layers.uv.new()
        for face in bm.faces:
            for l in face.loops:
                l[uvl].uv = (l.vert.co.x / 2 + 0.5, l.vert.co.y / 2 + 0.5)
    bm.to_mesh(me); bm.free()
    return me


# ── background: blurred painted sky drifting (two layers) mixed with a 3-stop gradient + warm sun glow ──
# section = (timing, top, mid, bottom, sun glow colour, glow strength, transition frames)
SECTIONS = [(TT(t), *rest) for t, *rest in BEATS["bg"]]
bg = link(bpy.data.objects.new("bg", quad("bg")))
bg.scale = (5.4, 4.05, 1)                     # covers the end-card view (camera further back); demo view sees the middle
bg.rotation_euler = (rad(90), 0, 0)
bg.location = (0, 7, 0)
bgm = bpy.data.materials.new("bg"); bgm.use_nodes = True
N, Lk = bgm.node_tree.nodes, bgm.node_tree.links
N.clear()
tc = N.new("ShaderNodeTexCoord"); sep = N.new("ShaderNodeSeparateXYZ"); Lk.new(tc.outputs["UV"], sep.inputs[0])
c_top, c_mid, c_bot, c_sun = (N.new("ShaderNodeRGB") for _ in range(4))
r1 = N.new("ShaderNodeMapRange"); r1.interpolation_type = "SMOOTHSTEP"; r1.inputs["From Min"].default_value = 0.05; r1.inputs["From Max"].default_value = 0.5
r2 = N.new("ShaderNodeMapRange"); r2.interpolation_type = "SMOOTHSTEP"; r2.inputs["From Min"].default_value = 0.45; r2.inputs["From Max"].default_value = 0.98
Lk.new(sep.outputs["Y"], r1.inputs["Value"]); Lk.new(sep.outputs["Y"], r2.inputs["Value"])
m1 = mix_rgb(N, Lk, c_bot.outputs[0], c_mid.outputs[0], r1.outputs[0])
m2 = mix_rgb(N, Lk, sock_out(m1, "RGBA"), c_top.outputs[0], r2.outputs[0])
grad = sock_out(m2, "RGBA")
# painted clouds: two blurred copies of the app's sky, drifting right at different speeds (UV window 0.86 of the plate so the
# drift never reaches the edge)
PLATES = BEATS.get("bg_plates", ["blender/textures/promo/sky_soft.jpg", "blender/textures/promo/sky_mid.jpg"])
DRIFT = BEATS.get("bg_drift", [0.05, 0.11])     # UV x travel over the whole clip per layer
layers = []
for li, path in enumerate(PLATES):
    mp = N.new("ShaderNodeMapping"); Lk.new(tc.outputs["UV"], mp.inputs["Vector"])
    mp.inputs["Scale"].default_value = (0.86 - 0.06 * li, 0.86 - 0.06 * li, 1)
    for f, x in ((0, 0.02 + 0.01 * li), (NF, 0.02 + 0.01 * li + DRIFT[li % len(DRIFT)])):
        key_sock(mp.inputs["Location"], f, (x, 0.07 + 0.02 * li, 0))
    ti_ = N.new("ShaderNodeTexImage"); ti_.image = bpy.data.images.load(os.path.join(ROOT, path)); ti_.extension = "EXTEND"
    Lk.new(mp.outputs[0], ti_.inputs["Vector"])
    layers.append(ti_.outputs["Color"])
clouds = layers[0]
if len(layers) > 1:
    clouds = sock_out(mix_rgb(N, Lk, layers[0], layers[1], float(BEATS.get("bg_mid_amt", 0.32))), "RGBA")
# the plate keeps its painted light, the section gradient sets the mood: lerp(clouds, gradient, plate_mix)
pm = mix_rgb(N, Lk, clouds, grad, 0.0)
pm_fac = pm.inputs["Factor"]
# sun glow: radial falloff around a drifting point (aspect-corrected), screen-blended on top
sun_p = N.new("ShaderNodeCombineXYZ")
d_sub = N.new("ShaderNodeVectorMath"); d_sub.operation = "SUBTRACT"
Lk.new(tc.outputs["UV"], d_sub.inputs[0]); Lk.new(sun_p.outputs[0], d_sub.inputs[1])
d_sc = N.new("ShaderNodeVectorMath"); d_sc.operation = "MULTIPLY"; d_sc.inputs[1].default_value = (1.33, 1.0, 0)
Lk.new(d_sub.outputs[0], d_sc.inputs[0])
d_len = N.new("ShaderNodeVectorMath"); d_len.operation = "LENGTH"; Lk.new(d_sc.outputs[0], d_len.inputs[0])
fall = N.new("ShaderNodeMapRange"); fall.interpolation_type = "SMOOTHSTEP"
fall.inputs["From Min"].default_value = 0.7; fall.inputs["From Max"].default_value = 0.0
Lk.new(d_len.outputs["Value"], fall.inputs["Value"])
g_pow = math_node(N, "POWER", fall.outputs[0], 1.6, Lk)
g_amt = math_node(N, "MULTIPLY", g_pow.outputs[0], 0.5, Lk)
m3 = mix_rgb(N, Lk, sock_out(pm, "RGBA"), c_sun.outputs[0], g_amt.outputs[0], "SCREEN")
em = N.new("ShaderNodeEmission"); Lk.new(sock_out(m3, "RGBA"), em.inputs["Color"])
em_str = em.inputs["Strength"]
out = N.new("ShaderNodeOutputMaterial"); Lk.new(em.outputs[0], out.inputs[0])
bg.data.materials.append(bgm)


def key_bg(f, sec):
    _, ct, cm, cb, cs, g, _, *opt = sec
    pmix, bright = (opt + [None, None])[:2]
    for sock, v in ((c_top.outputs[0], hexc(ct)), (c_mid.outputs[0], hexc(cm)), (c_bot.outputs[0], hexc(cb)),
                    (c_sun.outputs[0], hexc(cs)), (g_amt.inputs[1], g),
                    (pm_fac, float(BEATS.get("plate_mix", 0.5)) if pmix is None else pmix),
                    (em_str, 1.0 if bright is None else bright)):
        key_sock(sock, f, v)


for i, s in enumerate(SECTIONS):
    if i:                                      # hold the old colours until the timing, then cross-fade over s[6] frames
        key_bg(s[0] - 1, SECTIONS[i - 1])      # (0 frames = hard change, used at the cut to the end card)
    key_bg(s[0] + s[6], s)
# the sun drifts slowly, low in the frame like the app's sunset
for f, x, y in ((0, 0.62, 0.3), (F_CARD - 1, 0.68, 0.36), (F_CARD, 0.3, 0.32), (NF, 0.34, 0.34)):
    key_sock(sun_p.inputs["X"], f, x); key_sock(sun_p.inputs["Y"], f, y)
interp(bgm.node_tree, "BEZIER")

# ── world: warm reflections on the titanium frame ──
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
wbg = w.node_tree.nodes["Background"]
wbg.inputs["Color"].default_value = hexc(BEATS.get("world", "#e8c4b4"))
wbg.inputs["Strength"].default_value = 0.6


# ── iPhone 17 Pro Max ──
def rounded_rect(bm, w, h, r, z, segs=14):
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for k in range(segs + 1):
            a = rad(a0 + 90 * k / segs)
            pts.append(bm.verts.new((cx + r * math.cos(a), cy + r * math.sin(a), z)))
    return bm.faces.new(pts)


PW, PH, PR, THICK = 1.0, 2.13, 0.16, 0.09
SW = PW - 0.06
VW, VH = 440, 956                              # app view in points (1320 × 2868 px recording)
SH = SW * VH / VW
SCR_Y = -THICK / 2 - 0.006
phone = link(bpy.data.objects.new("PHONE", None))
me = bpy.data.meshes.new("body"); bm = bmesh.new()
f0 = rounded_rect(bm, PW, PH, PR, -THICK / 2)
ext = bmesh.ops.extrude_face_region(bm, geom=[f0])
bmesh.ops.translate(bm, vec=(0, 0, THICK), verts=[v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(me); bm.free()
body = link(bpy.data.objects.new("body", me))
bev = body.modifiers.new("bevel", "BEVEL"); bev.width, bev.segments, bev.limit_method = 0.025, 5, "ANGLE"
me.shade_smooth() if hasattr(me, "shade_smooth") else None
ti = bpy.data.materials.new("titanium"); ti.use_nodes = True
bsdf = next(n for n in ti.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
bsdf.inputs["Base Color"].default_value = hexc("#9a938a"); bsdf.inputs["Metallic"].default_value = 1.0; bsdf.inputs["Roughness"].default_value = 0.3
me.materials.append(ti)
body.parent = phone
body.rotation_euler = (rad(90), 0, 0)
GAIN = float(BEATS.get("screen_gain", 1.0))


def screen_material(name):
    """Emission material playing the recording (frame offset set by the caller through the image user)."""
    sm = bpy.data.materials.new(name); sm.use_nodes = True
    n = sm.node_tree.nodes; n.clear()
    tex = n.new("ShaderNodeTexImage")
    img = bpy.data.images.load(SCREEN, check_existing=True); img.source = "MOVIE"
    tex.image = img
    tex.interpolation = "Cubic"
    iu = tex.image_user
    iu.frame_duration = 100000
    iu.use_auto_refresh = True
    iu.use_cyclic = False
    e = n.new("ShaderNodeEmission"); e.inputs["Strength"].default_value = GAIN
    o = n.new("ShaderNodeOutputMaterial")
    sm.node_tree.links.new(tex.outputs["Color"], e.inputs["Color"]); sm.node_tree.links.new(e.outputs[0], o.inputs[0])
    return sm, iu


for name, wdt, hgt, r, yoff, kind in (("glass", PW - 0.012, PH - 0.012, PR - 0.006, -THICK / 2 - 0.004, "black"),
                                      ("screen", SW, SH, PR - 0.035, SCR_Y, "screen"),
                                      ("screen_card", SW, SH, PR - 0.035, SCR_Y - 0.0004, "card")):
    if kind == "card" and BEATS.get("card_screen") is None:
        continue
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    rounded_rect(bm, wdt, hgt, r, 0)
    uv = bm.loops.layers.uv.new()
    for face in bm.faces:
        for l in face.loops:
            l[uv].uv = (l.vert.co.x / wdt + 0.5, l.vert.co.y / hgt + 0.5)
    bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new(name, me))
    ob.parent = phone
    ob.rotation_euler = (rad(90), 0, 0)
    ob.location = (0, yoff, 0)
    if kind == "black":
        me.materials.append(mat_emit("glass", "#050505")[0])
    elif kind == "screen":
        sm, iu = screen_material("screen")
        # clip frame f shows recording frame (f − frame_start) → clip frame 0 = recording second FILM0 + APP0
        iu.frame_start = -round((FILM0 + APP0) * FPS)
        me.materials.append(sm)
    else:
        # optional: on the end card the screen restarts from app second card_screen (e.g. the hovering crane again)
        sm, iu = screen_material("screen_card")
        iu.frame_start = F_CARD - round((FILM0 + float(BEATS["card_screen"])) * FPS)
        me.materials.append(sm)
        key(ob, "hide_render", 0, True); key(ob, "hide_render", F_CARD, False)
        interp(ob, "CONSTANT")
me = bpy.data.meshes.new("island"); bm = bmesh.new()
rounded_rect(bm, 0.3, 0.085, 0.0425, 0)
bm.to_mesh(me); bm.free()
isl = link(bpy.data.objects.new("island", me))
isl.parent = phone; isl.rotation_euler = (rad(90), 0, 0); isl.location = (0, -THICK / 2 - 0.009, SH / 2 - 0.075)
me.materials.append(mat_emit("island", "#000000")[0])
for i, (x, z, hh) in enumerate(((PW / 2 + 0.006, 0.45, 0.22), (-PW / 2 - 0.006, 0.55, 0.12), (-PW / 2 - 0.006, 0.3, 0.16), (-PW / 2 - 0.006, 0.08, 0.16))):
    me = bpy.data.meshes.new(f"btn{i}"); bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1); bmesh.ops.scale(bm, vec=(0.02, 0.04, hh), verts=bm.verts)
    bm.to_mesh(me); bm.free()
    b = link(bpy.data.objects.new(f"btn{i}", me)); b.parent = phone; b.location = (x, 0, z); me.materials.append(ti)

# soft contact shadow behind the phone: superellipse falloff (rounded-rect look), dusky plum, low alpha
sh = link(bpy.data.objects.new("shadow", quad("shadow")))
sh.parent = phone
sh.rotation_euler = (rad(90), 0, 0)
sh.location = (0.07, 0.35, -0.11)
sh.scale = (PW * 0.5 + 0.22, PH * 0.5 + 0.22, 1)
shm = bpy.data.materials.new("shadow"); shm.use_nodes = True; blended(shm)
N, Lk = shm.node_tree.nodes, shm.node_tree.links
N.clear()
uvn = N.new("ShaderNodeUVMap")
c0 = N.new("ShaderNodeVectorMath"); c0.operation = "SUBTRACT"; c0.inputs[1].default_value = (0.5, 0.5, 0)
Lk.new(uvn.outputs[0], c0.inputs[0])
c1 = N.new("ShaderNodeVectorMath"); c1.operation = "MULTIPLY"; c1.inputs[1].default_value = (2.0, 2.0, 0)
Lk.new(c0.outputs[0], c1.inputs[0])
c2 = N.new("ShaderNodeVectorMath"); c2.operation = "ABSOLUTE"; Lk.new(c1.outputs[0], c2.inputs[0])
sx = N.new("ShaderNodeSeparateXYZ"); Lk.new(c2.outputs[0], sx.inputs[0])
px = math_node(N, "POWER", sx.outputs["X"], 5.0, Lk); py = math_node(N, "POWER", sx.outputs["Y"], 5.0, Lk)
ad = math_node(N, "ADD", px.outputs[0], py.outputs[0], Lk)
rt = math_node(N, "POWER", ad.outputs[0], 0.2, Lk)
fo = N.new("ShaderNodeMapRange"); fo.interpolation_type = "SMOOTHSTEP"
fo.inputs["From Min"].default_value = 1.0; fo.inputs["From Max"].default_value = 0.55
Lk.new(rt.outputs[0], fo.inputs["Value"])
al = math_node(N, "MULTIPLY", fo.outputs[0], float(BEATS.get("shadow_a", 0.3)), Lk)
tr = N.new("ShaderNodeBsdfTransparent")
se = N.new("ShaderNodeEmission"); se.inputs["Color"].default_value = hexc(BEATS.get("shadow_col", "#4a2a38"))
mx = N.new("ShaderNodeMixShader")
Lk.new(al.outputs[0], mx.inputs[0]); Lk.new(tr.outputs[0], mx.inputs[1]); Lk.new(se.outputs[0], mx.inputs[2])
so = N.new("ShaderNodeOutputMaterial"); Lk.new(mx.outputs[0], so.inputs[0])
sh.data.materials.append(shm)

# ── lights: warm key from the sun side (lower right, like the app's sunset), cool sky fill from the upper left ──
key_l = bpy.data.lights.new("key", "AREA"); key_l.size = 6; key_l.energy = 620; key_l.color = hexc("#ffdcc0")[:3]
kl = link(bpy.data.objects.new("key", key_l)); kl.location = (4, -5, 3); kl.rotation_euler = (rad(60), 0, rad(40))
rim_d = bpy.data.lights.new("rim", "AREA"); rim_d.size = 4; rim_d.energy = 420; rim_d.color = hexc("#c9d6ff")[:3]
rim = link(bpy.data.objects.new("rim", rim_d)); rim.location = (-4.5, -1.5, 2.0); rim.rotation_euler = (rad(90), 0, rad(-70))


# ── soft sprites: bokeh discs and out-of-focus sakura petals (colour + opacity from the object colour) ──
def sprite_material(name, petal):
    """petal=False: bokeh disc (flat, slightly brighter soft rim). petal=True: a soft five-petal-blossom petal (rounded
    teardrop with a small notch at the tip, slightly darker pink base), out of focus."""
    m = bpy.data.materials.new(name); m.use_nodes = True; blended(m)
    N, Lk = m.node_tree.nodes, m.node_tree.links
    N.clear()
    uvn = N.new("ShaderNodeUVMap")
    c0 = N.new("ShaderNodeVectorMath"); c0.operation = "SUBTRACT"; c0.inputs[1].default_value = (0.5, 0.5, 0)
    Lk.new(uvn.outputs[0], c0.inputs[0])
    oi = N.new("ShaderNodeObjectInfo")
    if not petal:
        dl = N.new("ShaderNodeVectorMath"); dl.operation = "LENGTH"; Lk.new(c0.outputs[0], dl.inputs[0])
        d = dl.outputs["Value"]
        edge = N.new("ShaderNodeMapRange"); edge.interpolation_type = "SMOOTHSTEP"
        edge.inputs["From Min"].default_value = 0.5; edge.inputs["From Max"].default_value = 0.34
        Lk.new(d, edge.inputs["Value"])
        rimr = N.new("ShaderNodeMapRange"); rimr.interpolation_type = "SMOOTHSTEP"
        rimr.inputs["From Min"].default_value = 0.2; rimr.inputs["From Max"].default_value = 0.44
        rimr.inputs["To Min"].default_value = 0.75; rimr.inputs["To Max"].default_value = 1.0
        Lk.new(d, rimr.inputs["Value"])
        a0 = math_node(N, "MULTIPLY", edge.outputs[0], rimr.outputs[0], Lk)
        alpha = math_node(N, "MULTIPLY", a0.outputs[0], oi.outputs["Alpha"], Lk)
        col = oi.outputs["Color"]
    else:
        # teardrop: ellipse whose width grows toward the top (y), tip notch = a small circle cut at the top
        sx_ = N.new("ShaderNodeSeparateXYZ"); Lk.new(c0.outputs[0], sx_.inputs[0])
        yy = math_node(N, "ADD", sx_.outputs["Y"], 0.5, Lk)                       # 0 at the base, 1 at the tip
        wid = math_node(N, "MULTIPLY_ADD", yy.outputs[0], 0.5, Lk); wid.inputs[2].default_value = 0.35   # half-width 0.175..0.425
        wid2 = math_node(N, "MULTIPLY", wid.outputs[0], 0.5, Lk)
        xn = math_node(N, "DIVIDE", sx_.outputs["X"], wid2.outputs[0], Lk)
        yn = math_node(N, "MULTIPLY", sx_.outputs["Y"], 2.1, Lk)
        cv = N.new("ShaderNodeCombineXYZ"); Lk.new(xn.outputs[0], cv.inputs[0]); Lk.new(yn.outputs[0], cv.inputs[1])
        ln = N.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"; Lk.new(cv.outputs[0], ln.inputs[0])
        body_ = N.new("ShaderNodeMapRange"); body_.interpolation_type = "SMOOTHSTEP"
        body_.inputs["From Min"].default_value = 1.0; body_.inputs["From Max"].default_value = 0.55
        Lk.new(ln.outputs["Value"], body_.inputs["Value"])
        nv = N.new("ShaderNodeVectorMath"); nv.operation = "SUBTRACT"; nv.inputs[1].default_value = (0.0, 0.5, 0)
        Lk.new(c0.outputs[0], nv.inputs[0])
        nl = N.new("ShaderNodeVectorMath"); nl.operation = "LENGTH"; Lk.new(nv.outputs[0], nl.inputs[0])
        notch = N.new("ShaderNodeMapRange"); notch.interpolation_type = "SMOOTHSTEP"
        notch.inputs["From Min"].default_value = 0.06; notch.inputs["From Max"].default_value = 0.13
        Lk.new(nl.outputs["Value"], notch.inputs["Value"])
        a0 = math_node(N, "MULTIPLY", body_.outputs[0], notch.outputs[0], Lk)
        alpha = math_node(N, "MULTIPLY", a0.outputs[0], oi.outputs["Alpha"], Lk)
        # base of the petal a deeper pink, tip lighter
        shade = N.new("ShaderNodeMapRange"); shade.inputs["To Min"].default_value = 0.78; shade.inputs["To Max"].default_value = 1.08
        Lk.new(yy.outputs[0], shade.inputs["Value"])
        tint = mix_rgb(N, Lk, oi.outputs["Color"], (0, 0, 0, 1), 1.0, "MULTIPLY")
        sv = N.new("ShaderNodeCombineColor"); Lk.new(shade.outputs[0], sv.inputs[0]); Lk.new(shade.outputs[0], sv.inputs[1]); Lk.new(shade.outputs[0], sv.inputs[2])
        Lk.new(sv.outputs[0], sock_in(tint, "B", "RGBA"))
        col = sock_out(tint, "RGBA")
    e = N.new("ShaderNodeEmission"); Lk.new(col, e.inputs["Color"])
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    Lk.new(alpha.outputs[0], mx.inputs[0]); Lk.new(tr.outputs[0], mx.inputs[1]); Lk.new(e.outputs[0], mx.inputs[2])
    o = N.new("ShaderNodeOutputMaterial"); Lk.new(mx.outputs[0], o.inputs[0])
    return m


def drift_sprite(name, me, x, y, z, size, color, alpha, rise, sway, dx=None):
    ob = link(bpy.data.objects.new(name, me))
    ob.rotation_euler = (rad(90), 0, 0)
    ob.scale = (size, size, 1)
    ob.color = hexc(color)[:3] + (alpha,)
    dx = rng.uniform(-0.3, 0.3) if dx is None else dx
    key(ob, "location", 0, (x, y, z)); key(ob, "location", NF, (x + dx, y, z + rise))
    for fc in fcurves(ob):
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
        if fc.array_index in (0, 2):
            mo = fc.modifiers.new("NOISE"); mo.scale, mo.strength, mo.phase = rng.uniform(90, 160), sway, rng.uniform(0, 100)
    return ob


bokeh_m = sprite_material("bokeh", False)
bokeh_me = quad("bokeh"); bokeh_me.materials.append(bokeh_m)
BOKEH_COLS = BEATS.get("bokeh_cols", ["#fff1d6", "#ffe0c0", "#ffd2c6", "#ffe8dc", "#fff6e6", "#e6eeff"])
BOKEH_A = float(BEATS.get("bokeh_alpha", 1.0))
for i in range(int(BEATS.get("bokeh_n", 22))):
    y = rng.uniform(1.5, 6.0)
    side = rng.choice((-1, 1))
    x = side * rng.uniform(0.7, 4.6) if rng.random() < 0.8 else rng.uniform(-4.5, 4.5)
    z = rng.uniform(-3.2, 3.4)
    size = rng.uniform(0.1, 0.4) * (1 + y * 0.12)
    drift_sprite(f"bokeh{i}", bokeh_me, x, y, z, size, BOKEH_COLS[i % len(BOKEH_COLS)], rng.uniform(0.1, 0.28) * BOKEH_A,
                 rng.uniform(0.1, 0.35), rng.uniform(0.04, 0.1))

# sakura petals: fall slowly and sway, spin in the view plane and "tumble" (x scale oscillates like a turning petal);
# behind the phone only, kept off the end-card text column at their end-card position
petal_m = sprite_material("petal", True)
petal_me = quad("petal"); petal_me.materials.append(petal_m)
PETAL_COLS = BEATS.get("petal_cols", ["#ffa8c0", "#ff94b2", "#ffbccd", "#f2859f", "#ffc6d4"])
CX = float(BEATS.get("card_x", -1.05))
T_TOP = float(BEATS.get("title_z", 0.62)) + 0.35            # end-card text block (title top .. last line), text plane units
T_BOT = float(BEATS.get("title_z", 0.62)) - 1.45
for i in range(int(BEATS.get("petals_n", 26))):
    y = rng.uniform(0.6, 5.0)
    fall = rng.uniform(0.09, 0.18) * DUR * (0.8 + 0.08 * y)
    x = rng.choice((-1, 1)) * rng.uniform(0.8, 3.8 + y * 0.35)
    z = rng.uniform(-2.0, 3.6 + fall)
    # does it cross the end-card text column during the card? (x drifts by up to dx, sway ±0.2) → hidden on the card
    zc0, zc1 = z - fall * C_CARD / DUR, z - fall
    D1_ = float(BEATS.get("card_d", 7.4))
    k_ = D1_ / (D1_ + y)                                      # world → end-card text plane (y = 0) projection
    on_text = (abs((x + 0.8) * k_ - CX) < 1.45 and min(zc0, zc1) * k_ - 0.2 < T_TOP and max(zc0, zc1) * k_ + 0.2 > T_BOT)
    size = rng.uniform(0.05, 0.085) * (1 + y * 0.12) * float(BEATS.get("petal_size", 1.0))
    ob = drift_sprite(f"petal{i}", petal_me, x, y, z, size, PETAL_COLS[i % len(PETAL_COLS)],
                      rng.uniform(0.7, 0.95) * float(BEATS.get("petal_alpha", 1.0)), -fall, rng.uniform(0.08, 0.2),
                      dx=rng.uniform(0.4, 1.2))
    if on_text:
        key(ob, "hide_render", 0, False); key(ob, "hide_render", F_CARD, True)
        constant_hide(ob)
    spin = rng.uniform(0.5, 1.4) * rng.choice((-1, 1)) * DUR
    r0 = rng.uniform(0, 6.28)
    key(ob, "rotation_euler", 0, (rad(90), r0, 0)); key(ob, "rotation_euler", NF, (rad(90), r0 + spin, 0))
    period = rng.uniform(1.2, 2.6) * FPS
    ph = rng.uniform(0, period)
    for k in range(int(NF / (period / 2)) + 2):
        f = k * period / 2 - ph
        s_x = size * (1.0 if k % 2 == 0 else rng.uniform(0.2, 0.45))
        key(ob, "scale", round(f), (s_x, size, 1))
    for fc in fcurves(ob):
        if fc.data_path == "rotation_euler":
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"

# ── end card: title (letters fade and rise in softly), stack, author, studio ──
def font(*paths):
    for p in paths:
        p = os.path.expanduser(p)
        if os.path.exists(p):
            try:
                return bpy.data.fonts.load(p, check_existing=True)
            except RuntimeError:
                pass
    return None


TITLE_FONT = font(*([BEATS["title_font"]] if BEATS.get("title_font") else []), "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
                  "~/Library/Fonts/SFProDisplay-Bold.otf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
BODY_FONT = font("~/Library/Fonts/SFProRounded-Semibold.otf", "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
BOLD_FONT = font("~/Library/Fonts/SFProRounded-Bold.otf", "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
LABEL_FONT = font("/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf")


def fade_mat(name, color, strength=1.0):
    """Emission over transparent; returns (material, mix factor socket) so the caller keys the opacity."""
    m = bpy.data.materials.new(name); m.use_nodes = True; blended(m)
    N, Lk = m.node_tree.nodes, m.node_tree.links
    N.clear()
    e = N.new("ShaderNodeEmission"); e.inputs["Color"].default_value = hexc(color); e.inputs["Strength"].default_value = strength
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader"); mx.inputs[0].default_value = 0.0
    Lk.new(tr.outputs[0], mx.inputs[1]); Lk.new(e.outputs[0], mx.inputs[2])
    o = N.new("ShaderNodeOutputMaterial"); Lk.new(mx.outputs[0], o.inputs[0])
    return m, mx.inputs[0]


def soft_in(ob, fac, f_in, loc, alpha=1.0, rise=0.09, frames=26):
    """Fade + rise + tiny scale-up, eased (no pop)."""
    x, y, z = loc
    key(ob, "hide_render", 0, True); key(ob, "hide_render", f_in, False)
    for f, a_, dz, s_ in ((f_in, 0.0, -rise, 0.96), (f_in + frames, alpha, 0.0, 1.0)):
        key_sock(fac, f, a_)
        key(ob, "location", f, (x, y, z + dz)); key(ob, "scale", f, (s_, s_, s_))
    constant_hide(ob)


def text(name, body, fnt, size, mat, loc, align="CENTER", parent=None):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body, cu.size, cu.align_x, cu.align_y = body, size, align, "CENTER"
    if fnt:
        cu.font = fnt
    ob = link(bpy.data.objects.new(name, cu))
    ob.rotation_euler = (rad(90), 0, 0)
    ob.location = loc
    ob.parent = parent
    cu.materials.append(mat)
    return ob


def measure(body, size, fnt):
    cu = bpy.data.curves.new("m", "FONT"); cu.body, cu.size, cu.align_x = body, size, "LEFT"
    if fnt:
        cu.font = fnt
    ob = link(bpy.data.objects.new("m", cu))
    bpy.context.view_layer.update()
    xs = [v[0] for v in ob.bound_box]
    r = (min(xs), max(xs))
    bpy.data.objects.remove(ob); bpy.data.curves.remove(cu)
    return r


EX = CX
TITLE = BEATS.get("title", "Origami Crane")
T_SIZE, T_Z, T_MAXW = 0.62, float(BEATS.get("title_z", 0.62)), float(BEATS.get("title_maxw", 2.3))
full = measure(TITLE, T_SIZE, TITLE_FONT)
T_SIZE *= min(1.0, T_MAXW / (full[1] - full[0]))
full = measure(TITLE, T_SIZE, TITLE_FONT)
x_left = EX - (full[0] + full[1]) / 2                 # origin of the left-aligned title so it is centred on EX
TXT = {"title": "#2b2d58", "stack": "#4a3a5e", "by": "#9a3550", "love": "#4a3a5e", "shadow": "#ffffff",
       **BEATS.get("text_col", {})}
f_title = F_CARD + FR(float(BEATS.get("title_in", 0.1)))
step = float(BEATS.get("title_step", 0.045))
k_letter = 0
for i, ch in enumerate(TITLE):
    if ch == " ":
        continue
    pre = measure(TITLE[:i + 1], T_SIZE, TITLE_FONT)
    one = measure(ch, T_SIZE, TITLE_FONT)
    cx = x_left + pre[1] - one[1] + (one[0] + one[1]) / 2   # letter ink right edge = prefix ink right edge (kerning)
    fi = f_title + FR(step * k_letter)
    k_letter += 1
    for idx, (col, off, a_) in enumerate(((TXT["title"], (0, 0, 0), 1.0),
                                          (TXT["shadow"], (0.0, 0.02, -0.012), float(BEATS.get("title_glow_a", 0.35))))):
        m_, fac = fade_mat(f"title{i}_{idx}", col, 1.0)
        cu = bpy.data.curves.new(f"title{i}_{idx}", "FONT")
        cu.body, cu.size, cu.align_x, cu.align_y = ch, T_SIZE, "LEFT", "CENTER"
        cu.offset_x = -(one[0] + one[1]) / 2
        if TITLE_FONT:
            cu.font = TITLE_FONT
        cu.materials.append(m_)
        ob = link(bpy.data.objects.new(f"title{i}_{idx}", cu))
        ob.rotation_euler = (rad(90), 0, 0)
        soft_in(ob, fac, fi, (cx + off[0], off[1], T_Z + off[2]), a_, rise=0.12, frames=30)

BODY = [("stack", "Expo · React Native · Skia · Reanimated · Blender", BODY_FONT, 0.142, TXT["stack"], T_Z - 0.56, 0.0),
        ("by", "by Hoa Hoang · @novahoangdev", BOLD_FONT, 0.19, TXT["by"], T_Z - 0.94, 0.12),
        ("love", "From @vgangstudio with love", BODY_FONT, 0.16, TXT["love"], T_Z - 1.3, 0.24)]
for name, body_, fnt, size, col, z, dt in BODY:
    m_, fac = fade_mat(name + "_m", col, 1.0)
    ob = text(name, body_, fnt, size, m_, (EX, 0, z))
    soft_in(ob, fac, F_CARD + FR(float(BEATS.get("body_in", 0.45)) + dt), (EX, 0, z), 1.0, rise=0.07, frames=24)
# a thin vermilion rule between the title and the stack line (the crane's paper colour)
rule_m, rule_f = fade_mat("rule_m", BEATS.get("rule_col", "#d8392b"), 1.0)
me = bpy.data.meshes.new("rule"); bm = bmesh.new(); rounded_rect(bm, 0.5, 0.016, 0.008, 0, 4); bm.to_mesh(me); bm.free()
me.materials.append(rule_m)
rule = link(bpy.data.objects.new("rule", me)); rule.rotation_euler = (rad(90), 0, 0)
soft_in(rule, rule_f, F_CARD + FR(float(BEATS.get("body_in", 0.45)) - 0.1), (EX, 0, T_Z - 0.32), 1.0, rise=0.0, frames=24)

# ── camera: fixed during the demo, fixed (further back) on the end card; one straight cut ──
cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 50; cam_d.sensor_fit = "VERTICAL"; cam_d.sensor_height = 24
cam_d.clip_start = 0.05
cam = link(bpy.data.objects.new("cam", cam_d)); sc.camera = cam
cam.rotation_euler = (rad(90), 0, 0)
D0, D1 = float(BEATS.get("camera_d", 5.0)), float(BEATS.get("card_d", 7.4))
CP = BEATS.get("card_phone", {"loc": [1.15, -2.0, 0.0], "rot": [0, 0, -6]})
key(cam, "location", 0, (0, -D0, 0)); key(cam, "location", F_CARD, (0, -D1, 0))
key(phone, "location", 0, (0, 0, 0)); key(phone, "rotation_euler", 0, (0, 0, 0))
key(phone, "location", F_CARD, tuple(CP["loc"])); key(phone, "rotation_euler", F_CARD, tuple(rad(a) for a in CP["rot"]))
for idb in (cam, phone):
    interp(idb, "CONSTANT")
if LABEL:                                       # parented to the camera so it stays in a screen corner
    lb = text("label", LABEL, LABEL_FONT, 0.032, mat_emit("label_m", "#FFFFFF", 0.75)[0], (0, 0, 0), align="LEFT")
    lb.parent = cam
    lb.location, lb.rotation_euler = (-0.6, -0.43, -2.0), (0, 0, 0)

# ── compositor: soft bloom, dusky vignette, warm light leak drifting in from the lower right (the sun side) ──
tree = bpy.data.node_groups.new("promo_comp", "CompositorNodeTree")
tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
sc.compositing_node_group = tree
T, TL = tree.nodes, tree.links
rl = T.new("CompositorNodeRLayers"); rl.scene = sc
gl = T.new("CompositorNodeGlare")
gl.inputs["Type"].default_value = "Bloom"
gl.inputs["Threshold"].default_value = 0.9
gl.inputs["Size"].default_value = 0.6
gl.inputs["Strength"].default_value = 0.16
TL.new(rl.outputs["Image"], gl.inputs["Image"])
vg = T.new("CompositorNodeEllipseMask")
vg.inputs["Mask"].default_value = 0.8; vg.inputs["Value"].default_value = 0.2
vg.inputs["Size"].default_value = (1.12, 1.06)
try:
    vg.inputs["Operation"].default_value = "Add"
except TypeError as ex:
    print("ellipse op", ex)
vb = T.new("CompositorNodeBlur"); vb.inputs["Size"].default_value = (300 * PCT / 100, 300 * PCT / 100)
TL.new(vg.outputs[0], vb.inputs["Image"])
vt = T.new("ShaderNodeMix"); vt.data_type = "RGBA"; vt.blend_type = "MIX"; vt.inputs["Factor"].default_value = 1.0
sock_in(vt, "A", "RGBA").default_value = hexc(BEATS.get("vignette", "#b98aa0"))
TL.new(vb.outputs["Image"], vt.inputs["Factor"])
sock_in(vt, "B", "RGBA").default_value = (1, 1, 1, 1)
mul = T.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"; mul.inputs["Factor"].default_value = 1.0
TL.new(gl.outputs["Image"], sock_in(mul, "A", "RGBA")); TL.new(sock_out(vt, "RGBA"), sock_in(mul, "B", "RGBA"))
lk = T.new("CompositorNodeEllipseMask")
lk.inputs["Mask"].default_value = 0.0; lk.inputs["Value"].default_value = 1.0
lk.inputs["Size"].default_value = (0.6, 0.45); lk.inputs["Rotation"].default_value = rad(30)
try:
    lk.inputs["Operation"].default_value = "Add"
except TypeError:
    pass
for f, p in ((0, (1.02, -0.02)), (NF, (0.86, 0.02))):
    key_sock(lk.inputs["Position"], f, p)
lb_ = T.new("CompositorNodeBlur"); lb_.inputs["Size"].default_value = (320 * PCT / 100, 320 * PCT / 100)
TL.new(lk.outputs[0], lb_.inputs["Image"])
lc = T.new("ShaderNodeMix"); lc.data_type = "RGBA"; lc.blend_type = "MULTIPLY"; lc.inputs["Factor"].default_value = 1.0
sock_in(lc, "A", "RGBA").default_value = hexc(BEATS.get("leak", "#ffc79a"))
TL.new(lb_.outputs["Image"], sock_in(lc, "B", "RGBA"))
scr = T.new("ShaderNodeMix"); scr.data_type = "RGBA"; scr.blend_type = "SCREEN"
TL.new(sock_out(mul, "RGBA"), sock_in(scr, "A", "RGBA")); TL.new(sock_out(lc, "RGBA"), sock_in(scr, "B", "RGBA"))
for f, s in ((0, 0.12), (F_CARD // 2, 0.15), (F_CARD, 0.1), (NF, 0.12)):
    key_sock(scr.inputs["Factor"], f, s)
go = T.new("NodeGroupOutput")
TL.new(sock_out(scr, "RGBA"), go.inputs[0])

os.makedirs(OUT, exist_ok=True)
sc.render.image_settings.file_format = "PNG"
print(f"PROMO beats {os.path.basename(BEATS_PATH)} | dur {DUR:.2f}s ({NF} frames), app {APP0}..{APP_END} "
      f"(recording {FILM0 + APP0:.3f}s..{FILM0 + APP_END:.3f}s), end card @ {C_CARD:.2f}s, title font {TITLE_FONT and TITLE_FONT.name}")
STILLS = arg("--stills", "")
if STILLS:                                     # quick look at a few moments (seconds in the promo clip)
    for sec in (float(x) for x in STILLS.split(",")):
        sc.frame_set(FR(sec))
        sc.render.filepath = os.path.join(OUT, f"still_{sec:06.3f}.png")
        bpy.ops.render.render(write_still=True)
    sys.exit(0)
RANGE = arg("--range", "")                     # "a,b": render only frames a..b (parallel rendering across processes)
if RANGE:
    sc.frame_start, sc.frame_end = (int(x) for x in RANGE.split(","))
if os.environ.get("PROMO_FAST") == "1":
    sc.eevee.taa_render_samples = 8
sc.render.filepath = os.path.join(OUT, "####")
print("PROMO frames", sc.frame_end - sc.frame_start + 1)
bpy.ops.render.render(animation=True)
print("PROMO DONE", OUT)
