import { Skia } from "react-native-skia";

/**
 * Living light for the room. The Blender passes split the table light into
 *   table = base (sky/bounce) + sun (unoccluded direct sun) × lattice (static shoji/pillar shadows) × leaves (garden dapples)
 * so the leaf dapples can sway in the wind: the leaves mask is sampled through a slow domain warp, two warped samples are mixed so
 * the dapples also twinkle (light flickering through moving leaves), and the sun breathes very slightly.
 * All children are sampled in table-image pixel coordinates (the texcoords of the table grid / of the paper's sun-projected points).
 */
const warp = `
float2 leafWarp(float2 p, float t, float k) {
  float2 d = float2(
    5.0 * sin(t * 1.10 + p.x * 0.013 + p.y * 0.007) + 2.5 * sin(t * 2.70 + p.y * 0.031),
    3.5 * cos(t * 0.90 + p.y * 0.011 - p.x * 0.005) + 2.0 * cos(t * 2.10 + p.x * 0.027));
  // gusts: every few seconds the whole canopy leans a little further
  float g = 0.5 + 0.5 * sin(t * 0.37) * sin(t * 0.23 + 1.3);
  return p + d * k * (0.6 + 0.8 * g);
}
// the furin's shadow on the floor swings with the chime (same motion as the painted one in layerFx): rotate the lattice-mask
// pixels around the shadow of its hanging point, in a soft column along the string
float2 furinShadow(float2 p, float t) {
  float2 pv = float2(1163.0, 907.0);
  float2 ax = float2(0.165, 0.986);
  float2 d = p - pv;
  float along = dot(d, ax);
  float side = dot(d, float2(ax.y, -ax.x));
  float m = smoothstep(60.0, 40.0, abs(side)) * smoothstep(-5.0, 10.0, along) * smoothstep(470.0, 430.0, along);
  float a = -m * (0.10 * sin(t * 1.7) + 0.05 * sin(t * 3.1 + 1.0) + 0.03 * sin(t * 5.3));
  float cs = cos(a), sn = sin(a);
  return pv + float2(cs * d.x + sn * d.y, -sn * d.x + cs * d.y);
}
float leafMix(float a, float b, float2 p, float t) {
  return mix(a, b, 0.35 + 0.25 * sin(t * 1.7 + p.x * 0.02));
}
`;

const table = `
uniform shader base;
uniform shader sun;
uniform shader lattice;
uniform shader leaves;
uniform float time;
uniform float sway;
uniform float sunK;
${warp}
half4 main(float2 p) {
  // the passes combine in linear light: srgb(lin(base) + lin(sun) · visibility)
  half3 b = pow(base.eval(p).rgb, half3(2.2));
  half3 s = pow(sun.eval(p).rgb, half3(2.2));
  float la = leaves.eval(leafWarp(p, time, sway)).r;
  float lb = leaves.eval(leafWarp(p + float2(17.0, -11.0), time * 1.3 + 4.0, sway * 1.4)).r;
  float v = lattice.eval(furinShadow(p, time)).r * leafMix(la, lb, p, time);
  return half4(pow(b + s * v * sunK, half3(1.0 / 2.2)), 1.0);
}
`;
export const tableFx = Skia.RuntimeEffect.Make(table)!;

/** sun visibility on the paper facets (same warp as the table so the dapples slide across paper and wood together) */
const paperMask = `
uniform shader lattice;
uniform shader leaves;
uniform float time;
uniform float sway;
uniform float shade;
${warp}
half4 main(float2 p) {
  float la = leaves.eval(leafWarp(p, time, sway)).r;
  float lb = leaves.eval(leafWarp(p + float2(17.0, -11.0), time * 1.3 + 4.0, sway * 1.4)).r;
  float v = lattice.eval(furinShadow(p, time)).r * leafMix(la, lb, p, time);
  return half4(half3(mix(shade, 1.0, v)), 1.0);
}
`;
export const paperMaskFx = Skia.RuntimeEffect.Make(paperMask)!;

/**
 * A painted multiplane layer (sky, hills, garden, house): horizontal drift (clouds), a soft sway for foliage, and a warm haze
 * toward the sun for depth. Sampled in image pixel coordinates.
 */
const layer = `
uniform shader img;
uniform float2 size;
uniform float time;
uniform float drift;
uniform float sway;
uniform float3 furin;   // painted wind chime: pivot (image px) and swing strength (0 = this layer has none)
half4 main(float2 p) {
  float2 q = p;
  // the furin swings on its string in the breeze: rotate the pixels below the pivot (narrow column, soft edges)
  if (furin.z > 0.0) {
    float2 d = p - furin.xy;
    float m = smoothstep(46.0, 30.0, abs(d.x)) * step(0.0, d.y) * smoothstep(150.0, 135.0, d.y);
    float a = furin.z * m * (0.10 * sin(time * 1.7) + 0.05 * sin(time * 3.1 + 1.0) + 0.03 * sin(time * 5.3));
    float cs = cos(a), sn = sin(a);
    q = furin.xy + float2(cs * d.x + sn * d.y, -sn * d.x + cs * d.y);
  }
  q.x += time * drift; // the image repeats in x (no mod: a jump in the coordinate breaks the sampler's derivatives too)
  // foliage sways more toward the top of the layer, gently and out of phase across it
  float k = sway * (1.0 - q.y / size.y);
  q.x += k * (3.0 * sin(time * 1.3 + q.y * 0.02 + q.x * 0.004) + 1.5 * sin(time * 2.9 + q.x * 0.03));
  q.y += k * 1.2 * cos(time * 1.1 + q.x * 0.015);
  // beyond the painted top or bottom (the layer's skirts): a soft horizontal average of the last row, so it reads as distant
  // forest shade instead of stretched pixel streaks. Every tap is taken unconditionally and the results are blended with
  // step/smoothstep: an image sample inside a per-pixel branch gets undefined screen derivatives in the 2×2 pixel quads
  // that straddle the branch edge, which showed as a dashed line of wrong texels along each skirt boundary.
  half4 c = img.eval(float2(q.x, clamp(q.y, drift > 0.0 ? 10.0 : 0.0, size.y - 1.0)));
  float2 b = float2(q.x, size.y - 1.0);
  half4 bot = (img.eval(b + float2(-90.0, 0.0)) + img.eval(b + float2(-30.0, 0.0)) + img.eval(b + float2(30.0, 0.0)) + img.eval(b + float2(90.0, 0.0))) * 0.25;
  c = mix(c, bot, step(size.y - 1.0, q.y));
  if (drift > 0.0) {
    // the sky above its painted top (top skirt): one flat colour, the average of the top rows, blended into the painting
    // over the first 64 px so there is no seam (the first painted rows carry a light JPEG edge line: never sample above row 10)
    half4 acc = half4(0.0);
    for (int i = 0; i < 8; i++) acc += img.eval(float2(size.x * (float(i) + 0.5) / 8.0, 14.0));
    c = mix(acc / 8.0, c, smoothstep(10.0, 64.0, q.y));
  } else {
    // cut-out layers (hills, garden, house): their top rows hold a few half-transparent pixels that stretch into a dashed line
    c *= step(3.0, q.y);
  }
  return c;
}
`;
export const layerFx = Skia.RuntimeEffect.Make(layer)!;
