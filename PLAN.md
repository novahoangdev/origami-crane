# Origami Crane: fold it, then let it fly

> **Status (05/11, v9 after the user's review of v8):** "errors mid-fold (dark wedges in the narrow-legs kite), many errors in the reverse folds, and now the crane is thin and flat". v9:
> - The crack fill never worked: RN Skia applies only the last image filter given as siblings in a `<Paint>`, so dilate + erode was just an erode. Nested (`<Morphology erode><Morphology dilate/></Morphology>`), it closes the slits between a leg's layers in the reverse folds (3.5 pt while folding) and the hinge cracks of the living crane (≤ 5 pt: a bigger kernel over the whole layer cost ~40 % of the frame).
> - The exact (Newell) order now runs during the folds too; parallel layers are decided by their plane offsets alone.
> - Softer cel bands (shadow band 0.46 instead of 0.32, wider wrap): a flap turning away from the sun mid-fold is a deeper red, not a near-black wedge.
> - Volume: the living crane's body layers are pressed to 40 % (was 3 %) and wings to 10 %, and the body puffs out below the wing hinge like a real crane's; the order is computed on the un-puffed copy (`wf`), since the puff bends every body facet and would split the plane groups into single facets (20 ms → 5 ms a tick in the dev build).
> - Recording: a stale "host recording in progress" on the Rec sim (no recorder running) is cleared by rebooting it.

> **Status (05/11, v8 after the user's review of v6/v7):** "the crane still looks see-through in flight (check every frame until it is fixed); fake crease lines on the sheet; the rays are ugly and fake; the chase camera is not smooth"; plus a new format: a real-use screen recording. v8:
> - See-through crane, found frame by frame on 10 fps sim recordings: (1) the per-facet painter's sort flipped wing/body order from frame to frame as the wings swing about their hinges (the neck's inner part drawn over the wing): the living crane is now ordered exactly (Newell on plane groups: a group is drawn after another when it lies wholly on the camera's side of the other's plane, topological order, `newellOrder` in fold/mesh.ts, ~5 ms); (2) the bake keeps every layer 4 mm apart, so the body was ~3 cm thick with 1 cm gaps between the neck, body and wing stacks and edge-on the sky showed through: once alive the layers are pressed together (`thin` in applyLife: body/neck/tail toward the mid plane, each wing shifted with its hinge and squeezed toward its hinge plane); (3) the remaining hairline cracks along the hinges are closed by a morphological close of the silhouette in the paper's red under the paper, its radius following the crane's size on screen. Checked on every frame of the Release take from the awakening to the vanish.
> - Fake creases on the flat sheet: the layer-edge shadows now come only from the sheet's real cut edges (uv on the border of the square), not from every triangle edge; off once the crane is alive.
> - Sky: no god-ray fan and no lens ghosts under the open sky (rays only pour down indoors).
> - Chase camera: no hard clamps (soft min/max) and the rig follows its target with a critically smooth lag.
> - **Real-use screen recording** (`tools/rec_user.sh vN`, `EXPO_PUBLIC_USERSIM=1`): home screen → touch dot on the app icon → splash → the interactive app with hints, step dots and captions, operated by a scripted user through the real pan/tap handlers (thinking pauses, uneven curved swipes, a hesitant half swipe that springs back on steps 4 and 10, iOS-style touch dots), the crane flies off, a tap on "Tap to fold another" and the next (indigo) sheet. Edit in `blender/scripts/user_edit.py` (icon found by template match, sync marker painted out, the calm piano under it). → `render/promo/origami-crane-user-9x19-v8.mp4` (1080×2346, 60 fps, 69.7 s, −16 LUFS).
> - **Clips v8:** take 14:31, film start 2.18 → `origami-crane-demo-v8.mp4` (4:3) + `origami-crane-screen-9x19-v8.mp4`.

> **Status (05/11, v6 after the user's review of v5):** "the sound is still loud, noisy and unpleasant; the crane and the light are still broken; the crane looks see-through; the paper still has a little shadow trouble". v6:
> - See-through crane: a diagnostic render (front facets red, back facets blue) showed the frosted veil was the paper's back side, drawn with a paler back texture; the stacked layer edges alternated front/back and striped. The back is now the same vermilion as the front (the front texture mirrored and shifted). Light through the paper fades over the first three folds (a folded stack barely transmits; left bright, the crane glowed like a lantern you could see into); the awakening sweep, the inner glow and the awakening light column are much fainter.
> - Layer edges: every facet is drawn after a faint copy of itself shifted 0.7/1.0 pt (`stackEdges` in fold/mesh.ts, flagged in the texcoords), so each layer's cut edge throws a thin soft shadow on the layer below, exact along the edges; edge-on slivers cast none.
> - Sound: −16 LUFS (was −14), the bass note softer and a −5 dB low shelf under 160 Hz (energy below 150 Hz −23 dB, was −14; the soap-bubbles piano that the user liked sits at −17), a lighter left hand (4 notes a bar), a fainter hammer, and no noise-based effects at all (no paper crinkles, whoosh or breeze), only a few faint birds.
> - The chase camera steps aside earlier as the crane leaves through the panel.
> - **Clips v6:** take 2 at 12:48 (take 1 froze, retaken automatically), film start 2.07 → `render/promo/origami-crane-demo-v6.mp4` (4:3) and `render/promo/origami-crane-screen-9x19-v6.mp4` (9:19), 42.6 s, −16 LUFS, peak −3.4 dB.

> **Status (05/11, v5 after the user's review of v4):** the music still snagged, the shadows on the paper while folding were broken, the crane looked broken in flight (seen from behind: edge-on sticks) and the vanishing glow was an ugly blown-out disc with rays. v5:
> - Calm piano score (`blender/scripts/mix_calm.py`, beat sheet `"mixer": "mix_calm.py"`): one steady tempo (73 BPM, the bar fitted so the end card lands on a downbeat), D major only, felt piano broken chords + a simple tune, a slow string pad, celesta on the awakening and the vanish, a rolled Dadd9 on the card; SFX much softer (−9 dB). Modelled on the soap-bubbles calm piano the user liked. v4 bent its tempo around every fold and modulated twice.
> - Paper self-shadowing off (`OCCLUDE`): it darkened whole triangles, so shadow edges on the paper stepped along the triangulation. The floor shadow is dilated 1 pt in a layer before the blur (the facet seams showed as light lines inside it) and a little darker; the leaf/lattice dapples on the paper fade out once the crane lifts off (pale facet polygons on the body).
> - Flight: outside it banks and sweeps across the view in front of the veranda (seen in profile, wings beating), then curves back toward the sun and climbs; the dissolve shrinks it smoothly. The vanish is a small soft warm glow (no rays, no clipping, no burst particles).
> - **Final clips v5:** take 12:03 (05/11, the first take's recorder timestamps bunched up, 65–85 frames/s, so the picture drifted against the events: rec.sh now warns on that too), film start 2.15, events checked on `render/promo/v5/evcheck.jpg` → `render/promo/origami-crane-demo-v5.mp4` (4:3, 1920×1440) and `render/promo/origami-crane-screen-9x19-v5.mp4` (720×1564), both 60 fps, 42.6 s, −13.9 LUFS, peak −2.0 dB.
> - Two formats per take, as in soap-bubbles: the 4:3 promo and `render/promo/origami-crane-screen-9x19-vN.mp4` (the bare screen recording with the same soundtrack, `tools/screen_video.sh`, run by `final.sh`).

> **Status (05/11, v4 after the user's review of v3):** the v3 clip was too fast, the rim light on the paper edges looked bad, the effects cheap, the music grating and the leaves fake. v4:
> - Demo storyboard v4: frame 1 = the room in a wide shot with the flat sheet lying in the sunbeam, a slow push in (0.6 → 3.4 s), then one fold every ~1.55 s (fold 1 at 4.9 s, fold 14 = awaken at 25.0 s), take-off 27.4, climb out through the panel 32.2, vanish 37.2, app_end 39.6 (no hovering-crane intro, no rewind).
> - Restraint: rim light, cut-edge highlight and star glints removed; ink line thinner (dilate 0.8) and fainter; fewer, smaller bursts; one soft floor ring; the vanish is a quiet halo + soft rays (no cross spikes, no ring); the wing-tip glitter is sparse scattered dust (the old even emission traced a dotted line along the flight path).
> - Leaves: Codex paintings (red maple, green maple, sakura) keyed to alpha (`tools/leaf_key.py`), mapped onto curled + twisted planes and rendered tumbling in Blender Eevee (`blender/scripts/leaf_sprites.py`, 16 frames, back-lit) → `app/assets/fx/leaves.png`; flutter motion in `stepPool` (fast and flat-on, then gliding edge-on, gusty drift).
> - Clip music: a sampled score (Steinway, strings, flute, horns from the local Logic/GarageBand library, hall reverb, no drums) timed from the beat-sheet events (`blender/scripts/mix_clip.py`, `beats/v4.json`), −14 LUFS.
> - Fixed a dashed line of wrong texels along the sky/hills skirt boundaries: image samples inside per-pixel branches in `layerFx` (undefined derivatives in the 2×2 quads straddling the edge); the shader now samples unconditionally and blends with step/smoothstep.
> - Frame rate: the first v4 takes ran at ~14 fps on screen while the UI thread reported 60 (CPU 130 %). Bisected by hiding draw groups: the paper mesh. Its washi textures were sampled with mipmaps, but the paper shader decodes its texture coordinates with floor() (facet light packed into them), so the derivatives jump at every facet edge; the paper textures now sample without mipmaps (`FLAT`), back to 60 fps.
> - **Final clip v4:** take 00:20 (05/11) on the Rec sim, 60 fps raw throughout, film start 2.62, events checked on `render/promo/v4/evcheck.jpg`; rendered 00:45 → `render/promo/origami-crane-demo-v4.mp4` (1920×1440, 60 fps, 42.6 s, −14.0 LUFS, peak −1.4 dB) + `origami-crane-sheet-v4.jpg`.
> - The Rec sim had been deleted; recreated as "Origami Crane Rec 17 Pro Max" (`notes/udid_rec.txt`). `final.sh` records 47 demo s (SECS) for the longer storyboard.

> **Status (04/11, 07:17):** M0–M4 ✅, M5 ✅ (audio, polish, new-sheet flow, more papers) · **art direction v2: anime Japanese house** (user reference: Ghibli/Shinkai-style painterly short).
> - Scene: multiplane anime backgrounds painted with Codex (sky with pink-edged cumulus drifting, hazy hills + village, garden with maples, hydrangeas, stone lantern, house frame with an open panel), each a real 3D plane so the camera has parallax; painted engawa floor split into base + sun + lattice + leaves passes so the leaf dapples sway and twinkle on the floor and on the paper; outside ground plane.
> - Paper: anime cel bands + ink outline (dilated silhouette), star glints on the facet mirroring the sun, gold flecks, awakening light sweep.
> - Life v2: levitate + glance, 1¼ banking loops around the room (flap-flap-glide) with a glitter trail off the wing tips, then out through the open panel; the camera chases it outside and looks up into the sunset sky (god rays, swallows crossing), the crane shrinks into the light with a flash; sakura petals and leaves drift past; warm flash cut back to the room as a new sheet slides in.
> - Demo storyboard (EXPO_PUBLIC_DEMO=1): frame 1 = finished crane hovering in the beam (glitter, rim light, swallows outside), rewind to the flat sheet (2.3 s), ghost finger folds 14 steps (4.8–14.85), awaken ring of light + glow sweep, loops, out through the opening (camera follows, looks through the panel, stops on the veranda edge), flies into the sunset and vanishes (~24.8), petals; app_end ≈ 27 s. Events logged as `EVT name t`.
> - In-app sound (expo-audio, `src/fx/sfx.ts`, synthesised by `tools/sfx.py`): paper creases per fold and while dragging, rewind whoosh, awakening bell arpeggio (D yo-scale), take-off whoosh + wing beats, vanishing shimmer, garden ambience loop with distant birds, the odd furin (glass wind chime) ding. The demo clock now starts on the first fully drawn frame (all images decoded), so demo t = 0 is the first visible frame. The swipe hint has marching dashes, a warm glow and a comet gliding along the swipe.
> - Polish 01:10: the crane keeps a faint inner glow while alive (hovering intro, flight) and glows like a paper lantern when backlit under the sunset sky (sky fill, no lattice shade, ink line fades so edge-on wings don't read as dark sticks); warmer red-tinted shadow; demo clock gated on every layer image (frame 1 is the full picture); fixed the band torn along the bottom of the sky shot (ground strip now starts in front of the eye); half the falling leaves are maple orange.
> - Polish 01:25: the crane vanishes in a starburst bloom (thin uneven rays, cross spikes, halo, expanding ring of light, `vanishFx`); outside the chase camera steps 0.85 to the right for a three-quarter view of the wings; the sky and hills layers run on below their painted bottom (blurred skirt) and the backstop is a sky-to-forest gradient, so no empty band ever shows through the gaps in the garden trees; demo warm-up holds the clock at 0 for 24 frames while the whole first frame is built and drawn (pipelines compile), so frame 1 is complete.
> - Fold bake v3 (agent, 01:30): steps 1–11 and 14 validate on every keyframe (no stretch, no tears, no crossings, layers 0.004 apart): narrow legs fold every connected layer, petal folds use the exact thick-layer motion, the wings of step 14 hinge on their stack faces so the final crane no longer interpenetrates; the reverse folds (12, 13) open the point into a V with a bendable fan at the base (crossings hidden inside the stacks — accepted: a fully valid version needs the body opened ~90° or a different crease). The 4-way triangle subdivision is now off by default (`FOLD_SUBDIV=1` to restore): 292 facets instead of 1,168, scene tick 5–12 ms instead of 50–110 ms in the debug build. Dev perf log: `PERF_LOG` in `src/debug.ts`.
> - Demo frame 1 is now an establishing shot of the anime house (camera dollied back and lowered: the open panel framed by the eave and pillars, the furin hanging in it, garden and hills beyond, the crane hovering in the beam); it dollies in to the folding close-up during the rewind (`WIDE_DIST/WIDE_PITCH/WIDE_LIFT`).
> - Small things: the painted furin swings on its string (layerFx rotation around the pivot) and its shadow on the floor swings with it; the near edge of the sun patch has a penumbra (`tools/feather_mask.py`); stronger god rays in the establishing shot; the swipe hint is at least 110 pt long (steps 13–14 projected to a tiny arrow); "Tap to fold another" only appears once the crane has vanished; `START_STEP` debug knob for the interactive app. Promo v2 test take: 60/60 from second 2, frame 1 = establishing shot.
> - Awakening pillar (`awakenFx`): a soft column of warm light rises from the floor through the crane with motes drifting up in it, over the 1.9 s before take-off.
> - Recording hardening (02:40): Release test takes t3/t4 on the Rec sim. t3 froze at the awakening because the soap-bubbles session started its rec script mid-take (it SIGSTOPs other sims' apps) and `check.txt` still said 60/60 (encoder noise), so rec.sh now writes `rawcheck.txt` from the raw .mov frame timestamps and warns on frozen seconds. In Release the canvas reached the screen ~0.18 s after the clock started, so the warm-up is now 90 frames and `filmstart.sh` warns when frame 1 would be blank; t4: film start 2.13, full picture, 60 fps throughout. Default take length 37 demo s. Final take plan: start ≈ 07:00 so the 30-min full render is done ≈ 07:30 (commands in `notes/promo.md`).
> - The interactive app also opens on the room and glides in to the sheet (first 3 s); petals/leaves passing the lens are capped at 80 pt; the launch is cream from the native splash (expo-splash-screen, `#fdf0d7` = the splash image's own background) through the first frame, instead of white then dark brown. `tools/final.sh vN` runs the final take end to end (waits for other sessions' recorders, retakes frozen takes).
> - New app icon in the anime look (Codex: the glowing washi crane in the sunlit room; the old photo icon is kept in `blender/textures/icon_raw/icon_photo.png`). Release + Debug rebuilt 03:24. Half-res preview of the whole clip from Release take t5: `render/promo/origami-crane-demo-t5-preview.mp4` (with a t5 label; the final has none).
> - **Final clip v3:** take 06:50 on the Rec sim (Release, TS 0.5), rawcheck clean (no frozen second), film start 2.48 with the full establishing shot, events checked on `render/promo/v3/evcheck.jpg`; rendered 07:16 → `render/promo/origami-crane-demo-v3.mp4` (1920×1440, 60 fps, 30.45 s, −14.2 LUFS, peak −1.5 dB) + `origami-crane-sheet-v3.jpg`, caption `render/promo/caption.txt`.
> - More papers (M5): in the interactive app every new sheet takes the next paper: vermilion washi → indigo chiyogami (gold flecks kept) → sakura pink, re-dyed in the paper shader from the same washi texture (luminance pattern kept), with matching ink line and shadow colours (`PAPERS` in CraneScene). The demo always folds the vermilion one.
> - Running: fold mid-motion polish (agent: squash folds already continuous), promo pipeline + music/SFX port from Soap Bubbles (agent). Clip version to be recorded ≈ 07:20 as asked.

An iPhone demo of about 15 seconds to post on X. A square of vermilion washi lies on a hinoki table in a tea room, morning sun glowing through a shoji screen behind it. Swipe along the dashed fold line and the paper folds under your finger, step by step, into a traditional paper crane. On the last fold the crane comes alive: it lifts its neck, flaps its wings, hops, takes off through the sunbeam and flies out of the screen. The paper is real-time 3D: every facet is lit by the window, glows red where the sun shines through it (you can see the kozo fibres and the darker inner layers), and casts a soft red-tinted shadow on the table.

Plan written on 03/11/2026. The fold sequence is built and baked in Blender (Python, headless); the app scrubs it with the finger (Reanimated) and renders the paper as a real 3D mesh in Skia (`Vertices` + runtime shaders for translucency, paper sides, crease shading and the shadow).

---

## 0. Summary

**Clip story.** Frame 1 is the finished crane mid-flap in the sunbeam, glowing red, its shadow sweeping the table — then a quick rewind of the folds plays it back as the "how": the flat sheet, a diagonal fold, the square base collapsing, the petal fold lifting like a flower, the neck and tail rising, the head tucking, the wings opening. The crane flaps, hops and flies up past the camera; the camera tilts up to follow it into the light. Gold flecks in the paper sparkle as it turns.

**Architecture: baked fold keyframes + real-time 3D rendering in Skia.**

- **Blender** (`blender/scripts/fold_crane.py`) builds the paper as a mesh whose edges include every crease of the crane crease pattern (exact, by bisecting a square with each crease line), then computes the fold sequence as dense keyframes: simple folds are hinge rotations of the moving facets about the crease line (axis lifted by the stack height so layers land on top with real thickness), the collapses (square base, petal folds) are rigid single-vertex / bar-and-hinge solutions. Each keyframe is stored as shape keys for preview renders and exported to `app/assets/fold/crane.bin` (Float32 positions) + `crane.json` (uv, triangles, step ranges, swipe hints, wing mask and hinge axes).
- **The app** interpolates between the two keyframes around the current progress, applies wing flap / hop / flight transforms, projects with a perspective camera that can move (gyro, finger orbit, flight follow), sorts triangles back to front (painter's algorithm; layers have real thickness so sorting is stable) and draws one `Vertices` mesh (unshared vertices so every facet is flat-shaded). Per-facet light values are packed into the texture coordinates (`u + 2·floor(a·255)`), so a single runtime shader gets paper uv + facet light without per-vertex colours.
- **The table and the room** are also drawn in 3D: the table top is a textured grid (Blender top-down render with the window light baked in), the shoji wall and room behind are a far textured plane — so the camera can tilt up and follow the crane with true parallax.

### Stack

Same as `../soap-bubbles/app` (and `../showcase/neon-sign`, `../showcase/goku-vs-frieza`): Expo SDK 58, RN 0.88.1, `react-native-skia` 3.8.x, Reanimated 4.7.1 + worklets 0.13, gesture-handler 3.3, expo-haptics, expo-dev-client. Dev build, no Expo Go. `react-native-webgpu` only if the Skia mesh path cannot hold 60 fps (it would give a depth buffer and shadow maps). Blender 5.2.2 at `/Applications/Blender.app`, headless `-b -P` only (the Blender MCP belongs to another project). FFmpeg for the promo.

**2D assets: generate freely with Codex, no need to ask** (washi texture with kozo fibres and gold flecks, hinoki wood, shoji paper, bamboo leaf shadow gobo, concept art, app icon):

```sh
codex exec --skip-git-repo-check -s workspace-write "Generate <description>, no text. Save it as <name>.png in the current directory and print its absolute path."
```

If Codex can't save the file, take the image from `~/Library/Application Support/orca/codex-accounts/*/home/generated_images/`. Compress images before putting them in `app/assets` or `blender/textures`.

---

## 1. Art direction

- Tone: a quiet Japanese tea room at 8 a.m. Warm low sun through a shoji screen behind the table (back light), bamboo-leaf shadows drifting on the shoji, dust motes in the beam. Soft, calm, photographic (50 mm, f/2.8, gentle depth of field on the room).
- Paper: vermilion washi (`#d8392b` → deep `#9e1f1a` in shadow) on the front, warm cream (`#f3e9d6`) on the back, a few gold flecks that glint. When light passes through: glowing orange-red with visible fibres, every extra layer inside shows as a darker shape.
- Table: pale hinoki wood, fine grain, a sharp warm patch of sunlight with the shoji grid shadow, cool soft shade elsewhere.
- Crease lines stay visible after unfolding (a faint line + shading change), like real paper.
- UI: only a dashed fold line + a soft arrow showing where to swipe, a tiny step counter (dots) at the bottom. Hidden in the promo recording.

## 2. Experience and storyboard

| Seconds | Shot | Interaction / effect |
|---|---|---|
| 0–1.5 | Frame 1 = best moment: finished crane mid-flap in the beam, glowing | Wings flap, shadow sweeps, flecks glint |
| 1.5–2 | Rewind (paper unfolds fast) to the flat sheet | Scrub backwards with a light whoosh |
| 2–4 | Diagonal fold, fold again | Finger swipes along the arrow, paper follows 1:1, crease haptic |
| 4–6 | Square base collapses | Four flaps fold in, layers glow differently |
| 6–8.5 | Petal folds (front and back) | The flap lifts like a flower petal, light through the lifting layer |
| 8.5–10.5 | Narrow legs, reverse-fold neck and tail, head | Neck and tail swing up |
| 10.5–11.5 | Pull the wings open | The crane stands, slight wobble |
| 11.5–14.5 | It comes alive: flap, hop, take off, fly out of the screen | Camera tilts up following it, light flare as it crosses the sun |
| 14.5– | End card (promo) | |

Gestures: pan along the hint arrow scrubs the current step (projected finger travel / hint length → progress), release > 45 % completes with a spring, otherwise springs back. Haptic tick at the crease, soft rumble while a collapse moves. Tap the finished crane → it flies; tap empty table → a new sheet slides in. Two-finger drag = orbit the camera (and gyro parallax on device).

## 3. Fold sequence (Blender)

Paper = 2 × 2 world units, centred at the origin on the table (z up, table plane z = 0). Coloured side down at the start so that the finished crane shows the colour outside (traditional), thickness 0.004 per layer.

| Step | Fold | Motion |
|---|---|---|
| 1 | Valley fold diagonal (triangle) | hinge 180° |
| 2 | Fold in half again (small triangle) | hinge 180° |
| 3 | Open and squash both flaps → square base | single-vertex collapse (analytic) / squash |
| 4 | Kite folds front, fold top down, unfold (precreases) | hinges |
| 5 | Petal fold front | bar-and-hinge (degree-1) |
| 6 | Turn over, kite + petal back → bird base | as 4–5 |
| 7 | Narrow both legs (front and back) | hinges |
| 8 | Inside-reverse fold neck and tail up | rigid reverse fold |
| 9 | Reverse fold the head | rigid |
| 10 | Fold the wings down and open slightly | hinge (also the flap axis) |

Output (`tools/fold.sh` → `blender/scripts/fold_crane.py`):

- `app/assets/fold/crane.bin`: Float32 LE, `keyframes × vertexCount × 3` positions (world units).
- `app/assets/fold/crane.json`: `vertexCount`, `triCount`, `keyframes`, `uv` (paper coords 0..1), `tris`, `steps[] {name, from, to, hint: {a: [x,y,z], b: [x,y,z]}}` (keyframe range per swipe and the swipe arrow in world space at the start of the step), `wings {mask: per-vertex −1/0/+1, axisL: [p, q], axisR: [p, q]}`, `head` point, `layerThickness`.
- `render/fold_preview/step_NN.png`: Cycles preview of each step's end state for checking.

## 4. Rendering (app)

- **Mesh step (UI-thread worklet, no allocation per frame):** progress `p` (float keyframe index) → lerp positions → crane life transforms (wing rotation about the hinge axes, body bob, flight path) → camera view/projection → per-triangle normal, depth, visible side (winding), light terms → sort indices by depth (insertion sort from last frame's order: near-sorted, O(n)) → write `Float32Array` vertices + textures in sorted order → `modify()`.
- **Paper shader (`paper.ts`):** washi albedo texture (front vermilion with gold flecks, back cream), fibre map, per-facet terms decoded from texcoords: `diffuse = max(n·L, 0)`, `trans = max(−n·L, 0)` (light from behind the visible side), layer count hint. Colour = albedo · (ambient + diffuse · sun) + transmission · sunColour · paperTint · fibre(uv) (fibres and inner layers darker), gold fleck specular when `reflect(v, n)` meets the sun, crease darkening near facet edges via a crease-distance channel.
- **Shadow (`shadow.ts`):** the same triangles projected onto z = 0 along the sun direction, drawn into a group with `<Blur>` (sigma grows with height above the table) and a sharper contact layer, tinted by transmitted red light at low alpha (coloured shadow).
- **Table and room:** table grid (24 × 24 quads, perspective-correct enough) textured with `table.jpg`; shoji wall plane textured with `backdrop.jpg`, light shafts + dust motes in a soft additive layer; post: bloom on the beam, vignette, grain.
- **Life:** after step 10 a spring "wake" (neck up, wings flap 2.2 Hz with ease, tail bob), hop, take-off along a spline that rises toward the camera and exits top-right; the camera tilts up 25° following it; shadow shrinks and fades with height; a flare when the crane crosses the sun.

## 5. Blender scene

`blender/scripts/build_scene.py` + `render_passes.py` (Cycles), camera exactly as `app/assets/scene/layout.json`:

- Room: hinoki table (Codex wood texture + bump), shoji screen wall behind (emissive-backlit paper with a bamboo-leaf gobo), tatami edge, warm sun from behind-left through the shoji, cool sky fill.
- Passes: `bg.jpg` (1320 × 2868, from the app camera, no paper; reference for the look), `table.jpg` (top-down ortho of the table region with the sun patch baked), `backdrop.jpg` (the shoji wall plane, as seen from the camera, slightly blurred), `layout.json` (camera, sun direction/colour, ambient, table and backdrop extents).

## 6. Folder structure

```
origami-crane/
  PLAN.md  README.md
  blender/scripts/  build_scene.py  render_passes.py  fold_crane.py  promo.py
  blender/textures/ raw/ (Codex)
  tools/            build.sh  fold.sh  embed.sh  rec.sh  promo.sh  sheet.sh
  notes/            versions.md  promo.md  udid.txt
  render/           fold_preview/  promo/
  app/
    src/scene/CraneScene.tsx   Canvas, layers, clock, gestures, demo
    src/scene/camera.ts        view/projection, orbit, follow
    src/fold/model.ts          load crane.json/bin, keyframe lerp
    src/fold/mesh.ts           per-frame worklet: transform, light, sort, pack
    src/fold/life.ts           wake, flap, hop, flight
    src/shaders/paper.ts  shadow.ts  room.ts  post.ts
    src/ui/FoldHint.tsx  Steps.tsx
    src/demo/script.ts
```

## 7. Demo mode and X clip

- `EXPO_PUBLIC_DEMO=1` plays the storyboard of section 2 with scripted swipes (ghost finger), seeded; `EXPO_PUBLIC_TIMESCALE=0.5` for smooth recordings (`tools/rec.sh` compresses time back to 60 fps CFR), as in Soap Bubbles.
- Clip rules (latest from Neon Sign / Pumpkin / Soap Bubbles): 4:3 1920 × 1440, 60 fps; the phone stays still in the centre, one straight cut to the end card; frame 1 is the most beautiful moment; no status bar, no extra UI in the recording. End card: "Origami Crane", "Expo · React Native · Skia · Reanimated · Blender", "by Hoa Hoang · @novahoangdev", "From @vgangstudio with love". Audio: calm, catchy koto/marimba hook + paper SFX (crease, rustle, flutter), −14 LUFS, true peak ≤ −1 dBTP.
- **Not recorded until asked.**

## 8. Milestones (each one recordable)

| Milestone | Content | Done when |
|---|---|---|
| **M0** | Plan, Codex assets, Blender room + passes (preview), app scaffold, sim, 3D table + flat paper on screen | Paper lies on the table on the sim |
| **M1** | Fold sequence v1 from Blender (steps 1–3 at least), mesh renderer (lerp, sort, pack), paper shader (two sides, diffuse, transmission), swipe-to-fold with hints + haptics | Fold the first steps by finger |
| **M2** | Full crane sequence (14 swipes: each turn-over is its own step), shadow with colour, fibres and inner layers when backlit, crease lines, gold flecks | A crane, folded by finger, looks like real paper |
| **M3** | Life: wake, flap, hop, flight out of the screen, camera follow, flare, dust motes, post | The crane flies away |
| **M4** | Demo mode, final Blender render, Release perf 60/60, (promo pipeline when asked) | Storyboard plays by itself |
| **M5** | Audio, polish rounds, second paper (indigo / gold chiyogami), new-sheet flow | |

## 9. Risks

- **The crane geometry** (squash and petal folds are not single hinges): exact crease edges + per-step rigid solutions; fallback = per-facet slerp between flat-folded keyframe states with a lift to avoid interpenetration.
- **Painter's sort artefacts on coincident layers:** real layer thickness in the bake, sort by triangle centroid depth with a small per-layer bias; split long triangles if needed.
- **Per-frame CPU cost** (~1–3 k triangles in a worklet): no allocation, near-sorted insertion sort, Float32Array vertices (copied in one go by Skia 3.8).
- **Graphite pitfalls:** no `BlurMask` on animated paths, `makeTextureImage()` for big images, check SkSL offline (`tools/perf/sksl_check.mjs` pattern from neon-sign).
- **Reanimated Release crashes:** every helper called from a worklet is `"worklet"`, declared before use, numeric only.

## 10. Defaults chosen (changeable)

- Display name "Origami Crane", bundle id `dev.hoanghoa.origamicrane`.
- Device: only the project's sim "Origami Crane 17 Pro Max" (UDID `AC781F88-417C-4594-958A-156653F473D2`, iOS 27.0), portrait, 1320 × 2868 px = 440 × 956 pt. iOS only. Metro port 8093 (8092 is taken by Soap Bubbles).
- English in code, comments and docs (the repo may go public; same rule as Soap Bubbles); chat stays Vietnamese.
- No git repo and no push.
