import { Skia } from "react-native-skia";

/**
 * Washi paper facet shader for the folded mesh (fold/mesh.ts packs the facet light into the texcoords).
 * Double-dyed vermilion washi (the back a little paler). Light from behind the visible side passes through the sheet: an orange-red glow with the
 * kozo fibres showing (paper_fibre), the colour of the dyed side always filtering it.
 */
const src = `
uniform shader front;
uniform shader back;
uniform shader fibre;
uniform float texSize;
uniform float3 sunCol;
uniform float3 amb;
uniform float glowK;
uniform float time;
uniform float toon;     // 0 = smooth photographic shading, 1 = anime cel bands
uniform float2 magic;   // awakening sweep: band position along the sheet (0..1+), strength
uniform float sky;      // 0 in the room, 1 out under the open sunset sky
uniform float3 dye;     // another paper colour for the vermilion washi (dyeK 0 = the original), gold flecks kept
uniform float dyeK;
uniform float edgeK;   // opacity of the layer-edge shadows

half4 main(float2 p) {
  float hx = floor(p.x * 0.5);
  float hy = floor(p.y * 0.5);
  // layer-edge shadow copy (fold/mesh.ts stackEdges): a faint warm-dark fringe on the layer below
  if (hy >= 4096.0) return half4(0.11, 0.025, 0.01, 1.0) * edgeK;
  float2 uv = float2(p.x - hx * 2.0, p.y - hy * 2.0) / 0.998;
  float side = floor(hx / 256.0);
  float diff = (hx - side * 256.0) / 255.0;
  float spec = floor(hy / 256.0) / 15.0;
  float trans = (hy - floor(hy / 256.0) * 256.0) / 255.0;

  // paper reads whiter than the wood under the same warm sun (keeps the cream back cream)
  half3 sunW = mix(half3(sunCol), half3(1.0, 0.97, 0.92), 0.4);
  float2 tp = uv * texSize;
  half3 F0 = front.eval(tp).rgb;
  // re-dye: keep the texture's light/dark fibre pattern (luminance over the vermilion average 0.355), skip the gold flecks
  float fl0 = smoothstep(0.30, 0.55, F0.g - F0.b * 0.5);
  half3 F = mix(F0, clamp(half3(dye) * (dot(F0, half3(0.3, 0.59, 0.11)) / 0.355), 0.0, 1.0), dyeK * (1.0 - fl0));
  float fib = fibre.eval(tp * 1.0).r;
  // double-dyed washi: the back is the same vermilion as the front (its own fibre pattern: the front texture mirrored and
  // shifted). A paler back read as a frosted veil over the folded model and striped the stacked layer edges
  half3 Fb0 = front.eval(float2(texSize - tp.x, tp.y + texSize * 0.37)).rgb;
  half3 Fb = mix(Fb0, clamp(half3(dye) * (dot(Fb0, half3(0.3, 0.59, 0.11)) / 0.355), 0.0, 1.0), dyeK);
  half3 alb = side > 0.5 ? F : Fb;

  // reflected light: soft wrap so facets turned away from the sun are not flat black
  float wrap = clamp((diff + 0.45) / 1.45, 0.0, 1.0);
  // anime cel shading: two soft-edged tone steps (shadow / mid / lit), the way background painters band light
  // (soft: a flap turning away from the sun mid-fold goes a deeper red, never a near-black wedge)
  float cel = 0.46 + 0.32 * smoothstep(0.30, 0.46, wrap) + 0.22 * smoothstep(0.62, 0.76, wrap);
  wrap = mix(wrap, cel, toon);
  // out under the sky the shade is filled by the glowing peach-violet sunset instead of the dim room
  half3 ambC = mix(half3(amb) * 0.6, half3(0.52, 0.37, 0.43), sky);
  half3 col = alb * (ambC + sunW * wrap * 1.2);
  // soft sheen of the fibres + gold flecks (bright yellow texels of the front) glinting as the facet turns into the sun
  col += half3(sunCol) * 0.10 * spec;
  float fleck = side > 0.5 ? fl0 : 0.0;
  float tw = 0.6 + 0.4 * sin(time * 7.0 + uv.x * 211.0 + uv.y * 137.0);
  col += half3(1.0, 0.85, 0.5) * fleck * (0.18 * diff + 0.7 * spec * tw);

  // transmitted light: filtered by the dyed fibres; seen from the cream side it is a warm pink-red, from the red side deep orange-red
  half3 tint = F * F * 1.6 + F * 0.35;
  float fibreK = 0.55 + 0.9 * fib;
  col += half3(sunCol) * tint * trans * glowK * fibreK;
  // flying into the low sun the whole crane is backlit: the layered washi glows like a paper lantern, fibres showing
  col += half3(sunCol) * tint * sky * (0.3 + 0.22 * (1.0 - diff)) * fibreK;

  // the crane comes alive: a band of warm light runs through the paper (diagonally across the original sheet)
  float band = (uv.x + uv.y) * 0.5;
  float mg = exp(-pow((band - magic.x) * 4.0, 2.0)) * magic.y;
  col = mix(col, col + half3(1.0, 0.86, 0.6) * 0.55, mg * (0.7 + 0.3 * fib));


  // a touch more saturation: anime reds read vivid, never brown
  float lum = dot(col, half3(0.299, 0.587, 0.114));
  col = max(half3(0.0), mix(half3(lum), col, 1.15));
  return half4(col, 1.0);
}
`;

export const paperFx = Skia.RuntimeEffect.Make(src)!;

/** soft photographic finish: vignette + warm lift around the sun + fine grain, drawn with softLight (0.5 = no change) */
const post = `
uniform float2 view;
uniform float2 sun;
uniform float time;
float hash(float2 p) { p = fract(p * float2(443.897, 441.423)); p += dot(p, p.yx + 19.19); return fract((p.x + p.y) * p.x); }
half4 main(float2 p) {
  float2 uv = p / view;
  float2 c = uv - float2(0.5, 0.5);
  c.x *= view.x / view.y;
  float vig = smoothstep(0.85, 0.25, length(c));
  float warm = exp(-length((uv - sun) * float2(view.x / view.y, 1.0)) * 2.4);
  float g = hash(p + fract(time * 13.0) * 97.0) - 0.5;
  float v = 0.5 - (1.0 - vig) * 0.26 + warm * 0.10 + g * 0.035;
  // anime grade: golden highlights at the top, cool teal-violet in the lower shade
  float top = smoothstep(0.75, 0.0, uv.y);
  half3 tint = mix(half3(-0.02, 0.0, 0.035), half3(0.05, 0.02, -0.03), top);
  return half4(half3(v) + tint + half3(warm * 0.03, 0.0, -warm * 0.02), 1.0);
}
`;
export const postFx = Skia.RuntimeEffect.Make(post)!;

/** sun visibility (sunmask.jpg) → multiply factor for the paper: lit = 1, lattice shadow = `shade` */
const mask = `
uniform shader m;
uniform float shade;
half4 main(float2 p) {
  float v = m.eval(p).r;
  return half4(half3(mix(shade, 1.0, v)), 1.0);
}
`;
export const sunMaskFx = Skia.RuntimeEffect.Make(mask)!;
