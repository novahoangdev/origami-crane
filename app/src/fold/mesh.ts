import { project } from "../scene/camera";

/**
 * Per-frame paper mesh (UI-thread worklets, no allocation): keyframe lerp → life transform → per-facet light → back-to-front sort →
 * packed Float32 buffers for Skia `<Vertices>` (unshared vertices, so every facet is flat-shaded like folded paper).
 *
 * Facet data rides in the texture coordinates (Skia Vertices has no cheap per-vertex attributes besides colours):
 *   tex.x = u·0.998 + 2·(diffuse8 + 256·frontVisible)
 *   tex.y = v·0.998 + 2·(trans8 + 256·spec4)   (kept < 8192 so float32 still resolves uv to ~0.5 px)
 * The paper shader splits them again with floor(x / 2) (see shaders/paper.ts).
 */

/** sort key: plane depth along a shared ray (true) or centroid depth (false) */
export const SORT_PLANE = true;
// per-facet self-shadowing darkened whole triangles, so shadow edges followed the triangulation in jagged steps: off
export const OCCLUDE = false;

export type Geo = {
  V: number;
  T: number;
  K: number;
  pos: number[];
  tris: number[];
  uv: number[];
  wing: number[]; // per vertex: −1 / 0 / +1
  axisL: number[]; // [px,py,pz, qx,qy,qz]
  axisR: number[];
};

export type Scratch = {
  w: Float32Array; // world positions V×3
  s: Float32Array; // screen x, y, depth V×3
  sh: Float32Array; // shadow screen positions V×3
  lt: Float32Array; // sun-mask image coords of the sun-projected point V×2
  dep: Float32Array; // facet depth T
  pkx: Float32Array; // packed facet terms T
  pky: Float32Array;
  cen: Float32Array; // facet centroids T×3
  sb: Float32Array; // sun-space facet data T×13 (3 × u,v,d + bbox)
  frame: number;
  lastP: number;
  m: Float32Array; // life rotation matrix (columns = images of x, y, z)
  glint: Float32Array; // brightest specular facet this frame: x, y, z, strength
  dn: Float32Array; // dominant facet normal of the last frame (area weighted): the stack direction
  vis: Float32Array; // sun visibility per facet (0.3^layers between the facet and the sun)
  ord: Int32Array; // back-to-front facet order, kept between frames (near-sorted → insertion sort is ~O(n))
  wf: Float32Array; // world positions without the body puff (see applyLife)
  flat: Int32Array; // [1] when wf is valid this frame
  axL: Float32Array; // wing hinge axes as used this frame (shifted when the layers are pressed together)
  axR: Float32Array;
  wn: Float32Array; // rest wing normals L, R (set by the scene from the last keyframe)
  gp: Float32Array; // newellOrder: per plane group nx, ny, nz, d, screen bbox, depth sum, count  (T×10)
  fg: Int32Array; // facet → group
  gof: Int32Array; // group offsets into glist (T+1)
  gfill: Int32Array;
  glist: Int32Array; // facets by group
  adj: Uint8Array; // group × group 'row is drawn before column'
  indeg: Int32Array;
  done: Uint8Array;
};

export const makeScratch = (V: number, T: number): Scratch => {
  const ord = new Int32Array(T);
  for (let i = 0; i < T; i++) ord[i] = i;
  return {
    w: new Float32Array(V * 3),
    s: new Float32Array(V * 3),
    sh: new Float32Array(V * 3),
    lt: new Float32Array(V * 2),
    dep: new Float32Array(T),
    pkx: new Float32Array(T),
    pky: new Float32Array(T),
    cen: new Float32Array(T * 3),
    vis: new Float32Array(T).fill(1),
    sb: new Float32Array(T * 13),
    frame: 0,
    lastP: 0,
    dn: new Float32Array([0, 0, 1]),
    m: new Float32Array(9),
    glint: new Float32Array(4),
    ord,
    wf: new Float32Array(V * 3),
    flat: new Int32Array(1),
    axL: new Float32Array(6),
    axR: new Float32Array(6),
    wn: new Float32Array(6),
    gp: new Float32Array(T * 10),
    fg: new Int32Array(T),
    gof: new Int32Array(T + 1),
    gfill: new Int32Array(T),
    glist: new Int32Array(T),
    adj: new Uint8Array(T * T),
    indeg: new Int32Array(T),
    done: new Uint8Array(T),
  };
};

