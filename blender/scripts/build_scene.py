# Builds the tea room in code (Cycles) and saves blender/room.blend.
#   - pale hinoki table, top plane z = 0, x in [-6, 6], y in [-7, 6.85] (the app needs x in [-5, 5], y in [-6, 7])
#   - shoji wall at y = 7: four sliding panels (wooden frame + kumiko lattice + translucent washi), one clear glass band
#     (yukimi window) in the second panel: the sun passes through it and lays a sharp patch with the lattice shadow on the table
#   - bamboo outside (culms + leaf sprays, between the sun and the shoji): leaf shadows on the paper, dapples in the patch
#   - warm low sun from behind-left-above (light travels along SUN_TRAVEL), cool sky fill for the shade
#   - the app camera: pos (0, -4.2, 5.6), target (0, 0.3, 0), vertical fov 42 deg, 1320x2868
# World units = paper units (the sheet is 2 x 2 at the origin), z up, the camera looks toward +y.
# Layout data used by render_passes.py is stored in scene["oc"].
#
# Scene knobs (env vars): OC_SUN (sun strength), OC_SKY (fill strength), OC_EXPOSURE
# Run: Blender -b --factory-startup -P blender/scripts/build_scene.py
import bpy, bmesh, math, os, random
from mathutils import Vector, Matrix

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TEX = os.path.join(ROOT, "blender", "textures")
BLEND = os.path.join(ROOT, "blender", "room.blend")
rng = random.Random(7)
rad = math.radians

CAM_POS, CAM_TARGET, FOV_Y = Vector((0, -4.2, 5.6)), Vector((0, 0.3, 0)), 42.0
SCREEN_PX = (1320, 2868)

SUN_TRAVEL = Vector((0.45, -1.0, -0.75)).normalized()       # direction the light travels
SUN_DIR = -SUN_TRAVEL                                       # from the scene toward the sun
SUN_COLOR = (1.0, 0.80, 0.58)
SUN_STRENGTH = float(os.environ.get("OC_SUN", "8.0"))
SUN_ANGLE = 0.7                                             # deg: sharp shadows
SKY_COLOR = (0.50, 0.62, 1.0)
SKY_STRENGTH = float(os.environ.get("OC_SKY", "0.36"))
EXPOSURE = float(os.environ.get("OC_EXPOSURE", "-0.3"))

WALL_Y = 7.0                                                # shoji paper plane
PANEL_X = [-14.5, -10.0, -5.5, -1.0, 3.5, 8.0, 12.5]              # panel edges (the backdrop shows x in [-9, 9])
Z0, Z1 = -0.5, 11.6                                         # shoji bottom / top (kamoi beam above)
STILE, RAIL, BOTTOM = 0.2, 0.2, 0.9                         # frame widths (bottom rail is a tall koshi board)
KUMIKO_W = 0.055
COLS, ROWS = 5, 11
GLASS_PANEL, GLASS_ROWS = 2, (3, 7)                         # panel index, kumiko rows [a, b) that are clear glass

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def coll(name):
    c = bpy.data.collections.new(name)
    sc.collection.children.link(c)
    return c


def obj(name, data, c):
    ob = bpy.data.objects.new(name, data)
    c.objects.link(ob)
    return ob


def img(name, colorspace="sRGB"):
    im = bpy.data.images.load(os.path.join(TEX, name), check_existing=True)
    im.colorspace_settings.name = colorspace
    return im


class M:
    """Tiny node-building helper."""

    def __init__(self, name):
        self.m = bpy.data.materials.new(name)
        self.m.use_nodes = True
        self.nt = self.m.node_tree
        self.n = self.nt.nodes
        self.bsdf = next(n for n in self.n if n.type == "BSDF_PRINCIPLED")
        self.out = next(n for n in self.n if n.type == "OUTPUT_MATERIAL")

    def node(self, t, **kw):
        nd = self.n.new(t)
        for k, v in kw.items():
            if k in nd.inputs:
                nd.inputs[k].default_value = v
            else:
                setattr(nd, k, v)
        return nd

    def link(self, a, b):
        self.nt.links.new(a, b)

    def set(self, sock, x):
        if isinstance(x, (int, float, tuple)):
            sock.default_value = x
        else:
            self.link(x, sock)


