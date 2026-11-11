/**
 * The crane comes alive after the last fold (a = seconds since then):
 *   awaken  0 … TAKEOFF          a sweep of light runs through the paper, it levitates, lifts its wings, glances at the viewer
 *   loop    TAKEOFF … +LOOP_T    one and a quarter graceful loops around the table, banking into the turn, flap-flap-glide
 *   climb   … +CLIMB_T           up and out through the open panel into the sky, strong wing beats, shrinking into the clouds
 * Writes the life array used by mesh.ts applyLife:
 *   [flap, yaw, pitch, tx, ty, tz, cx, cy, cz, heading, roll, scale, thin]
 * and the flight state st = [x, y, z (body centre, world), dissolve 0..1, speed].
 * base = [cx, cy, cz, heading] (rest body centre and forward angle, from crane.json head/tail).
 */
const sstep = (a: number, b: number, x: number) => {
  "worklet";
  const t = Math.max(0, Math.min(1, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

export const TAKEOFF = 2.4;
export const LOOP_T = 4.8;
const CLIMB_T = 5.2;
const QA = 2.1; // seconds of the climb spent reaching the open panel
const R = 1.25;
const PHI_END = Math.PI * 2.5;
/** seconds after the last fold when the crane has vanished into the light */
export const FLIGHT_END = TAKEOFF + LOOP_T + CLIMB_T;

/** body-centre offset from rest along the flight (s = seconds since take-off), written into o[0..2] */
const path = (s: number, lift: number, o: number[]) => {
  "worklet";
  if (s <= LOOP_T) {
    const u = Math.max(0, s / LOOP_T);
    const phi = PHI_END * (2 * u * u - u * u * u); // eases in, leaves at full speed
    o[0] = -R * Math.sin(phi);
    o[1] = R - R * Math.cos(phi);
    o[2] = lift + 1.45 * Math.pow(u, 1.25);
    return;
  }
  const q = s - LOOP_T;
  const v = (PHI_END * R) / LOOP_T;
  // A: toward the open panel, low enough to pass through it (house plane y = 7, opening top z ≈ 3.6)
  const qa = Math.min(q, QA);
  o[0] = -R + R * 0.85 * sstep(0, 1.6, qa);
  o[1] = R + v * qa + 0.65 * qa * qa;
  o[2] = lift + 1.45 + 0.4 * qa;
  if (q <= QA) return;
  // B: outside it does not fly straight away from the lens (seen from behind its wings are only thin edges): it banks
  // right and sweeps across the sky in front of the veranda, so the camera sees it in profile with its wings beating,
  // then curves back toward the low sun and shrinks into the glow. Heading and speed are smooth functions of time;
  // the position is their integral (midpoint steps, cheap enough for the three calls per frame).
  const u = q - QA;
  const vy0 = v + 1.3 * QA;
  const N = 24;
  const dtu = u / N;
  let x = 0, y = 0, z = 0;
  for (let i = 0; i < N; i++) {
    const t = (i + 0.5) * dtu;
    const turn = sstep(0.0, 1.0, t) - sstep(1.4, 2.8, t); // 0 = straight out, 1 = across the view
    const hd = Math.PI / 2 - turn * 0.85; // +y → 41° off +x → back toward the sun
    const sp = vy0 * (1 - 0.35 * sstep(0, 1.0, t)) + 4.5 * sstep(1.6, 3.1, t);
    x += Math.cos(hd) * sp * dtu;
    y += Math.sin(hd) * sp * dtu;
    z += (0.6 + 2.4 * sstep(0.8, 3.1, t)) * dtu;
  }
  o[0] += x;
  o[1] += y;
  o[2] += z;
};

export const lifePose = (a: number, base: number[], L: number[], st: number[], tmp: number[], hover = 0) => {
  "worklet";
  L[6] = base[0];
  L[7] = base[1];
  L[8] = base[2];
  L[9] = base[3];
  L[11] = 1;
  // press the layers together as it comes alive (mesh.ts applyLife thin)
  L[12] = a < 0 ? 0 : sstep(0.0, 0.8, a);
  if (a < 0) {
    for (let i = 0; i < 6; i++) L[i] = 0;
    L[10] = 0;
    st[0] = base[0];
    st[1] = base[1];
    st[2] = base[2];
    st[3] = 0;
    st[4] = 0;
    return;
  }
  // awaken: levitate with a slow breathing bob, wings rise to a dihedral, first lazy beats.
  // hover = 1 (demo intro) holds the envelopes at their 1.3 s values while the wing beat and bob keep going
  const e = hover ? Math.min(a, 1.3) : a;
  const lift = 0.22 * sstep(0.15, 1.3, e) + 0.025 * Math.sin(a * 3.1) * sstep(0.3, 1.0, e);
  const s = hover ? -1 : a - TAKEOFF;
  let flap: number;
  if (s < 0) {
    const amp = 0.55 * sstep(0.8, 1.6, hover ? 1.6 : a);
    flap = 0.3 * sstep(0.3, 1.0, e) + amp * Math.sin((a - 0.8) * Math.PI * 2 * 1.6);
    L[3] = 0;
    L[4] = 0;
    L[5] = lift;
    L[1] = hover ? 0.18 * Math.sin(a * 0.9) : 0.32 * Math.sin(Math.PI * sstep(0.4, 1.5, a)); // a glance toward the viewer
    L[2] = 0.07 * sstep(0, 0.8, e);
    L[10] = 0.06 * Math.sin(a * 2.3) * sstep(0.3, 1.2, e);
    st[0] = base[0];
    st[1] = base[1];
    st[2] = base[2] + lift;
    st[3] = 0;
    st[4] = 0;
    L[0] = flap;
    return;
  }
  // flight: position, velocity and turn rate from the path
  const lift0 = 0.22;
  path(s, lift0, tmp);
  const px = tmp[0], py = tmp[1], pz = tmp[2];
  const h = 0.02;
  path(s + h, lift0, tmp);
  const vx = (tmp[0] - px) / h, vy = (tmp[1] - py) / h, vz = (tmp[2] - pz) / h;
  path(s + 2 * h, lift0, tmp);
  const vx2 = (tmp[0] - px) / h - vx, vy2 = (tmp[1] - py) / h - vy;
  const vxy = Math.hypot(vx, vy) || 1e-3;
  const heading = Math.atan2(vy, vx);
  // turn rate (signed curvature × speed) → bank angle, like a bird leaning into the turn
  const turn = (vx * vy2 - vy * vx2) / (vxy * vxy * h);
  const bank = Math.max(-0.75, Math.min(0.75, Math.atan(turn * vxy * 0.18)));
  let yaw = heading - base[3];
  while (yaw > Math.PI) yaw -= Math.PI * 2;
  while (yaw < -Math.PI) yaw += Math.PI * 2;
  // blend in from the awaken pose over the first half second
  const k = sstep(0, 0.5, s);
  L[1] = yaw * k;
  L[2] = 0.07 + (Math.atan2(vz, vxy) * 0.75 - 0.07) * k;
  L[10] = bank * k;
  L[3] = px;
  L[4] = py;
  L[5] = pz;
  // wings: flap-flap-glide while looping, strong steady beats on the climb
  if (s < LOOP_T) {
    const cyc = (s + 0.45) % 1.55;
    const win = sstep(0.0, 0.12, cyc) * (1 - sstep(0.85, 1.0, cyc));
    flap = 0.32 * (1 - win) + win * (0.12 + 0.78 * Math.sin(cyc * Math.PI * 2 * 2.3));
  } else {
    const q = s - LOOP_T;
    flap = 0.1 + 0.85 * Math.sin(q * Math.PI * 2 * 2.7 + 0.7);
  }
  L[0] = flap;
  // dissolve into the light at the end of the climb
  const dis = sstep(FLIGHT_END - TAKEOFF - 0.9, FLIGHT_END - TAKEOFF, s);
  L[11] = 1 - 0.9 * dis;
  st[0] = base[0] + px;
  st[1] = base[1] + py;
  st[2] = base[2] + pz;
  st[3] = dis;
  st[4] = Math.hypot(vx, vy, vz);
};