/** rotate point (x,y,z) about the axis p→q by angle a, write into w[o..] */
const rotAxis = (w: Float32Array, o: number, ax: ArrayLike<number>, a: number) => {
  "worklet";
  const px = ax[0], py = ax[1], pz = ax[2];
  let kx = ax[3] - px, ky = ax[4] - py, kz = ax[5] - pz;
  const kl = Math.hypot(kx, ky, kz) || 1;
  kx /= kl;
  ky /= kl;
  kz /= kl;
  const vx = w[o] - px, vy = w[o + 1] - py, vz = w[o + 2] - pz;
  const c = Math.cos(a), s = Math.sin(a);
  const d = kx * vx + ky * vy + kz * vz;
  // Rodrigues
  w[o] = px + vx * c + (ky * vz - kz * vy) * s + kx * d * (1 - c);
  w[o + 1] = py + vy * c + (kz * vx - kx * vz) * s + ky * d * (1 - c);
  w[o + 2] = pz + vz * c + (kx * vy - ky * vx) * s + kz * d * (1 - c);
};

/**
 * Life transform after the last fold: wing flap about the hinge axes, then a rigid body motion about the body centre c:
 * roll about the body's forward axis, pitch about its left axis, yaw about z, uniform scale, then move c to c + t.
 *   life = [flap, yaw, pitch, tx, ty, tz, cx, cy, cz, heading, roll, scale, thin]
 * heading = rest forward angle in the xy plane (tail → head).
 */
const applyLife = (g: Geo, sc: Scratch, life: number[]) => {
  "worklet";
  const w = sc.w;
  const flap = life[0];
  const aL = sc.axL, aR = sc.axR;
  for (let k = 0; k < 6; k++) {
    aL[k] = g.axisL[k] ?? 0;
    aR[k] = g.axisR[k] ?? 0;
  }
  // thin = 0..1 (life[12]): the living crane's layers pressed together. The bake keeps every layer 4 mm apart (exact
  // for folding), so a body ~3 cm thick with 1 cm gaps between the stacks; seen edge-on in flight the sky showed through
  // the gaps between the neck, body and wing stacks. Body, neck and tail lie in y planes: squeeze them toward the body's
  // mid plane; each wing is shifted with its hinge and its own layers squeezed toward the hinge plane, so the roots
  // stay on the body.
  const th = life[12] ?? 0;
  // wf: the same crane without the body puff (planar layers) for newellOrder: the puff bends every body facet, which
  // would split the plane groups into single facets; the layer order is the same with or without it
  const wf = sc.wf;
  sc.flat[0] = th > 0 && g.axisL.length === 6 ? 1 : 0;
  if (th > 0 && g.axisL.length === 6) {
    // body layers pressed to 40 % (the cracks left are closed in the scene), wing layers to 10 % (a wing is thin)
    const k = 1 - 0.6 * th, kw = 1 - 0.9 * th;
    // and the body puffs out like a real crane's when its wings are pulled: the two halves of the body (either side of the
    // mid plane) bow apart below the wing hinge, most in the middle, not at the hinge line or the bottom point
    const zh = g.axisL[2], xc = 0.065, puff = 0.055 * th;
    const yL = g.axisL[1], yR = g.axisR[1], ym = (yL + yR) / 2;
    const dL = ym + (yL - ym) * k - yL, dR = ym + (yR - ym) * k - yR;
    aL[1] += dL;
    aL[4] += dL;
    aR[1] += dR;
    aR[4] += dR;
    const nWL = sc.wn; // wing normals (rest pose), computed once from the first wing facet of each side
    for (let i = 0; i < g.V; i++) {
      const o = i * 3, m = g.wing[i];
      if (m === 0) {
        const y0 = w[o + 1] - ym;
        let y1 = y0 * k;
        const z = w[o + 2];
        if (z > 0 && z < zh) {
          const ux = (w[o] - xc) / 0.26;
          const bx = Math.max(0, 1 - ux * ux);
          y1 += (y0 >= 0 ? 1 : -1) * puff * Math.pow(Math.sin((Math.PI * z) / zh), 0.8) * bx;
        }
        w[o + 1] = ym + y1;
        wf[o] = w[o];
        wf[o + 1] = ym + y0 * k;
        wf[o + 2] = z;
        continue;
      }
      const b = m < 0 ? 0 : 3, ax = m < 0 ? aL : aR, dy = m < 0 ? dL : dR;
      w[o + 1] += dy;
      const nx = nWL[b], ny = nWL[b + 1], nz = nWL[b + 2];
      const d = (w[o] - ax[0]) * nx + (w[o + 1] - ax[1]) * ny + (w[o + 2] - ax[2]) * nz;
      w[o] -= nx * d * (1 - kw);
      w[o + 1] -= ny * d * (1 - kw);
      w[o + 2] -= nz * d * (1 - kw);
      wf[o] = w[o];
      wf[o + 1] = w[o + 1];
      wf[o + 2] = w[o + 2];
    }
  }
  const fl = sc.flat[0] === 1;
  if (flap !== 0 && g.axisL.length === 6) {
    for (let i = 0; i < g.V; i++) {
      const m = g.wing[i];
      if (m < 0) rotAxis(w, i * 3, aL, -flap);
      else if (m > 0) rotAxis(w, i * 3, aR, flap);
      if (fl && m < 0) rotAxis(wf, i * 3, aL, -flap);
      else if (fl && m > 0) rotAxis(wf, i * 3, aR, flap);
    }
  }
  const yaw = life[1], pitch = life[2], roll = life[10] ?? 0, scl = life[11] ?? 1;
  if (yaw === 0 && pitch === 0 && roll === 0 && scl === 1 && life[3] === 0 && life[4] === 0 && life[5] === 0) return;
  const ox = life[6], oy = life[7], oz = life[8], hd = life[9];
  // body frame at rest: f = forward, l = left, u = up
  const fx = Math.cos(hd), fy = Math.sin(hd);
  const lx = -fy, ly = fx;
  // rotation matrix M = Rz(yaw) · Rl(−pitch) · Rf(roll), built by rotating the basis vectors
  const cr = Math.cos(roll), sr = Math.sin(roll), cp = Math.cos(-pitch), sp = Math.sin(-pitch), cy = Math.cos(yaw), sy = Math.sin(yaw);
  const m = sc.m;
  for (let k = 0; k < 3; k++) {
    let x = k === 0 ? 1 : 0, y = k === 1 ? 1 : 0, z = k === 2 ? 1 : 0;
    // roll about f (horizontal axis): Rodrigues with k = (fx, fy, 0)
    let d = fx * x + fy * y;
    let x1 = x * cr + fy * z * sr + fx * d * (1 - cr);
    let y1 = y * cr - fx * z * sr + fy * d * (1 - cr);
    let z1 = z * cr + (fx * y - fy * x) * sr;
    // pitch about l
    d = lx * x1 + ly * y1;
    const x2 = x1 * cp + ly * z1 * sp + lx * d * (1 - cp);
    const y2 = y1 * cp - lx * z1 * sp + ly * d * (1 - cp);
    const z2 = z1 * cp + (lx * y1 - ly * x1) * sp;
    // yaw about z
    x1 = x2 * cy - y2 * sy;
    y1 = x2 * sy + y2 * cy;
    z1 = z2;
    m[k * 3] = x1 * scl;
    m[k * 3 + 1] = y1 * scl;
    m[k * 3 + 2] = z1 * scl;
  }
  const tx = ox + life[3], ty = oy + life[4], tz = oz + life[5];
  for (let i = 0; i < g.V; i++) {
    const o = i * 3;
    const vx = w[o] - ox, vy = w[o + 1] - oy, vz = w[o + 2] - oz;
    w[o] = tx + m[0] * vx + m[3] * vy + m[6] * vz;
    w[o + 1] = ty + m[1] * vx + m[4] * vy + m[7] * vz;
    w[o + 2] = tz + m[2] * vx + m[5] * vy + m[8] * vz;
    if (fl) {
      const ux = wf[o] - ox, uy = wf[o + 1] - oy, uz = wf[o + 2] - oz;
      wf[o] = tx + m[0] * ux + m[3] * uy + m[6] * uz;
      wf[o + 1] = ty + m[1] * ux + m[4] * uy + m[7] * uz;
      wf[o + 2] = tz + m[2] * ux + m[5] * uy + m[8] * uz;
    }
  }
};

