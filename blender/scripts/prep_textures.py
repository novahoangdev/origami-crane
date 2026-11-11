# Codex images (blender/textures/raw/*.png) -> compact textures:
#   blender/textures/hinoki_wood.jpg, shoji_paper.jpg      1024 px, for the Blender room
#   app/assets/scene/paper_front.jpg                        vermilion washi with gold flecks, 1024 px (used as is by the app)
#   app/assets/scene/paper_back.jpg                         warm cream (#f3e9d6) washi derived from the fibre texture, 1024 px
#   app/assets/scene/paper_fibre.jpg                        grayscale fibre / transmission map, mean ~0.75, 1024 px
#   app/assets/icon.png, splash-icon.png, concept/concept_crane.jpg
# Run: Blender -b --factory-startup -P blender/scripts/prep_textures.py
import os
import numpy as np
import OpenImageIO as oiio

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RAW = os.path.join(ROOT, "blender", "textures", "raw")
TEX = os.path.join(ROOT, "blender", "textures")
SCENE = os.path.join(ROOT, "app", "assets", "scene")
ASSETS = os.path.join(ROOT, "app", "assets")
os.makedirs(SCENE, exist_ok=True)


def load(name, w, h=None):
    buf = oiio.ImageBuf(os.path.join(RAW, name))
    s = buf.spec()
    h = h or w
    buf = oiio.ImageBufAlgo.resize(buf, roi=oiio.ROI(0, w, 0, h, 0, 1, 0, s.nchannels))
    return np.asarray(buf.get_pixels(oiio.FLOAT))[..., :3].copy()


def save(arr, path, quality=88):
    h, w, c = arr.shape
    spec = oiio.ImageSpec(w, h, c, "uint8")
    if path.endswith(".jpg"):
        spec.attribute("Compression", f"jpeg:{quality}")
    else:
        spec.attribute("png:compressionLevel", 9)
    out = oiio.ImageOutput.create(path)
    out.open(path, spec)
    out.write_image(np.ascontiguousarray(np.clip(arr * 255 + 0.5, 0, 255).astype(np.uint8)))
    out.close()
    print("TEX", os.path.relpath(path, ROOT), w, h, f"{os.path.getsize(path) / 1024:.0f} KB")


def seam_fix(a, band=48):
    """Cross-fade the image with a half-offset copy near the borders so it tiles without a visible seam."""
    h, w, _ = a.shape
    b = np.roll(a, (h // 2, w // 2), (0, 1))
    y = np.minimum(np.arange(h), h - 1 - np.arange(h))[:, None]
    x = np.minimum(np.arange(w), w - 1 - np.arange(w))[None, :]
    m = np.clip(np.minimum(x, y) / band, 0, 1)[..., None]
    return a * m + b * (1 - m)


lum = lambda a: a @ np.array([0.2126, 0.7152, 0.0722], np.float32)

wood = seam_fix(load("hinoki_wood.png", 1024))
save(wood, os.path.join(TEX, "hinoki_wood.jpg"), 90)
save(seam_fix(load("shoji.png", 1024)), os.path.join(TEX, "shoji_paper.jpg"), 90)

front = seam_fix(load("washi_red.png", 1024))
save(front, os.path.join(SCENE, "paper_front.jpg"), 90)

# fibre map: grayscale, contrast-stretched around a mean of 0.75 (fibres = brighter / darker streaks)
fib = seam_fix(load("washi_fibre.png", 1024))
g = lum(fib)
g = (g - g.mean()) / (g.std() + 1e-6)
g = np.clip(0.75 + 0.09 * g, 0.0, 1.0)
save(np.repeat(g[..., None], 3, 2), os.path.join(SCENE, "paper_fibre.jpg"), 90)
print("FIBRE mean", round(float(g.mean()), 3))

# back side: warm cream #f3e9d6 modulated by the fibre structure (gentle, mean stays on the target colour)
cream = np.array([0xF3, 0xE9, 0xD6], np.float32) / 255
back = cream[None, None, :] * (1.0 + 0.55 * (g[..., None] - 0.75))
save(back, os.path.join(SCENE, "paper_back.jpg"), 90)

icon = load("icon.png", 1024)
save(icon, os.path.join(ASSETS, "icon.png"))
save(icon, os.path.join(ASSETS, "splash-icon.png"))
os.makedirs(os.path.join(ROOT, "concept"), exist_ok=True)
save(load("concept_crane.png", 1024, 1536), os.path.join(ROOT, "concept", "concept_crane.jpg"), 88)
