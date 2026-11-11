/**
 * Perspective camera shared by every 3D layer (paper, shadow, table, backdrop). World: z up, table plane z = 0, the camera looks
 * toward +y. Same numbers as app/assets/scene/layout.json (Blender renders the room from this camera).
 *
 * A camera is packed into a flat number array so worklets can pass it around without allocating:
 *   [ex, ey, ez,  rx, ry, rz,  ux, uy, uz,  fx, fy, fz,  focalPx, cx, cy]
 */
export const CAM_BASE = { pos: [0, -4.2, 5.6], target: [0, 0.3, 0], fovY: 42 };
export const CAM_LEN = 15;

/** build the camera basis: orbit the base position around the target by yaw (around z) and pitch, then dolly by `dist` */
export const makeCamera = (
  out: number[],
  w: number,
  h: number,
  yaw: number,
  pitch: number,
  dist: number,
  tx: number,
  ty: number,
  tz: number,
  fovY: number,
) => {
  "worklet";
  const bx = CAM_BASE.pos[0] - CAM_BASE.target[0];
  const by = CAM_BASE.pos[1] - CAM_BASE.target[1];
  const bz = CAM_BASE.pos[2] - CAM_BASE.target[2];
  const r0 = Math.hypot(bx, by, bz) * dist;
  const az = Math.atan2(by, bx) + yaw;
  const el = Math.atan2(bz, Math.hypot(bx, by)) + pitch;
  const ex = tx + r0 * Math.cos(el) * Math.cos(az);
  const ey = ty + r0 * Math.cos(el) * Math.sin(az);
  const ez = tz + r0 * Math.sin(el);
  let fx = tx - ex, fy = ty - ey, fz = tz - ez;
  const fl = Math.hypot(fx, fy, fz);
  fx /= fl;
  fy /= fl;
  fz /= fl;
  // right = f × up(0,0,1)
  let rx = fy, ry = -fx;
  const rl = Math.hypot(rx, ry) || 1;
  rx /= rl;
  ry /= rl;
  // up = r × f
  const ux = ry * fz, uy = -rx * fz, uz = rx * fy - ry * fx;
  out[0] = ex;
  out[1] = ey;
  out[2] = ez;
  out[3] = rx;
  out[4] = ry;
  out[5] = 0;
  out[6] = ux;
  out[7] = uy;
  out[8] = uz;
  out[9] = fx;
  out[10] = fy;
  out[11] = fz;
  out[12] = h / 2 / Math.tan((fovY * Math.PI) / 360);
  out[13] = w / 2;
  out[14] = h / 2;
};

/** world point → screen; writes sx, sy and the view depth into out[o..o+2] */
export const project = (c: number[], x: number, y: number, z: number, out: Float32Array | number[], o: number) => {
  "worklet";
  const dx = x - c[0], dy = y - c[1], dz = z - c[2];
  const zc = Math.max(0.05, dx * c[9] + dy * c[10] + dz * c[11]);
  const xc = dx * c[3] + dy * c[4] + dz * c[5];
  const yc = dx * c[6] + dy * c[7] + dz * c[8];
  out[o] = c[13] + (xc / zc) * c[12];
  out[o + 1] = c[14] - (yc / zc) * c[12];
  out[o + 2] = zc;
};

/** camera from an eye point looking at a target (z up) */
export const makeCameraLook = (
  out: number[],
  w: number,
  h: number,
  ex: number,
  ey: number,
  ez: number,
  tx: number,
  ty: number,
  tz: number,
  fovY: number,
) => {
  "worklet";
  let fx = tx - ex, fy = ty - ey, fz = tz - ez;
  const fl = Math.hypot(fx, fy, fz) || 1;
  fx /= fl;
  fy /= fl;
  fz /= fl;
  let rx = fy, ry = -fx;
  const rl = Math.hypot(rx, ry) || 1;
  rx /= rl;
  ry /= rl;
  out[0] = ex;
  out[1] = ey;
  out[2] = ez;
  out[3] = rx;
  out[4] = ry;
  out[5] = 0;
  out[6] = ry * fz;
  out[7] = -rx * fz;
  out[8] = rx * fy - ry * fx;
  out[9] = fx;
  out[10] = fy;
  out[11] = fz;
  out[12] = h / 2 / Math.tan((fovY * Math.PI) / 360);
  out[13] = w / 2;
  out[14] = h / 2;
};