/**
 * Self-shadowing through the paper: for each facet centroid, count the other facets between it and the sun. Everything is
 * projected into "sun space" (u, v across the beam, d toward the sun), so most pairs are rejected by a 2D bbox test and the rest
 * by a 2D point-in-triangle test. Paper is translucent: every layer in between keeps ~30 % of the light.
 * Work is spread over `phases` frames (facets t ≡ phase mod phases), the result is smooth enough for paper.
 */
const sunOcclusion = (g: Geo, sc: Scratch, sun: number[], phase: number, phases: number) => {
  "worklet";
  const T = g.T, w = sc.w, tris = g.tris, cen = sc.cen, vis = sc.vis, sb = sc.sb;
  const dx = sun[0], dy = sun[1], dz = sun[2];
  // e1 = normalize(d × z), e2 = d × e1
  let e1x = dy, e1y = -dx;
  const el = Math.hypot(e1x, e1y) || 1;
  e1x /= el;
  e1y /= el;
  const e2x = -dz * e1y, e2y = dz * e1x, e2z = dx * e1y - dy * e1x;
  // per facet: 3 projected vertices (u, v, d) + bbox
  for (let t = 0; t < T; t++) {
    const o = t * 13;
    let u0 = 1e9, u1 = -1e9, v0 = 1e9, v1 = -1e9;
    for (let k = 0; k < 3; k++) {
      const q = tris[t * 3 + k] * 3;
      const x = w[q], y = w[q + 1], z = w[q + 2];
      const u = x * e1x + y * e1y, v = x * e2x + y * e2y + z * e2z, d = x * dx + y * dy + z * dz;
      sb[o + k * 3] = u;
      sb[o + k * 3 + 1] = v;
      sb[o + k * 3 + 2] = d;
      u0 = Math.min(u0, u);
      u1 = Math.max(u1, u);
      v0 = Math.min(v0, v);
      v1 = Math.max(v1, v);
    }
    sb[o + 9] = u0;
    sb[o + 10] = u1;
    sb[o + 11] = v0;
    sb[o + 12] = v1;
  }
  for (let t = phase; t < T; t += phases) {
    const cx = cen[t * 3], cy = cen[t * 3 + 1], cz = cen[t * 3 + 2];
    const pu = cx * e1x + cy * e1y, pv = cx * e2x + cy * e2y + cz * e2z, pd = cx * dx + cy * dy + cz * dz + 1e-3;
    let n = 0;
    for (let u = 0; u < T && n < 3; u++) {
      const o = u * 13;
      if (u === t || pu < sb[o + 9] || pu > sb[o + 10] || pv < sb[o + 11] || pv > sb[o + 12]) continue;
      const au = sb[o], av = sb[o + 1], ad = sb[o + 2];
      const bu = sb[o + 3] - au, bv = sb[o + 4] - av, bd = sb[o + 5] - ad;
      const cu = sb[o + 6] - au, cv = sb[o + 7] - av, cd = sb[o + 8] - ad;
      const det = bu * cv - bv * cu;
      if (det > -1e-9 && det < 1e-9) continue;
      const qu = pu - au, qv = pv - av;
      const l1 = (qu * cv - qv * cu) / det, l2 = (bu * qv - bv * qu) / det;
      if (l1 < 0 || l2 < 0 || l1 + l2 > 1) continue;
      if (ad + l1 * bd + l2 * cd > pd) n++;
    }
    vis[t] = n === 0 ? 1 : n === 1 ? 0.3 : n === 2 ? 0.09 : 0.03;
  }
};