def box(name, c, mn, mx, mat):
    """Axis-aligned box mesh from corner mn to corner mx."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector([mn[i] + (v.co[i] + 0.5) * (mx[i] - mn[i]) for i in range(3)])
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    return obj(name, me, c)


def plane(name, c, verts, mat, uv=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], [list(range(len(verts)))])
    if uv:
        lay = me.uv_layers.new()
        for i, l in enumerate(me.loops):
            lay.data[i].uv = uv[l.vertex_index]
    me.materials.append(mat)
    return obj(name, me, c)


# ── render settings ──
sc.render.engine = "CYCLES"
sc.cycles.samples = 64
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 8
sc.cycles.diffuse_bounces = 4
sc.cycles.transparent_max_bounces = 16
sc.render.resolution_x, sc.render.resolution_y = SCREEN_PX
sc.view_settings.view_transform = os.environ.get("OC_VIEW", "Khronos PBR Neutral")
for look in [os.environ.get("OC_LOOK", "AgX - Punchy"), "AgX - Base Contrast", "None"]:
    try:
        sc.view_settings.look = look
        break
    except TypeError:
        pass
sc.view_settings.exposure = EXPOSURE

# ── world: cool sky fill for lighting; camera rays (seen through the glass) get a bright warm garden haze ──
w = bpy.data.worlds.new("world")
sc.world = w
w.use_nodes = True
nt = w.node_tree
bg_out = next(n for n in nt.nodes if n.type == "OUTPUT_WORLD")
for n in list(nt.nodes):
    if n.type != "OUTPUT_WORLD":
        nt.nodes.remove(n)
lp = nt.nodes.new("ShaderNodeLightPath")
sky = nt.nodes.new("ShaderNodeBackground")
sky.inputs["Color"].default_value = SKY_COLOR + (1,)
sky.inputs["Strength"].default_value = SKY_STRENGTH
haze = nt.nodes.new("ShaderNodeBackground")
haze.inputs["Color"].default_value = (1.0, 0.86, 0.66, 1)
haze.inputs["Strength"].default_value = 2.4
mixw = nt.nodes.new("ShaderNodeMixShader")
nt.links.new(lp.outputs["Is Camera Ray"], mixw.inputs[0])
nt.links.new(sky.outputs[0], mixw.inputs[1])
nt.links.new(haze.outputs[0], mixw.inputs[2])
nt.links.new(mixw.outputs[0], bg_out.inputs["Surface"])

# ── materials ──
# hinoki table: Codex texture, grain along y (toward the wall), 5 units per tile, faint grain bump
mt = M("hinoki")
tc = mt.node("ShaderNodeTexCoord")
mp = mt.node("ShaderNodeMapping")
mp.inputs["Scale"].default_value = (1 / 5.0, 1 / 5.0, 1)
mt.link(tc.outputs["Object"], mp.inputs["Vector"])
it = mt.node("ShaderNodeTexImage", image=img("hinoki_wood.jpg"))
mt.link(mp.outputs[0], it.inputs["Vector"])
hsv = mt.node("ShaderNodeHueSaturation")
hsv.inputs["Saturation"].default_value = float(os.environ.get("OC_WOOD_SAT", "1.1"))
hsv.inputs["Value"].default_value = 0.95
mt.link(it.outputs["Color"], hsv.inputs["Color"])
mt.link(hsv.outputs[0], mt.bsdf.inputs["Base Color"])
mt.bsdf.inputs["Roughness"].default_value = 0.32
mt.bsdf.inputs["Specular IOR Level"].default_value = 0.5
bw = mt.node("ShaderNodeRGBToBW")
mt.link(it.outputs["Color"], bw.inputs[0])
bump = mt.node("ShaderNodeBump")
bump.inputs["Strength"].default_value = 0.08
bump.inputs["Distance"].default_value = 0.01
mt.link(bw.outputs[0], bump.inputs["Height"])
mt.link(bump.outputs[0], mt.bsdf.inputs["Normal"])
MAT_TABLE = mt.m

# shoji frame / kumiko: slightly darker, aged hinoki
mf = M("shoji_wood")
mf.bsdf.inputs["Base Color"].default_value = (0.47, 0.33, 0.21, 1)
mf.bsdf.inputs["Roughness"].default_value = 0.6
MAT_WOOD = mf.m
mk = M("kamoi_wood")
mk.bsdf.inputs["Base Color"].default_value = (0.30, 0.20, 0.12, 1)
mk.bsdf.inputs["Roughness"].default_value = 0.55
MAT_DARK = mk.m

# washi on the shoji: mostly translucent (the sun and the leaf shadows glow through), a little front diffuse
ms = M("shoji_paper")
for n in list(ms.n):
    if n.type == "BSDF_PRINCIPLED":
        ms.n.remove(n)
tcs = ms.node("ShaderNodeTexCoord")
mps = ms.node("ShaderNodeMapping")
mps.inputs["Scale"].default_value = (1 / 3.0, 1 / 3.0, 1)
ms.link(tcs.outputs["Object"], mps.inputs["Vector"])
its = ms.node("ShaderNodeTexImage", image=img("shoji_paper.jpg"))
ms.link(mps.outputs[0], its.inputs["Vector"])
tint = ms.node("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
tint.inputs["Factor"].default_value = 1.0
ins = [s for s in tint.inputs if s.type == "RGBA"]
ms.link(its.outputs["Color"], ins[0])
ins[1].default_value = (1.0, 0.97, 0.92, 1)
tcol = [s for s in tint.outputs if s.type == "RGBA"][0]
tr = ms.node("ShaderNodeBsdfTranslucent")
ms.link(tcol, tr.inputs["Color"])
df = ms.node("ShaderNodeBsdfDiffuse")
ms.link(tcol, df.inputs["Color"])
mxs = ms.node("ShaderNodeMixShader")
mxs.inputs[0].default_value = 0.15
ms.link(tr.outputs[0], mxs.inputs[1])
ms.link(df.outputs[0], mxs.inputs[2])
ms.link(mxs.outputs[0], ms.out.inputs["Surface"])
MAT_PAPER = ms.m

# clear glass: transparent (shadow rays pass straight through, no caustics noise), faint warm tint
mg = M("glass")
for n in list(mg.n):
    if n.type == "BSDF_PRINCIPLED":
        mg.n.remove(n)
tp = mg.node("ShaderNodeBsdfTransparent")
tp.inputs["Color"].default_value = (0.97, 0.96, 0.93, 1)
mg.link(tp.outputs[0], mg.out.inputs["Surface"])
MAT_GLASS = mg.m

# plaster wall above the kamoi
mw = M("plaster")
mw.bsdf.inputs["Base Color"].default_value = (0.62, 0.54, 0.42, 1)
mw.bsdf.inputs["Roughness"].default_value = 0.9
MAT_PLASTER = mw.m

# bamboo: leaves translucent green (glow when backlit), culms waxy green-yellow
ml = M("bamboo_leaf")
ml.bsdf.inputs["Base Color"].default_value = (0.16, 0.30, 0.07, 1)
ml.bsdf.inputs["Roughness"].default_value = 0.5
lt = ml.node("ShaderNodeBsdfTranslucent")
lt.inputs["Color"].default_value = (0.35, 0.55, 0.10, 1)
mxl = ml.node("ShaderNodeMixShader")
mxl.inputs[0].default_value = 0.4
ml.link(ml.bsdf.outputs[0], mxl.inputs[1])
ml.link(lt.outputs[0], mxl.inputs[2])
ml.link(mxl.outputs[0], ml.out.inputs["Surface"])
MAT_LEAF = ml.m
mc = M("bamboo_culm")
mc.bsdf.inputs["Base Color"].default_value = (0.32, 0.38, 0.12, 1)
mc.bsdf.inputs["Roughness"].default_value = 0.35
MAT_CULM = mc.m

# ── table ──
C_TABLE = coll("table")
table = box("table_top", C_TABLE, (-6, -7, -0.6), (6, 7.0, 0.0), MAT_TABLE)

# ── shoji wall ──
C_SHOJI = coll("shoji")
D_FRAME = (WALL_Y - 0.16, WALL_Y + 0.02)                    # frame depth in y (room side in front of the paper)
D_KUMIKO = (WALL_Y - 0.07, WALL_Y - 0.002)
for pi in range(len(PANEL_X) - 1):
    x0, x1 = PANEL_X[pi], PANEL_X[pi + 1]
    # alternate panels sit on two rails (a slight depth offset, as real sliding shoji)
    off = 0.0 if pi % 2 == 0 else -0.05
    fy = (D_FRAME[0] + off, D_FRAME[1] + off)
    box(f"stile_l{pi}", C_SHOJI, (x0, fy[0], Z0), (x0 + STILE, fy[1], Z1), MAT_WOOD)
    box(f"stile_r{pi}", C_SHOJI, (x1 - STILE, fy[0], Z0), (x1, fy[1], Z1), MAT_WOOD)
    box(f"rail_t{pi}", C_SHOJI, (x0, fy[0], Z1 - RAIL), (x1, fy[1], Z1), MAT_WOOD)
    box(f"koshi{pi}", C_SHOJI, (x0, fy[0], Z0), (x1, fy[1], Z0 + BOTTOM), MAT_WOOD)
    ix0, ix1, iz0, iz1 = x0 + STILE, x1 - STILE, Z0 + BOTTOM, Z1 - RAIL
    cw, rh = (ix1 - ix0) / COLS, (iz1 - iz0) / ROWS
    ky = (D_KUMIKO[0] + off, D_KUMIKO[1] + off)
    for ci in range(1, COLS):
        x = ix0 + ci * cw
        box(f"kv{pi}_{ci}", C_SHOJI, (x - KUMIKO_W / 2, ky[0], iz0), (x + KUMIKO_W / 2, ky[1], iz1), MAT_WOOD)
    for ri in range(1, ROWS):
        z = iz0 + ri * rh
        wbar = KUMIKO_W * (2.2 if pi == GLASS_PANEL and ri in GLASS_ROWS else 1.0)   # thicker rails around the glass
        box(f"kh{pi}_{ri}", C_SHOJI, (ix0, ky[0], z - wbar / 2), (ix1, ky[1], z + wbar / 2), MAT_WOOD)
    # paper (and the glass band): quads at the paper plane, split at the glass rows
    py = WALL_Y + off
    if pi == GLASS_PANEL:
        za, zb = iz0 + GLASS_ROWS[0] * rh, iz0 + GLASS_ROWS[1] * rh
        bands = [(iz0, za, MAT_PAPER), (za, zb, MAT_GLASS), (zb, iz1, MAT_PAPER)]
        sc["glass_rect"] = [ix0, ix1, za, zb]
    else:
        bands = [(iz0, iz1, MAT_PAPER)]
    for bi, (a, b, mat) in enumerate(bands):
        plane(f"paper{pi}_{bi}", C_SHOJI, [(ix0, py, a), (ix1, py, a), (ix1, py, b), (ix0, py, b)], mat)
# kamoi beam + plaster wall above, a sill on the table side
box("kamoi", C_SHOJI, (-16, WALL_Y - 0.35, Z1), (14, WALL_Y + 0.1, Z1 + 0.7), MAT_DARK)
box("plaster", C_SHOJI, (-16, WALL_Y + 0.05, Z1 + 0.7), (14, WALL_Y + 0.3, 16), MAT_PLASTER)
box("shiki", C_SHOJI, (-16, WALL_Y - 0.3, Z0 - 0.6), (14, WALL_Y + 0.1, Z0), MAT_DARK)

# ── bamboo outside (between the sun and the shoji) ──
C_BAMBOO = coll("bamboo")


def wall_hit_to_world(tx, tz, y):
    """Point at depth y whose sun shadow lands on the wall at (tx, WALL_Y, tz)."""
    t = (y - WALL_Y) / -SUN_TRAVEL.y
    return Vector((tx, WALL_Y, tz)) - SUN_TRAVEL * t


def culm(name, base, h, r):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=r, radius2=r * 0.85, depth=h)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MAT_CULM)
    ob = obj(name, me, C_BAMBOO)
    ob.location = base + Vector((0, 0, h / 2))
    # nodes: thin rings every ~3 units
    z = rng.uniform(0.5, 2.5)
    while z < h:
        me2 = bpy.data.meshes.new(name + "_n")
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=r * 1.12, radius2=r * 1.12, depth=0.12)
        bm.to_mesh(me2)
        bm.free()
        me2.materials.append(MAT_CULM)
        o2 = obj(name + "_n", me2, C_BAMBOO)
        o2.location = base + Vector((0, 0, z))
        z += rng.uniform(2.6, 3.4)
    return ob


# culms whose shadows fall on the paper as soft vertical bands (none crosses the glass window's light)
for i, (tx, y, r) in enumerate([(4.9, 10.5, 0.28), (7.4, 11.5, 0.22), (-7.6, 10.8, 0.25), (1.9, 12.5, 0.18)]):
    p = wall_hit_to_world(tx, 0, y)
    culm(f"culm{i}", Vector((p.x, y, -6)), 30, r)

leaf_bm = bmesh.new()
twig_bm = bmesh.new()


def leaf(base, direction, length, width):
    """Lanceolate bamboo leaf: a flat strip that tapers to a point, slightly arched, facing roughly the wall."""
    d = direction.normalized()
    side = d.cross(Vector((0, 1, 0)))
    if side.length < 1e-3:
        side = Vector((1, 0, 0))
    side.normalize()
    side = (side + Vector((0, rng.uniform(-0.3, 0.3), 0))).normalized()
    n = 8
    left, right = [], []
    for k in range(n + 1):
        t = k / n
        wdt = width * (math.sin(math.pi * min(1, t * 1.15)) ** 0.7) * (1 - t) ** 0.25 * (1.0 if t < 1 else 0)
        c = base + d * (length * t) + Vector((0, 0, -0.25 * length * t * t))   # droop
        left.append(leaf_bm.verts.new(c + side * wdt / 2))
        right.append(leaf_bm.verts.new(c - side * wdt / 2))
    for k in range(n):
        leaf_bm.faces.new((left[k], right[k], right[k + 1], left[k + 1]))


def twig(a, b, r=0.025):
    geom = bmesh.ops.create_cone(twig_bm, cap_ends=False, segments=5, radius1=r, radius2=r * 0.7, depth=(b - a).length)
    rot = (b - a).to_track_quat("Z", "Y").to_matrix().to_4x4()
    bmesh.ops.transform(twig_bm, matrix=Matrix.Translation((a + b) / 2) @ rot, verts=geom["verts"])


def spray(tx, tz, y, n, spread=1.0, hang=0.0):
    """A branch tip with n leaves fanning out; (tx, tz) is where its shadow lands on the wall."""
    o = wall_hit_to_world(tx, tz, y)
    root = o + Vector((rng.uniform(-0.8, 0.8), rng.uniform(-0.3, 0.3), rng.uniform(0.5, 1.0)))
    twig(root, o)
    ang0 = rng.uniform(0, 2 * math.pi)
    for k in range(n):
        a = ang0 + (k - n / 2) * 0.55 * spread + rng.uniform(-0.2, 0.2)
        dirv = Vector((math.cos(a), rng.uniform(-0.25, 0.25), math.sin(a) * 0.6 - 0.55 - hang))
        leaf(o + Vector((0, rng.uniform(-0.1, 0.1), 0)), dirv, rng.uniform(1.3, 2.1), rng.uniform(0.2, 0.3))


# leaf shadow targets on the wall (x, z): dense top right, a branch top left, a few tips over the glass window
targets = [(rng.uniform(1.5, 9.5), rng.uniform(5.5, 12.0)) for _ in range(16)]
targets += [(rng.uniform(-9.5, -6.0), rng.uniform(6.0, 12.0)) for _ in range(6)]
targets += [(rng.uniform(4.0, 9.0), rng.uniform(1.0, 5.0)) for _ in range(4)]
targets += [(-4.6, 7.4), (-2.6, 8.2), (-1.4, 7.0)]
for tx, tz in targets:
    spray(tx, tz, rng.uniform(8.2, 10.2), rng.randint(4, 7))
me = bpy.data.meshes.new("leaves")
leaf_bm.to_mesh(me)
leaf_bm.free()
me.materials.append(MAT_LEAF)
obj("leaves", me, C_BAMBOO)
me = bpy.data.meshes.new("twigs")
twig_bm.to_mesh(me)
twig_bm.free()
me.materials.append(MAT_CULM)
obj("twigs", me, C_BAMBOO)

# soft out-of-focus garden far behind the glass (camera rays only: no light, no shadow)
mgd = M("garden")
for n in list(mgd.n):
    if n.type == "BSDF_PRINCIPLED":
        mgd.n.remove(n)
nz = mgd.node("ShaderNodeTexNoise")
nz.inputs["Scale"].default_value = 0.18
nz.inputs["Detail"].default_value = 3.0
tcg = mgd.node("ShaderNodeTexCoord")
mgd.link(tcg.outputs["Object"], nz.inputs["Vector"])
rmp = mgd.node("ShaderNodeValToRGB")
el = rmp.color_ramp.elements
el[0].position, el[0].color = 0.35, (0.34, 0.42, 0.20, 1)
el[1].position, el[1].color = 0.66, (1.0, 0.86, 0.60, 1)
mid = el.new(0.5)
mid.color = (0.74, 0.76, 0.48, 1)
mgd.link(nz.outputs["Fac"], rmp.inputs["Fac"])
em = mgd.node("ShaderNodeEmission")
em.inputs["Strength"].default_value = 2.2
mgd.link(rmp.outputs["Color"], em.inputs["Color"])
mgd.link(em.outputs[0], mgd.out.inputs["Surface"])
garden = plane("garden", C_BAMBOO, [(-60, 40, -30), (60, 40, -30), (60, 40, 50), (-60, 40, 50)], mgd.m)
for k in ("visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter", "visible_shadow"):
    setattr(garden, k, False)

# ── lights ──
C_LIGHT = coll("lights")
sun = bpy.data.lights.new("sun", "SUN")
sun.energy = SUN_STRENGTH
sun.color = SUN_COLOR
sun.angle = rad(SUN_ANGLE)
so = obj("sun", sun, C_LIGHT)
so.rotation_euler = SUN_TRAVEL.to_track_quat("-Z", "Y").to_euler()
# cool soft bounce from the room behind the camera (an open engawa / white wall), faint
fill = bpy.data.lights.new("room_fill", "AREA")
fill.shape = "RECTANGLE"
fill.size, fill.size_y = 30, 12
fill.energy = float(os.environ.get("OC_FILL", "550"))
fill.color = (0.70, 0.80, 1.0)
fo = obj("room_fill", fill, C_LIGHT)
fo.location = (0, -16, 7)
fo.rotation_euler = (Vector((0, 2, 0)) - Vector(fo.location)).to_track_quat("-Z", "Y").to_euler()
fo.visible_camera = False
fo.visible_glossy = True

# ── cameras ──
cd = bpy.data.cameras.new("app_cam")
cd.sensor_fit = "VERTICAL"
cd.sensor_height = 24.0
cd.lens = 12.0 / math.tan(rad(FOV_Y / 2))
cd.clip_start, cd.clip_end = 0.05, 200
cam = obj("app_cam", cd, sc.collection)
cam.location = CAM_POS
cam.rotation_euler = (CAM_TARGET - CAM_POS).to_track_quat("-Z", "Y").to_euler()
sc.camera = cam

cd = bpy.data.cameras.new("table_cam")
cd.type = "ORTHO"
cd.ortho_scale = 13.0
cd.clip_start, cd.clip_end = 0.1, 100
oc = obj("table_cam", cd, sc.collection)
oc.location = (0, 0.5, 30)
oc.rotation_euler = (0, 0, 0)

cd = bpy.data.cameras.new("backdrop_cam")
cd.type = "ORTHO"
cd.ortho_scale = 18.0
cd.clip_start, cd.clip_end = 0.1, 100
bc = obj("backdrop_cam", cd, sc.collection)
bc.location = (0, -20, (-0.5 + 13) / 2)
bc.rotation_euler = (rad(90), 0, 0)

sc["oc"] = {
    "camera": {"pos": list(CAM_POS), "target": list(CAM_TARGET), "fovY": FOV_Y, "up": [0, 0, 1]},
    "sun_dir": [round(c, 4) for c in SUN_DIR],
    "sun_color": list(SUN_COLOR),
    "sun_strength": SUN_STRENGTH,
    "sky_color": list(SKY_COLOR),
    "sky_strength": SKY_STRENGTH,
    "screen_px": list(SCREEN_PX),
}
bpy.ops.wm.save_as_mainfile(filepath=BLEND, compress=True)
print("SAVED", BLEND, "glass", list(sc["glass_rect"]))
