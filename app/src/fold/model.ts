import { FOLD_META, FOLD_POS_B64 } from "./foldData";

/** Baked fold sequence (see PLAN §3): keyframe positions K × V × 3 (world units, z up, table z = 0). */
export type FoldStep = { name: string; from: number; to: number; hint: { a: number[]; b: number[] } };
export type FoldModel = {
  V: number;
  T: number;
  K: number;
  uv: number[];
  tris: number[];
  steps: FoldStep[];
  pos: number[]; // flat K*V*3 (plain array: cheap to copy into the UI runtime, fast to index in worklets)
  wingMask: number[] | null;
  axisL: number[][] | null;
  axisR: number[][] | null;
  head: number[] | null;
  tail: number[] | null;
};

const B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

const decode = (s: string): Float32Array => {
  const lut = new Uint8Array(128);
  for (let i = 0; i < B64.length; i++) lut[B64.charCodeAt(i)] = i;
  let n = (s.length / 4) * 3;
  if (s.endsWith("==")) n -= 2;
  else if (s.endsWith("=")) n -= 1;
  const out = new Uint8Array(n);
  let o = 0;
  for (let i = 0; i < s.length; i += 4) {
    const a = lut[s.charCodeAt(i)], b = lut[s.charCodeAt(i + 1)], c = lut[s.charCodeAt(i + 2)], d = lut[s.charCodeAt(i + 3)];
    const v = (a << 18) | (b << 12) | (c << 6) | d;
    if (o < n) out[o++] = (v >> 16) & 255;
    if (o < n) out[o++] = (v >> 8) & 255;
    if (o < n) out[o++] = v & 255;
  }
  return new Float32Array(out.buffer);
};

let cached: FoldModel | null = null;

export const loadFold = (): FoldModel => {
  if (cached) return cached;
  const m = FOLD_META as any;
  const pos = Array.from(decode(FOLD_POS_B64));
  cached = {
    V: m.vertexCount,
    T: m.triCount,
    K: m.keyframes,
    uv: m.uv,
    tris: m.tris,
    steps: m.steps,
    pos,
    wingMask: m.wings?.mask ?? null,
    axisL: m.wings?.axisL ?? null,
    axisR: m.wings?.axisR ?? null,
    head: m.head ?? null,
    tail: m.tail ?? null,
  };
  return cached;
};
