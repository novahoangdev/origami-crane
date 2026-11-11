import React, { useEffect, useMemo, useState } from "react";
import { Image as RNImage, StyleSheet, Text, View, type LayoutChangeEvent } from "react-native";
import {
  Atlas, Blur, Canvas, Circle, DashPathEffect, FilterMode, Morphology, Oval, Rect, Fill, Group, ImageShader, MipmapMode, Paint, Path, Shader, Skia, Vertices, type SkImage, useColorBuffer, useImage, useRSXformBuffer, useRectBuffer,
  LinearGradient,
  RadialGradient,
  vec,
} from "react-native-skia";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import { SensorType, useAnimatedSensor, useDerivedValue, useFrameCallback, useSharedValue, type SharedValue } from "react-native-reanimated";
import { scheduleOnRN } from "react-native-worklets";
import { initSfx, sfxEvent } from "../fx/sfx";
import * as Haptics from "expo-haptics";
import { loadFold } from "../fold/model";
import { buildGrid, buildPaper, EDGE_SLOT, makeScratch, stackEdges, type Geo } from "../fold/mesh";
import { FLIGHT_END, LOOP_T, TAKEOFF, lifePose } from "../fold/life";
import { BIRD_CELL, NBIRDS, birdCell, birdXform } from "../fx/birds";
import { CELL, STRIDE, burst, emit, leafCell, makePool, rand, spriteCell, spriteColor, spriteXform, stepPool } from "../fx/particles";
import { CAM_LEN, makeCamera, makeCameraLook, project } from "./camera";
import { paperFx, postFx, sunMaskFx } from "../shaders/paper";
import { atmosFx, awakenFx, vanishFx } from "../shaders/atmos";
import { layerFx, paperMaskFx, tableFx } from "../shaders/room";
import { LAYERS, PASSES } from "./sceneAssets";
import { TIMESCALE } from "./clock";
import { DEBUG_P, FORCE_DEMO, FORCE_USERSIM, HIDE_LAYERS, HOLD_INTRO, PERF_LOG, START_STEP } from "../debug";

const LAYOUT = require("../../assets/scene/layout.json");
const DEMO = process.env.EXPO_PUBLIC_DEMO === "1" || FORCE_DEMO;
/**
 * screen-recording mode: the interactive app (hints, step dots, captions) operated by a scripted "user" whose touches go
 * through the same pan / tap handlers as a real finger, with an iOS-style touch dot drawn where the finger is. Thinking
 * pauses, uneven swipes, a hesitant half swipe that springs back now and then, a tap for another sheet at the end.
 */
const USERSIM = !DEMO && (process.env.EXPO_PUBLIC_USERSIM === "1" || FORCE_USERSIM);
const LOGEVT = DEMO || USERSIM;
const urnd = (n: number) => {
  "worklet";
  const x = Math.sin(n * 12.9898 + 4.1) * 43758.5453;
  return x - Math.floor(x);
};
const CAM_PITCH = -0.48; // lower than the Blender reference camera so the backlit shoji shows at the top
// demo storyboard (scene seconds): frame 1 = the room with the flat sheet lying in the sunbeam, a slow zoom in to the sheet
// (DEMO_ZOOM), then a ghost finger folds every step unhurriedly, the crane wakes up and flies away. (The older storyboard
// opened on the finished crane and rewound it: DEMO_INTRO / DEMO_REWIND, kept at 0.)
const DEMO_INTRO = HOLD_INTRO ? 1e9 : 0;
const DEMO_REWIND = 0;
const DEMO_ZOOM = 3.6; // the first fold starts here
const DEMO_WAIT = 0.25; // pause before each swipe
const NGLOW = 260;
const NPETAL = 70;
const WIDE_DIST = 0.55; // demo intro establishing shot: extra dolly distance, pitch and target lift
const WIDE_PITCH = -0.1;
const WIDE_LIFT = 0.7;
/** papers for the interactive app: the vermilion washi, then indigo chiyogami (gold flecks kept), then sakura pink; ink line
 * and shadow follow the colour. The demo always folds the vermilion one. */
const PAPERS = [
  { dye: [0, 0, 0], k: 0, ink: "#4a1510", sh1: "#5e2414", sh2: "#7a3420" },
  { dye: [0.13, 0.2, 0.5], k: 1, ink: "#121b38", sh1: "#1e2442", sh2: "#3a3c5c" },
  { dye: [0.96, 0.6, 0.68], k: 1, ink: "#6a2638", sh1: "#6a3040", sh2: "#8a4852" },
];
const HINT_MIN = 110; // shortest swipe hint on screen (pt)
const WARM = 90; // frames the demo clock holds at 0 after the images are ready (Release: the canvas can reach the screen ~35 frames late)
const DEMO_SWIPE = 0.85; // one unhurried swipe per step
const LINEAR = { filter: FilterMode.Linear, mipmap: MipmapMode.Linear };
// the paper textures: no mipmaps. The paper shader decodes its texture coordinates with floor() (facet light packed into
// them), so screen derivatives jump at every facet edge and a mip lookup there picks a tiny level (and was very slow)
const FLAT = { filter: FilterMode.Linear, mipmap: MipmapMode.None };

// table and backdrop grids (perspective by subdivision: Skia interpolates texcoords affinely per triangle)
const TG = { nx: 20, ny: 26 };
const BG = { nx: 12, ny: 9 };
const gridIdx = (nx: number, ny: number) => {
  const out: number[] = [];
  for (let j = 0; j < ny; j++)
    for (let i = 0; i < nx; i++) {
      const a = j * (nx + 1) + i, b = a + 1, c = a + nx + 2, d = a + nx + 1;
      out.push(a, b, c, a, c, d);
    }
  return out;
};
const gridTex = (nx: number, ny: number, w: number, h: number, vBot = h, vTop = 0) => {
  const out = new Float32Array((nx + 1) * (ny + 1) * 2);
  for (let j = 0; j <= ny; j++)
    for (let i = 0; i <= nx; i++) {
      const k = j * (nx + 1) + i;
      out[k * 2] = (i / nx) * w;
      out[k * 2 + 1] = vBot + (vTop - vBot) * (j / ny); // image top = far edge (+y) / top (+z); past the image it clamps
    }
  return out;
};

/**
 * the far layers run on below their painted bottom edge (the last row of pixels stretched down), so that seen through the gaps
 * in the garden trees from a low camera there is always hillside or sky behind, never the empty backstop
 */
const skirt = (name: string) => (/sky/i.test(name) ? 24 : /hills/i.test(name) ? 12 : 0);
/** the sky also runs on above its top edge (its blue top row stretched up), for the camera looking up from the veranda */
const skirtTop = (name: string) => (/sky/i.test(name) ? 30 : 0);

