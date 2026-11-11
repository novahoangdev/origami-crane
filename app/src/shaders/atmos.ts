import { Skia } from "react-native-skia";

/**
 * Morning air, drawn with "screen" over the scene: soft god rays fanning from the sun behind the shoji (the lattice breaks them
 * into shafts) and dust motes drifting through them, only visible inside the beams.
 */
const src = `
uniform float2 view;
uniform float2 sun;     // sun position in screen pt (may be far off-screen)
uniform float time;
uniform float k;        // overall strength
uniform float down;     // 1 = indoors: shafts only pour down/forward from the opening, not across the ceiling

float hash(float2 p) { p = fract(p * float2(443.897, 441.423)); p += dot(p, p.yx + 19.19); return fract((p.x + p.y) * p.x); }
float noise(float x) { float i = floor(x); float f = fract(x); f = f * f * (3.0 - 2.0 * f); return mix(hash(float2(i, 3.1)), hash(float2(i + 1.0, 3.1)), f); }

// a soft lens ghost: disc with a slightly brighter rim
float ghost(float2 p, float2 c, float r) {
  float x = length(p - c) / r;
  return smoothstep(1.0, 0.75, x) * (0.55 + 0.45 * smoothstep(0.5, 0.95, x));
}

half4 main(float2 p) {
  float2 d = p - sun;
  float ang = atan(d.x, d.y);
  float r = length(d);
  // shafts: angular bands (lattice) + slow drifting variation
  // shafts shimmer: leaves outside keep cutting them, so the bands slide and breathe
  float bands = noise(ang * 38.0 + time * 0.16) * 0.55 + noise(ang * 97.0 - time * 0.27) * 0.3 + noise(ang * 211.0 + time * 0.6) * 0.15;
  bands = smoothstep(0.32, 0.85, bands) * (0.85 + 0.15 * sin(time * 1.9 + ang * 13.0));
  float fall = exp(-r / (view.y * 0.75));
  // when the sun itself is in frame, keep the shafts as soft streaks instead of a hard starburst
  float onScreen = 1.0 - smoothstep(0.0, view.y * 0.25, max(max(-sun.x, sun.x - view.x), max(-sun.y, sun.y - view.y)));
  float beam = bands * fall * (1.0 - 0.6 * onScreen) * smoothstep(0.0, view.y * 0.08, r);
  beam *= mix(1.0, smoothstep(-0.15, 0.55, d.y / max(r, 1.0)), down);
  // out under the open sky there are no shafts at all (painted-on rays fanning across the clouds looked fake): only the haze
  beam *= down;
  // warm haze around the sun (the low sun bleeding through the opening)
  float haze = mix(1.0, 0.55, down) * (exp(-r / (view.y * 0.18)) * 0.42 + exp(-r / (view.y * 0.6)) * 0.08) * (1.0 - 0.35 * onScreen);
  // dust motes: one per cell, drifting slowly, twinkling
  float dust = 0.0;
  for (int l = 0; l < 2; l++) {
    float s = l == 0 ? 34.0 : 61.0;
    float2 q = p / s + float2(time * (0.05 + 0.03 * float(l)), -time * 0.07);
    float2 c = floor(q);
    float h = hash(c + float(l) * 17.0);
    float2 o = float2(hash(c + 3.7), hash(c + 9.1));
    float2 w = fract(q) - o;
    float sz = 0.035 + 0.05 * h;
    float tw = 0.5 + 0.5 * sin(time * (1.0 + 2.0 * h) + h * 40.0);
    dust += step(0.62, h) * smoothstep(sz, 0.0, length(w)) * tw;
  }
  float3 warm = float3(1.0, 0.82, 0.58);
  float3 col = (warm * (beam * 0.16 + dust * beam * 1.4 + dust * 0.03 * down) + float3(1.0, 0.72, 0.45) * haze) * k;
  // anime lens ghosts: with the sun in frame under the open sky, a few soft tinted discs line up through the frame centre
  float gk = 0.0; // lens ghosts off (read as fake)
  if (gk > 0.001) {
    float2 axis = view * 0.5 - sun;
    float u = view.y;
    col += float3(0.45, 0.85, 0.75) * ghost(p, sun + axis * 0.55, u * 0.035) * 0.10 * gk;
    col += float3(1.0, 0.70, 0.40) * ghost(p, sun + axis * 1.20, u * 0.06) * 0.08 * gk;
    col += float3(0.95, 0.55, 0.75) * ghost(p, sun + axis * 1.65, u * 0.022) * 0.14 * gk;
    col += float3(0.55, 0.75, 1.0) * ghost(p, sun + axis * 2.10, u * 0.09) * 0.05 * gk;
  }
  return half4(half3(col), 0.0);
}
`;
export const atmosFx = Skia.RuntimeEffect.Make(src)!;

