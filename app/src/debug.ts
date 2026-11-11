/** Dev-only knobs for inspecting a frame on the simulator (keep at defaults when committing). */
export const DEBUG_P = -1; // ≥ 0: freeze the fold at this keyframe
export const FORCE_DEMO = false; // dev: play the demo storyboard without EXPO_PUBLIC_DEMO
export const FORCE_USERSIM = false; // dev: the scripted-user screen recording mode without EXPO_PUBLIC_USERSIM
export const HOLD_INTRO = false; // dev: keep the demo intro (hovering crane) forever
export const PERF_LOG = false; // dev: log "PERF fps tickMs" every 2 s (UI-thread frame rate and the cost of one scene tick)
export const START_STEP = -1; // dev, interactive only: ≥ 0 starts at this step (0-based) instead of the flat sheet
export const HIDE_LAYERS = 0; // dev: bit i hides scene layer i (sky = bit 0)