/** inverse smoothstep: finger progress → linear keyframe progress (the bake eases each step with smoothstep) */
const sstep = (a: number, b: number, x: number) => {
  "worklet";
  const t = Math.max(0, Math.min(1, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

const unease = (y: number) => {
  "worklet";
  return 0.5 - Math.sin(Math.asin(1 - 2 * Math.max(0, Math.min(1, y))) / 3);
};

/** load bundled images (null entries stay null); returns null until all are decoded */
const useAssetImages = (srcs: (number | null)[]): (SkImage | null)[] | null => {
  const [imgs, setImgs] = useState<(SkImage | null)[] | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all(
      srcs.map((src) =>
        src == null
          ? Promise.resolve(null)
          : Skia.Data.fromURI(RNImage.resolveAssetSource(src)?.uri ?? "").then((d) => Skia.Image.MakeFromEncoded(d) ?? null),
      ),
    )
      .then((r) => live && setImgs(r))
      .catch(() => live && setImgs(srcs.map(() => null)));
    return () => {
      live = false;
    };
    // the sources are module constants
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return imgs;
};

const MAXL = 5; // multiplane layers (sky, hills, garden, house, …)
const LG = { nx: 10, ny: 8 };

const reportErr = (m: string) => console.error("frame:", m);

const haptic = (k: number) => {
  if (k === 0) Haptics.selectionAsync().catch(() => {});
  else Haptics.impactAsync(k === 1 ? Haptics.ImpactFeedbackStyle.Light : Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
};

export function CraneScene() {
  const model = useMemo(() => loadFold(), []);
  const [size, setSize] = useState({ w: 440, h: 956 });
  const [flownJs, setFlownJs] = useState(false); // the crane vanished into the light: offer another sheet
  const [stepJs, setStepJs] = useState(!DEMO && START_STEP >= 0 ? START_STEP : 0);
  const newSheetJs = () => {
    setStepJs(0);
    setFlownJs(false);
  };

  const tableImg = useImage(require("../../assets/scene/table.jpg"));
  const backImg = useImage(require("../../assets/scene/backdrop.jpg"));
  const frontImg = useImage(require("../../assets/scene/paper_front.jpg"));
  const paperBackImg = useImage(require("../../assets/scene/paper_back.jpg"));
  const fibreImg = useImage(require("../../assets/scene/paper_fibre.jpg"));
  const maskImg = useImage(require("../../assets/scene/sunmask.jpg"));
  const passImgs = useAssetImages([PASSES.tableBase, PASSES.tableSun, PASSES.maskLattice, PASSES.maskLeaves]);
  const layerImgs = useAssetImages(LAYERS.slice(0, MAXL).map((l) => l.src));
  const livingLight = !!passImgs && passImgs.every((im) => im);
  const lmSv = useSharedValue([0, 0, 1, 1, 1, 1]);
  useEffect(() => {
    if (maskImg) lmSv.set([LAYOUT.table.x[0], LAYOUT.table.y[0], LAYOUT.table.x[1], LAYOUT.table.y[1], maskImg.width(), maskImg.height()]);
  }, [maskImg, lmSv]);

  const T = model.T;
  const geo = useSharedValue<Geo>({
    V: model.V,
    T: model.T,
    K: model.K,
    pos: model.pos,
    tris: model.tris,
    uv: model.uv,
    wing: model.wingMask ?? new Array(model.V).fill(0),
    axisL: model.axisL ? [...model.axisL[0], ...model.axisL[1]] : [],
    axisR: model.axisR ? [...model.axisR[0], ...model.axisR[1]] : [],
  });
  const scratch = useSharedValue(
    (() => {
      const sc = makeScratch(model.V, model.T);
      // rest wing normals (last keyframe), for pressing the living crane's layers together (mesh.ts applyLife)
      const base = (model.K - 1) * model.V * 3, P = model.pos, wm = model.wingMask;
      for (let side = 0; side < 2 && wm; side++) {
        for (let t = 0; t < model.T; t++) {
          const a = model.tris[t * 3], b = model.tris[t * 3 + 1], c = model.tris[t * 3 + 2];
          if (wm[a] !== (side === 0 ? -1 : 1)) continue;
          const ux = P[base + b * 3] - P[base + a * 3], uy = P[base + b * 3 + 1] - P[base + a * 3 + 1], uz = P[base + b * 3 + 2] - P[base + a * 3 + 2];
          const vx = P[base + c * 3] - P[base + a * 3], vy = P[base + c * 3 + 1] - P[base + a * 3 + 1], vz = P[base + c * 3 + 2] - P[base + a * 3 + 2];
          const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
          const l = Math.hypot(nx, ny, nz);
          if (l < 1e-9) continue;
          sc.wn[side * 3] = nx / l;
          sc.wn[side * 3 + 1] = ny / l;
          sc.wn[side * 3 + 2] = nz / l;
          break;
        }
      }
      return sc;
    })(),
  );
  const paperV = useSharedValue(new Float32Array(T * 6));
  const paperT = useSharedValue(new Float32Array(T * 6));
  // the paper as drawn: every facet preceded by the shadow strips of its cut edges (fold/mesh.ts stackEdges)
  const paperV2 = useSharedValue(new Float32Array(T * EDGE_SLOT));
  const paperT2 = useSharedValue(new Float32Array(T * EDGE_SLOT));
  const shadowV = useSharedValue(new Float32Array(T * 6));
  const lightT = useSharedValue(new Float32Array(T * 6));
  const tableV = useSharedValue(new Float32Array((TG.nx + 1) * (TG.ny + 1) * 2));
  const backV = useSharedValue(new Float32Array((BG.nx + 1) * (BG.ny + 1) * 2));
  const tmp = useSharedValue(new Float32Array(3));
  const groundV = useSharedValue(new Float32Array((LG.nx + 1) * (LG.ny + 1) * 2));
  const lv0 = useSharedValue(new Float32Array((LG.nx + 1) * (LG.ny + 1) * 2));
  const lv1 = useSharedValue(new Float32Array((LG.nx + 1) * (LG.ny + 1) * 2));
  const lv2 = useSharedValue(new Float32Array((LG.nx + 1) * (LG.ny + 1) * 2));
  const lv3 = useSharedValue(new Float32Array((LG.nx + 1) * (LG.ny + 1) * 2));
  const lv4 = useSharedValue(new Float32Array((LG.nx + 1) * (LG.ny + 1) * 2));
  const layerDefs = useSharedValue(LAYERS.slice(0, MAXL).map((l) => [l.x[0], l.x[1], l.y, l.z[0] - skirt(l.name), l.z[1] + skirtTop(l.name)]));
  const gardenL = LAYERS.find((l) => /garden/i.test(l.name));
  const gardenD = useSharedValue(gardenL ? [gardenL.x[0], gardenL.x[1], gardenL.y, gardenL.z[0]] : []);
  const cam = useSharedValue(new Array(CAM_LEN).fill(0));
  const life = useSharedValue([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0]);
  const flight = useSharedValue([0, 0, 0, 0, 0]); // crane centre x, y, z, dissolve, speed
  const tmp3 = useSharedValue([0, 0, 0]);
  const glow = useSharedValue(makePool(NGLOW));
  const petals = useSharedValue(makePool(NPETAL));
  const fxs = useSharedValue([0, 0, 0, 0, 0, 0, 0, 0]); // awaken burst done, dissolve burst done, trail accumulator, petal accumulator, magic band, magic k
  // wing tips (farthest wing vertex from the hinge at the last keyframe): the glitter trail comes off them
  const tips = useMemo(() => {
    const m = model.wingMask, ax = model.axisL;
    if (!m || !ax) return [-1, -1];
    const base = (model.K - 1) * model.V * 3;
    const best = [-1, -1], bd = [0, 0];
    for (let i = 0; i < model.V; i++) {
      if (!m[i]) continue;
      const x = model.pos[base + i * 3], y = model.pos[base + i * 3 + 1], z = model.pos[base + i * 3 + 2];
      const d = Math.hypot(y - ax[0][1], z - ax[0][2]);
      const k = m[i] < 0 ? 0 : 1;
      if (d > bd[k]) {
        bd[k] = d;
        best[k] = i;
      }
      void x;
    }
    return best;
  }, [model]);
  const tipsSv = useSharedValue(tips);
  const lifeBase = useSharedValue(
    model.head && model.tail
      ? [(model.head[0] + model.tail[0]) / 2, (model.head[1] + model.tail[1]) / 2, 0.25, Math.atan2(model.head[1] - model.tail[1], model.head[0] - model.tail[0])]
      : [0, 0, 0, 0],
  );
  const hint = useSharedValue([0, 0, 0, 0, 0]); // ax, ay, bx, by, alpha
  const sunPt = useSharedValue([0, 0, -1]); // ray origin x, y, indoor factor (−1 = not initialised)
  const orbit = useSharedValue([0, 0, 0, 0]); // yaw, pitch (two-finger drag), drag start yaw, pitch
  const grav = useAnimatedSensor(SensorType.GRAVITY, { interval: 16 });
  const drag2 = useSharedValue(0);
  const tickK = useSharedValue(0);
  const paperSv = useSharedValue(0); // which paper (PAPERS); the interactive app takes the next one for every new sheet
  const prewarm = useSharedValue(0); // particles pre-warmed for the first frame
  const wideSv = useSharedValue(0); // demo establishing shot 1 → 0
  const perf = useSharedValue([0, 0, 0]); // PERF_LOG: frames, tick ms, window start
  const readySv = useSharedValue(0); // 0 = loading, 1..WARM-1 = warming up (clock held at 0), WARM = clock running
  const held = useSharedValue([0, 0, 0]); // last flight position (the camera keeps looking there after the crane vanished)
  const chase = useSharedValue([0, 0, 0, 0, 0, 0, 0]); // smoothed chase eye xyz, target xyz, 1 = initialised
  const insideK = useSharedValue(1); // house frame visible (camera still inside)
  const floorK = useSharedValue(1); // floor/table visible
  const shadowK = useSharedValue(1); // shadow strength, fades as the crane climbs
  const crackR = useSharedValue(2); // gap-closing radius (pt) under the living crane: 7.5 mm of paper at its distance
  const ab = useSharedValue([0, 0, 0, 0, 0, 30]); // awaken pillar: floor x, y, crane x, y (screen), age 0..1, half width
  const vb = useSharedValue([0, 0, 0, 1]); // vanish bloom: screen x, y, age 0..1 (0 = off), size
  const ring = useSharedValue([0, 0, 1, 1, 0]); // awaken ring: cx, cy, rx, ry, alpha
  const cutK = useSharedValue(0); // warm white flash covering the cut back into the room
  const slide = useSharedValue(0); // 1 → 0: a new sheet sliding in
  const frame = useSharedValue([0, 0.3, 0, 1]); // camera target x, y, z, dolly
  const ghost = useSharedValue([0, 0, 0, 0]); // demo timer, x, y, alpha

  const tableIdx = useMemo(() => gridIdx(TG.nx, TG.ny), []);
  const backIdx = useMemo(() => gridIdx(BG.nx, BG.ny), []);
  const tableTex = useMemo(() => (tableImg ? gridTex(TG.nx, TG.ny, tableImg.width(), tableImg.height()) : null), [tableImg]);
  const layerTex = useMemo(
    () =>
      layerImgs
        ? layerImgs.map((im, i) => {
            if (!im) return null;
            const l = LAYERS[i], zr = l.z[1] - l.z[0];
            const h = im.height();
            return gridTex(LG.nx, LG.ny, im.width(), h, (h * (zr + skirt(l.name))) / zr, (-h * skirtTop(l.name)) / zr);
          })
        : null,
    [layerImgs],
  );
  const backTex = useMemo(() => (backImg ? gridTex(BG.nx, BG.ny, backImg.width(), backImg.height()) : null), [backImg]);

  // fold state: `p` = shown keyframe (float), `goal` = where it is heading, `step` = current step index
  const steps = model.steps;
  const stepsSv = useSharedValue(steps.map((s) => [s.from, s.to, ...s.hint.a, ...s.hint.b]));
  const s0 = !DEMO && START_STEP >= 0 ? Math.min(START_STEP, model.steps.length - 1) : -1;
  const p = useSharedValue(s0 >= 0 ? model.steps[s0].from : 0);
  const goal = useSharedValue(s0 >= 0 ? model.steps[s0].from : 0);
  const step = useSharedValue(Math.max(0, s0));
  const drag = useSharedValue([0, 0, 0, 0]); // active, x0, y0, startGoal
  const time = useSharedValue(0);
  const last = useSharedValue(-1);
  const alive = useSharedValue(-1); // time the crane came alive (−1 = not yet)

  const usim = useSharedValue([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]); // USERSIM: phase, timer, x0, y0, x1, y1, dur, hesitated, last x, last y, tapped, tries
  const touch = useSharedValue([0, 0, 0, 0]); // USERSIM touch dot: x, y, alpha, pressed

  const sun: number[] = LAYOUT.sunDir;
  const sunCol: number[] = LAYOUT.sunColor;
  const amb: number[] = LAYOUT.ambient;
  const table = LAYOUT.table;
  const back = LAYOUT.backdrop;
  const W = size.w, H = size.h;

  // ── the pan / tap handlers (shared by the gestures and the USERSIM driver) ──
  function panBegin(x: number, y: number) {
    "worklet";
    if (step.value >= stepsSv.value.length) return;
    drag.value = [1, x, y, 0];
    scheduleOnRN(haptic, 0);
  }
  function panMove(x: number, y: number) {
    "worklet";
    const si = step.value;
    const ss = stepsSv.value;
    if (!drag.value[0] || si >= ss.length) return;
    const hv = hint.value;
    const vx = hv[2] - hv[0], vy = hv[3] - hv[1];
    const l2 = Math.max(400, vx * vx + vy * vy);
    const prog = Math.max(0, Math.min(1, ((x - drag.value[1]) * vx + (y - drag.value[2]) * vy) / l2));
    goal.value = ss[si][0] + (ss[si][1] - ss[si][0]) * unease(prog);
  }
  function panRelease(velX: number, velY: number) {
    "worklet";
    const si = step.value;
    const ss = stepsSv.value;
    drag.value = [0, 0, 0, 0];
    if (si >= ss.length) return;
    const prog = (goal.value - ss[si][0]) / Math.max(1e-3, ss[si][1] - ss[si][0]); // linear keyframe progress
    const hv = hint.value;
    const fling = velX * (hv[2] - hv[0]) + velY * (hv[3] - hv[1]) > 0 && Math.hypot(velX, velY) > 600;
    goal.value = prog > 0.45 || fling ? ss[si][1] : ss[si][0];
  }
  function tapSheet() {
    "worklet";
    // finished (or flown away): start over with a fresh sheet
    if (step.value >= stepsSv.value.length) {
      alive.value = -1;
      paperSv.value = (paperSv.value + 1) % PAPERS.length;
      step.value = 0;
      scheduleOnRN(newSheetJs);
      scheduleOnRN(sfxEvent, "sheet");
      goal.value = 0;
      p.value = 0;
    }
  }
  /** USERSIM: one frame of the scripted user */
  function userSim(t: number, dt: number) {
    "worklet";
    const u = usim.value, tc = touch.value;
    const ss = stepsSv.value, n = ss.length, si = step.value;
    const down = u[0] === 2 || u[0] === 3 || u[0] === 6;
    tc[2] += ((down ? 1 : 0) - tc[2]) * (1 - Math.exp(-dt * (down ? 28 : 12)));
    tc[3] += ((u[0] === 3 ? 1 : 0) - tc[3]) * (1 - Math.exp(-dt * 16));
    touch.modify();
    if (t < 4.0) return; // the app has just opened: the camera glides in to the sheet
    if (si < n) {
      const hv = hint.value;
      if (u[0] === 0) {
        if (hv[4] > 0.6 && drag.value[0] === 0) {
          u[0] = 1;
          u[1] = si === 0 && u[11] === 0 ? 0.8 : 0.35 + 0.75 * urnd(si * 7.3 + u[11] * 3.1);
        }
      } else if (u[0] === 1) {
        // thinking, then the finger comes down near the start of the arrow
        u[1] -= dt;
        if (u[1] <= 0) {
          const r = si * 5.1 + u[11] * 1.7;
          const vx = hv[2] - hv[0], vy = hv[3] - hv[1];
          const hes = (si === 3 || si === 9) && u[7] === 0; // a hesitant half swipe the first time on these steps
          const frac = hes ? 0.3 : 1.06 + 0.16 * urnd(r + 2);
          u[2] = hv[0] + (urnd(r) - 0.5) * 12;
          u[3] = hv[1] + (urnd(r + 1) - 0.5) * 12;
          u[4] = hv[0] + vx * frac + (urnd(r + 3) - 0.5) * 18;
          u[5] = hv[1] + vy * frac + (urnd(r + 4) - 0.5) * 18;
          u[6] = hes ? 0.42 : 0.42 + 0.34 * urnd(r + 5);
          u[7] = hes ? 1 : 0;
          tc[0] = u[2];
          tc[1] = u[3];
          u[0] = 2;
          u[1] = 0;
        }
      } else if (u[0] === 2) {
        u[1] += dt;
        if (u[1] > 0.09) {
          panBegin(u[2], u[3]);
          u[0] = 3;
          u[1] = 0;
          u[8] = u[2];
          u[9] = u[3];
        }
      } else if (u[0] === 3) {
        u[1] += dt;
        const k = Math.min(1, u[1] / u[6]);
        const e = 0.5 - 0.5 * Math.cos(Math.PI * k);
        const dx = u[4] - u[2], dy = u[5] - u[3], l = Math.hypot(dx, dy) || 1;
        const w = Math.sin(Math.PI * k) * (3 + 4 * urnd(si + 9)); // a thumb never moves in a straight line
        const x = u[2] + dx * e - (dy / l) * w, y = u[3] + dy * e + (dx / l) * w;
        tc[0] = x;
        tc[1] = y;
        panMove(x, y);
        const vx = dt > 0 ? (x - u[8]) / dt : 0, vy = dt > 0 ? (y - u[9]) / dt : 0;
        u[8] = x;
        u[9] = y;
        if (k >= 1) {
          panRelease(vx, vy);
          u[0] = 4;
          u[1] = 0;
          u[11] += 1;
        }
      } else if (u[0] === 4) {
        u[1] += dt;
        if (u[1] > 0.25) u[0] = 0;
      }
      return;
    }
    // folded: watch it fly away, then tap "Tap to fold another"
    const la = alive.value < 0 ? -1 : t - alive.value;
    if (u[10] === 0 && la > FLIGHT_END + 1.4) {
      u[10] = 1;
      u[0] = 6;
      u[1] = 0;
      tc[0] = W / 2 + 8;
      tc[1] = H - 74;
    } else if (u[0] === 6) {
      u[1] += dt;
      if (u[1] > 0.11) {
        tapSheet();
        u[0] = 0;
        u[10] = 0;
      }
    }
  }

  function tick(timestamp: number) {
    "worklet";
    // the scene clock holds at 0 until every image is decoded, then for WARM more frames while the whole first frame is built
    // and drawn (the GPU compiles every pipeline on its first draw), so demo t = 0 is already the full picture
    const warming = readySv.value < WARM;
    if (warming && readySv.value > 0) {
      readySv.value += 1;
      if (LOGEVT && readySv.value === WARM) console.log("EVT clock 0.000"); // the demo clock starts on the next frame
    }
    const dt = warming || last.value < 0 ? 0 : Math.min(0.05, (timestamp - last.value) / 1000) * TIMESCALE;
    last.value = timestamp;
    const t = time.value + dt;
    time.value = t;
    const ss = stepsSv.value;
    const nSteps = ss.length;

    // demo intro: hover (life clock held, see lifePose hover), then rewind the whole fold back to the flat sheet
    if (DEMO && t >= DEMO_INTRO && t < DEMO_INTRO + DEMO_REWIND) {
      if (alive.value >= 0) {
        alive.value = -1;
        step.value = 0;
        ghost.value[0] = 0;
        burst(glow.value, 40, flight.value[0], flight.value[1], flight.value[2], 0.4, 0.5);
        console.log("EVT " + "rewind" + " " + t.toFixed(3));
        scheduleOnRN(sfxEvent, "rewind");
      }
      const u = (t - DEMO_INTRO) / DEMO_REWIND;
      const e = u * u * (3 - 2 * u);
      goal.value = (geo.value.K - 1) * (1 - e);
      p.value = goal.value;
    }
    if (USERSIM) userSim(t, dt);
    // demo: a ghost finger swipes every step (wait, press, swipe along the hint, release)
    const gh = ghost.value;
    if (DEMO && step.value < nSteps && t > DEMO_ZOOM - DEMO_WAIT) {
      const h = ss[step.value];
      const dur = DEMO_SWIPE;
      gh[0] += dt;
      const u = gh[0] - DEMO_WAIT;
      if (u < 0) gh[3] = Math.max(0, gh[3] - dt * 4);
      else {
        const prog = Math.min(1, u / dur);
        const e = prog * prog * (3 - 2 * prog);
        goal.value = h[0] + (h[1] - h[0]) * unease(e);
        gh[1] = hint.value[0] + (hint.value[2] - hint.value[0]) * e;
        gh[2] = hint.value[1] + (hint.value[3] - hint.value[1]) * e;
        gh[3] = Math.min(1, gh[3] + dt * 6);
        if (prog >= 1) gh[0] = -1e9; // released: wait for the step to finish
      }
      if (gh[0] < -1e8) gh[3] = Math.max(0, gh[3] - dt * 5);
    }
    ghost.modify();
    // ease toward the goal (keyframes are already eased per step)
    const sp = drag.value[0] ? 18 : DEMO ? 11 : 6.5;
    const np = p.value + (goal.value - p.value) * (1 - Math.exp(-sp * dt));
    p.value = Math.abs(goal.value - np) < (DEMO ? 0.02 : 0.002) ? goal.value : np;
    if (DEBUG_P >= 0) p.value = DEBUG_P;
    // paper "ticks" under the finger: a light haptic every few keyframes while dragging
    const tk = Math.floor(p.value / 4);
    if (drag.value[0] && tk !== tickK.value) {
      scheduleOnRN(haptic, 0);
      scheduleOnRN(sfxEvent, "drag");
    }
    tickK.value = tk;
    // step finished
    const si = step.value;
    const rewinding = DEMO && t >= DEMO_INTRO && t < DEMO_INTRO + DEMO_REWIND + 0.25;
    if (!rewinding && si < nSteps && drag.value[0] === 0 && p.value >= ss[si][1] - 0.001) {
      step.value = si + 1;
      ghost.value[0] = 0;
      scheduleOnRN(setStepJs, si + 1);
      scheduleOnRN(haptic, 2);
      scheduleOnRN(sfxEvent, "fold");
      if (LOGEVT) console.log("EVT fold" + (si + 1) + " " + t.toFixed(3));
      // a little shine where the flap landed
      if (si + 1 === nSteps) {
        alive.value = t;
        fxs.value[0] = 0;
        fxs.value[1] = 0;
        fxs.value[6] = 0;
        fxs.value[7] = 0;
      }
    }

    // camera: slow handheld drift; when alive, follow the flight
    // flown out of the frame: a fresh sheet slides in from the bottom
    if (!DEMO && alive.value >= 0 && t - alive.value > FLIGHT_END + 3.2) {
      alive.value = -1;
      step.value = 0;
      goal.value = 0;
      p.value = 0;
      paperSv.value = (paperSv.value + 1) % PAPERS.length;
      slide.value = 1;
      cutK.value = 1;
      scheduleOnRN(newSheetJs);
      scheduleOnRN(sfxEvent, "sheet");
      ghost.value[0] = 0;
    }
    slide.value = Math.max(0, slide.value - dt * 1.6);
    cutK.value = Math.max(0, cutK.value - dt * 1.4);
    const L = life.value;
    // demo intro starts 1.4 s into the awaken so frame 1 already hovers
    const la = alive.value < 0 ? -1 : t - alive.value + (DEMO && t < DEMO_INTRO ? 1.4 : 0);
    const st = flight.value;
    if (geo.value.axisL.length === 6) lifePose(la, lifeBase.value, L, st, tmp3.value, DEMO && t < DEMO_INTRO ? 1 : 0);
    if (la > FLIGHT_END) {
      // vanished into the light
      L[11] = 1e-4;
      L[5] += 200;
    }
    const flyZ = la >= 0 ? Math.max(0, st[2] - lifeBase.value[2]) : 0;
    shadowK.value = Math.max(0, 1 - flyZ / 3.2) * (la > FLIGHT_END ? 0 : 1);
    if (slide.value > 0) {
      const e = slide.value * slide.value * (3 - 2 * slide.value);
      L[4] -= e * 4.5;
      L[1] += e * 0.5;
    }
    // frame the paper: track its centre and dolly in as the model gets smaller (bbox of last frame's world positions)
    const wv = scratch.value.w;
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9, z1 = 0;
    for (let i = 0; i < wv.length; i += 3) {
      x0 = Math.min(x0, wv[i]);
      x1 = Math.max(x1, wv[i]);
      y0 = Math.min(y0, wv[i + 1]);
      y1 = Math.max(y1, wv[i + 1]);
      z1 = Math.max(z1, wv[i + 2]);
    }
    const fr = frame.value;
    const kf = 1 - Math.exp(-1.6 * dt);
    if (la >= 0 && la <= FLIGHT_END + 0.3) {
      // follow the flight (softly, so the loop sweeps across the frame)
      const kk = 1 - Math.exp(-2.2 * dt);
      fr[0] += (st[0] * 0.55 - fr[0]) * kk;
      fr[1] += (Math.min(2.2, st[1] * 0.45) + 0.3 - fr[1]) * kk;
      fr[2] += (Math.min(3.0, st[2] * 0.6) - fr[2]) * kk;
      fr[3] += (0.92 - fr[3]) * kk;
    }
    if (alive.value < 0) {
      fr[0] += ((x0 + x1) / 2 - fr[0]) * kf;
      fr[1] += ((y0 + y1) / 2 + 0.3 - fr[1]) * kf;
      fr[2] += (z1 * 0.35 - fr[2]) * kf;
      const rad = Math.max(x1 - x0, y1 - y0, z1 * 1.4);
      fr[3] += (Math.max(0.55, Math.min(1, 0.32 + rad / 2.9)) - fr[3]) * kf;
    }
    const c = cam.value;
    // two-finger orbit eases back to rest; device tilt adds a little parallax (gravity x/y ≈ 0 when held upright… ±9.8)
    const ob = orbit.value;
    if (!drag2.value) {
      ob[0] *= 1 - Math.min(1, dt * 0.8);
      ob[1] *= 1 - Math.min(1, dt * 0.8);
    }
    const gv = grav.sensor.value;
    const gx = Math.max(-1, Math.min(1, (gv.x ?? 0) / 9.8)), gz = Math.max(-1, Math.min(1, (gv.z ?? 0) / 9.8));
    // demo intro: an establishing shot of the whole room (the crane hovering in the sunbeam, shoji walls and the garden in
    // the open panel), dollying in to the folding close-up while the folds rewind
    let wide = 0;
    if (DEMO && t < DEMO_ZOOM + 0.4) {
      // slow push-in from the room to the sheet
      const u = Math.max(0, Math.min(1, (t - 0.6) / (DEMO_ZOOM - 0.2)));
      wide = 1 - u * u * (3 - 2 * u);
    } else if (!DEMO && t < 3.2) {
      // the app opens on the room too, then glides in to the sheet
      const u = Math.max(0, Math.min(1, (t - 0.8) / 2.2));
      wide = 1 - u * u * (3 - 2 * u);
    }
    wideSv.value = wide;
    makeCamera(c, W, H, ob[0] + gx * 0.12 + Math.sin(t * 0.21) * 0.025, ob[1] - gz * 0.06 + CAM_PITCH + Math.sin(t * 0.17) * 0.015 + Math.min(0.42, flyZ * 0.11) + WIDE_PITCH * wide, fr[3] * (1 + WIDE_DIST * wide), fr[0], fr[1], fr[2] + WIDE_LIFT * wide, 42);
    // chase: as the crane heads for the open panel the camera follows it out of the house and looks up into the sky
    {
      const sC = la - TAKEOFF;
      const ck = la >= 0 ? sstep(LOOP_T + 0.15, LOOP_T + 1.5, sC) : 0;
      const hd = held.value;
      if (la >= 0 && la <= FLIGHT_END) {
        hd[0] = st[0];
        hd[1] = st[1];
        hd[2] = st[2];
      }
      if (ck > 0) {
        const ex0 = c[0], ey0 = c[1], ez0 = c[2];
        // soft min/max: the chase rig has no hard clamps (a clamp engaging is a kink in the camera path)
        const smin = (a: number, b: number, k: number) => -k * Math.log(Math.exp(-a / k) + Math.exp(-b / k));
        // follow through the opening, then stop on the veranda edge and watch it fly into the sun
        const side = 0.85 * sstep(6.0, 9.0, hd[1]); // once outside, step aside: a three-quarter view shows the wings, not just their edges
        const ex1 = Math.tanh(hd[0] * 0.7) + side;
        const ey1 = smin(8.6, hd[1] - 4.2, 0.4);
        const cap = 2.5 + 0.9 * sstep(6.4, 7.6, ey1);
        const ez1 = smin(cap, -smin(-1.0, -(hd[2] - 0.6), 0.3), 0.3);
        const far = sstep(9, 16, hd[1]);
        let tx1 = hd[0], ty1 = hd[1] + 2.0 * (1 - far), tz1 = hd[2] + 1.3 * (1 - far);
        // still inside: look through the middle of the open panel, not at the wall above it
        const thru = 1 - sstep(6.0, 7.4, ey1);
        tx1 += (0 - tx1) * thru * 0.6;
        ty1 += (-smin(-ty1, -9, 0.4) - ty1) * thru;
        tz1 += (1.9 - tz1) * thru;
        // and the rig itself lags a little behind (critically smooth, ~0.3 s): the crane's own speed changes and the
        // panel passage never jerk the frame
        const ch = chase.value;
        if (ch[6] === 0) {
          ch[0] = ex1; ch[1] = ey1; ch[2] = ez1; ch[3] = tx1; ch[4] = ty1; ch[5] = tz1; ch[6] = 1;
        } else {
          const kc = 1 - Math.exp(-3.2 * dt), kt = 1 - Math.exp(-4.5 * dt);
          ch[0] += (ex1 - ch[0]) * kc; ch[1] += (ey1 - ch[1]) * kc; ch[2] += (ez1 - ch[2]) * kc;
          ch[3] += (tx1 - ch[3]) * kt; ch[4] += (ty1 - ch[4]) * kt; ch[5] += (tz1 - ch[5]) * kt;
        }
        const e = ck * ck * (3 - 2 * ck);
        makeCameraLook(
          c,
          W,
          H,
          ex0 + (ch[0] - ex0) * e,
          ey0 + (ch[1] - ey0) * e,
          ez0 + (ch[2] - ez0) * e,
          fr[0] + (ch[3] - fr[0]) * e,
          fr[1] + (ch[4] - fr[1]) * e,
          fr[2] + (ch[5] - fr[2]) * e,
          42 + 8 * e,
        );
      } else chase.value[6] = 0;
      // which parts of the house are still in front of the lens
      const ey = c[1];
      insideK.value = 1 - sstep(5.3, 6.3, ey);
      floorK.value = 1 - sstep(5.6, 6.6, ey);
    }

    buildPaper(geo.value, scratch.value, p.value, L, c, sun, paperV.value, paperT.value, shadowV.value, lightT.value, lmSv.value, true);
    if (la >= 0) {
      // the stacked layers of a wing or of the neck sit up to 12 mm apart: seen edge-on close to the lens the gap between
      // two stacks would show the sky through the crane, so the closing radius follows the crane's size on screen
      const tm = tmp.value;
      project(c, st[0], st[1], st[2], tm, 0);
      crackR.value = Math.max(1.5, Math.min(5, (0.0075 * c[12]) / Math.max(0.05, tm[2]))); // (capped: a big morphology kernel over the whole layer is slow)
    } else crackR.value = 3.5; // folding: the thin slits between the layers of a leg opening in the reverse folds
    if (la > FLIGHT_END) {
      // gone into the light: park the mesh off-screen (projected behind the lens it would smear thin slivers across the sky)
      paperV.value.fill(-1e4);
      shadowV.value.fill(-1e4);
    }
    stackEdges(geo.value.T, paperV.value, paperT.value, paperV2.value, paperT2.value, 0.7, 1.0);
    // ── particles ──
    {
      const gp = glow.value, pp = petals.value, fx = fxs.value, sc = scratch.value;
      if (la >= 0 && fx[0] === 0) {
        fx[0] = 1;
        if (t < 0.1) {
          // demo frame 1: pre-warm, so the glitter and the dust are already alive in the very first frame
          burst(gp, 16, st[0], st[1], st[2] + 0.15, 0.3, 0.35);
          for (let k = 0; k < 45; k++) emit(gp, 1, -2.5 + rand(gp) * 5, -1.5 + rand(gp) * 6.5, 0.1 + rand(gp) * 2.8, 0, 0, 0, 6 + rand(gp) * 5, 0.014 + rand(gp) * 0.014);
          for (let k = 0; k < 6; k++) emit(pp, k % 3 === 0 ? 5 : 3, -2.2 + rand(pp) * 4.4, -1 + rand(pp) * 6, 0.6 + rand(pp) * 2.2, 0, 0, 0, 9 + rand(pp) * 3, 0.09);
          for (let k = 0; k < 24; k++) {
            stepPool(gp, 0.03, k * 0.03);
            stepPool(pp, 0.03, k * 0.03);
          }
        }
        if (LOGEVT) console.log("EVT " + (t < 0.1 ? "start" : "awaken") + " " + t.toFixed(3));
        if (t >= 0.1) scheduleOnRN(sfxEvent, "awaken");
        burst(gp, 16, st[0], st[1], st[2] + 0.15, 0.3, 0.35);
      }
      if (la > TAKEOFF && fx[6] === 0 && t > DEMO_INTRO) {
        fx[6] = 1;
        if (LOGEVT) console.log("EVT " + "takeoff" + " " + t.toFixed(3));
        scheduleOnRN(sfxEvent, "takeoff");
      }
      if (la > TAKEOFF + LOOP_T && fx[7] === 0 && t > DEMO_INTRO) {
        fx[7] = 1;
        if (LOGEVT) console.log("EVT " + "climb" + " " + t.toFixed(3));
        scheduleOnRN(sfxEvent, "climb");
      }
      // a ring of light ripples out over the floor as it awakens (projected circle → screen ellipse)
      {
        const rg = ring.value, tm = tmp.value;
        const u = la >= 0 && la < 1.3 && t > (DEMO ? DEMO_INTRO : 0) ? la / 1.3 : -1;
        if (u >= 0) {
          const r = 0.25 + 2.4 * (1 - (1 - u) * (1 - u));
          const bx = lifeBase.value[0], by = lifeBase.value[1];
          project(c, bx, by, 0.003, tm, 0);
          rg[0] = tm[0];
          rg[1] = tm[1];
          project(c, bx + r, by, 0.003, tm, 0);
          const rx = Math.abs(tm[0] - rg[0]);
          project(c, bx, by + r, 0.003, tm, 0);
          const ry = Math.abs(tm[1] - rg[1]);
          rg[2] = rx;
          rg[3] = ry;
          rg[4] = (1 - u) * (1 - u);
        } else rg[4] = 0;
        ring.modify();
      }
      // pillar of light rising through the crane as it awakens (not on the demo's first frame: it is already alive there)
      {
        const b = ab.value, tm = tmp.value;
        const u = la >= 0 && la < 1.9 && t > (DEMO ? DEMO_INTRO : 0) ? la / 1.9 : 0;
        b[4] = u;
        if (u > 0) {
          const bx = lifeBase.value[0], by = lifeBase.value[1];
          project(c, bx, by, 0.003, tm, 0);
          b[0] = tm[0];
          b[1] = tm[1];
          b[5] = Math.max(18, Math.abs(tm[2] > 0 ? (0.32 * c[12]) / tm[2] : 30));
          project(c, st[0], st[1], st[2], tm, 0);
          b[2] = tm[0];
          b[3] = tm[1];
        }
        ab.modify();
      }
      if (la > TAKEOFF && la < TAKEOFF + 0.05) scheduleOnRN(haptic, 1);
      // light sweep through the paper as it awakens
      fx[4] = la >= 0 ? la / 0.9 : -1;
      fx[5] = la >= 0 ? Math.max(0, 1 - la / 1.4) : 0;
      // a little glitter dust off both wing tips while flying: sparse, scattered around the tip and of mixed sizes and
      // lifetimes, so it never lines up into a dotted line along the flight path
      if (la > TAKEOFF && la < FLIGHT_END) {
        fx[2] += dt * 9;
        const tp = tipsSv.value;
        while (fx[2] >= 1) {
          fx[2] -= 1;
          for (let k = 0; k < 2; k++) {
            const vi = tp[k];
            if (vi < 0) continue;
            if (rand(gp) < 0.4) continue;
            const j = 0.07;
            emit(gp, 0, sc.w[vi * 3] + (rand(gp) - 0.5) * j, sc.w[vi * 3 + 1] + (rand(gp) - 0.5) * j, sc.w[vi * 3 + 2] + (rand(gp) - 0.5) * j, (rand(gp) - 0.5) * 0.12, (rand(gp) - 0.5) * 0.12, -0.05 - rand(gp) * 0.05, 0.35 + rand(gp) * 0.9, 0.008 + rand(gp) * rand(gp) * 0.03);
          }
        }
      }
      // vanishing into the light: a soft warm glow, then petals and leaves drift in through the opening
      if (la >= 0 && st[3] > 0.7 && fx[1] === 0) {
        fx[1] = 1;
        if (LOGEVT) console.log("EVT " + "vanish" + " " + t.toFixed(3));
        scheduleOnRN(sfxEvent, "vanish");
        if (!DEMO) scheduleOnRN(setFlownJs, true);
        vb.value[2] = 1e-4;
      }
      if (la > FLIGHT_END - 0.6 && la < FLIGHT_END + 3.0) {
        fx[3] += dt * 12;
        while (fx[3] >= 1) {
          fx[3] -= 1;
          const leaf = rand(pp) < 0.55;
          emit(pp, leaf ? 5 : 3, c[0] - 3 + rand(pp) * 6, c[1] + 2.5 + rand(pp) * 4, c[2] - 0.5 + rand(pp) * 3.5, 0, 0, 0, 6 + rand(pp) * 3, leaf ? 0.13 + rand(pp) * 0.07 : 0.09 + rand(pp) * 0.04);
        }
      }
      // now and then a petal or a leaf drifts in through the open panel and across the room
      if (insideK.value > 0.5 && rand(pp) < dt * 0.55) {
        const leaf = rand(pp) < 0.35;
        emit(pp, leaf ? 5 : 3, -2.2 + rand(pp) * 4.4, 6.4, 1.2 + rand(pp) * 2.2, 0, 0, 0, 12 + rand(pp) * 4, leaf ? 0.09 + rand(pp) * 0.05 : 0.06 + rand(pp) * 0.03);
      }
      // frame 1 already has dust floating in the beam and a few leaves on their way in
      if (prewarm.value === 0) {
        prewarm.value = 1;
        for (let k = 0; k < 45; k++) emit(gp, 1, -2.5 + rand(gp) * 5, -1.5 + rand(gp) * 6.5, 0.1 + rand(gp) * 2.8, 0, 0, 0, 6 + rand(gp) * 5, 0.014 + rand(gp) * 0.014);
        for (let k = 0; k < 4; k++) emit(pp, k % 2 === 0 ? 5 : 3, -2.2 + rand(pp) * 4.4, 1 + rand(pp) * 5, 0.8 + rand(pp) * 2.2, 0, 0, 0, 12 + rand(pp) * 4, 0.07 + rand(pp) * 0.05);
        for (let k = 0; k < 30; k++) {
          stepPool(gp, 0.05, k * 0.05);
          stepPool(pp, 0.05, k * 0.05);
        }
      }
      // dust motes always floating in the beam
      if (rand(gp) < dt * 6) emit(gp, 1, -2.5 + rand(gp) * 5, -1.5 + rand(gp) * 6.5, 0.1 + rand(gp) * 2.8, 0, 0, 0, 6 + rand(gp) * 5, 0.014 + rand(gp) * 0.014);
      // the starburst stays pinned where the crane vanished
      {
        const b = vb.value;
        if (b[2] > 0) {
          const hd = held.value, tm = tmp.value;
          project(c, hd[0], hd[1], hd[2], tm, 0);
          b[0] = tm[0];
          b[1] = tm[1];
          b[3] = W * 0.16;
          b[2] += dt / 1.8;
          if (b[2] >= 1) b[2] = 0;
        }
        if (alive.value < 0) b[2] = 0;
        vb.modify();
      }
      stepPool(gp, dt, t);
      stepPool(pp, dt, t);
      glow.modify();
      petals.modify();
      fxs.modify();
    }
    buildGrid(c, 20, 26, [table.x[0], table.y[0], 0], [table.x[1] - table.x[0], 0, 0], [0, table.y[1] - table.y[0], 0], tableV.value, tmp.value);
    buildGrid(c, 12, 9, [back.x[0], back.y, back.z[0]], [back.x[1] - back.x[0], 0, 0], [0, 0, back.z[1] - back.z[0]], backV.value, tmp.value);
    {
      const ld = layerDefs.value;
      const bufs = [lv0, lv1, lv2, lv3, lv4];
      // outside ground between the floor edge and the garden painting (seen when the camera rises), textured with the
      // bottom strip of the garden layer
      if (gardenD.value.length) {
        const g = gardenD.value;
        // start the strip in front of the eye once the camera stands outside: vertices behind it would project wildly (the
        // depth is clamped) and tear a band along the bottom of the frame
        const y0 = Math.min(g[2] - 0.5, Math.max(6.9, c[1] + 0.35));
        const z0 = -0.35 + ((y0 - 6.9) / (g[2] - 6.9)) * (g[3] + 0.35);
        buildGrid(c, LG.nx, LG.ny, [g[0], y0, z0], [g[1] - g[0], 0, 0], [0, g[2] - y0, g[3] - z0], groundV.value, tmp.value);
        groundV.modify();
      }
      for (let i = 0; i < ld.length; i++) {
        const d = ld[i];
        buildGrid(c, LG.nx, LG.ny, [d[0], d[2], d[3]], [d[1] - d[0], 0, 0], [0, 0, d[4] - d[3]], bufs[i].value, tmp.value);
        bufs[i].modify();
      }
    }

    // swipe hint for the current step (only when resting at the step start)
    const hv = hint.value;
    if (si < nSteps) {
      const h = ss[si];
      const tm = tmp.value;
      project(c, h[2], h[3], h[4], tm, 0);
      hv[0] = tm[0];
      hv[1] = tm[1];
      project(c, h[5], h[6], h[7], tm, 0);
      hv[2] = tm[0];
      hv[3] = tm[1];
      // small late steps (the wings, the head) project to a tiny arrow: keep it at least HINT_MIN pt long (it is also the
      // swipe length that completes the step)
      {
        const dx = hv[2] - hv[0], dy = hv[3] - hv[1];
        const l = Math.hypot(dx, dy);
        if (l < HINT_MIN) {
          const ux = l > 1 ? dx / l : 0, uy = l > 1 ? dy / l : 1;
          hv[2] = hv[0] + ux * HINT_MIN;
          hv[3] = hv[1] + uy * HINT_MIN;
        }
      }
      const rest = Math.abs(p.value - h[0]) < 0.02 && drag.value[0] === 0 && !DEMO ? 1 : 0;
      hv[4] += (rest - hv[4]) * (1 - Math.exp(-5 * dt));
    } else hv[4] *= 0.9;

    {
      const tm = tmp.value;
      project(c, c[0] + sun[0] * 60, c[1] + sun[1] * 60, c[2] + sun[2] * 60, tm, 0);
      const sp2 = sunPt.value;
      // rays start at the sun when it is in view (outside, in the sky); indoors they pour in through the open panel
      // indoors the eaves hide the sun: the light enters through the opening
      const sunIn = insideK.value < 0.5 && tm[2] > 0.1 && tm[0] > -W * 0.2 && tm[0] < W * 1.2 && tm[1] > -H * 0.15 && tm[1] < H * 1.1 ? 1 : 0;
      let ox = tm[0], oy = tm[1];
      if (!sunIn) {
        project(c, -0.1, 7.0, 2.6, tm, 0);
        ox = tm[0];
        oy = Math.min(tm[1], H * 0.55);
      }
      const kk = 1 - Math.exp(-4 * dt);
      sp2[0] += (ox - sp2[0]) * (sp2[2] < 0 ? 1 : kk);
      sp2[1] += (oy - sp2[1]) * (sp2[2] < 0 ? 1 : kk);
      sp2[2] += (1 - sunIn - sp2[2]) * kk; // indoors 1, sky 0 (the shader's 'down')
      sunPt.modify();
    }
    paperV.modify();
    paperT.modify();
    paperV2.modify();
    paperT2.modify();
    shadowV.modify();
    lightT.modify();
    tableV.modify();
    backV.modify();
    hint.modify();
    life.modify();
  }
  useFrameCallback(({ timestamp }) => {
    "worklet";
    try {
      const t0 = PERF_LOG ? Date.now() : 0;
      tick(timestamp);
      if (PERF_LOG) {
        const pf = perf.value;
        pf[0] += 1;
        pf[1] += Date.now() - t0;
        if (pf[2] === 0) pf[2] = timestamp;
        if (timestamp - pf[2] > 2000) {
          console.log("PERF fps " + ((pf[0] * 1000) / (timestamp - pf[2])).toFixed(1) + " tick " + (pf[1] / pf[0]).toFixed(2) + "ms t " + time.value.toFixed(1));
          pf[0] = 0;
          pf[1] = 0;
          pf[2] = timestamp;
        }
      }
    } catch (err) {
      scheduleOnRN(reportErr, String(err) + " " + String((err as Error).stack ?? ""));
    }
  });

  // ── gestures: swipe along the hint arrow scrubs the step ──
  const pan = Gesture.Pan()
    .maxPointers(1)
    .minDistance(4)
    .enabled(!DEMO && !USERSIM)
    .onStart((e) => panBegin(e.x, e.y))
    .onUpdate((e) => panMove(e.x, e.y))
    .onEnd((e) => panRelease(e.velocityX, e.velocityY));
  const tap = Gesture.Tap()
    .maxDuration(250)
    .enabled(!DEMO && !USERSIM)
    .onEnd(() => tapSheet());
  const pan2 = Gesture.Pan()
    .minPointers(2)
    .maxPointers(2)
    .onStart(() => {
      drag2.set(1);
      const ob = orbit.value;
      orbit.set([ob[0], ob[1], ob[0], ob[1]]);
    })
    .onUpdate((e) => {
      const ob = orbit.value;
      orbit.set([ob[2] - e.translationX * 0.006, Math.max(-0.35, Math.min(0.45, ob[3] + e.translationY * 0.004)), ob[2], ob[3]]);
    })
    .onEnd(() => drag2.set(0));
  const gesture = Gesture.Race(pan2, pan, tap);

  // ── particle sprites ──
  const atlasImg = useImage(require("../../assets/fx/atlas.png"));
  const ptmp = useSharedValue(new Float32Array(3));
  const glowXf = useRSXformBuffer(NGLOW, (val, i) => {
    "worklet";
    spriteXform(glow.value, i, cam.value, ptmp.value, time.value, val);
  });
  const glowCol = useColorBuffer(NGLOW, (val, i) => {
    "worklet";
    spriteColor(glow.value, i, val as unknown as Float32Array, 1);
  });
  const glowRect = useRectBuffer(NGLOW, (val, i) => {
    "worklet";
    val.setXYWH(spriteCell(glow.value, i) * CELL, 0, CELL, CELL);
  });
  const petalXf = useRSXformBuffer(NPETAL, (val, i) => {
    "worklet";
    spriteXform(petals.value, i, cam.value, ptmp.value, time.value, val);
  });
  const petalCol = useColorBuffer(NPETAL, (val, i) => {
    "worklet";
    spriteColor(petals.value, i, val as unknown as Float32Array, 1);
  });
  const petalRect = useRectBuffer(NPETAL, (val, i) => {
    "worklet";
    leafCell(petals.value, i, val);
  });
  void STRIDE;
  const birdImg = useImage(require("../../assets/fx/bird.png"));
  const leavesImg = useImage(require("../../assets/fx/leaves.png"));
  const bpos = useSharedValue([0, 0, 0]);
  const birdXf = useRSXformBuffer(NBIRDS, (val, i) => {
    "worklet";
    birdXform(i, time.value, cam.value, ptmp.value, bpos.value, val);
  });
  const birdRect = useRectBuffer(NBIRDS, (val, i) => {
    "worklet";
    val.setXYWH(birdCell(i, time.value) * BIRD_CELL, 0, BIRD_CELL, BIRD_CELL);
  });

  const hintPath = useDerivedValue(() => {
    const h = hint.value;
    const path = Skia.PathBuilder.Make();
    path.moveTo(h[0], h[1]);
    path.lineTo(h[2], h[3]);
    // arrow head
    const dx = h[2] - h[0], dy = h[3] - h[1];
    const l = Math.hypot(dx, dy) || 1;
    const ux = dx / l, uy = dy / l;
    path.moveTo(h[2] - ux * 16 - uy * 9, h[3] - uy * 16 + ux * 9);
    path.lineTo(h[2], h[3]);
    path.lineTo(h[2] - ux * 16 + uy * 9, h[3] - uy * 16 - ux * 9);
    return path.build();
  });
  const hintOp = useDerivedValue(() => hint.value[4] * 0.9);
  const dotX = useDerivedValue(() => hint.value[0]);
  const dotY = useDerivedValue(() => hint.value[1]);
  // the dashes march toward the arrow head, and a soft comet glides along the swipe every 1.6 s (eased like a finger)
  const hintPhase = useDerivedValue(() => -((time.value * 26) % 19));
  const cometU = useDerivedValue(() => {
    const u = (time.value % 1.6) / 1.1;
    return u >= 1 ? -1 : u * u * (3 - 2 * u);
  });
  const cometX = useDerivedValue(() => hint.value[0] + (hint.value[2] - hint.value[0]) * Math.max(0, cometU.value));
  const cometY = useDerivedValue(() => hint.value[1] + (hint.value[3] - hint.value[1]) * Math.max(0, cometU.value));
  const cometOp = useDerivedValue(() => (cometU.value < 0 ? 0 : Math.sin(Math.PI * cometU.value) * 0.9));
  const dotR = useDerivedValue(() => 9 + 2.5 * Math.sin(time.value * 4.2));
  const shadowCore = useDerivedValue(() => 0.62 * shadowK.value * shadowK.value);
  const shadowSoft = useDerivedValue(() => 0.42 * shadowK.value);
  const ghostX = useDerivedValue(() => ghost.value[1]);
  const ghostY = useDerivedValue(() => ghost.value[2]);
  const ghostOp = useDerivedValue(() => ghost.value[3] * 0.62);
  const ghostC = useDerivedValue(() => vec(ghost.value[1] - 5, ghost.value[2] - 7));
  // a ring ripples out when the ghost finger presses down (ghost[0] = time since the step's wait began)
  const ghostR = useDerivedValue(() => 20 + Math.max(0, ghost.value[0] - DEMO_WAIT) * 60);
  const ghostRingOp = useDerivedValue(() => {
    const u = ghost.value[0] - DEMO_WAIT;
    return u < 0 || u > 0.4 ? 0 : (1 - u / 0.4) * 0.6;
  });
  const postU = useDerivedValue(() => ({ view: [W, H], sun: [0.3, 0.1], time: time.value }));
  const layerIdx = useMemo(() => gridIdx(LG.nx, LG.ny), []);
  const sizes = useMemo(() => Array.from({ length: MAXL }, (_, i) => (layerImgs && layerImgs[i] ? [layerImgs[i]!.width(), layerImgs[i]!.height()] : [1, 1])), [layerImgs]);
  // the glass wind chime painted in the house's open panel (house.png pixels): pivot x, y, swing strength (0 = none)
  const FURIN = LAYERS.slice(0, MAXL).map((l) => (/house/i.test(l.name) ? [921, 650, 1] : [0, 0, 0])).concat([[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]]);
  const lu0 = useDerivedValue(() => ({ size: sizes[0], time: time.value, drift: LAYERS[0]?.drift ?? 0, sway: LAYERS[0]?.sway ?? 0, furin: FURIN[0] }));
  const lu1 = useDerivedValue(() => ({ size: sizes[1], time: time.value, drift: LAYERS[1]?.drift ?? 0, sway: LAYERS[1]?.sway ?? 0, furin: FURIN[1] }));
  const lu2 = useDerivedValue(() => ({ size: sizes[2], time: time.value, drift: LAYERS[2]?.drift ?? 0, sway: LAYERS[2]?.sway ?? 0, furin: FURIN[2] }));
  const lu3 = useDerivedValue(() => ({ size: sizes[3], time: time.value, drift: LAYERS[3]?.drift ?? 0, sway: LAYERS[3]?.sway ?? 0, furin: FURIN[3] }));
  const lu4 = useDerivedValue(() => ({ size: sizes[4], time: time.value, drift: LAYERS[4]?.drift ?? 0, sway: LAYERS[4]?.sway ?? 0, furin: FURIN[4] }));
  const layerU = [lu0, lu1, lu2, lu3, lu4];
  const houseI = LAYERS.slice(0, MAXL).findIndex((l) => /house/i.test(l.name));
  const gardenI = LAYERS.slice(0, MAXL).findIndex((l) => /garden/i.test(l.name));
  const groundTex = useMemo(() => {
    if (gardenI < 0 || !layerImgs || !layerImgs[gardenI]) return null;
    const im = layerImgs[gardenI]!;
    const w = im.width(), h = im.height();
    const out = new Float32Array((LG.nx + 1) * (LG.ny + 1) * 2);
    for (let j = 0; j <= LG.ny; j++)
      for (let i = 0; i <= LG.nx; i++) {
        const k = j * (LG.nx + 1) + i;
        out[k * 2] = (i / LG.nx) * w;
        out[k * 2 + 1] = h - 2 - (j / LG.ny) * h * 0.06; // the last 6 % of the painting, stretched back to the garden plane
      }
    return out;
  }, [gardenI, layerImgs]);
  const houseY = houseI >= 0 ? LAYERS[houseI].y : 1e9;
  const outsideK = useDerivedValue(() => (flight.value[1] > houseY ? insideK.value : 0));
  const roomU = useDerivedValue(() => ({ time: time.value, sway: 1, sunK: 1 + 0.035 * Math.sin(time.value * 0.8) + 0.02 * Math.sin(time.value * 2.3) }));
  // out under the open sky: no lattice/leaf shadow on the paper any more, sky fill in the shade
  const skyK = useDerivedValue(() => {
    // flight is mutated in place by the frame worklet: read the clock too so this re-runs every frame
    if (time.value < -1) return 0;
    const u = Math.max(0, Math.min(1, (flight.value[1] - houseY + 0.4) / 1.8));
    return u * u * (3 - 2 * u);
  });
  // alive and flying: the paper keeps a faint inner glow, so it never turns into a dark shape in the room's shade
  const flyK = useDerivedValue(() => {
    const t = time.value;
    // demo intro: the hovering crane already glows a little, fading as the folds rewind
    if (DEMO && t < DEMO_INTRO + DEMO_REWIND) return 0.8 * Math.max(0, 1 - Math.max(0, t - DEMO_INTRO) / 0.6);
    if (alive.value < 0) return 0;
    const u = Math.max(0, Math.min(1, (t - alive.value - 0.15) / 0.9)); // swells with the awakening sweep
    return u * u * (3 - 2 * u);
  });
  // the lattice/leaf dapples on the paper: once the crane lifts off the floor the sun-projected lookups jump from facet to
  // facet (pale polygons on the body), so they fade out as it comes alive
  const maskU = useDerivedValue(() => ({ time: time.value, sway: 1, shade: 0.58 + 0.42 * Math.max(skyK.value, flyK.value) }));
  // backlit against the sunset the dark ink line would turn the edge-on wings into sticks: fade it
  const inkOp = useDerivedValue(() => 0.6 * (1 - 0.75 * skyK.value));
  const crackOp = useDerivedValue(() => 1);
  const crackCol = useDerivedValue(() => (paperSv.value === 0 ? "#c4200e" : PAPERS[paperSv.value].sh2));
  const maskU0 = useDerivedValue(() => ({ shade: 0.58 + 0.42 * Math.max(skyK.value, flyK.value) }));
  const syncMark = useDerivedValue(() => (time.value < 0.5 ? 1 : 0));
  // USERSIM touch dot (like iOS "Show Touches"): a soft translucent disc that swells a little while it drags
  const touchX = useDerivedValue(() => touch.value[0]);
  const touchY = useDerivedValue(() => touch.value[1]);
  const touchOp = useDerivedValue(() => touch.value[2]);
  const touchR = useDerivedValue(() => 19 + 2 * touch.value[3] + 4 * (1 - touch.value[2]));
  const ringOp = useDerivedValue(() => ring.value[4]);
  const ringRect = useDerivedValue(() => {
    const r = ring.value;
    return { x: r[0] - r[2], y: r[1] - r[3], width: r[2] * 2, height: r[3] * 2 };
  });
  const cutOp = useDerivedValue(() => cutK.value * cutK.value);
  const awakenU = useDerivedValue(() => ({ c: [ab.value[0], ab.value[1]], top: [ab.value[2], ab.value[3]], age: ab.value[4], w: ab.value[5], time: time.value }));
  const vanishU = useDerivedValue(() => ({ c: [vb.value[0], vb.value[1]], age: vb.value[2], size: vb.value[3], time: time.value }));
  const atmosU = useDerivedValue(() => ({ view: [W, H], sun: [sunPt.value[0], sunPt.value[1]], time: time.value, k: 1 + 0.6 * wideSv.value, down: Math.max(0, sunPt.value[2]) }));

  const ready = tableImg && backImg && frontImg && paperBackImg && fibreImg && maskImg && tableTex && backTex;
  // every painted layer, the light passes and the sprites too: frame 1 of the demo must be the full picture
  const allReady = !!ready && livingLight && !!layerImgs && layerImgs.every((im) => im) && !!atlasImg && !!birdImg && !!leavesImg;
  useEffect(() => {
    if (allReady && readySv.value === 0) readySv.set(1);
  }, [allReady, readySv]);
  useEffect(() => {
    // never hold the clock forever if an optional image fails to load
    const id = setTimeout(() => {
      if (readySv.value === 0) readySv.set(1);
    }, 5000);
    return () => clearTimeout(id);
  }, [readySv]);
  useEffect(() => {
    initSfx();
  }, []);
  const texSize = frontImg?.width() ?? 1024;
  // light through the paper: a single sheet glows when the sun is behind it, a folded stack of 4–16 layers barely does
  // (left as bright, the folded crane looked see-through), so the transmission fades over the first three folds
  const paperU = useDerivedValue(() => ({ texSize, sunCol, amb, glowK: 1.55 * Math.max(0.22, 1 - step.value / 3), toon: 0.7, time: time.value, magic: [fxs.value[4], 0.55 * fxs.value[5]], sky: Math.max(0.45 * skyK.value, 0.1 * flyK.value), dye: PAPERS[paperSv.value].dye, dyeK: PAPERS[paperSv.value].k, edgeK: 0.3 * (1 - flyK.value) }));
  const inkCol = useDerivedValue(() => PAPERS[paperSv.value].ink);
  const shadowCol1 = useDerivedValue(() => PAPERS[paperSv.value].sh1);
  const shadowCol2 = useDerivedValue(() => PAPERS[paperSv.value].sh2);

  const onLayout = (e: LayoutChangeEvent) => setSize({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height });

  return (
    <View style={styles.root} onLayout={onLayout}>
      <GestureDetector gesture={gesture}>
        <Canvas style={StyleSheet.absoluteFill}>
          {ready && (
            <Group>
              {/* backstop behind every layer: sky blue at the top, the forest shade at the bottom, so a sliver the layers
                  don't cover (the camera passing the veranda edge) reads as scenery, not as a blue band */}
              <Fill>
                <LinearGradient start={vec(0, 0)} end={vec(0, H)} colors={["#3a5687", "#7d86a8", "#4d6a48", "#3b5236"]} positions={[0, 0.45, 0.75, 1]} />
              </Fill>
              {layerImgs && layerTex && LAYERS.length > 0 ? (
                LAYERS.slice(0, MAXL).map((l, i) =>
                  layerImgs[i] && layerTex[i] && !((HIDE_LAYERS >> i) & 1) ? (
                    <Group key={l.name}>
                    {i === 1 && birdImg && <Atlas image={birdImg} sprites={birdRect} transforms={birdXf} sampling={LINEAR} opacity={0.85} />}
                    {/* the outside ground (behind the house frame, in front of the garden painting) */}
                    {i === houseI && groundTex && gardenI >= 0 && layerImgs[gardenI] && (
                      <Vertices vertices={groundV} textures={groundTex} indices={layerIdx} mode="triangles">
                        <ImageShader image={layerImgs[gardenI]} tx="clamp" ty="clamp" sampling={LINEAR} />
                      </Vertices>
                    )}
                    <Group opacity={i === houseI ? insideK : 1}>
                    <Vertices vertices={[lv0, lv1, lv2, lv3, lv4][i]} textures={layerTex[i]!} indices={layerIdx} mode="triangles">
                      <Shader source={layerFx} uniforms={layerU[i]}>
                        <ImageShader image={layerImgs[i]} tx="repeat" ty="clamp" sampling={LINEAR} />
                      </Shader>
                    </Vertices>
                    </Group>
                    </Group>
                  ) : null,
                )
              ) : (
                <Vertices vertices={backV} textures={backTex} indices={backIdx} mode="triangles">
                  <ImageShader image={backImg} sampling={LINEAR} />
                  <Blur blur={2.5} />
                </Vertices>
              )}
              <Group opacity={floorK}>
              {livingLight ? (
                <Vertices vertices={tableV} textures={tableTex} indices={tableIdx} mode="triangles">
                  <Shader source={tableFx} uniforms={roomU}>
                    <ImageShader image={passImgs![0]} sampling={LINEAR} />
                    <ImageShader image={passImgs![1]} sampling={LINEAR} />
                    <ImageShader image={passImgs![2]} sampling={LINEAR} />
                    <ImageShader image={passImgs![3]} sampling={LINEAR} />
                  </Shader>
                </Vertices>
              ) : (
                <Vertices vertices={tableV} textures={tableTex} indices={tableIdx} mode="triangles">
                  <ImageShader image={tableImg} sampling={LINEAR} />
                </Vertices>
              )}
              {/* paper shadow: a crisp core + a wide penumbra (sun disc + shoji diffusion); dilated by 1 pt first so the hairline
                  seams between the facets never show as light lines inside the shadow */}
              <Group opacity={shadowCore} blendMode="multiply">
                <Group layer={<Paint><Morphology operator="dilate" radius={1} /><Blur blur={2} /></Paint>}>
                  <Vertices vertices={shadowV} mode="triangles" color={shadowCol1} />
                </Group>
              </Group>
              <Group opacity={shadowSoft} blendMode="multiply">
                <Group layer={<Paint><Morphology operator="dilate" radius={1} /><Blur blur={10} /></Paint>}>
                  <Vertices vertices={shadowV} mode="triangles" color={shadowCol2} />
                </Group>
              </Group>
              </Group>
              {/* hairline cracks between the layers along a hinge (the wings swing about their own axes) would show the floor
                  through the fold: the paper silhouette closed by 7.5 mm of paper at the crane's distance (dilate, then erode back) in the paper's own red under
                  the paper fills them without growing the outline; seen edge-on, the stacked layers then read as one solid edge */}
              <Group opacity={crackOp} layer={<Paint><Morphology operator="erode" radius={crackR}><Morphology operator="dilate" radius={crackR} /></Morphology></Paint>}>
                <Vertices vertices={paperV} mode="triangles" color={crackCol} />
              </Group>
              {/* anime ink line: the paper silhouette dilated by 1.3 pt in a deep red-brown, drawn under the paper */}
              <Group opacity={inkOp} layer={<Paint><Morphology operator="dilate" radius={0.8} /><Blur blur={0.5} /></Paint>}>
                <Vertices vertices={paperV} mode="triangles" color={inkCol} />
              </Group>
              <Vertices vertices={paperV2} textures={paperT2} mode="triangles">
                <Shader source={paperFx} uniforms={paperU}>
                  <ImageShader image={frontImg} tx="repeat" ty="repeat" sampling={FLAT} />
                  <ImageShader image={paperBackImg} tx="repeat" ty="repeat" sampling={FLAT} />
                  <ImageShader image={fibreImg} tx="repeat" ty="repeat" sampling={FLAT} />
                </Shader>
              </Vertices>
              {/* once the crane is outside, the house frame (pillars, eaves) must cover it */}
              {houseI >= 0 && layerImgs && layerImgs[houseI] && layerTex && layerTex[houseI] && (
                <Group opacity={outsideK}>
                  <Vertices vertices={[lv0, lv1, lv2, lv3, lv4][houseI]} textures={layerTex[houseI]!} indices={layerIdx} mode="triangles">
                    <Shader source={layerFx} uniforms={layerU[houseI]}>
                      <ImageShader image={layerImgs[houseI]} tx="repeat" ty="clamp" sampling={LINEAR} />
                    </Shader>
                  </Vertices>
                </Group>
              )}
              {/* sun visibility on the paper: the same sorted facets, nearest wins inside the layer, multiplied onto the paper */}
              <Group layer={<Paint blendMode="multiply" />}>
                <Vertices vertices={paperV} textures={lightT} mode="triangles">
                  {livingLight ? (
                    <Shader source={paperMaskFx} uniforms={maskU}>
                      <ImageShader image={passImgs![2]} sampling={LINEAR} />
                      <ImageShader image={passImgs![3]} sampling={LINEAR} />
                    </Shader>
                  ) : (
                    <Shader source={sunMaskFx} uniforms={maskU0}>
                      <ImageShader image={maskImg} sampling={LINEAR} />
                    </Shader>
                  )}
                </Vertices>
              </Group>
              <Group blendMode="plus" opacity={ringOp}>
                <Oval rect={ringRect} style="stroke" strokeWidth={10} color="rgba(255,211,138,0.45)">
                  <Blur blur={9} />
                </Oval>
              </Group>
              {atlasImg && (
                <>
                  {leavesImg && <Atlas image={leavesImg} sprites={petalRect} transforms={petalXf} colors={petalCol} colorBlendMode="modulate" sampling={LINEAR} />}
                  <Group blendMode="plus">
                    <Atlas image={atlasImg} sprites={glowRect} transforms={glowXf} colors={glowCol} colorBlendMode="modulate" sampling={LINEAR} />
                  </Group>
                </>
              )}
              <StepDots n={steps.length} step={step} w={W} h={H} />
              <Group opacity={hintOp}>
                {/* warm glow under the dashed swipe line so it reads on both the bright paper and the shaded floor */}
                <Path path={hintPath} style="stroke" strokeWidth={9} strokeCap="round" strokeJoin="round" color="rgba(255,196,120,0.35)">
                  <Blur blur={5} />
                </Path>
                <Path path={hintPath} style="stroke" strokeWidth={3} strokeCap="round" strokeJoin="round" color="rgba(255,248,236,0.95)">
                  <DashPathEffect intervals={[10, 9]} phase={hintPhase} />
                </Path>
                <Circle cx={dotX} cy={dotY} r={dotR} color="rgba(255,248,236,0.5)" />
                <Group blendMode="plus" opacity={cometOp}>
                  <Circle cx={cometX} cy={cometY} r={16} color="rgba(255,190,110,0.55)">
                    <Blur blur={8} />
                  </Circle>
                  <Circle cx={cometX} cy={cometY} r={5} color="#fff6e6" />
                </Group>
              </Group>
              {DEMO && (
                <Group>
                  {/* fingertip: a soft contact shadow, a glassy disc lit from the top, a thin bright rim */}
                  <Group opacity={ghostOp}>
                    <Circle cx={ghostX} cy={ghostY} r={23} color="rgba(60,25,10,0.35)">
                      <Blur blur={6} />
                    </Circle>
                    <Circle cx={ghostX} cy={ghostY} r={20}>
                      <RadialGradient c={ghostC} r={26} colors={["rgba(255,252,246,0.95)", "rgba(255,244,228,0.55)"]} />
                    </Circle>
                    <Circle cx={ghostX} cy={ghostY} r={20} style="stroke" strokeWidth={1.4} color="rgba(255,255,255,0.9)" />
                  </Group>
                  <Circle cx={ghostX} cy={ghostY} r={ghostR} style="stroke" strokeWidth={2} color="#fff8ee" opacity={ghostRingOp} />
                </Group>
              )}
              <Fill blendMode="screen">
                <Shader source={atmosFx} uniforms={atmosU} />
              </Fill>
              <Fill blendMode="plus">
                <Shader source={vanishFx} uniforms={vanishU} />
              </Fill>
              <Fill blendMode="plus">
                <Shader source={awakenFx} uniforms={awakenU} />
              </Fill>
              <Fill blendMode="softLight">
                <Shader source={postFx} uniforms={postU} />
              </Fill>
              <Fill color="#fff3e0" opacity={cutOp} />
              {USERSIM && (
                <Group opacity={touchOp}>
                  <Circle cx={touchX} cy={touchY} r={touchR} color="rgba(40,30,25,0.16)">
                    <Blur blur={3} />
                  </Circle>
                  <Circle cx={touchX} cy={touchY} r={touchR} color="rgba(255,255,255,0.34)" />
                  <Circle cx={touchX} cy={touchY} r={touchR} style="stroke" strokeWidth={1.5} color="rgba(255,255,255,0.7)" />
                </Group>
              )}
              {/* demo sync marker in the top-left corner (hidden by the phone mockup's rounded corner) */}
              {LOGEVT && <Rect x={0} y={0} width={9} height={9} color="#ff00ff" opacity={syncMark} />}
            </Group>
          )}
        </Canvas>
      </GestureDetector>
      {!DEMO && (
        <Text style={styles.label} pointerEvents="none">
          {stepJs < steps.length ? `${stepJs + 1} / ${steps.length} · ${steps[stepJs].name}` : flownJs ? "Tap to fold another" : ""}
        </Text>
      )}
    </View>
  );
}

/** step progress: one small dot per fold, filled when done (hidden in the demo recording) */
function StepDots({ n, step, w, h }: { n: number; step: SharedValue<number>; w: number; h: number }) {
  const gap = 14;
  const x0 = w / 2 - ((n - 1) * gap) / 2;
  return (
    <Group opacity={DEMO ? 0 : 0.85}>
      {Array.from({ length: n }, (_, i) => (
        <Dot key={i} i={i} step={step} x={x0 + i * gap} y={h - 46} />
      ))}
    </Group>
  );
}
function Dot({ i, step, x, y }: { i: number; step: SharedValue<number>; x: number; y: number }) {
  const op = useDerivedValue(() => (step.value > i ? 0.95 : step.value === i ? 0.55 : 0.25));
  return <Circle cx={x} cy={y} r={3.5} color="#fff8ee" opacity={op} />;
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#fdf0d7" }, // same cream as the splash, so the launch never flashes dark
  label: {
    position: "absolute",
    bottom: 64,
    left: 0,
    right: 0,
    textAlign: "center",
    color: "rgba(255,248,236,0.82)",
    fontSize: 15,
    fontFamily: "Georgia",
    fontStyle: "italic",
    letterSpacing: 0.4,
    textShadowColor: "rgba(40,20,10,0.45)",
    textShadowRadius: 6,
  },
});
