import { project } from "../scene/camera";

/**
 * A loose V of swallows crossing the far sky every PERIOD seconds (bird.png: 3 wing frames of 128 px). Positions are analytic
 * in time, so there is no state: sprite i → RSXform / atlas cell.
 */
export const NBIRDS = 9;
export const BIRD_CELL = 128;
const PERIOD = 15;

export const birdPos = (i: number, t: number, out: number[]) => {
  "worklet";
  const u = ((t + 4) % PERIOD) / PERIOD; // 0..1 across the sky
  const row = Math.ceil(i / 2), side = i % 2 === 0 ? 1 : -1;
  const wob = Math.sin(t * 1.7 + i * 2.1) * 0.35;
  out[0] = -34 + 68 * u - row * 1.3 + wob * 0.4;
  out[1] = 44 + side * row * 1.1;
  out[2] = 10.5 + side * row * 0.25 + row * 0.55 + wob + Math.sin(u * Math.PI * 2) * 1.2;
};

export const birdXform = (
  i: number,
  t: number,
  cam: number[],
  tmp: Float32Array,
  pos: number[],
  out: { set: (scos: number, ssin: number, tx: number, ty: number) => void },
) => {
  "worklet";
  birdPos(i, t, pos);
  project(cam, pos[0], pos[1], pos[2], tmp, 0);
  if (tmp[2] < 1) {
    out.set(0.001, 0, -1e4, -1e4);
    return;
  }
  const sz = (0.9 * cam[12]) / tmp[2] / BIRD_CELL;
  const rot = Math.sin(t * 1.3 + i) * 0.12;
  const c = Math.cos(rot) * sz, s = Math.sin(rot) * sz;
  out.set(c, s, tmp[0] - (c * BIRD_CELL - s * BIRD_CELL) / 2, tmp[1] - (s * BIRD_CELL + c * BIRD_CELL) / 2);
};

/** wing frame: up, mid, down, mid … with a little phase per bird */
export const birdCell = (i: number, t: number) => {
  "worklet";
  const f = Math.floor(t * 9 + i * 1.7) % 4;
  return f === 0 ? 0 : f === 2 ? 2 : 1;
};
