"""Origami Crane: baked fold sequence of a traditional paper crane.

Run headless:  tools/fold.sh  (Blender -b --factory-startup -P this file -- [--no-render])
or plain:      <blender python> fold_crane.py --no-render

Model
-----
The paper is a 2x2 square centred at the origin (paper coords = world xy at
the start), coloured side DOWN (front = -z at the start).

The sequence is computed by a small flat-folding engine (plain numpy):
  * facets are convex polygons in paper coords, each with a 2D isometry
    (M, t) mapping paper -> world xy and a layer index z;
  * a fold splits the selected facets exactly along the crease line (so the
    final mesh contains every crease edge) and reflects the moving ones;
  * layer indices are compacted after every operation (each facet sits one
    layer above the highest facet it overlaps), so the stack has real
    thickness LAYER (0.004) and no two overlapping layers coincide;
  * every recorded "pose" stores per facet a 3D rigid transform (R, t) and a
    local offset w along the paper normal (the layer height).

Motion between two poses ("thick" phases, the default): every facet is a
rigid body whose layer offset is part of its transform, interpolated by a
screw between the two thick poses, so a simple fold is an exact hinge
rotation about the crease lifted to mid stack height and folded layers keep
their order and spacing (no stitching, facets never stretch).  The squash
folds use an analytic degree-1 single-vertex motion (squash_motion).
Legacy phases (custom=... without thick=True: petal, reverse folds, wings)
still interpolate base transforms + lerped offsets with the stitch pass.

Every bake is validated keyframe by keyframe (validate_frames: stretch,
crease gaps beyond the end states, triangle interpenetration, layer
separation); the app files are only written when everything passes
(--force-write overrides, --no-write skips).
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT_DIR = os.path.join(ROOT, "app", "assets", "fold")
PREVIEW_DIR = os.path.join(ROOT, "render", "fold_preview")

LAYER = 0.004   # world thickness of one paper layer
Z0 = 0.002      # height of the lowest layer above the table
EPS = 1e-9

# ---------------------------------------------------------------- 2D helpers


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def perp(d):
    return np.array([-d[1], d[0]])


def refl2(d):
    a, b = unit(d)
    return np.array([[a * a - b * b, 2 * a * b], [2 * a * b, b * b - a * a]])


def rot2(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s], [s, c]])


def clip_poly(P, s, eps=1e-10):
    """Split polygon P (n,2) by signed values s (n,). Returns (pos, neg)."""
    pos, neg = [], []
    n = len(P)
    for i in range(n):
        j = (i + 1) % n
        a, b, sa, sb = P[i], P[j], s[i], s[j]
        if sa >= -eps:
            pos.append(a)
        if sa <= eps:
            neg.append(a)
        if (sa > eps and sb < -eps) or (sa < -eps and sb > eps):
            x = a + (b - a) * (sa / (sa - sb))
            pos.append(x)
            neg.append(x)
    return np.array(pos), np.array(neg)


def poly_area(P):
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def point_in_poly(P, p, eps=1e-9):
    n = len(P)
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        if (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) < -eps:
            return False
    return True


def overlap(A, B, tol=1e-5):
    """Convex polygons overlap with positive area (touching does not count)."""
    for P in (A, B):
        n = len(P)
        for i in range(n):
            e = P[(i + 1) % n] - P[i]
            L = math.hypot(e[0], e[1])
            if L < 1e-12:
                continue
            ax = np.array([-e[1], e[0]]) / L
            pa, pb = A @ ax, B @ ax
            if pa.max() <= pb.min() + tol or pb.max() <= pa.min() + tol:
                return False
    return True


def share_edge(A, B, tol=1e-7):
    """Convex paper polygons share a boundary segment of positive length."""
    for i in range(len(A)):
        a0, a1 = A[i], A[(i + 1) % len(A)]
        da = a1 - a0
        La = math.hypot(*da)
        if La < 1e-9:
            continue
        u = da / La
        for j in range(len(B)):
            b0, b1 = B[j], B[(j + 1) % len(B)]
            if abs(np.cross(u, b0 - a0)) > tol or abs(np.cross(u, b1 - a0)) > tol:
                continue
            s0, s1 = sorted(((b0 - a0) @ u, (b1 - a0) @ u))
            if min(La, s1) - max(0.0, s0) > 1e-6:
                return True
    return False


def iso_from_points(src, dst):
    """2D isometry (M, t) (det +-1) mapping paper points src -> world dst."""
    src = np.asarray(src, float)
    dst = np.asarray(dst, float)
    cs, cd = src.mean(0), dst.mean(0)
    H = (src - cs).T @ (dst - cd)
    U, _, Vt = np.linalg.svd(H)
    best = None
    for D in (np.diag([1, 1]), np.diag([1, -1])):
        M = Vt.T @ D @ U.T
        err = np.abs((src - cs) @ M.T - (dst - cd)).max()
        if best is None or err < best[0]:
            best = (err, M)
    M = best[1]
    return M, cd - M @ cs

# ---------------------------------------------------------------- 3D helpers


def rodrigues(k, a):
    k = unit(k)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * (K @ K)


def axis_angle(R):
    c = (np.trace(R) - 1) / 2
    ang = math.acos(max(-1.0, min(1.0, c)))
    if ang < 1e-6:
        return np.array([0.0, 0.0, 1.0]), 0.0
    if math.pi - ang < 1e-3:
        B = (R + np.eye(3)) / 2
        i = int(np.argmax(np.diag(B)))
        k = B[:, i] / math.sqrt(max(B[i, i], 1e-12))
        return unit(k), ang
    k = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    return k / (2 * math.sin(ang)), ang


def hinge(p, q, ang, side):
    """Rotation (R, t) about the world line p->q (3D) by ang, the sign
    chosen so that a positive angle lifts the world point `side` upward."""
    p, q, side = (np.asarray(v, float) for v in (p, q, side))
    k = unit(q - p)
    r = side - p
    if np.cross(k, r)[2] < 0:
        k = -k
    R = rodrigues(k, ang)
    return R, p - R @ p


class Screw:
    """Screw interpolation from rigid transform A to B (x -> R x + t)."""

    def __init__(self, Ra, ta, Rb, tb, ref=None, up=(0, 0, 1)):
        self.Ra, self.ta = Ra, ta
        RD = Rb @ Ra.T
        tD = tb - RD @ ta
        k, ang = axis_angle(RD)
        self.k, self.ang = k, ang
        if ang < 1e-6:
            self.ang = 0.0
            self.c = np.zeros(3)
            self.d = tD
            return
        # point on the axis: (I - RD) c = tD - (tD.k) k  (least squares)
        slide = float(tD @ k)
        c = np.linalg.lstsq(np.eye(3) - RD, tD - slide * k, rcond=None)[0]
        c = c - (c @ k) * k
        self.c, self.d = c, slide * k
        if math.pi - ang < 1e-3 and ref is not None:
            r = np.asarray(ref, float) - c
            mid = rodrigues(k, ang / 2) @ r
            if mid @ np.asarray(up, float) < (rodrigues(-k, ang / 2) @ r) @ np.asarray(up, float):
                self.k = -k

    def at(self, s):
        if self.ang < 1e-6:
            return self.Ra, self.ta + s * self.d
        Rs = rodrigues(self.k, s * self.ang)
        R = Rs @ self.Ra
        t = Rs @ (self.ta - self.c) + self.c + s * self.d
        return R, t


def ease(s):
    return s * s * (3 - 2 * s)

# ---------------------------------------------------------------- paper


class Facet:
    __slots__ = ("poly", "M", "t", "z", "hist", "tags")

    def __init__(self, poly, M, t, z, hist, tags=()):
        self.poly, self.M, self.t, self.z, self.hist = poly, M, t, z, hist
        self.tags = set(tags)

    def copy(self, poly):
        return Facet(poly, self.M.copy(), self.t.copy(), self.z, list(self.hist), self.tags)

    def cen(self):
        return self.poly.mean(0)

    def wpoly(self):
        return self.poly @ self.M.T + self.t

    def wpt(self, p):
        return self.M @ np.asarray(p, float) + self.t

    def wcen(self):
        return self.wpt(self.cen())


class Paper:
    def __init__(self):
        sq = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], float)
        self.F = [Facet(sq, np.eye(2), np.zeros(2), 0.0, [])]
        self.npose = 0

    # -- queries
    def facet_at(self, p, pick="top"):
        c = [f for f in self.F if point_in_poly(f.poly, p)]
        if not c:
            raise ValueError("no facet contains %s" % (p,))
        return max(c, key=lambda f: f.z) if pick == "top" else min(c, key=lambda f: f.z)

    def where(self, p):
        """World xy of a paper point in the current flat state."""
        return self.facet_at(p).wpt(p)

    def zmax(self):
        return max(f.z for f in self.F)

    # -- operations
    def split(self, p, d, sel):
        p = np.asarray(p, float)
        n = perp(unit(d))
        out = []
        for f in self.F:
            if sel(f):
                s = (f.wpoly() - p) @ n
                if s.max() > 1e-7 and s.min() < -1e-7:
                    for q in clip_poly(f.poly, s):
                        if len(q) >= 3 and abs(poly_area(q)) > 1e-9:
                            out.append(f.copy(q))
                    continue
            out.append(f)
        self.F = out

    def fold(self, p, q, side, sel=lambda f: True, place="top", tag=None, under=None):
        """Valley fold over the top: split `sel` facets along the world line
        p->q and reflect those on the `side` of it onto the stack."""
        p = np.asarray(p, float)
        d = unit(np.subtract(q, p))
        n = perp(d)
        self.split(p, d, sel)
        sg = np.sign((np.asarray(side, float) - p) @ n)
        mov = [f for f in self.F if sel(f) and ((f.wcen() - p) @ n) * sg > 0]
        R = refl2(d)
        self.apply(mov, R, p - R @ p)
        if tag:
            for f in mov:
                f.tags.add(tag)
        if place == "top":
            self.restack(mov, flip=True)
        if under is not None:
            # keep these facets above the folded flap (it slides under them)
            for f in self.F:
                if under(f):
                    f.z += 1000.0
            self.compact()
        return mov

    def fold_flood(self, p, q, side, region, seed, tag=None):
        """Valley fold over the top that takes every layer physically attached
        to the seed flap: split the `region` facets along the world line p->q,
        then move the seed facets on the `side` of it plus everything on that
        side connected to them through a shared paper edge (a closed folded
        edge cannot be left behind)."""
        p = np.asarray(p, float)
        d = unit(np.subtract(q, p))
        n = perp(d)
        self.split(p, d, region)
        sg = np.sign((np.asarray(side, float) - p) @ n)
        cand = [f for f in self.F if region(f) and ((f.wcen() - p) @ n) * sg > 0]
        mov = [f for f in cand if seed(f)]
        ids = set(map(id, mov))
        grow = True
        while grow:
            grow = False
            for f in cand:
                if id(f) in ids:
                    continue
                if any(share_edge(f.poly, g.poly) for g in mov):
                    mov.append(f)
                    ids.add(id(f))
                    grow = True
        R = refl2(d)
        self.apply(mov, R, p - R @ p)
        if tag:
            for f in mov:
                f.tags.add(tag)
        self.restack(mov, flip=True)
        return mov

    def apply(self, fs, G, g):
        for f in fs:
            f.M = G @ f.M
            f.t = G @ f.t + g

    def restack(self, mov, flip=True, base=None):
        ids = set(map(id, mov))
        st = [f for f in self.F if id(f) not in ids]
        top = max([f.z for f in st], default=-1) if base is None else base
        zm = max(f.z for f in mov)
        zl = min(f.z for f in mov)
        for f in mov:
            f.z = top + 1 + ((zm - f.z) if flip else (f.z - zl))
        self.compact()

    def compact(self):
        F = sorted(self.F, key=lambda f: f.z)
        W = [f.wpoly() for f in F]
        lo = np.array([w.min(0) for w in W])
        hi = np.array([w.max(0) for w in W])
        newz = np.zeros(len(F))
        for i in range(len(F)):
            m = np.all(lo[:i] < hi[i] - 1e-5, 1) & np.all(hi[:i] > lo[i] + 1e-5, 1)
            z = 0.0
            for j in np.nonzero(m)[0]:
                if newz[j] + 1 > z and overlap(W[i], W[j]):
                    z = newz[j] + 1
            newz[i] = z
        for f, z in zip(F, newz):
            f.z = float(z)

    # -- poses
    def record(self):
        for f in self.F:
            det = float(np.linalg.det(f.M))
            R = np.eye(3)
            R[:2, :2] = f.M
            R[2, 2] = det
            t = np.array([f.t[0], f.t[1], 0.0])
            f.hist.append((R, t, det * (Z0 + f.z * LAYER)))
        self.npose += 1
        return self.npose - 1

    def record_from(self, base, xforms):
        """New pose = pose `base` with extra rigid transforms applied.
        xforms: list of (sel(f), R, t) applied in order to matching facets."""
        for f in self.F:
            R, t, w = f.hist[base]
            for sel, XR, Xt in xforms:
                if sel(f):
                    R, t = XR @ R, XR @ t + Xt
            f.hist.append((R, t, w))
        self.npose += 1
        return self.npose - 1

# ---------------------------------------------------------------- selectors


def ang_of(p):
    return math.degrees(math.atan2(p[1], p[0]))


def in_sector(lo, hi):
    """Facet whose paper centroid angle (deg, around the centre) is in [lo, hi)."""
    def sel(f):
        a = ang_of(f.cen())
        return lo <= a < hi or lo <= a + 360 < hi
    return sel


def all_of(*ss):
    return lambda f: all(s(f) for s in ss)


def any_of(*ss):
    return lambda f: any(s(f) for s in ss)


def half(a, b, c):
    """Paper half plane a*x + b*y > c (by facet centroid)."""
    return lambda f: a * f.cen()[0] + b * f.cen()[1] > c

# ---------------------------------------------------------------- sequence

# paper corners and midpoints
O = np.array([0.0, 0.0])
A = np.array([-1.0, -1.0])
B = np.array([1.0, -1.0])
C = np.array([1.0, 1.0])
D = np.array([-1.0, 1.0])
mAB, mBC, mCD, mDA = (A + B) / 2, (B + C) / 2, (C + D) / 2, (D + A) / 2

# sectors around the centre (paper angle ranges, degrees)
S1 = in_sector(-135, -90)   # O, A, mAB
S2 = in_sector(-90, -45)    # O, mAB, B
S3 = in_sector(-45, 0)      # O, B, mBC
S4 = in_sector(0, 45)       # O, mBC, C
S5 = in_sector(45, 90)      # O, C, mCD
S6 = in_sector(90, 135)     # O, mCD, D
S7 = in_sector(135, 180)    # O, D, mDA
S8 = in_sector(-180, -135)  # O, mDA, A


def w3(p, z=0.0):
    return np.array([p[0], p[1], z])


class Seq:
    def __init__(self):
        self.P = Paper()
        self.steps = []
        self.p0 = self.P.record()

    def step(self, name, phases, hint, frames=24):
        """phases: list of dict(a, b, w, lift, ref, custom); hint: paper point."""
        self.steps.append(dict(name=name, phases=phases, hint=hint, frames=frames))


def squash(P, flap, hinge_lo, hinge_hi, face_lo, face_hi, corner_lo, corner_hi,
           mid_lo, mid_hi, center_corner):
    """Final flat state of a squash fold (rigid placement by 3 points).
    The lower hinge sector stays; everything else is placed symmetrically."""
    Ow = P.where(O)
    Aw = P.where(corner_lo)
    Pw = P.where(mid_lo)
    d = unit(Aw - Ow)
    Pr = Ow + refl2(d) @ (Pw - Ow)
    top = max(f.z for f in P.F if not flap(f))
    fl = [f for f in P.F if face_lo(f)]
    hh = [f for f in P.F if hinge_hi(f)]
    fh = [f for f in P.F if face_hi(f)]
    hl = [f for f in P.F if hinge_lo(f)]
    for fs, src, dst in ((fl, (O, center_corner, mid_lo), (Ow, Aw, Pw)),
                         (hh, (O, corner_hi, mid_hi), (Ow, Aw, Pr)),
                         (fh, (O, center_corner, mid_hi), (Ow, Aw, Pr))):
        M, t = iso_from_points(src, dst)
        for f in fs:
            f.M, f.t = M.copy(), t.copy()
    for f in hl + hh:
        f.z = top + 1
    for f in fl + fh:
        f.z = top + 2
    P.compact()


def thick(f, pi):
    """Rigid transform of facet f in pose pi acting on (paper x, paper y, 0),
    with the layer offset folded in (x -> R x + t)."""
    R, t, w = f.hist[pi]
    return R, t + R[:, 2] * w


def frame3(a, b):
    a = unit(a)
    bp = unit(b - (b @ a) * a)
    return np.array([a, bp, np.cross(a, bp)]).T


def squash_motion(P, pa, pb, X1, X2, X3, X4, Ow, Aw, Bw, lift_frac=0.38):
    """Continuous squash fold of a pocket flap (degree-1 single vertex at O).
    X1 / X4: the flap sectors on the hinge (X1 ends flipped over, X4 returns);
    X2 / X3: the spine sectors (X2 attached to X1 by the centre crease, X3 to X4).
    Phase 1: the whole flap rises to vertical on its hinge.  Phase 2: the
    spine descends in the vertical hinge plane while the two layers open
    symmetrically; the sector directions at O come from the spherical linkage
    (all sector angles 45 deg).  Thickness: X1/X4 rotate about the hinge
    lifted to mid stack height, X2/X3 about their own lifted centre creases
    (screw axis of the final relative transform), so layers land exactly."""
    h = unit(w3(np.subtract(Aw, Ow)))
    up = np.array([0.0, 0.0, 1.0])
    v = w3(np.subtract(Bw, Ow))
    nf = unit(v - (v @ h) * h)
    c10 = unit(h + nf)
    F0 = {1: frame3(h, c10), 2: frame3(c10, nf), 3: frame3(nf, c10), 4: frame3(c10, h)}
    k = np.cross(nf, up)
    secs = {1: X1, 2: X2, 3: X3, 4: X4}

    def dirs(u, sg):
        if u <= lift_frac:
            Rk = rodrigues(k, (math.pi / 2) * u / lift_frac)
            return Rk @ c10, Rk @ nf, Rk @ c10
        phi = (math.pi / 2) * (1 - (u - lift_frac) / (1 - lift_frac))
        c2 = math.sin(phi) * up + math.cos(phi) * h
        m = unit(h + c2)
        cb = min(1.0, math.cos(math.pi / 4) / math.cos(phi / 2))
        sb = math.sqrt(max(0.0, 1 - cb * cb))
        return cb * m - sg * sb * nf, c2, cb * m + sg * sb * nf

    def G(u, sg):
        c1, c2, c3 = dirs(u, sg)
        return {1: frame3(h, c1) @ F0[1].T, 2: frame3(c1, c2) @ F0[2].T,
                3: frame3(c2, c3) @ F0[3].T, 4: frame3(c3, h) @ F0[4].T}

    G1 = None
    cache = {}

    def tables(F):
        """Per-facet data for the final facet list (facets split later inherit poses)."""
        key = (id(F), len(F))
        if key in cache:
            return cache[key]
        TA = [thick(f, pa) for f in F]
        TB = [thick(f, pb) for f in F]
        sec_of = [next((j for j in (1, 2, 3, 4) if secs[j](f)), 0) for f in F]
        best = None
        for sg in (1.0, -1.0):
            Gs = G(1.0, sg)
            err = max((np.abs(Gs[j] @ TA[i][0] - TB[i][0]).max() for i, j in enumerate(sec_of) if j), default=0)
            if best is None or err < best[0]:
                best = (err, sg)
        err, sg = best
        assert err < 1e-6, "squash kinematics do not reach the final state (%.2e)" % err
        hl = [(TA[i][1][2] + TB[i][1][2]) / 2 for i, j in enumerate(sec_of) if j == 1]
        Q = np.array([Ow[0], Ow[1], float(np.mean(hl))])
        G1 = G(1.0, sg)
        rel = {}
        for i, j in enumerate(sec_of):
            if j in (2, 3):
                par = 1 if j == 2 else 4
                Rp = G1[par]
                tp = Q - Rp @ Q
                RT = TB[i][0] @ TA[i][0].T
                tT = TB[i][1] - RT @ TA[i][1]
                RE = Rp.T @ RT
                tE = Rp.T @ (tT - tp)
                sc = Screw(np.eye(3), np.zeros(3), RE, tE)
                rel[i] = (par, sc.c, sc.d)
        cache[key] = (TA, TB, sec_of, sg, Q, G1, rel)
        return cache[key]

    def custom(Fs, s, Rs, ts):
        TA, TB, sec_of, sg, Q, G1, rel = tables(Fs)
        Gs = G(s, sg)
        fr2 = 0.0 if s <= lift_frac else (s - lift_frac) / (1 - lift_frac)
        for i, j in enumerate(sec_of):
            Ra, ta = TA[i]
            if j == 0:
                Rs[i], ts[i] = Ra, ta + (TB[i][1] - ta) * s
                continue
            if j in (1, 4):
                RD = Gs[j]
                tD = Q - RD @ Q
                res = TB[i][1] - (G1[j] @ ta + Q - G1[j] @ Q)
                Rs[i], ts[i] = RD @ Ra, RD @ ta + tD + res * fr2
                continue
            par, c, d = rel[i]
            Rp = Gs[par]
            tp = Q - Rp @ Q
            RE = Rp.T @ Gs[j]
            tE = c - RE @ c + d * fr2
            RD = Rp @ RE
            tD = Rp @ tE + tp
            Rs[i], ts[i] = RD @ Ra, RD @ ta + tD
    return custom


def thick_custom(pa, pb, group, zero, name="motion", parent=None):
    """Thick-rigid custom motion from a zero-thickness kinematic solution.
    group(f) -> key or None (static); zero(s) -> [(key, R, pivot)] delta
    rotations (relative to pose pa) of each group about a pivot on its crease.
    parent: {key: parent_key} for groups hinged to another moving group (their
    motion is the parent's composed with a rotation about the shared crease).
    Each facet rotates about the point of its own final screw axis (relative
    to the parent if any) nearest the pivot -- the crease lifted to the layer
    gap -- plus the screw slide, so it lands exactly on pose pb; static facets
    translate (stack height changes)."""
    parent = parent or {}
    cache = {}

    def tables(F):
        key = (id(F), len(F))
        if key in cache:
            return cache[key]
        TA = [thick(f, pa) for f in F]
        TB = [thick(f, pb) for f in F]
        gk = [group(f) for f in F]
        Z1 = {k: (R, c) for k, R, c in zero(1.0)}
        # final delta of a parent group (taken from any one of its facets)
        pfin = {}
        for i, g in enumerate(gk):
            if g is not None and g not in pfin:
                RT = TB[i][0] @ TA[i][0].T
                pfin[g] = (RT, TB[i][1] - RT @ TA[i][1])
        axes = []
        worst = 0.0
        for i, g in enumerate(gk):
            if g is None:
                axes.append(None)
                continue
            RT = TB[i][0] @ TA[i][0].T
            tT = TB[i][1] - RT @ TA[i][1]
            worst = max(worst, float(np.abs(RT - Z1[g][0]).max()))
            pg = parent.get(g)
            if pg is not None:
                # relative transform of this facet with respect to the parent
                # facets' final delta, about the parent's own lifted axis
                pRT, ptT = pfin[pg]
                RT, tT = pRT.T @ RT, pRT.T @ (tT - ptT)
            sc = Screw(np.eye(3), np.zeros(3), RT, tT)
            piv = np.asarray(Z1[g][1], float)
            if sc.ang < 1e-6:
                axes.append((piv, tT))
                continue
            c = sc.c + ((piv - sc.c) @ sc.k) * sc.k
            axes.append((c, sc.d))
        print("  %s: end rotation error %.2e" % (name, worst))
        assert worst < 1e-5, "%s kinematics do not reach the final state" % name
        # parent facets: one representative axis per parent group
        prep = {}
        for i, g in enumerate(gk):
            if g is not None and g not in prep:
                prep[g] = axes[i]
        cache[key] = (TA, TB, gk, axes, prep)
        return cache[key]

    def custom(F, s, Rs, ts):
        TA, TB, gk, axes, prep = tables(F)
        Z = {k: R for k, R, c in zero(s)}

        def delta(g, c, d):
            pg = parent.get(g)
            if pg is None:
                G = Z[g]
                return G, c - G @ c + d * s
            Gp, tp = delta(pg, *prep[pg])
            E = Gp.T @ Z[g]
            tE = c - E @ c + d * s
            return Gp @ E, Gp @ tE + tp
        for i, g in enumerate(gk):
            Ra, ta = TA[i]
            if g is None:
                Rs[i], ts[i] = Ra, ta + (TB[i][1] - ta) * s
                continue
            G, t = delta(g, *axes[i])
            Rs[i], ts[i] = G @ Ra, G @ ta + t
    return custom


def build(max_steps=99):
    S = Seq()
    P = S.P

    # 1. diagonal valley fold: far-right corner C onto near-left corner A
    P.fold(B, D, side=C)
    p1 = P.record()
    S.step("Diagonal fold", [dict(a=S.p0, b=p1)], hint=(0.8, 0.8))
    if len(S.steps) >= max_steps:
        return S

    # 2. fold in half: B onto D (crease from the centre to the corners A/C)
    P.fold(P.where(O), P.where(A), side=P.where(B))
    p2 = P.record()
    S.step("Fold in half", [dict(a=p1, b=p2)], hint=(0.8, -0.8))
    if len(S.steps) >= max_steps:
        return S

    # 3. squash the front flap (paper half x > y = sectors S1..S4)
    flap = half(1, -1, 0)
    Ow, Aw, Mw = P.where(O), P.where(A), P.where(mAB)
    # crease the midlines of the flap (world line centre -> side corner)
    P.split(Ow, Mw - Ow, flap)
    hs = [f for f in P.F if flap(f) and (S1(f) or S4(f))]
    lo_is_s4 = min(f.z for f in hs if S4(f)) < min(f.z for f in hs if S1(f))
    Bw = P.where(B)
    if lo_is_s4:
        squash(P, flap, S4, S1, S3, S2, C, A, mBC, mAB, B)
        X = (S1, S2, S3, S4)
    else:
        squash(P, flap, S1, S4, S2, S3, A, C, mAB, mBC, B)
        X = (S4, S3, S2, S1)
    p3 = P.record()
    cu3 = squash_motion(P, p2, p3, *X, Ow, Aw, Bw)
    S.step("Squash front", [dict(a=p2, b=p3, custom=cu3, thick=True)],
           hint=(0.7, -0.2), frames=28)
    if len(S.steps) >= max_steps:
        return S

    # 4. turn over, re-centre: square base diagonal along y, closed point far
    Ow, Aw = P.where(O), P.where(A)
    tgtO, tgtA = np.array([0.0, 0.7071]), np.array([0.0, -0.7071])
    M, g = iso_from_points((Ow, Aw, Ow + perp(Aw - Ow)), (tgtO, tgtA, tgtO - perp(tgtA - tgtO)))
    zm = P.zmax()
    cen = np.mean([f.wcen() for f in P.F], 0)
    P.apply(P.F, M, g)
    for f in P.F:
        f.z = zm - f.z
    P.compact()
    p4 = P.record()
    S.step("Turn over", [dict(a=p3, b=p4, lift=0.45, ref=w3(cen))], hint=(-0.5, 0.5), frames=22)
    if len(S.steps) >= max_steps:
        return S

    # 5. squash the back flap (paper half x < y = sectors S5..S8)
    flap = half(-1, 1, 0)
    Ow, Aw, Mw = P.where(O), P.where(A), P.where(mDA)
    P.split(Ow, Mw - Ow, flap)
    hs = [f for f in P.F if flap(f) and (S5(f) or S8(f))]
    lo_is_s5 = min(f.z for f in hs if S5(f)) < min(f.z for f in hs if S8(f))
    Bw = P.where(D)
    if lo_is_s5:
        squash(P, flap, S5, S8, S6, S7, C, A, mCD, mDA, D)
        X = (S8, S7, S6, S5)
    else:
        squash(P, flap, S8, S5, S7, S6, A, C, mDA, mCD, D)
        X = (S5, S6, S7, S8)
    p5 = P.record()
    cu5 = squash_motion(P, p4, p5, *X, Ow, Aw, Bw)
    S.step("Squash back", [dict(a=p4, b=p5, custom=cu5, thick=True)],
           hint=(-0.7, 0.2), frames=28)
    if len(S.steps) >= max_steps:
        return S

    # 6. petal fold front (kite creases + lift the bottom point of the face)
    front = half(-1, 1, 0)
    face = any_of(S6, S7)
    petal(S, P, front, face, "Petal fold front", "f")
    if len(S.steps) >= max_steps:
        return S

    # 7. turn over (about the long axis)
    turn_over(S, P, "Turn over", axis_x=0.0)
    if len(S.steps) >= max_steps:
        return S

    # 8. petal fold back -> bird base
    front = half(1, -1, 0)
    face = any_of(S2, S3)
    petal(S, P, front, face, "Petal fold back", "b")
    if len(S.steps) >= max_steps:
        return S

    # 9. narrow the legs (front), 10. turn over, 11. narrow the legs (back)
    narrow(S, P, any_of(S1, S4), any_of(S2, S3), "Narrow legs front", "nf")
    if len(S.steps) >= max_steps:
        return S
    turn_over(S, P, "Turn over", axis_x=0.0)
    if len(S.steps) >= max_steps:
        return S
    narrow(S, P, any_of(S5, S8), any_of(S6, S7), "Narrow legs back", "nb")
    if len(S.steps) >= max_steps:
        return S

    # 12. inside reverse fold neck (-x) and tail (+x) up between the wings
    half_f = half(-1, 1, 0)   # paper half now on top
    yV = 0.25
    legL = lambda f: f.wcen()[0] < 0 and not (S2(f) or S3(f) or S6(f) or S7(f))
    legR = lambda f: f.wcen()[0] > 0 and not (S2(f) or S3(f) or S6(f) or S7(f))
    pa = P.npose - 1
    cL = reverse_fold(P, legL, (0.0, yV), 270.0, 195.0, half_f, "neck")
    cR = reverse_fold(P, legR, (0.0, yV), 270.0, 345.0, half_f, "tail")
    pb = P.record()

    def custom12(F, s, Rs, ts, pa=pa, pb=pb):
        cL(F, s, Rs, ts, pa, pb)
        cR(F, s, Rs, ts, pa, pb)
        ts[:, 2] += max(cL.lift(s), cR.lift(s))
    custom12.lift = lambda s: max(cL.lift(s), cR.lift(s))
    hp = next(f for f in P.F if "neck" in f.tags).cen()
    S.step("Reverse fold neck and tail", [dict(a=pa, b=pb, custom=custom12, thick=True)], hint=tuple(hp), frames=30)
    if len(S.steps) >= max_steps:
        return S

    # 13. reverse fold the head (tip of the neck)
    pa = P.npose - 1
    nd = math.radians(180 - 2 * (192 - 270) - 180) if False else None
    neck_dir = 2 * 195.0 - 270.0           # reflected spine direction (deg)
    Vh = np.array([0.0, yV]) + 0.66 * np.array([math.cos(math.radians(neck_dir)), math.sin(math.radians(neck_dir))])
    head_dir = 200.0
    Lh = (neck_dir + head_dir) / 2.0
    cH = reverse_fold(P, tag("neck"), Vh, neck_dir, Lh, half_f, "head", open_deg=RF_OPT["head_open"])
    pb = P.record()
    hp = next(f for f in P.F if "head" in f.tags).cen()
    S.step("Reverse fold head", [dict(a=pa, b=pb, custom=lambda F, s, Rs, ts, pa=pa, pb=pb: cH(F, s, Rs, ts, pa, pb), thick=True)],
           hint=tuple(hp), frames=24)
    if len(S.steps) >= max_steps:
        return S

    # 14. wings down and open, the crane stands up
    wings_and_stand(S, P, yV + 0.28, half_f)
    return S


def narrow(S, P, hinge_sel, face_sel, name, key):
    pa = P.npose - 1
    hs = [f for f in P.F if hinge_sel(f)]
    pts = np.array([p for f in hs for p in f.wpoly()])
    Bt = pts[np.argmin(pts[:, 1])]
    for side in (-1, 1):
        q = pts[pts[:, 1] < 0.35]
        K = q[np.argmax(side * q[:, 0])]
        dirc = unit(unit(K - Bt) + np.array([0.0, 1.0]))
        seed = all_of(hinge_sel, lambda f, side=side: side * f.wcen()[0] > 0)
        P.fold_flood(Bt, Bt + dirc, side=K, region=any_of(hinge_sel, face_sel), seed=seed, tag=key)
    pb = P.record()
    hp = next(f for f in P.F if key in f.tags).cen()
    S.step(name, [dict(a=pa, b=pb)], hint=tuple(hp), frames=22)


def dir3(deg):
    return np.array([math.cos(math.radians(deg)), math.sin(math.radians(deg)), 0.0])


def _toward(a, b, ang):
    """Unit vector at angle `ang` from a on the great circle toward b."""
    t = b - (b @ a) * a
    nt = np.linalg.norm(t)
    if nt < 1e-12:
        return a
    return math.cos(ang) * a + math.sin(ang) * t / nt


def cone_rays(r0, rn, n, W, up):
    """n+1 unit rays from r0 to rn with consecutive angle W/n (an isometric
    fan of n rigid sectors), bulging toward `up` (spherical FABRIK, started
    from a symmetric bulge so the solution varies smoothly with the ends)."""
    gam = math.acos(np.clip(r0 @ rn, -1, 1))
    beta = W / n
    if gam >= W - 1e-9:
        if gam > W + 1e-6:
            print("  cone_rays: endpoints %.2f deg apart > fan %.2f deg" % (math.degrees(gam), math.degrees(W)))
        return [_toward(r0, rn, gam * i / n) if gam > 1e-9 else r0 for i in range(n + 1)]
    # bulge height of a circular arc of length W over chord gam (small angles)
    lift = math.sqrt(max(0.0, (W * W - gam * gam))) * 0.6
    upv = np.asarray(up, float)
    side = upv - (upv @ unit(r0 + rn)) * unit(r0 + rn)
    side = unit(side) if np.linalg.norm(side) > 1e-9 else unit(np.cross(r0, rn))
    rays = [unit(_toward(r0, rn, gam * i / n) + side * lift * math.sin(math.pi * i / n)) for i in range(n + 1)]
    rays[0], rays[n] = r0, rn
    for _ in range(400):
        for i in range(n - 1, 0, -1):
            rays[i] = _toward(rays[i + 1], rays[i], beta)
        for i in range(1, n):
            rays[i] = _toward(rays[i - 1], rays[i], beta)
        err = abs(math.acos(np.clip(rays[n - 1] @ rn, -1, 1)) - beta)
        if err < 1e-12:
            break
    return rays


# Reverse fold tuning (validator-guided; see the note in reverse_fold): fan of
# 4 sectors over half the crease->spine angle, body pages open 25 deg about the
# binding, the point's V opens by u=0.4, swings, and closes after u=0.6.
RF_OPT = dict(fan_frac=0.5, nfan=4, open_deg=25.0, bulge=1.0, head_open=0.0,
              t1=0.4, t2=0.6, t0=0.15, t3=0.85, sched=1.0, arm_lift=0.2, stack_pivot=1.0)


def _ss(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def rf_sched(u):
    """Reverse fold schedule: (flip fraction of the point's V about its spine,
    swing fraction, page opening fraction)."""
    o = RF_OPT
    if not o["sched"]:
        return u, u, math.sin(math.pi * u)
    t1, t2 = o["t1"], o["t2"]
    if u < t1:
        fl = 0.5 * _ss(u / t1)
    elif u <= t2:
        fl = 0.5
    else:
        fl = 0.5 + 0.5 * _ss((u - t2) / (1 - t2))
    sw = _ss((u - o["t0"]) / (o["t3"] - o["t0"]))
    op = min(_ss(u / t1), _ss((1 - u) / (1 - t2)))
    return fl, sw, op


def reverse_fold(P, sel, V, spine_deg, line_deg, front_half, key, fan_frac=None, nfan=None, open_deg=None):
    """Inside reverse fold of the narrow flap `sel` about the line through V
    (on the flap's spine) at angle line_deg; the tip lies on the side of the
    spine direction spine_deg and ends between the front and back layers.

    Motion (mirror-symmetric about the layer mid-plane): the point's two
    layers open about their shared spine (front up, back down) while the
    spine swings in the plane about V, so the point flips between the layers
    without ever separating from itself.  The paper next to the crease is a
    bendable fan of nfan thin sectors at V (fan_frac of the angle between the
    crease and the spine): an isometric cone that connects the static body to
    the moving point and flattens again at both ends."""
    fan_frac = RF_OPT["fan_frac"] if fan_frac is None else fan_frac
    nfan = RF_OPT["nfan"] if nfan is None else nfan
    open_deg = RF_OPT["open_deg"] if open_deg is None else open_deg
    V = np.asarray(V, float)
    d = np.array([math.cos(math.radians(line_deg)), math.sin(math.radians(line_deg))])
    sd = np.array([math.cos(math.radians(spine_deg)), math.sin(math.radians(spine_deg))])
    P.split(V, d, sel)
    n = perp(d)
    sg = np.sign(sd @ n)
    mov = [f for f in P.F if sel(f) and ((f.wcen() - V) @ n) * sg > 0]
    side_x = 1.0 if np.mean([f.wcen()[0] for f in mov]) > V[0] else -1.0
    # fan rays
    sec = ((spine_deg - line_deg) + 180) % 360 - 180          # signed crease -> spine angle
    sl = 1.0 if sec > 0 else -1.0
    W = abs(sec) * fan_frac
    ids = set(map(id, mov))
    for i in range(1, nfan + 1):
        ang = line_deg + sl * W * i / nfan
        P.split(V, (math.cos(math.radians(ang)), math.sin(math.radians(ang))), lambda f: id(f) in ids)
        ids = set(map(id, [f for f in P.F if sel(f) and ((f.wcen() - V) @ n) * sg > 0]))
    mov = [f for f in P.F if id(f) in ids]
    for f in mov:
        c = f.wcen() - V
        rel = (sl * (math.degrees(math.atan2(c[1], c[0])) - line_deg)) % 360
        k = int(rel / (W / nfan))
        f.tags.add("%s_fan%d" % (key, k) if k < nfan else "%s_tip" % key)
    Wm = [f.wpoly() for f in mov]
    R2 = refl2(d)
    P.apply(mov, R2, V - R2 @ V)
    for f in mov:
        f.tags.add(key)
    # z placement: between the front and back halves where the tip lands
    body = [f for f in P.F if id(f) not in ids]
    Wt = [f.wpoly() for f in mov]
    over = [g for g in body if any(overlap(g.wpoly(), w) for w in Wt)]
    hi = min([g.z for g in over if front_half(g)], default=None)
    lo = max([g.z for g in over if not front_half(g)], default=None)
    if hi is None or lo is None or hi <= lo:
        print("  reverse fold %s: no clean gap (lo=%s hi=%s)" % (key, lo, hi))
        lo = lo if lo is not None else 0.0
        for g in P.F:
            if front_half(g) and id(g) not in ids:
                g.z += 1000.0
        hi = lo + 1000.0
    mid = (hi + lo) / 2
    zf = [f.z for f in mov]
    zmin, zmax = min(zf), max(zf)
    span = max(zmax - zmin, 1.0)
    for f in mov:
        r = (f.z - zmin) / span   # 0..1 inside the tip
        if front_half(f):
            f.z = mid + 0.05 + 0.4 * (hi - mid) * (1 - r)
        else:
            f.z = mid - 0.05 - 0.4 * (mid - lo) * r
    P.compact()

    # kinematics (zero thickness, rotations about V)
    Dl = math.radians(((2 * (line_deg - spine_deg)) + 180) % 360 - 180)
    s3 = dir3(spine_deg)
    wv = dir3(line_deg) - (dir3(line_deg) @ s3) * s3
    ks = s3 if np.cross(s3, wv)[2] > 0 else -s3
    Mz = np.diag([1.0, 1.0, -1.0])
    a_dirs = [dir3(line_deg + sl * W * i / nfan) for i in range(nfan + 1)]
    F0 = [frame3(a_dirs[i], a_dirs[i + 1]) for i in range(nfan)]
    Wr = math.radians(W)

    sp_axis = unit(dir3(spine_deg))       # page opening axis (the spine / binding line)

    def page_rot(u, front):
        """Opening of the body pages on this side about the binding line."""
        a = math.radians(open_deg) * rf_sched(u)[2]
        if a == 0.0:
            return np.eye(3)
        # front page: the far (side_x) edge lifts
        R = rodrigues(sp_axis, a)
        if (R @ np.array([side_x, 0.0, 0.0]))[2] < 0:
            R = rodrigues(sp_axis, -a)
        return R if front else Mz @ R @ Mz

    def zero(u):
        fl, sw, _ = rf_sched(u)
        Tf = rodrigues((0, 0, 1), Dl * sw) @ rodrigues(ks, math.pi * fl)
        Rp = page_rot(u, True)
        rays = cone_rays(Rp @ a_dirs[0], Tf @ a_dirs[nfan], nfan, Wr, np.array([0, 0, RF_OPT["bulge"]]))
        fan = [frame3(rays[i], rays[i + 1]) @ F0[i].T for i in range(nfan)]
        return Tf, fan

    def group(f):
        if key + "_tip" in f.tags:
            return nfan
        for k in range(nfan):
            if "%s_fan%d" % (key, k) in f.tags:
                return k
        return None

    cache = {}

    def custom(F, s, Rs, ts, pa, pb):
        ck = (id(F), len(F))
        if ck not in cache:
            rows = []
            pages = []
            Tf1, fan1 = zero(1.0)
            worst = 0.0
            # one pivot height per original layer (same height at pa, same half)
            lay = {}
            for f in F:
                if key in f.tags and group(f) is not None:
                    ta_, tb_ = thick(f, pa)[1], thick(f, pb)[1]
                    lay.setdefault((front_half(f), round(ta_[2] / LAYER)), []).append((ta_[2] + tb_[2]) / 2)
            for i, f in enumerate(F):
                g = group(f) if key in f.tags else None
                if g is None:
                    if open_deg and not ({"neck", "tail", "head"} & f.tags) and \
                            side_x * (thick(f, pa)[0][:2, :2] @ f.cen() + thick(f, pa)[1][:2])[0] > 1e-6:
                        Ra, ta = thick(f, pa)
                        pages.append((i, front_half(f), Ra, ta))
                    continue
                Ra, ta = thick(f, pa)
                Rb, tb = thick(f, pb)
                fr = front_half(f)
                G1 = Tf1 if g == nfan else fan1[g]
                if not fr:
                    G1 = Mz @ G1 @ Mz
                e_ = float(np.abs(G1 @ Ra - Rb).max())
                if e_ > 1e-6 and worst < 1e-6:
                    print("    bad facet", i, g, fr, sorted(f.tags), np.round(Rb @ Ra.T, 3).tolist(), np.round(G1, 3).tolist())
                worst = max(worst, e_)
                # one pivot per stack (offset surfaces), outside the stack at
                # the start (front: above, back: below) so the layers move away
                # from the crease and the spine, ending at the exact flip pivot
                hs = [h for (frk, _), v in lay.items() if frk == fr for h in v]
                p1 = float(np.mean(hs))
                ha = [k_ * LAYER for (frk, k_) in lay if frk == fr]
                p0 = max(p1, max(ha) + LAYER / 2) if fr else min(p1, min(ha) - LAYER / 2)
                Pv = np.array([V[0], V[1], p1])
                res = tb - (G1 @ (ta - Pv) + Pv)
                rows.append((i, g, fr, Ra, ta, (p0, p1), res))
            print("  reverse fold %s: end rotation error %.2e, max residual %.4f" % (
                key, worst, max(np.abs(r[6]).max() for r in rows)))
            assert worst < 1e-6
            cache[ck] = (rows, pages)
        rows, pages = cache[ck]
        Tf, fan = zero(s)
        gp = _ss(s)
        for i, g, fr, Ra, ta, (p0, p1), res in rows:
            G = Tf if g == nfan else fan[g]
            if not fr:
                G = Mz @ G @ Mz
            Pv = np.array([V[0], V[1], p0 + (p1 - p0) * gp])
            Rs[i], ts[i] = G @ Ra, G @ (ta - Pv) + Pv + res * gp
        for i, fr, Ra, ta in pages:
            G = page_rot(s, fr)
            Pv = np.array([V[0], V[1], ts[i][2]])
            Rs[i], ts[i] = G @ Rs[i], G @ (ts[i] - Pv) + Pv
    custom.lift = lambda s: (0.46 * math.sin(math.radians(open_deg) * rf_sched(s)[2])
                             + RF_OPT["arm_lift"] * math.sin(math.pi * rf_sched(s)[0])) if open_deg else 0.0
    custom.zero = zero
    return custom


def wings_and_stand(S, P, yw, front_half, wing_deg=78.0):
    """Wings fold down along y = yw and the crane stands up (90 deg about x).
    Thick: each wing stack turns rigidly about the hinge line at the face of
    its stack that ends inside the bend (front wing: top of the front stack,
    back wing: bottom of the back stack), so its layers keep their spacing and
    the wing roots open away from the body instead of cutting into it.
    Motion: the wings start opening first, the body rises from flat to
    standing while they open (overlapping eased phases), lifted smoothly
    whenever a part would dip below the table."""
    pa = P.npose - 1
    flap = lambda f: not ({"neck", "tail", "head"} & f.tags)
    P.split((0.0, yw), (1.0, 0.0), flap)
    wingF = lambda f: flap(f) and front_half(f) and f.wcen()[1] > yw
    wingB = lambda f: flap(f) and not front_half(f) and f.wcen()[1] > yw
    for f in P.F:
        if wingF(f):
            f.tags.add("wingL")
        elif wingB(f):
            f.tags.add("wingR")
    P.record()   # flat pose with the wing creases (same as pa geometrically)
    TA = {id(f): thick(f, pa) for f in P.F}
    zL = max(TA[id(f)][1][2] for f in P.F if "wingL" in f.tags)
    zR = min(TA[id(f)][1][2] for f in P.F if "wingR" in f.tags)
    alpha = math.radians(wing_deg)
    up = w3((0.0, yw + 0.5))
    body_pts = np.array([p for f in P.F if not (f.tags & {"wingL", "wingR"}) for p in f.wpoly()])
    ybot = body_pts[:, 1].min()
    pivot = np.array([0.0, ybot, 0.0])
    hinge_pts = {"wingL": (np.array([-1.0, yw, zL]), np.array([1.0, yw, zL]), +1.0),
                 "wingR": (np.array([-1.0, yw, zR]), np.array([1.0, yw, zR]), -1.0)}

    def phases(s):
        return _ss(s / 0.9), _ss((s - 0.08) / 0.92)   # wings (slightly ahead), stand

    def delta(f, s, shift):
        sw, st = phases(s)
        R, t = np.eye(3), np.zeros(3)
        for k, (p1, p2, sg) in hinge_pts.items():
            if k in f.tags:
                R, t = hinge(p1, p2, sg * alpha * sw, up)
        Rg = rodrigues((1, 0, 0), math.radians(90) * st)
        tg = pivot - Rg @ pivot
        return Rg @ R, Rg @ t + tg + shift * st

    def pts_at(s, shift):
        out = []
        for f in P.F:
            Rd, td = delta(f, s, shift)
            Ra, ta = TA[id(f)]
            out.append(np.c_[f.poly, np.zeros(len(f.poly))] @ (Rd @ Ra).T + Rd @ ta + td)
        return out

    # final shift: stand on the table, body centred at the origin
    fin = pts_at(1.0, np.zeros(3))
    allp = np.concatenate(fin)
    bodyz = np.concatenate([q for q, f in zip(fin, P.F) if not (f.tags & {"wingL", "wingR"})])
    shift = np.array([-(bodyz[:, 0].min() + bodyz[:, 0].max()) / 2, -bodyz[:, 1].mean(), Z0 - allp[:, 2].min()])
    # lift profile so nothing dips below the table on the way
    ss_ = np.linspace(0, 1, 121)
    need = []
    for s in ss_:
        z = np.concatenate(pts_at(s, shift))[:, 2].min()
        need.append(max(0.0, Z0 - z))
    need = np.array(need)
    # smooth, conservative envelope (running max over a window, then a bump fit)
    env = np.array([need[max(0, i - 8):i + 9].max() for i in range(len(need))])

    def lift(s):
        return float(np.interp(s, ss_, env)) * 1.15

    pb_idx = P.npose
    for f in P.F:
        Rd, td = delta(f, 1.0, shift)
        Ra, ta = TA[id(f)]
        f.hist.append((Rd @ Ra, Rd @ ta + td, 0.0))
    P.npose += 1
    pb = pb_idx

    def custom(F, s, Rs, ts):
        for i, f in enumerate(F):
            Rd, td = delta(f, s, shift)
            Ra, ta = TA[id(f)] if id(f) in TA else thick(f, pa)
            Rs[i], ts[i] = Rd @ Ra, Rd @ ta + td + np.array([0, 0, lift(s)])
    hp = next(f for f in P.F if "wingL" in f.tags).cen()
    S.step("Wings down, stand up", [dict(a=pa, b=pb, custom=custom, thick=True)], hint=tuple(hp), frames=30)
    S.final = dict(pa=pa, pb=pb, pivot=pivot, shift=shift, yw=yw, zL=zL, zR=zR)


def tag(t):
    return lambda f: t in f.tags


def line_hit(p, d, a, b):
    """Intersection of the ray p + s d with the line a-b."""
    M = np.array([d, a - b]).T
    s, _ = np.linalg.solve(M, a - p)
    return p + s * d


def ray_frame(b, m):
    b = unit(b)
    n = unit(np.cross(b, m))
    return np.array([b, unit(np.cross(n, b)), n]).T


def petal(S, P, front, face, name, key):
    """Petal fold of the top flap of a square base lying as a diamond with the
    open point at -y.  Exact rigid motion: at each kite vertex K the centre
    rotates about the horizontal crease, the inner (hinge) triangle about the
    kite line, and the face side triangle follows (spherical four-bar)."""
    pa = P.npose - 1
    pts = np.array([f.wpoly() for f in P.F if front(f)]).reshape(-1, 2)
    Bt = pts[np.argmin(pts[:, 1])]
    Tp = pts[np.argmax(pts[:, 1])]
    Lc = pts[np.argmin(pts[:, 0])]
    Rc = pts[np.argmax(pts[:, 0])]
    axis = unit(Tp - Bt)
    KL = line_hit(Bt, rot2(math.radians(22.5)) @ axis, Tp, Lc)
    KR = line_hit(Bt, rot2(math.radians(-22.5)) @ axis, Tp, Rc)
    P.fold(Bt, KL, side=Lc, sel=front, tag="kL" + key)
    P.fold(Bt, KR, side=Rc, sel=front, tag="kR" + key)
    P.fold(KL, KR, side=Bt, sel=face, tag="pc" + key)
    pb = P.record()
    center = all_of(tag("pc" + key), lambda f: not (("kL" + key) in f.tags or ("kR" + key) in f.tags))
    sides = []
    for K, corner, kt in ((KL, Lc, "kL" + key), (KR, Rc, "kR" + key)):
        sides.append(dict(K=w3(K), kite=w3(Bt) - w3(K), out=w3(corner) - w3(K), tag=kt))

    up_side = w3(Bt)
    Rc1, _ = hinge(w3(KL), w3(KR), math.pi, up_side)

    def zero(s):
        """Zero-thickness rotations (about pivots on the creases) at s."""
        th = math.pi * s
        Rc_, _ = hinge(w3(KL), w3(KR), th, up_side)
        out = [("c", Rc_, w3(KL))]
        for sd in sides:
            K = sd["K"]
            b = Rc_ @ sd["kite"]
            kax = unit(sd["kite"])
            o = sd["out"]
            ang0 = math.acos(np.clip(kax @ unit(o), -1, 1))
            # hinge triangle about the kite line by psi keeps angle(b, m) = ang0
            Rh1, _ = hinge(K, K + sd["kite"], 1.0, K + o)
            ksg = unit(axis_angle(Rh1)[0]) * np.sign(axis_angle(Rh1)[1])
            par = (o @ ksg) * ksg
            per = o - par
            crs = np.cross(ksg, per)
            ub = unit(b)
            A_, B_, C_ = ub @ par, ub @ per, ub @ crs
            r = math.hypot(B_, C_)
            target = np.linalg.norm(o) * math.cos(ang0)
            ph = math.atan2(C_, B_)
            dlt = math.acos(np.clip((target - A_) / max(r, 1e-12), -1, 1))
            cands = [(ph + dlt) % (2 * math.pi), (ph - dlt) % (2 * math.pi)]
            psi = min(cands, key=lambda x: abs(x - math.pi * s))
            if s <= 0:
                psi = 0.0
            if s >= 1:
                psi = math.pi
            Rh = rodrigues(ksg, psi)
            m = Rh @ o
            Rf = ray_frame(b, m) @ ray_frame(sd["kite"], o).T
            out.append(("h" + sd["tag"], Rh, K))
            out.append(("f" + sd["tag"], Rf, K))
        return out

    def group(f):
        if center(f):
            return "c"
        for sd in sides:
            if sd["tag"] in f.tags:
                return ("f" if face(f) else "h") + sd["tag"]
        return None

    custom = thick_custom(pa, pb, group, zero, name, parent={"f" + sd["tag"]: "c" for sd in sides})
    hint = P.F[0]
    # hint: the bottom point of the face, slightly inside
    hp = None
    for f in P.F:
        if center(f):
            hp = f.cen()
            break
    S.step(name, [dict(a=pa, b=pb, custom=custom, thick=True)], hint=tuple(hp), frames=30)


def turn_over(S, P, name, axis_x=0.0):
    pa = P.npose - 1
    G = refl2((0.0, 1.0))
    g = np.array([2 * axis_x, 0.0])
    zm = P.zmax()
    cen = np.mean([f.wcen() for f in P.F], 0)
    P.apply(P.F, G, g)
    for f in P.F:
        f.z = zm - f.z
    P.compact()
    pb = P.record()
    hp = P.F[0].cen()
    S.step(name, [dict(a=pa, b=pb, lift=0.45, ref=w3(cen))], hint=tuple(hp), frames=22)

# ---------------------------------------------------------------- bake


SUBDIV = os.environ.get("FOLD_SUBDIV", "0") == "1"


def bake(S):
    P = S.P
    F = P.F
    vid = {}
    fv = []
    corner_f, corner_p, corner_g, tris = [], [], [], []
    def gid(p):
        return vid.setdefault((round(p[0] * 1e6), round(p[1] * 1e6)), len(vid))

    for fi, f in enumerate(F):
        local = {}

        def lv(p, fi=fi, local=local):
            key = (round(p[0] * 1e6), round(p[1] * 1e6))
            if key not in local:
                local[key] = len(corner_p)
                corner_f.append(fi)
                corner_p.append(np.asarray(p, float))
                corner_g.append(gid(p))
            return local[key]
        n = len(f.poly)
        sgn = poly_area(f.poly)
        for k in range(1, n - 1):
            a, b, c = f.poly[0], f.poly[k], f.poly[k + 1]
            ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
            # FOLD_SUBDIV=1: split every fan triangle 4 ways (smoother corner curl, but ~4x the facets the app sorts and
            # occlusion-tests each frame); default 0 keeps the real-time mesh light
            sub = ((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)) if SUBDIV else ((a, b, c),)
            for t in sub:
                i0, i1, i2 = (lv(p) for p in t)
                # paper polygon CCW seen from +z; the front (coloured) side faces -z
                tris.append((i0, i2, i1) if sgn > 0 else (i0, i1, i2))
    NV = len(vid)
    corner_f = np.array(corner_f)
    corner_p = np.array(corner_p)
    corner_g = np.array(corner_g)
    P3 = np.c_[corner_p, np.zeros(len(corner_p))]

    def positions(Rs, ts, ws, wts):
        R = Rs[corner_f]
        t = ts[corner_f]
        w = ws[corner_f]
        off = R[:, :, 2] * w[:, None]
        ideal = np.einsum("nij,nj->ni", R, P3) + t
        wt = wts[corner_f]
        acc = np.zeros((NV, 3))
        ws_ = np.zeros(NV)
        np.add.at(acc, corner_g, ideal * wt[:, None])
        np.add.at(ws_, corner_g, wt)
        st = acc / ws_[:, None]
        return st[corner_g] + off

    def pose_arrays(pi):
        Rs = np.array([f.hist[pi][0] for f in F])
        ts = np.array([f.hist[pi][1] for f in F])
        ws = np.array([f.hist[pi][2] for f in F])
        return Rs, ts, ws

    def thick_arrays(pi):
        Rs, ts, ws = pose_arrays(pi)
        return Rs, ts + Rs[:, :, 2] * ws[:, None]

    def positions_thick(Rs, ts):
        """Every facet rigid (no stitching): offsets are part of the transform."""
        return np.einsum("nij,nj->ni", Rs[corner_f], P3) + ts[corner_f]

    frames = []
    R0, t0, w0 = pose_arrays(S.p0)
    frames.append(positions_thick(*thick_arrays(S.p0)))
    steps_out = []
    for st in S.steps:
        k0 = len(frames) - 1
        phases = st["phases"]
        # one smoothstep over the whole step, keyframes evenly spaced in the
        # linear fold parameter (the app inverts it so flaps follow the finger)
        wts_ = np.array([ph.get("w", 1.0) for ph in phases], float)
        cum = np.concatenate([[0.0], np.cumsum(wts_ / wts_.sum())])
        n = st["frames"]
        prep = []
        for ph in phases:
            thick_mode = ph.get("thick", ph.get("custom") is None)
            if thick_mode:
                Ra, ta = thick_arrays(ph["a"])
                Rb, tb = thick_arrays(ph["b"])
                wa = wb = np.zeros(len(F))
            else:
                Ra, ta, wa = pose_arrays(ph["a"])
                Rb, tb, wb = pose_arrays(ph["b"])
            screws = []
            static = np.zeros(len(F))
            for i, f in enumerate(F):
                ref = ph.get("ref")
                if ref is None:
                    ref = Ra[i] @ w3(f.cen()) + ta[i]
                screws.append(Screw(Ra[i], ta[i], Rb[i], tb[i], ref=ref))
                same = np.abs(Ra[i] - Rb[i]).max() < 1e-7 and np.abs(ta[i] - tb[i]).max() < 1e-7
                static[i] = 20.0 if same else 1.0
            prep.append((screws, static, wa, wb, ph.get("lift", 0.0), ph.get("custom"), thick_mode))
        for k in range(1, n + 1):
            s_all = ease(k / n)
            j = min(int(np.searchsorted(cum, s_all, side="right")) - 1, len(phases) - 1)
            s = min(1.0, max(0.0, (s_all - cum[j]) / (cum[j + 1] - cum[j])))
            screws, static, wa, wb, lift, custom, thick_mode = prep[j]
            Rs = np.empty((len(F), 3, 3))
            ts = np.empty((len(F), 3))
            for i, sc in enumerate(screws):
                Rs[i], ts[i] = sc.at(s)
            if custom is not None:
                custom(F, s, Rs, ts)
            ts[:, 2] += lift * math.sin(math.pi * s)
            if thick_mode:
                frames.append(positions_thick(Rs, ts))
                continue
            ws = wa + (wb - wa) * s
            frames.append(positions(Rs, ts, ws, static))
        k1 = len(frames) - 1
        # hint arrow: world point of the paper hint at the start and the end
        hp = np.asarray(st["hint"], float)
        fi = max((i for i, f in enumerate(F) if point_in_poly(f.poly, hp)),
                 key=lambda i: F[i].hist[phases[0]["a"]][2] * F[i].hist[phases[0]["a"]][0][2, 2])

        def wp(pi):
            R, t, w = F[fi].hist[pi]
            return R @ (w3(hp) + np.array([0, 0, w])) + t
        steps_out.append(dict(name=st["name"], **{"from": k0, "to": k1},
                              hint=dict(a=[round(float(v), 4) for v in wp(phases[0]["a"])],
                                        b=[round(float(v), 4) for v in wp(phases[-1]["b"])])))
    return dict(frames=np.array(frames, dtype=np.float32), uv=(corner_p + 1) / 2, paper=corner_p,
                tris=np.array(tris, dtype=np.int32), steps=steps_out,
                corner_f=corner_f, corner_g=corner_g)


def write_outputs(S, R, extra=None):
    os.makedirs(OUT_DIR, exist_ok=True)
    fr = R["frames"]
    K, V, _ = fr.shape
    meta = {
        "version": len(R["steps"]),
        "vertexCount": int(V),
        "triCount": int(len(R["tris"])),
        "keyframes": int(K),
        "layerThickness": LAYER,
        "uv": [round(float(x), 6) for x in R["uv"].reshape(-1)],
        "tris": [int(x) for x in R["tris"].reshape(-1)],
        "steps": R["steps"],
        "wings": None,
        "head": None,
        "tail": None,
    }
    if extra:
        meta.update(extra)
    binp = os.path.join(OUT_DIR, "crane.bin")
    jsp = os.path.join(OUT_DIR, "crane.json")
    with open(binp + ".tmp", "wb") as fh:
        fh.write(fr.astype("<f4").tobytes())
    with open(jsp + ".tmp", "w") as fh:
        json.dump(meta, fh, separators=(",", ":"))
    os.replace(binp + ".tmp", binp)
    os.replace(jsp + ".tmp", jsp)
    print("wrote %s: V=%d T=%d K=%d steps=%d" % (OUT_DIR, V, len(R["tris"]), K, len(R["steps"])))


def crane_meta(S, R):
    """Wing mask, wing hinge axes, head and tail points of the finished crane."""
    if not hasattr(S, "final"):
        return None
    F = S.P.F
    cf = R["corner_f"]
    fr = R["frames"][-1]
    fin = S.final
    mask = [(-1 if "wingL" in F[i].tags else 1 if "wingR" in F[i].tags else 0) for i in cf]
    Rg = rodrigues((1, 0, 0), math.radians(90))
    piv = fin["pivot"]
    tg = piv - Rg @ piv + fin["shift"]
    axes = {}
    for key, tagn in (("axisL", "wingL"), ("axisR", "wingR")):
        xs = [F[i].wpoly()[:, 0] for i in range(len(F)) if tagn in F[i].tags]
        xs = np.concatenate(xs)
        y = fin["yw"]
        z = fin["zL"] if tagn == "wingL" else fin["zR"]
        a = Rg @ np.array([xs.min(), y, z]) + tg
        b = Rg @ np.array([xs.max(), y, z]) + tg
        axes[key] = [[round(float(v), 4) for v in a], [round(float(v), 4) for v in b]]
    hm = np.array(["head" in F[i].tags for i in cf])
    tm = np.array(["tail" in F[i].tags for i in cf])
    head = fr[hm][np.argmin(fr[hm][:, 0])]
    tail = fr[tm][np.argmax(np.linalg.norm(fr[tm] - fr.mean(0), axis=1))]
    return {"wings": dict(mask=mask, **axes),
            "head": [round(float(v), 4) for v in head],
            "tail": [round(float(v), 4) for v in tail]}


def _bary(F, A, B, C):
    v0, v1, v2 = B - A, C - A, F - A
    d00 = (v0 * v0).sum(-1)
    d01 = (v0 * v1).sum(-1)
    d11 = (v1 * v1).sum(-1)
    d20 = (v2 * v0).sum(-1)
    d21 = (v2 * v1).sum(-1)
    den = d00 * d11 - d01 * d01
    den = np.where(np.abs(den) < 1e-18, 1e-18, den)
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    return 1 - v - w, v, w


def validate_frames(fr, paper, tris, pid, layer, steps, verbose=True,
                    strain_max=0.01, sep_min=0.75, report=None):
    """Check every keyframe.
    * stretch: every triangle edge within strain_max of its paper length;
    * interpenetration: no triangle edge crosses the interior of another
      triangle (pairs sharing a paper vertex are skipped: they meet on a crease);
    * layer separation: overlapping, nearly parallel triangles are at least
      sep_min * layer apart (touching layers would flicker in the painter's sort).
    Returns dict(ok, per-step stats, summary)."""
    tris = np.asarray(tris)
    T = len(tris)
    P0 = paper[tris]
    rest = np.linalg.norm(P0[:, [1, 2, 0]] - P0, axis=2)
    tp = pid[tris]
    share = (tp[:, None, :, None] == tp[None, :, None, :]).any((2, 3))
    upper = np.triu(np.ones((T, T), bool), 1)
    base_ok = upper & ~share
    bw = np.array([[1 / 3, 1 / 3, 1 / 3], [0.6, 0.2, 0.2], [0.2, 0.6, 0.2], [0.2, 0.2, 0.6]])
    E0, E1 = [0, 1, 2], [1, 2, 0]
    cos_par = math.cos(math.radians(25))
    per_step = []
    worst_all = dict(strain=0.0, cross=0, sep=1e9)

    def frame_stats(X):
        lens = np.linalg.norm(X[:, E1] - X[:, E0], axis=2)
        strain = np.abs(lens / rest - 1).max(1)
        nrm = np.cross(X[:, 1] - X[:, 0], X[:, 2] - X[:, 0])
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-18
        lo, hi = X.min(1), X.max(1)
        tol = layer
        box = np.ones((T, T), bool)
        for c in range(3):
            box &= (lo[:, None, c] < hi[None, :, c] + tol) & (hi[:, None, c] > lo[None, :, c] - tol)
        I, J = np.nonzero(box & base_ok)
        ncross = 0
        cross_pairs = []
        for a, b in ((I, J), (J, I)):
            A, Bv, Cv = X[b, 0], X[b, 1], X[b, 2]
            nb = nrm[b]
            for e in range(3):
                Pp, Qp = X[a, E0[e]], X[a, E1[e]]
                dp = ((Pp - A) * nb).sum(1)
                dq = ((Qp - A) * nb).sum(1)
                m = (dp * dq < 0) & (np.minimum(np.abs(dp), np.abs(dq)) > 2e-5)
                if not m.any():
                    continue
                s = (dp / (dp - dq + 1e-30))[:, None]
                Xc = Pp + (Qp - Pp) * s
                u, v, w = _bary(Xc, A, Bv, Cv)
                hit = m & (u > 1e-3) & (v > 1e-3) & (w > 1e-3)
                if hit.any():
                    ncross += int(hit.sum())
                    cross_pairs += list(zip(a[hit].tolist(), b[hit].tolist()))
        # layer separation
        par = np.abs((nrm[I] * nrm[J]).sum(1)) > cos_par
        Ip, Jp = I[par], J[par]
        sep = 1e9
        sep_pairs = []
        for a, b in ((Ip, Jp), (Jp, Ip)):
            A, Bv, Cv = X[b, 0], X[b, 1], X[b, 2]
            nb = nrm[b]
            for wv in bw:
                pnt = (X[a] * wv[None, :, None]).sum(1)
                dist = ((pnt - A) * nb).sum(1)
                foot = pnt - dist[:, None] * nb
                u, v, w = _bary(foot, A, Bv, Cv)
                inside = (u > 1e-3) & (v > 1e-3) & (w > 1e-3)
                if inside.any():
                    dd = np.abs(dist[inside])
                    sep = min(sep, float(dd.min()))
                    bad = dd < sep_min * layer
                    if bad.any():
                        sep_pairs += list(zip(a[inside][bad].tolist(), b[inside][bad].tolist()))
        return strain, ncross, sep, cross_pairs, sep_pairs

    # tear check: corners of one paper point (different facets) may sit apart
    # by the layer gap at a thick crease, but mid-motion never more than the
    # larger of the two end states + 3 layers
    order = np.argsort(pid, kind="stable")
    ps = pid[order]
    first = np.r_[0, np.nonzero(np.diff(ps))[0] + 1]
    gid = np.repeat(np.arange(len(first)), np.diff(np.r_[first, len(ps)]))
    head = order[first][gid]

    def gaps(X):
        d = np.linalg.norm(X[order] - X[head], axis=1)
        g = np.zeros(len(first))
        np.maximum.at(g, gid, d)
        return g

    ok = True
    for si, st in enumerate(steps):
        smax, sarg, ncr, crk, sp, spk, nsep = 0.0, None, 0, [], 1e9, None, 0
        gend = np.maximum(gaps(fr[st["from"]]), gaps(fr[st["to"]])) + 3 * layer
        tear = 0.0
        for k in range(st["from"], st["to"] + 1):
            tear = max(tear, float((gaps(fr[k]) - gend).max()) + 3 * layer)
            strain, nc, sep, cp, sps = frame_stats(fr[k][tris])
            if report is not None:
                report(k, cp, sps)
            i = int(np.argmax(strain))
            if strain[i] > smax:
                smax, sarg = float(strain[i]), (k, i)
            if nc:
                ncr += nc
                crk.append(k)
            if sps:
                nsep += len(sps)
                if spk is None:
                    spk = (k, sps[0])
            sp = min(sp, sep)
        torn = tear > 3 * layer + 1e-6
        good = smax <= strain_max and ncr == 0 and nsep == 0 and not torn
        ok &= good
        per_step.append(dict(name=st["name"], strain=smax, cross=ncr, sep=sp, nsep=nsep, tear=tear))
        worst_all["strain"] = max(worst_all["strain"], smax)
        worst_all["cross"] += ncr
        worst_all["sep"] = min(worst_all["sep"], sp)
        if verbose:
            print("  %2d %-26s strain %.4f%s  gap+ %.4f%s  crossings %4d%s  min sep %.4f (%d below %.4f)%s %s" % (
                si + 1, st["name"], smax, " @k%d tri%d" % sarg if sarg and smax > 1e-4 else "",
                max(0.0, tear - 3 * layer), " TORN" if torn else "",
                ncr, " frames %d..%d" % (crk[0], crk[-1]) if crk else "",
                sp if sp < 1e8 else float("nan"), nsep, sep_min * layer,
                " first @k%d %s" % spk if spk else "", "OK" if good else "FAIL"))
    summary = "VALID" if ok else "INVALID"
    summary += ": worst strain %.4f, crossings %d, min layer sep %.4f" % (
        worst_all["strain"], worst_all["cross"], worst_all["sep"])
    return dict(ok=ok, steps=per_step, summary=summary)


def check(R):
    """Print per step end: z range and minimum separation sanity."""
    fr = R["frames"]
    for st in R["steps"]:
        P = fr[st["to"]]
        print("  %-22s k=%3d..%3d  z=[%.4f, %.4f] x=[%.2f,%.2f] y=[%.2f,%.2f]" % (
            st["name"], st["from"], st["to"], P[:, 2].min(), P[:, 2].max(),
            P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max()))

# ---------------------------------------------------------------- Blender


def blender_preview(R, only=None, kframes=None):
    import bpy
    from mathutils import Vector

    os.makedirs(PREVIEW_DIR, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    fr = R["frames"]
    tris = R["tris"]
    me = bpy.data.meshes.new("crane")
    me.from_pydata([tuple(v) for v in fr[0]], [], [tuple(t) for t in tris])
    me.update()
    uvl = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            uvl.data[li].uv = tuple(R["uv"][vi])
    ob = bpy.data.objects.new("crane", me)
    sc.collection.objects.link(ob)
    ob.shape_key_add(name="flat")
    keys = []
    for st in R["steps"]:
        kb = ob.shape_key_add(name=st["name"])
        kb.data.foreach_set("co", fr[st["to"]].reshape(-1))
        keys.append(kb)

    mat = bpy.data.materials.new("paper")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfDiffuse")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.inputs[1].default_value = (0.70, 0.08, 0.05, 1)   # front: vermilion
    mix.inputs[2].default_value = (0.90, 0.82, 0.66, 1)   # back: cream
    nt.links.new(geo.outputs["Backfacing"], mix.inputs[0])
    nt.links.new(mix.outputs[0], bsdf.inputs["Color"])
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    mat.use_backface_culling = False
    ob.data.materials.append(mat)

    # table
    bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
    tb = bpy.context.active_object
    tm = bpy.data.materials.new("table")
    tm.use_nodes = True
    tm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.45, 0.32, 1)
    tb.data.materials.append(tm)

    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 3.0
    so = bpy.data.objects.new("sun", sun)
    so.rotation_euler = (math.radians(40), math.radians(-25), math.radians(20))
    sc.collection.objects.link(so)
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.8
    sc.world = world

    cam = bpy.data.cameras.new("cam")
    cam.lens = 40
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co

    def aim(loc, target):
        co.location = loc
        d = Vector(target) - Vector(loc)
        co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()

    try:
        sc.render.engine = "BLENDER_EEVEE"
    except TypeError:
        sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.render.film_transparent = False
    views = [("app", (0, -4.2, 5.6), (0, 0, 0), 330, 600),
             ("side", (0.6, -5.5, 1.3), (0, 0, 0.35), 560, 360)]
    if kframes:
        cv = [float(v) for v in os.environ.get("FOLD_VIEW", "1.6,-2.6,2.4,0,0.25,0.15").split(",")]
        aim(tuple(cv[:3]), tuple(cv[3:6]))
        cam.lens = 50
        sc.render.resolution_x, sc.render.resolution_y = 360, 360
        for kb in keys:
            kb.value = 0.0
        for k in kframes:
            ob.data.shape_keys.key_blocks[0].data.foreach_set("co", fr[k].reshape(-1))
            sc.render.filepath = os.path.join(PREVIEW_DIR, "mid_%03d.png" % k)
            bpy.ops.render.render(write_still=True)
        return
    for i, st in enumerate(R["steps"]):
        if only is not None and i not in only:
            continue
        for kb in keys:
            kb.value = 0.0
        keys[i].value = 1.0
        for name, loc, tgt, w, h in views:
            aim(loc, tgt)
            sc.render.resolution_x, sc.render.resolution_y = w, h
            sc.render.filepath = os.path.join(
                PREVIEW_DIR, "step_%02d%s.png" % (i + 1, "" if name == "app" else "_side"))
            bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(PREVIEW_DIR, "crane_preview.blend"))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    max_steps = 99
    only = None
    kframes = None
    for a in argv:
        if a.startswith("--steps="):
            max_steps = int(a.split("=")[1])
        if a.startswith("--frames="):
            kframes = [int(x) for x in a.split("=")[1].split(",")]
        if a.startswith("--rf="):
            for kv in a.split("=", 1)[1].split(","):
                k_, v_ = kv.split(":")
                RF_OPT[k_] = float(v_)
        if a.startswith("--only="):
            only = [int(x) - 1 for x in a.split("=")[1].split(",")]
    S = build(max_steps)
    R = bake(S)
    check(R)
    print("validation (every keyframe):")
    V = validate_frames(R["frames"].astype(float), R["paper"], R["tris"], R["corner_g"], LAYER, R["steps"])
    print(V["summary"])
    if "--no-write" not in argv:
        if V["ok"] or "--force-write" in argv:
            write_outputs(S, R, crane_meta(S, R))
        else:
            print("NOT written: the sequence does not validate (use --force-write to override)")
    if "--no-render" not in argv:
        try:
            import bpy  # noqa: F401
        except ImportError:
            print("no bpy: skipping previews")
            return
        blender_preview(R, only, kframes)


if __name__ == "__main__":
    main()
