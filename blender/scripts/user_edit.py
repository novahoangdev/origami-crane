# The edit of the "real use" screen recording (tools/rec_user.sh): numpy + ffmpeg, run with Blender's Python.
#   python3.13 blender/scripts/user_edit.py --raw render/promo/user_v7/raw.mov --beats blender/scripts/beats/user_v7.json \
#       --out render/promo/origami-crane-user-9x19-v7.mp4 --work render/promo/user_v7
# 1. the VFR simulator recording → 60 fps CFR (real time)
# 2. app t = 0 from the magenta sync marker (tools/filmstart.sh), the marker painted out
# 3. the moment the launch animation starts (first frame that differs from the home screen) and the app icon on the home
#    screen (normalised cross-correlation against app/assets/icon.png over a few sizes): an iOS-style touch dot is drawn
#    on the icon for the tap that opens the app
# 4. the music: mix_calm.py on the beat sheet (its events are app seconds), delayed so its t = 0 sits on app t = 0
# 5. 1080 × 2346, 60 fps, H.264 + AAC, ending FADE s after the end chord
import json, os, subprocess, sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
argv = sys.argv[1:]
arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
RAW, BEATS_P, OUT, WORK = (os.path.join(ROOT, arg(k)) for k in ("--raw", "--beats", "--out", "--work"))
BEATS = json.load(open(BEATS_P))
FF = "ffmpeg"
SCREEN = os.path.join(WORK, "screen.mp4")
W0, H0 = 1320, 2868


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def frames(path, t0, dur, w, h, fps=None, gray=True):
    vf = f"scale={w}:{h}" + (f",fps={fps}" if fps else "") + (",format=gray" if gray else "")
    raw = run([FF, "-v", "error", "-ss", str(t0), "-t", str(dur), "-i", path, "-vf", vf, "-f", "rawvideo", "-pix_fmt",
               "gray" if gray else "rgb24", "-"], capture_output=True).stdout
    c = 1 if gray else 3
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, c).astype(np.float32)


# 1. CFR
run([FF, "-v", "error", "-y", "-i", RAW, "-vf", "fps=60", "-c:v", "libx264", "-preset", "fast", "-crf", "12", "-pix_fmt",
     "yuv420p", SCREEN])
# 2. app t = 0
fs_out = run([os.path.join(ROOT, "tools/filmstart.sh"), SCREEN], capture_output=True, text=True, cwd=ROOT).stdout.strip()
FS = float(fs_out.splitlines()[-1])
print(f"USER film start (app t = 0) {FS:.3f} s")
# 3. launch moment + icon position
f = frames(SCREEN, 0, min(FS, 6.0), 165, 358, gray=True)
d = np.abs(f - f[0]).mean(axis=(1, 2, 3))
Z = (int(np.argmax(d > 4.0)) if (d > 4.0).any() else 60) / 60.0
home = frames(SCREEN, max(0.0, Z - 0.3), 0.02, 330, 717, gray=True)[0, :, :, 0]
icon_png = os.path.join(ROOT, "app/assets/icon.png")
best = (-2, 0, 0, 0)
for px in range(40, 60, 2):          # icon side in this 1/4-scale frame (iPhone home icons ≈ 64 pt = 192 px → 48)
    ic = frames(icon_png, 0, 1, px, px, gray=True)[0, :, :, 0]
    ic = ic - ic.mean()
    icn = np.sqrt((ic ** 2).sum()) + 1e-6
    H_, W_ = home.shape
    # sliding normalised cross-correlation (FFT for the numerator, box sums for the local norms)
    F1 = np.fft.rfft2(home, (H_ + px, W_ + px))
    F2 = np.fft.rfft2(ic[::-1, ::-1], (H_ + px, W_ + px))
    num = np.fft.irfft2(F1 * F2, (H_ + px, W_ + px))[px - 1:H_, px - 1:W_]
    cs = np.cumsum(np.cumsum(np.pad(home, ((1, 0), (1, 0))), 0), 1)
    cs2 = np.cumsum(np.cumsum(np.pad(home ** 2, ((1, 0), (1, 0))), 0), 1)
    box = lambda c: c[px:, px:] - c[:-px, px:] - c[px:, :-px] + c[:-px, :-px]
    s1, s2 = box(cs), box(cs2)
    var = np.maximum(s2 - s1 ** 2 / (px * px), 1e-6)
    ncc = num / (icn * np.sqrt(var))
    ncc[var < px * px * 100.0] = -2.0   # flat wallpaper patches (std < 10 levels) give meaningless scores
    j = int(np.argmax(ncc))
    y, x = divmod(j, ncc.shape[1])
    if ncc[y, x] > best[0]:
        best = (float(ncc[y, x]), x + px / 2, y + px / 2, px)
score, cx, cy, px = best
cx, cy = cx * 4, cy * 4               # → 1320 × 2868
print(f"USER launch at {Z:.3f} s, icon at ({cx:.0f}, {cy:.0f}) size {px * 4} px, match {score:.2f}")
# the touch dot image (same look as the in-app USERSIM dot, 3x)
R = 66
yy, xx = np.mgrid[0:2 * R, 0:2 * R] + 0.5
r = np.hypot(xx - R, yy - R)
disc = np.clip(R - 6 - r + 0.5, 0, 1)
ring = np.clip(1 - np.abs(r - (R - 6)) / 2.2, 0, 1)
rgba = np.zeros((2 * R, 2 * R, 4), np.float32)
a = np.maximum(disc * 0.34, ring * 0.7)
rgba[..., :3] = 255
rgba[..., 3] = a * 255
DOT = os.path.join(WORK, "touch_dot.png")
run([FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{2 * R}x{2 * R}", "-i", "-", DOT],
    input=rgba.astype(np.uint8).tobytes())
# 4. music
AUD = os.path.join(ROOT, BEATS["audio"])
run(["/Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13", os.path.join(ROOT, "blender/scripts/mix_calm.py"),
     "--beats", os.path.relpath(BEATS_P, ROOT)], cwd=ROOT)
# 5. edit
END = FS + float(BEATS["app_end"]) + float(BEATS.get("card", 3.0)) - 0.4
t_on, t_off = max(0.0, Z - 0.3), Z + 0.05
vf = (f"[0:v]split[s0][s1];[s1]crop=44:44:44:0[pt];[s0][pt]overlay=0:0:enable='between(t,{FS - 0.7:.3f},{FS + 0.7:.3f})'[m];"
      f"[1:v]format=rgba,fade=t=in:st=0:d=0.06:alpha=1[dot];"
      f"[m][dot]overlay={cx - R:.0f}:{cy - R:.0f}:enable='between(t,{t_on:.3f},{t_off:.3f})',"
      f"scale=1080:2346:flags=lanczos,setsar=1,fps=60,format=yuv420p,fade=t=out:st={END - 0.8:.3f}:d=0.8[v];"
      f"[2:a]adelay={int(FS * 1000)}|{int(FS * 1000)},atrim=0:{END:.3f},afade=t=out:st={END - 1.2:.3f}:d=1.2[a]")
run([FF, "-v", "error", "-y", "-i", SCREEN, "-loop", "1", "-i", DOT, "-i", AUD, "-filter_complex", vf, "-map", "[v]",
     "-map", "[a]", "-t", f"{END:.3f}", "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-r", "60",
     "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", OUT])
print(f"USER → {os.path.relpath(OUT, ROOT)} ({END:.1f} s)")