/**
 * Exact back-to-front order for the living crane (Newell, on layers): facets are grouped by their plane (one group = one
 * flat piece of one layer; pieces of the same plane never overlap). For every pair of groups whose screen boxes overlap,
 * the planes decide which is in front: A is in front of B when all of A lies on the camera's side of B's plane, or all of
 * B on the far side of A's plane (straddling pairs stay undecided). Groups are drawn in a topological order of these
 * relations, the farthest ready group first; a cycle (rare) is broken by depth. Exact for stacked parallel layers and for
 * the wings swinging against the body, where one sort key per facet flipped the order from frame to frame (a wing drawn
 * over the neck, the neck's inner part showing through the wing).
 */
const newellOrder = (g: Geo, sc: Scratch, ex: number, ey: number, ez: number) => {
  "worklet";
  const T = g.T, w = sc.flat[0] === 1 ? sc.wf : sc.w, s = sc.s, tris = g.tris, dep = sc.dep;
  const gp = sc.gp, gof = sc.gof, adj = sc.adj, indeg = sc.indeg, done = sc.done, ord = sc.ord, fg = sc.fg;
  let G = 0;
  // 1. planes → groups (gp per group: nx, ny, nz, d (camera-oriented), x0, x1, y0, y1, depth sum, count)
  for (let t = 0; t < T; t++) {
    const a = tris[t * 3] * 3, b = tris[t * 3 + 1] * 3, c = tris[t * 3 + 2] * 3;
    const e1x = w[b] - w[a], e1y = w[b + 1] - w[a + 1], e1z = w[b + 2] - w[a + 2];
    const e2x = w[c] - w[a], e2y = w[c + 1] - w[a + 1], e2z = w[c + 2] - w[a + 2];
    let nx = e1y * e2z - e1z * e2y, ny = e1z * e2x - e1x * e2z, nz = e1x * e2y - e1y * e2x;
    const nl = Math.hypot(nx, ny, nz);
    if (nl < 1e-12) {
      fg[t] = -1;
      continue;
    }
    nx /= nl;
    ny /= nl;
    nz /= nl;
    let d = nx * w[a] + ny * w[a + 1] + nz * w[a + 2];
    if (nx * ex + ny * ey + nz * ez - d < 0) {
      nx = -nx;
      ny = -ny;
      nz = -nz;
      d = -d;
    }
    let k = -1;
    for (let q = 0; q < G; q++) {
      const o = q * 10;
      if (gp[o] * nx + gp[o + 1] * ny + gp[o + 2] * nz > 0.99995 && Math.abs(gp[o + 3] - d) < 2e-4) {
        k = q;
        break;
      }
    }
    const x0 = Math.min(s[a], s[b], s[c]), x1 = Math.max(s[a], s[b], s[c]);
    const y0 = Math.min(s[a + 1], s[b + 1], s[c + 1]), y1 = Math.max(s[a + 1], s[b + 1], s[c + 1]);
    if (k < 0) {
      k = G++;
      const o = k * 10;
      gp[o] = nx;
      gp[o + 1] = ny;
      gp[o + 2] = nz;
      gp[o + 3] = d;
      gp[o + 4] = x0;
      gp[o + 5] = x1;
      gp[o + 6] = y0;
      gp[o + 7] = y1;
      gp[o + 8] = 0;
      gp[o + 9] = 0;
    } else {
      const o = k * 10;
      gp[o + 4] = Math.min(gp[o + 4], x0);
      gp[o + 5] = Math.max(gp[o + 5], x1);
      gp[o + 6] = Math.min(gp[o + 6], y0);
      gp[o + 7] = Math.max(gp[o + 7], y1);
    }
    gp[k * 10 + 8] += dep[t];
    gp[k * 10 + 9] += 1;
    fg[t] = k;
  }
  // facets listed by group (counting sort), so the side tests can run over a group's vertices
  gof.fill(0, 0, G + 1);
  for (let t = 0; t < T; t++) if (fg[t] >= 0) gof[fg[t] + 1]++;
  for (let q = 0; q < G; q++) gof[q + 1] += gof[q];
  const fill = sc.gfill;
  for (let q = 0; q < G; q++) fill[q] = gof[q];
  const glist = sc.glist;
  for (let t = 0; t < T; t++) if (fg[t] >= 0) glist[fill[fg[t]]++] = t;
  // 2. relations between overlapping groups
  for (let i = 0; i < G * G; i++) adj[i] = 0;
  for (let q = 0; q < G; q++) {
    indeg[q] = 0;
    done[q] = 0;
  }
  const E = 1e-4;
  for (let i = 0; i < G; i++) {
    const oi = i * 10;
    for (let j = i + 1; j < G; j++) {
      const oj = j * 10;
      if (gp[oi + 5] < gp[oj + 4] || gp[oj + 5] < gp[oi + 4] || gp[oi + 7] < gp[oj + 6] || gp[oj + 7] < gp[oi + 6]) continue;
      // parallel layers (most pairs): the plane offsets decide, the one nearer the camera is in front
      if (gp[oi] * gp[oj] + gp[oi + 1] * gp[oj + 1] + gp[oi + 2] * gp[oj + 2] > 0.9995) {
        const dd = gp[oi + 3] - gp[oj + 3];
        if (dd > E) {
          adj[j * G + i] = 1;
          indeg[i]++;
        } else if (dd < -E) {
          adj[i * G + j] = 1;
          indeg[j]++;
        }
        continue;
      }
      // i's vertices against j's plane, and j's against i's
      let ip = 0, ineg = 0, jp = 0, jneg = 0;
      for (let f = gof[i]; f < gof[i + 1]; f++) {
        const t = glist[f];
        for (let k = 0; k < 3; k++) {
          const v = tris[t * 3 + k] * 3;
          const dd = gp[oj] * w[v] + gp[oj + 1] * w[v + 1] + gp[oj + 2] * w[v + 2] - gp[oj + 3];
          if (dd > E) ip++;
          else if (dd < -E) ineg++;
        }
      }
      for (let f = gof[j]; f < gof[j + 1]; f++) {
        const t = glist[f];
        for (let k = 0; k < 3; k++) {
          const v = tris[t * 3 + k] * 3;
          const dd = gp[oi] * w[v] + gp[oi + 1] * w[v + 1] + gp[oi + 2] * w[v + 2] - gp[oi + 3];
          if (dd > E) jp++;
          else if (dd < -E) jneg++;
        }
      }
      const fi = ineg === 0 ? 1 : ip === 0 ? -1 : 0, fj = jneg === 0 ? 1 : jp === 0 ? -1 : 0;
      const iFront = fi > 0 || fj < 0, jFront = fi < 0 || fj > 0;
      if (iFront && !jFront) {
        adj[j * G + i] = 1;
        indeg[i]++;
      } else if (jFront && !iFront) {
        adj[i * G + j] = 1;
        indeg[j]++;
      }
    }
  }
  // 3. topological order of the groups, farthest ready first; then their facets
  let n = 0;
  for (let k = 0; k < G; k++) {
    let best = -1, bd = -1e30, forced = -1, fd = -1e30;
    for (let q = 0; q < G; q++) {
      if (done[q]) continue;
      const dq = gp[q * 10 + 8] / gp[q * 10 + 9];
      if (indeg[q] === 0 && dq > bd) {
        bd = dq;
        best = q;
      }
      if (dq > fd) {
        fd = dq;
        forced = q;
      }
    }
    const q = best >= 0 ? best : forced;
    done[q] = 1;
    for (let f = gof[q]; f < gof[q + 1]; f++) ord[n++] = glist[f];
    const r = q * G;
    for (let u = 0; u < G; u++) if (adj[r + u]) indeg[u]--;
  }
  // degenerate facets last (they draw nothing)
  for (let t = 0; t < T; t++) if (fg[t] < 0) ord[n++] = t;
};

