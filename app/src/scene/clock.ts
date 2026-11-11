/**
 * Shared clock. EXPO_PUBLIC_TIMESCALE (default 1) slows the whole scene for simulator capture: record at 0.5 then compress time
 * back → 120 frames per demo second (the sim is only 60 Hz). All motion must derive from CraneScene's `time` (already scaled
 * by the factor) or go through `ms()` / `spring()`; never use Date.now / performance.now / timestamps for visuals.
 */
export const TIMESCALE = Math.max(0.05, Number(process.env.EXPO_PUBLIC_TIMESCALE ?? "1") || 1);

/** duration (ms, scene time) → real ms */
export const ms = (d: number) => {
  "worklet";
  return d / TIMESCALE;
};

/** spring slowed exactly by TIMESCALE: duration ∝ sqrt(mass / stiffness) → divide stiffness and damping by TIMESCALE */
export const spring = <T extends { stiffness?: number; damping?: number; mass?: number }>(cfg: T): T => ({
  ...cfg,
  stiffness: (cfg.stiffness ?? 100) * TIMESCALE * TIMESCALE,
  damping: (cfg.damping ?? 10) * TIMESCALE,
});
