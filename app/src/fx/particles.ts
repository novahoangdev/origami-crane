import { project } from "../scene/camera";

/**
 * World-space particles (UI-thread worklets, fixed pools, no allocation per frame), drawn with Skia Atlas sprites from
 * assets/fx/atlas.png (8 cells of 128 px: 0 sparkle, 1 soft dot, 2 star glint, 3–6 petal tumbling frames, 7 flash; see
 * tools/fx_atlas.py).
 *
 * Pool layout: one Float32Array, STRIDE floats per particle:
 *   0 x  1 y  2 z  3 vx  4 vy  5 vz  6 age  7 life (0 = dead)  8 size (world)  9 kind  10 spin  11 seed
 * kinds: 0 gold sparkle, 1 dust mote, 2 star glint, 3 petal, 4 flash, 5 leaf (uses the petal frames tinted green)
 */
export const STRIDE = 12;
export const CELL = 128;

export type Pool = { a: Float32Array; n: number; next: number; seed: number };

export const makePool = (n: number): Pool => ({ a: new Float32Array(n * STRIDE), n, next: 0, seed: 1 });

const rnd = (p: Pool) => {
  "worklet";
  // xorshift-ish LCG, deterministic so demo recordings repeat
  p.seed = (p.seed * 16807) % 2147483647;
  return p.seed / 2147483647;
};

export const emit = (
  p: Pool,
  kind: number,
  x: number,
  y: number,
  z: number,
  vx: number,
  vy: number,
  vz: number,
  life: number,
  size: number,
) => {
  "worklet";
  const i = p.next;
  p.next = (p.next + 1) % p.n;
  const o = i * STRIDE, a = p.a;
  a[o] = x;
  a[o + 1] = y;
  a[o + 2] = z;
  a[o + 3] = vx;
  a[o + 4] = vy;
  a[o + 5] = vz;
  a[o + 6] = 0;
  a[o + 7] = life;
  a[o + 8] = size;
  a[o + 9] = kind;
  a[o + 10] = (rnd(p) - 0.5) * 6;
  a[o + 11] = rnd(p);
};

/** burst of gold sparkles from a point (radius r), drifting up */
export const burst = (p: Pool, n: number, x: number, y: number, z: number, r: number, speed: number) => {
  "worklet";
  for (let k = 0; k < n; k++) {
    const th = rnd(p) * Math.PI * 2, ph = Math.acos(2 * rnd(p) - 1);
    const dx = Math.sin(ph) * Math.cos(th), dy = Math.sin(ph) * Math.sin(th), dz = Math.cos(ph);
    const sp = speed * (0.4 + rnd(p));
    emit(p, 0, x + dx * r, y + dy * r, z + dz * r, dx * sp, dy * sp, dz * sp + 0.35, 1.1 + rnd(p) * 1.1, 0.035 + rnd(p) * 0.07);
  }
};

export const rand = rnd;

/** tumble phase 0..1 of a leaf or petal (each one turns at its own rate) */
const leafPhase = (a: Float32Array, o: number) => {
  "worklet";
  const sd = a[o + 11];
  const x = a[o + 6] * (0.35 + sd * 0.55) + sd * 5;
  return x - Math.floor(x);
};

/**
 * Advance every particle. Sparkles slow down and sink a little; motes drift on a slow curl; petals and leaves fall with
 * flutter (wind from the open panel toward the camera).
 */
export const stepPool = (p: Pool, dt: number, t: number) => {
  "worklet";
  const a = p.a;
  for (let i = 0; i < p.n; i++) {
    const o = i * STRIDE;
    if (a[o + 7] <= 0) continue;
    a[o + 6] += dt;
    if (a[o + 6] >= a[o + 7]) {
      a[o + 7] = 0;
      continue;
    }
    const k = a[o + 9];
    const sd = a[o + 11];
    if (k === 0) {
      const dr = Math.exp(-1.8 * dt);
      a[o + 3] *= dr;
      a[o + 4] *= dr;
      a[o + 5] = a[o + 5] * dr - 0.25 * dt;
    } else if (k === 1) {
      a[o + 3] = 0.06 * Math.sin(t * 0.31 + sd * 40);
      a[o + 4] = 0.05 * Math.cos(t * 0.27 + sd * 23);
      a[o + 5] = 0.03 * Math.sin(t * 0.4 + sd * 11);
    } else if (k === 3 || k === 5) {
      // a real falling leaf: it tumbles (leafPhase), glides sideways while it lies flat to the air and drops while it is edge-on;
      // a light breeze from the open panel carries it toward the camera
      const ph = leafPhase(a, o) * Math.PI * 2;
      const flat = Math.abs(Math.cos(ph));
      const gust = 0.5 + 0.5 * Math.sin(t * 0.6 + sd * 7);
      a[o + 3] = 0.1 + 0.32 * flat * Math.sin(ph * 0.5 + sd * 11) + 0.08 * gust;
      a[o + 4] = -0.3 - 0.18 * gust;
      a[o + 5] = -0.12 - 0.3 * (1 - flat);
    }
    a[o] += a[o + 3] * dt;
    a[o + 1] += a[o + 4] * dt;
    a[o + 2] += a[o + 5] * dt;
  }
};