/**
 * Build one frame.
 *   p     keyframe position (float, 0..K−1)
 *   cam   packed camera (scene/camera.ts)
 *   sun   unit vector toward the sun
 *   outV / outT  paper vertices / texcoords (T×3×2), sorted back to front
 *   outS  shadow vertices (T×3×2), projected onto the table along the sun
 *   outL  sun-mask texcoords (T×3×2, sorted like outV): where the sun ray through each vertex meets the table, so the shoji
 *         lattice shadow (sunmask.jpg) also falls across the paper
 *   lm    [x0, y0, x1, y1, imgW, imgH] table region of the sun mask
 */
export const buildPaper = (
  g: Geo,
  sc: Scratch,
  p: number,
  life: number[],
  cam: number[],
  sun: number[],
  outV: Float32Array,
  outT: Float32Array,
  outS: Float32Array,
  outL: Float32Array,
  lm: number[],
  parts = false,
) => {
  "worklet";
  const V = g.V, T = g.T;
  const lt = sc.lt;
  const k0 = Math.max(0, Math.min(g.K - 1, Math.floor(p)));
  const k1 = Math.min(g.K - 1, k0 + 1);
  const f = Math.max(0, Math.min(1, p - k0));
  const b0 = k0 * V * 3, b1 = k1 * V * 3;
  const pos = g.pos, w = sc.w, s = sc.s, sh = sc.sh;
  for (let i = 0; i < V * 3; i++) w[i] = pos[b0 + i] + (pos[b1 + i] - pos[b0 + i]) * f;
  // a fresh sheet is never perfectly flat: the corners curl up a little, relaxing during the first fold
  const curl = Math.max(0, 1 - p / 14);
  if (curl > 0) {
    const uvs = g.uv;
    for (let i = 0; i < V; i++) {
      const u = uvs[i * 2], v = uvs[i * 2 + 1];
      const du = Math.min(u, 1 - u), dv = Math.min(v, 1 - v);
      const cr = Math.max(0, 1 - Math.hypot(du, dv) / 0.32);
      const ed = Math.max(0, 1 - Math.min(du, dv) / 0.12);
      w[i * 3 + 2] += curl * (0.05 * cr * cr + 0.008 * ed * ed) * (0.8 + 0.4 * Math.sin(u * 5.1 + v * 3.7));
    }
  }
  applyLife(g, sc, life);
  const lx = sun[0], ly = sun[1], lz = Math.max(0.05, sun[2]);
  for (let i = 0; i < V; i++) {
    const o = i * 3;
    project(cam, w[o], w[o + 1], w[o + 2], s, o);
    // shadow: slide along −sun down to the table
    // + a little lift so the sheet lying flat still shows a thin contact shadow along its edges
    const h = Math.max(0, w[o + 2]) + 0.035;
    const gx = w[o] - (lx * h) / lz, gy = w[o + 1] - (ly * h) / lz;
    project(cam, gx, gy, 0.001, sh, o);
    lt[i * 2] = ((gx - lm[0]) / (lm[2] - lm[0])) * lm[4];
    lt[i * 2 + 1] = ((lm[3] - gy) / (lm[3] - lm[1])) * lm[5];
  }
  const ex = cam[0], ey = cam[1], ez = cam[2];
  // shared sort ray: eye → model centre
  let mx0 = 0, my0 = 0, mz0 = 0;
  for (let i = 0; i < V; i++) {
    mx0 += w[i * 3];
    my0 += w[i * 3 + 1];
    mz0 += w[i * 3 + 2];
  }
  let rx0 = mx0 / V - ex, ry0 = my0 / V - ey, rz0 = mz0 / V - ez;
  const rl0 = Math.hypot(rx0, ry0, rz0) || 1;
  rx0 /= rl0;
  ry0 /= rl0;
  rz0 /= rl0;
  const rf0 = rx0 * cam[9] + ry0 * cam[10] + rz0 * cam[11];
  const tris = g.tris, dep = sc.dep, cen = sc.cen;
  const dn0 = sc.dn[0], dn1 = sc.dn[1], dn2 = sc.dn[2];
  const gl = sc.glint;
  gl[3] = 0;
  let an0 = 0, an1 = 0, an2 = 0;
  for (let t = 0; t < T; t++) {
    const a = tris[t * 3] * 3, b = tris[t * 3 + 1] * 3, c = tris[t * 3 + 2] * 3;
    cen[t * 3] = (w[a] + w[b] + w[c]) / 3;
    cen[t * 3 + 1] = (w[a + 1] + w[b + 1] + w[c + 1]) / 3;
    cen[t * 3 + 2] = (w[a + 2] + w[b + 2] + w[c + 2]) / 3;
  }
  // spread over 2 frames when the paper is calm; every facet every frame when it moves fast (rewind, quick folds)
  const fast = Math.abs(p - sc.lastP) > 0.35;
  sc.lastP = p;
  sc.frame = (sc.frame + 1) % 2;
  if (OCCLUDE && T <= 1500) sunOcclusion(g, sc, sun, fast ? 0 : sc.frame, fast ? 1 : 2);
  for (let t = 0; t < T; t++) {
    const a = tris[t * 3] * 3, b = tris[t * 3 + 1] * 3, c = tris[t * 3 + 2] * 3;
    const e1x = w[b] - w[a], e1y = w[b + 1] - w[a + 1], e1z = w[b + 2] - w[a + 2];
    const e2x = w[c] - w[a], e2y = w[c + 1] - w[a + 1], e2z = w[c + 2] - w[a + 2];
    let nx = e1y * e2z - e1z * e2y, ny = e1z * e2x - e1x * e2z, nz = e1x * e2y - e1y * e2x;
    const nl = Math.hypot(nx, ny, nz) || 1;
    nx /= nl;
    ny /= nl;
    nz /= nl;
    const mx = (w[a] + w[b] + w[c]) / 3, my = (w[a + 1] + w[b + 1] + w[c + 1]) / 3, mz = (w[a + 2] + w[b + 2] + w[c + 2]) / 3;
    const vx = ex - mx, vy = ey - my, vz = ez - mz;
    const front = nx * vx + ny * vy + nz * vz > 0 ? 1 : 0;
    const sg = front ? 1 : -1;
    const dl = sg * (nx * lx + ny * ly + nz * sun[2]);
    const sv = sc.vis[t];
    const diff = Math.max(0, dl) * sv, trans = Math.max(0, -dl) * sv;
    // specular (Blinn half vector): drives the paper sheen and the gold flecks glinting as a facet turns into the sun
    const vl = Math.hypot(vx, vy, vz) || 1;
    let hx = lx + vx / vl, hy = ly + vy / vl, hz = sun[2] + vz / vl;
    const hl = Math.hypot(hx, hy, hz) || 1;
    hx /= hl;
    hy /= hl;
    hz /= hl;
    const nh = Math.max(0, sg * (nx * hx + ny * hy + nz * hz));
    const spec = Math.pow(nh, 24) * sv;
    // remember the brightest mirror-like facet: a star glint is drawn there (fx/particles.ts)
    const sharp = Math.pow(nh, 160) * sv;
    if (sharp > gl[3]) {
      gl[0] = cen[t * 3];
      gl[1] = cen[t * 3 + 1];
      gl[2] = cen[t * 3 + 2];
      gl[3] = sharp;
    }
    sc.pkx[t] = 2 * (Math.floor(diff * 255) + 256 * front);
    sc.pky[t] = 2 * (Math.floor(trans * 255) + 256 * Math.floor(Math.min(1, spec) * 15));
    // painter's sort key (far first). Stacked layers are only 0.004 apart, so comparing centroids at different screen points
    // mixes perspective into the order. Instead take the depth of the facet's plane along one shared ray (through the model
    // centre), clamped to the facet's own depth range: parallel layers then sort exactly, far-apart facets keep their real depth.
    const da = s[a + 2], db = s[b + 2], dc = s[c + 2];
    const dmin = Math.min(da, db, dc), dmax = Math.max(da, db, dc);
    const ndr = nx * rx0 + ny * ry0 + nz * rz0;
    let key = (da + db + dc) / 3;
    // facets parallel to the stack (most of a flat-folded model) compare exactly with the unclamped plane depth; the
    // rest (moving flaps, the 3D crane) are clamped to their own depth range
    const par = Math.abs(nx * dn0 + ny * dn1 + nz * dn2) > 0.985;
    if (SORT_PLANE && Math.abs(ndr) > 0.15) {
      const tt = (nx * (w[a] - ex) + ny * (w[a + 1] - ey) + nz * (w[a + 2] - ez)) / ndr;
      key = par ? tt * rf0 : Math.max(dmin, Math.min(dmax, tt * rf0));
    }
    const sgd = nx * dn0 + ny * dn1 + nz * dn2 >= 0 ? nl : -nl;
    an0 += nx * sgd;
    an1 += ny * sgd;
    an2 += nz * sgd;
    dep[t] = key;
  }
  const anl = Math.hypot(an0, an1, an2) || 1;
  sc.dn[0] = an0 / anl;
  sc.dn[1] = an1 / anl;
  sc.dn[2] = an2 / anl;
  // insertion sort, far → near (the order barely changes between frames); the living crane: exact pairwise order
  const ord = sc.ord;
  if (parts) newellOrder(g, sc, ex, ey, ez);
  else for (let i = 1; i < T; i++) {
    const key = ord[i];
    const d = dep[key];
    let j = i - 1;
    while (j >= 0 && dep[ord[j]] < d) {
      ord[j + 1] = ord[j];
      j--;
    }
    ord[j + 1] = key;
  }
  const uv = g.uv;
  for (let k = 0; k < T; k++) {
    const t = ord[k];
    const px = sc.pkx[t], py = sc.pky[t];
    for (let j = 0; j < 3; j++) {
      const vi = tris[t * 3 + j];
      const o = (k * 3 + j) * 2;
      outV[o] = s[vi * 3];
      outV[o + 1] = s[vi * 3 + 1];
      outT[o] = uv[vi * 2] * 0.998 + px;
      outT[o + 1] = uv[vi * 2 + 1] * 0.998 + py;
      outS[o] = sh[vi * 3];
      outS[o + 1] = sh[vi * 3 + 1];
      outL[o] = lt[vi * 2];
      outL[o + 1] = lt[vi * 2 + 1];
    }
  }
};