/**
 * The crane vanishing into the light: a small, soft warm glow that swells gently where it was and fades (no rays, never
 * clipping to white). Drawn with "plus"; age 0..1 over the bloom, size in pt.
 */
const vanish = `
uniform float2 c;
uniform float age;
uniform float size;
uniform float time;
half4 main(float2 p) {
  if (age <= 0.0 || age >= 1.0) return half4(0.0);
  float r = length(p - c) / size;
  float env = smoothstep(0.0, 0.25, age) * pow(1.0 - age, 2.0);
  float v = (exp(-r * r * 4.0) * 0.32 + exp(-r * 1.6) * 0.12) * env;
  half3 col = mix(half3(1.0, 0.66, 0.38), half3(1.0, 0.88, 0.7), exp(-r * r * 6.0));
  return half4(col * v, v);
}
`;
export const vanishFx = Skia.RuntimeEffect.Make(vanish)!;

/**
 * The crane awakening: a soft pillar of warm light rises from the floor through the crane, with motes of light drifting up
 * inside it. c = floor point under the crane (screen pt), top = crane (screen pt), age 0..1, w = half width (pt). "plus".
 */
const awaken = `
uniform float2 c;
uniform float2 top;
uniform float age;
uniform float w;
uniform float time;
float h1(float x) { return fract(sin(x * 91.7) * 43758.5453); }
half4 main(float2 p) {
  if (age <= 0.0 || age >= 1.0) return half4(0.0);
  float env = smoothstep(0.0, 0.12, age) * pow(1.0 - age, 1.3);
  // the pillar: from the floor point up past the crane, widening a little, brightest around the crane
  float ht = max(1.0, c.y - top.y) * 2.2;
  float v = (c.y - p.y) / ht;                       // 0 at the floor, 1 at the top of the pillar
  float x = (p.x - mix(c.x, top.x, clamp(v * 2.2, 0.0, 1.0))) / (w * (1.0 + 0.6 * v));
  float core = exp(-x * x * 3.0) * smoothstep(-0.05, 0.08, v) * (1.0 - smoothstep(0.55, 1.0, v));
  float glow = exp(-x * x * 0.6) * smoothstep(-0.1, 0.1, v) * (1.0 - smoothstep(0.4, 1.0, v)) * 0.35;
  // rising motes
  float m = 0.0;
  for (int i = 0; i < 10; i++) {
    float fi = float(i);
    float sp = 0.25 + 0.35 * h1(fi);
    float yy = fract(h1(fi + 3.0) + age * sp * 2.5);
    float2 q = float2(mix(c.x, top.x, 0.5) + (h1(fi + 7.0) - 0.5) * w * 1.6, c.y - yy * ht * 0.9);
    float d = length(p - q);
    m += exp(-d * d / 18.0) * (1.0 - yy) * (0.6 + 0.4 * sin(time * 9.0 + fi * 3.0));
  }
  // restrained: a faint warm column and a few motes, never a blown-out spot under the crane
  float val = (core * 0.1 + glow * 0.38 + m * 0.45) * env;
  half3 col = half3(1.0, 0.74, 0.46);
  return half4(col * val, clamp(val, 0.0, 1.0));
}
`;
export const awakenFx = Skia.RuntimeEffect.Make(awaken)!;
