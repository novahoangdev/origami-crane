"""Tumbling leaf / petal sprites for the falling leaves in the app (headless):
  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P blender/scripts/leaf_sprites.py
Each keyed painting (blender/textures/leaves_raw/keyed/*.png, from tools/leaf_key.py) is mapped onto a gently curled, subdivided
plane, lit by a warm low sun from behind-above (so the leaf glows through when it turns into the light) plus a soft sky fill,
and rendered while it flips through one full turn about a tilted axis (FRAMES frames, transparent film).
Output: render/leaf_frames/<name>_NN.png; tools/leaf_atlas.sh packs them into app/assets/fx/leaves.png (rows = kinds).
"""
import math
import os

import bpy

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SRC = os.path.join(ROOT, "blender", "textures", "leaves_raw", "keyed")
OUT = os.path.join(ROOT, "render", "leaf_frames")
os.makedirs(OUT, exist_ok=True)
FRAMES = 16
RES = 160
KINDS = [  # name, curl (rad), size (plane half-extent), tilt of the tumble axis (rad)
    ("leaf_maple_red", 0.55, 1.0, 0.45),
    ("leaf_maple_green", 0.45, 1.0, 0.35),
    ("petal_sakura", 0.9, 0.9, 0.6),
]

sc = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
# render engine: Eevee (identifier differs between versions)
for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        sc.render.engine = eng
        break
    except TypeError:
        pass
sc.render.resolution_x = sc.render.resolution_y = RES
sc.render.film_transparent = True
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
sc.view_settings.view_transform = "Standard"
world = bpy.data.worlds.new("w")
sc.world = world
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs[0].default_value = (0.55, 0.5, 0.62, 1)  # soft violet-peach sky fill
bg.inputs[1].default_value = 0.9

cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 2.6
cam = bpy.data.objects.new("cam", cam_data)
sc.collection.objects.link(cam)
cam.location = (0, -6, 0)
cam.rotation_euler = (math.pi / 2, 0, 0)
sc.camera = cam

sun_d = bpy.data.lights.new("sun", "SUN")
sun_d.energy = 5.0
sun_d.color = (1.0, 0.82, 0.58)
sun = bpy.data.objects.new("sun", sun_d)
sc.collection.objects.link(sun)
sun.rotation_euler = (math.radians(-35), math.radians(20), 0)  # from behind-above: backlight through the leaf
fill_d = bpy.data.lights.new("fill", "SUN")
fill_d.energy = 1.8
fill_d.color = (0.85, 0.88, 1.0)
fill = bpy.data.objects.new("fill", fill_d)
sc.collection.objects.link(fill)
fill.rotation_euler = (math.radians(70), 0, math.radians(-30))
# a soft front light too, so the back of a leaf turning away from the sun never goes dark grey
front_d = bpy.data.lights.new("front", "SUN")
front_d.energy = 2.2
front_d.color = (1.0, 0.9, 0.82)
front = bpy.data.objects.new("front", front_d)
sc.collection.objects.link(front)
front.rotation_euler = (math.radians(90), 0, 0)  # shining along +y, toward the camera's view
back_d = bpy.data.lights.new("back", "SUN")
back_d.energy = 2.2
back_d.color = (1.0, 0.9, 0.82)
back = bpy.data.objects.new("back", back_d)
sc.collection.objects.link(back)
back.rotation_euler = (math.radians(-90), 0, 0)


def leaf_material(name):
    img = bpy.data.images.load(os.path.join(SRC, name + ".png"))
    img.alpha_mode = "STRAIGHT"
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    bsdf = nt.nodes.new("ShaderNodeBsdfDiffuse")
    trans = nt.nodes.new("ShaderNodeBsdfTranslucent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix2 = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Color"])
    nt.links.new(tex.outputs["Color"], trans.inputs["Color"])
    mix.inputs[0].default_value = 0.5  # half the light passes through the leaf
    nt.links.new(bsdf.outputs[0], mix.inputs[1])
    nt.links.new(trans.outputs[0], mix.inputs[2])
    nt.links.new(tex.outputs["Alpha"], mix2.inputs[0])
    nt.links.new(tr.outputs[0], mix2.inputs[1])
    nt.links.new(mix.outputs[0], mix2.inputs[2])
    nt.links.new(mix2.outputs[0], out.inputs["Surface"])
    for attr, val in (("blend_method", "HASHED"), ("surface_render_method", "DITHERED")):
        try:
            setattr(m, attr, val)
        except (AttributeError, TypeError):
            pass
    try:
        m.use_backface_culling = False
    except AttributeError:
        pass
    return m


for name, curl, half, tilt in KINDS:
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=24, y_subdivisions=24, size=2 * half)
    leaf = bpy.context.active_object
    leaf.data.materials.append(leaf_material(name))
    # a gentle cup along the leaf and a little twist, like a real dry leaf
    bend = leaf.modifiers.new("bend", "SIMPLE_DEFORM")
    bend.deform_method = "BEND"
    bend.angle = curl
    bend.deform_axis = "Y"
    twist = leaf.modifiers.new("twist", "SIMPLE_DEFORM")
    twist.deform_method = "TWIST"
    twist.angle = 0.25
    twist.deform_axis = "Y"
    # face the camera at frame 0, then tumble about a tilted axis
    pivot = bpy.data.objects.new("pivot", None)
    sc.collection.objects.link(pivot)
    leaf.parent = pivot
    leaf.rotation_euler = (math.pi / 2, 0, 0)
    for f in range(FRAMES):
        u = f / FRAMES
        pivot.rotation_euler = (2 * math.pi * u, tilt * math.sin(2 * math.pi * u), 0.35 * math.sin(4 * math.pi * u + 0.6))
        bpy.context.view_layer.update()
        sc.render.filepath = os.path.join(OUT, f"{name}_{f:02d}.png")
        bpy.ops.render.render(write_still=True)
    print("LEAF", name, FRAMES, "frames")
    bpy.data.objects.remove(leaf, do_unlink=True)
    bpy.data.objects.remove(pivot, do_unlink=True)