/**
 * Layer edges: stacked paper shows the raw cut edges of the sheet as thin soft shadows on the layers below. From the sorted
 * mesh (inV/inT, back to front) build the drawn mesh with 5 triangles per facet slot: up to two thin quads along the
 * facet's edges that lie on the border of the square (shifted by dx, dy pt, flagged in their texture y with + 8192 so
 * the paper shader draws them as a faint dark shadow), then the facet itself. Edges inside the sheet (the triangulation,
 * creases) cast nothing: shadowing every facet edge drew a web of fake crease lines over the flat sheet. A facet covers
 * the part of its own strip that falls inward, so only the fringe beyond a cut edge darkens what lies below.
 */
export const EDGE_SLOT = 30; // floats per facet slot: 5 triangles × 3 vertices × 2
export const stackEdges = (T: number, inV: Float32Array, inT: Float32Array, outV: Float32Array, outT: Float32Array, dx: number, dy: number) => {
  "worklet";
  const E = 0.004;
  for (let k = 0; k < T; k++) {
    const a = k * 6, b = k * EDGE_SLOT;
    let q = 0; // quads written (≤ 2)
    for (let e = 0; e < 3; e++) {
      const i = e, j = (e + 1) % 3;
      const ui = (inT[a + i * 2] % 2) / 0.998, vi = (inT[a + i * 2 + 1] % 2) / 0.998;
      const uj = (inT[a + j * 2] % 2) / 0.998, vj = (inT[a + j * 2 + 1] % 2) / 0.998;
      const border = (ui < E && uj < E) || (ui > 1 - E && uj > 1 - E) || (vi < E && vj < E) || (vi > 1 - E && vj > 1 - E);
      if (!border || q >= 2) continue;
      const o = b + q * 12;
      const ax = inV[a + i * 2], ay = inV[a + i * 2 + 1], bx = inV[a + j * 2], by = inV[a + j * 2 + 1];
      const tx = inT[a + i * 2], ty = inT[a + i * 2 + 1] + 8192;
      // (A, B, B + d), (A, B + d, A + d)
      outV[o] = ax; outV[o + 1] = ay; outV[o + 2] = bx; outV[o + 3] = by; outV[o + 4] = bx + dx; outV[o + 5] = by + dy;
      outV[o + 6] = ax; outV[o + 7] = ay; outV[o + 8] = bx + dx; outV[o + 9] = by + dy; outV[o + 10] = ax + dx; outV[o + 11] = ay + dy;
      for (let m = 0; m < 12; m += 2) {
        outT[o + m] = tx;
        outT[o + m + 1] = ty;
      }
      q++;
    }
    for (; q < 2; q++) {
      const o = b + q * 12;
      for (let m = 0; m < 12; m++) outV[o + m] = -1e4;
    }
    const f = b + 24;
    for (let m = 0; m < 6; m++) {
      outV[f + m] = inV[a + m];
      outT[f + m] = inT[a + m];
    }
  }
};

/** a flat textured grid (table or backdrop) projected with the camera; tex = image pixel coords (static, set once) */
export const buildGrid = (
  cam: number[],
  nx: number,
  ny: number,
  corner: number[], // origin xyz
  du: number[], // edge 1 xyz
  dv: number[], // edge 2 xyz
  out: Float32Array,
  tmp: Float32Array,
) => {
  "worklet";
  for (let j = 0; j <= ny; j++) {
    for (let i = 0; i <= nx; i++) {
      const a = i / nx, b = j / ny;
      const k = j * (nx + 1) + i;
      project(
        cam,
        corner[0] + du[0] * a + dv[0] * b,
        corner[1] + du[1] * a + dv[1] * b,
        corner[2] + du[2] * a + dv[2] * b,
        tmp,
        0,
      );
      out[k * 2] = tmp[0];
      out[k * 2 + 1] = tmp[1];
    }
  }
};