/** leaves.png cell for a leaf / petal sprite: 16 tumble frames per row; rows red maple, green maple, sakura petal */
export const LEAF_FRAMES = 16;
export const leafCell = (p: Pool, i: number, out: { setXYWH: (x: number, y: number, w: number, h: number) => void }) => {
  "worklet";
  const a = p.a, o = i * STRIDE;
  const k = a[o + 9];
  const row = k === 3 ? 2 : a[o + 11] < 0.55 ? 0 : 1;
  const f = Math.min(LEAF_FRAMES - 1, Math.floor(leafPhase(a, o) * LEAF_FRAMES));
  out.setXYWH(f * CELL, row * CELL, CELL, CELL);
};

/** fade envelope 0..1 of a particle (quick in, eased out) */
const env = (a: Float32Array, o: number) => {
  "worklet";
  const u = a[o + 6] / a[o + 7];
  return Math.min(1, u * 8) * (1 - u) * (1 - u) * (2 - (1 - u));
};

/**
 * RSXform for sprite i: world → screen with the camera, scale from the world size and depth, spin.
 * Dead sprites get a tiny scale far off-screen (never a zero RSXform: Graphite logs a warning per sprite per frame).
 */
export const spriteXform = (
  p: Pool,
  i: number,
  cam: number[],
  tmp: Float32Array,
  t: number,
  out: { set: (scos: number, ssin: number, tx: number, ty: number) => void },
) => {
  "worklet";
  const a = p.a, o = i * STRIDE;
  if (a[o + 7] <= 0) {
    out.set(0.001, 0, -1e4, -1e4);
    return;
  }
  project(cam, a[o], a[o + 1], a[o + 2], tmp, 0);
  if (tmp[2] < 0.3) {
    out.set(0.001, 0, -1e4, -1e4);
    return;
  }
  const k = a[o + 9];
  let sz = (a[o + 8] * cam[12]) / tmp[2] / (CELL * 0.5);
  if (k === 0) sz *= 0.75 + 0.5 * Math.abs(Math.sin(t * (6 + a[o + 11] * 9) + a[o + 11] * 50)); // twinkle
  if (k === 4) sz *= 0.6 + 1.4 * (a[o + 6] / a[o + 7]);
  // petals and leaves drifting right past the lens would fill the frame as soft blobs: cap them at ~80 pt
  if ((k === 3 || k === 5) && sz * CELL > 80) sz = 80 / CELL;
  const rot = k === 3 || k === 5 ? a[o + 10] * 0.12 * a[o + 6] + a[o + 11] * 6 : k === 2 ? a[o + 10] * 0.05 + t * 0.4 : a[o + 11] * 6;
  const c = Math.cos(rot) * sz, s = Math.sin(rot) * sz;
  // RSXform maps the sprite centre (CELL/2, CELL/2) onto the projected point
  out.set(c, s, tmp[0] - (c * CELL - s * CELL) / 2, tmp[1] - (s * CELL + c * CELL) / 2);
};

/** atlas cell for sprite i (petals/leaves pick a tumbling frame from their spin phase) */
export const spriteCell = (p: Pool, i: number) => {
  "worklet";
  const a = p.a, o = i * STRIDE;
  const k = a[o + 9];
  if (k === 0) return 0;
  if (k === 1) return 1;
  if (k === 2) return 2;
  if (k === 4) return 7;
  const ph = Math.abs(Math.sin(a[o + 6] * (2.2 + a[o + 11] * 2) + a[o + 11] * 9));
  return 3 + Math.min(3, Math.floor((1 - ph) * 4));
};

/** colour (premultiplied-ish modulate) for sprite i: writes r, g, b, a into c */
export const spriteColor = (p: Pool, i: number, c: Float32Array, glow: number) => {
  "worklet";
  const a = p.a, o = i * STRIDE;
  if (a[o + 7] <= 0) {
    c[0] = 0;
    c[1] = 0;
    c[2] = 0;
    c[3] = 0;
    return;
  }
  const e = env(a, o);
  const k = a[o + 9];
  if (k === 0) {
    // gold → white-hot core
    c[0] = 1;
    c[1] = 0.82 + 0.15 * a[o + 11];
    c[2] = 0.45 + 0.35 * a[o + 11];
    c[3] = e;
  } else if (k === 1) {
    c[0] = 1;
    c[1] = 0.9;
    c[2] = 0.7;
    c[3] = e * (0.25 + 0.35 * Math.abs(Math.sin(a[o + 6] * 1.3 + a[o + 11] * 20))) * glow;
  } else if (k === 2) {
    c[0] = 1;
    c[1] = 0.95;
    c[2] = 0.85;
    c[3] = Math.min(1, a[o + 8] * 6) * e;
  } else if (k === 4) {
    c[0] = 1;
    c[1] = 0.88;
    c[2] = 0.66;
    c[3] = e * 0.9;
  } else {
    // leaves and petals: the painted, Blender-lit sprites as they are (leaves.png), just faded in and out
    c[0] = 1;
    c[1] = 1;
    c[2] = 1;
    c[3] = Math.min(1, e * 1.6);
  }
  // Atlas colours modulate premultiplied sprite texels: premultiply so alpha also fades additive sprites
  c[0] *= c[3];
  c[1] *= c[3];
  c[2] *= c[3];
};
