import { useEffect, useRef } from "react";

/*
  A scene drawn in monospace glyphs, in two WebGL2 passes:
  1. "temple": raymarch a small portico at one sample per character cell, writing
     ink density and a material id. "text": rasterize a word into the same grid on a 2D canvas.
  2. Pick a glyph from a density ramp for each cell and draw it from a glyph atlas.
  The cursor scrambles nearby glyphs, a slow scan line "reads" the field, and the first
  frames decode out of noise. Nothing runs while the canvas is offscreen.
*/

// Density ramp, then edge glyphs: | / \\ (the ramp's "-" doubles as the horizontal edge).
const RAMP = " .:-=+*#%@";
const GLYPHS = RAMP + "|/\\";

const VERT = `#version 300 es
in vec2 aPos;
out vec2 vUv;
void main() { vUv = aPos * 0.5 + 0.5; gl_Position = vec4(aPos, 0.0, 1.0); }`;

const SCENE = `#version 300 es
precision highp float;
uniform vec2 uCells;
uniform vec2 uCellPx;
uniform float uYaw;
uniform float uPitch;
uniform float uZoom;
out vec4 o;

float sdBox(vec3 p, vec3 b) { vec3 q = abs(p) - b; return length(max(q, 0.0)) + min(max(q.x, max(q.y, q.z)), 0.0); }
float sdCyl(vec3 p, float r, float h) { vec2 d = abs(vec2(length(p.xz), p.y)) - vec2(r, h); return min(max(d.x, d.y), 0.0) + length(max(d, 0.0)); }
float sdCylX(vec3 p, float r, float h) { vec2 d = abs(vec2(length(p.yz), p.x)) - vec2(r, h); return min(max(d.x, d.y), 0.0) + length(max(d, 0.0)); }

const float TOP = 0.6;     // stylobate top
const float CAP = 3.6;     // column top

float column(vec3 q, float top) {
  float t = clamp((q.y - TOP) / (CAP - TOP), 0.0, 1.0);
  float a = atan(q.z, q.x);
  float r = 0.27 - 0.035 * t + 0.012 * cos(a * 20.0);
  float shaft = max(length(q.xz) - r, abs(q.y - (TOP + top) * 0.5) - (top - TOP) * 0.5);
  return shaft * 0.8;
}

vec2 map(vec3 p) {
  float stone = 1e9;
  stone = min(stone, sdBox(p - vec3(0.0, 0.1, 0.0), vec3(3.7, 0.1, 2.0)));
  stone = min(stone, sdBox(p - vec3(0.0, 0.3, 0.0), vec3(3.45, 0.1, 1.75)));
  stone = min(stone, sdBox(p - vec3(0.0, 0.5, 0.0), vec3(3.2, 0.1, 1.5)));

  // two rows of six columns
  float cx = clamp(floor(p.x) + 0.5, -2.5, 2.5);
  vec3 q = vec3(p.x - cx, p.y, abs(p.z) - 0.95);
  bool broken = cx > 1.0 && cx < 2.0 && p.z > 0.0;
  float broke = 1e9;
  if (broken) {
    float a = atan(q.z, q.x);
    float top = 1.85 + 0.16 * sin(a * 3.0 + 1.0) + 0.07 * sin(a * 7.0);
    broke = column(q, top);
    broke = min(broke, sdCyl(q - vec3(0.0, 0.66, 0.0), 0.34, 0.06));
  } else {
    stone = min(stone, column(q, CAP));
    stone = min(stone, sdCyl(q - vec3(0.0, 0.66, 0.0), 0.34, 0.06));
    stone = min(stone, sdCyl(q - vec3(0.0, CAP - 0.04, 0.0), 0.33, 0.06));
    stone = min(stone, sdBox(q - vec3(0.0, CAP + 0.08, 0.0), vec3(0.38, 0.07, 0.38)));
  }

  // entablature, cornice, pediment
  stone = min(stone, sdBox(p - vec3(0.0, 4.05, 0.0), vec3(3.05, 0.3, 1.3)));
  stone = min(stone, sdBox(p - vec3(0.0, 4.42, 0.0), vec3(3.22, 0.08, 1.45)));
  vec3 g = p - vec3(0.0, 4.5, 0.0);
  float s = 0.27;
  float gable = max(max(-g.y, (g.y + abs(g.x) * s - 0.86) / sqrt(1.0 + s * s)), abs(g.z) - 1.38);
  stone = min(stone, gable);

  // the fallen drum
  float c = cos(0.35), sn = sin(0.35);
  vec3 d = p - vec3(1.9, 0.27, 2.75);
  d.xz = mat2(c, -sn, sn, c) * d.xz;
  broke = min(broke, sdCylX(d, 0.26, 0.42));
  vec3 d2 = p - vec3(2.85, 0.2, 2.45);
  broke = min(broke, sdBox(d2, vec3(0.2, 0.2, 0.17)) - 0.02);

  float ground = p.y;
  vec2 r = vec2(stone, 1.0);
  if (broke < r.x) r = vec2(broke, 2.0);
  if (ground < r.x) r = vec2(ground, 3.0);
  return r;
}

vec3 normal(vec3 p) {
  const vec2 k = vec2(1.0, -1.0);
  const float e = 0.002;
  return normalize(k.xyy * map(p + k.xyy * e).x + k.yyx * map(p + k.yyx * e).x +
                   k.yxy * map(p + k.yxy * e).x + k.xxx * map(p + k.xxx * e).x);
}

float shadow(vec3 ro, vec3 rd) {
  float res = 1.0, t = 0.05;
  for (int i = 0; i < 40; i++) {
    float h = map(ro + rd * t).x;
    res = min(res, 9.0 * h / t);
    t += clamp(h, 0.03, 0.4);
    if (res < 0.01 || t > 14.0) break;
  }
  return clamp(res, 0.0, 1.0);
}

float occlusion(vec3 p, vec3 n) {
  float occ = 0.0, w = 1.0;
  for (int i = 1; i <= 5; i++) {
    float h = 0.06 * float(i);
    occ += (h - map(p + n * h).x) * w;
    w *= 0.7;
  }
  return clamp(1.0 - 2.2 * occ, 0.0, 1.0);
}

void main() {
  vec2 cell = floor(gl_FragCoord.xy);
  vec2 size = uCells * uCellPx;
  vec2 uv = ((cell + 0.5) * uCellPx - 0.5 * size) / size.y;

  vec3 ta = vec3(0.0, 2.25, 0.5);
  vec3 ro = ta + uZoom * vec3(sin(uYaw) * cos(uPitch), sin(uPitch), cos(uYaw) * cos(uPitch));
  vec3 ww = normalize(ta - ro);
  vec3 uu = normalize(cross(ww, vec3(0.0, 1.0, 0.0)));
  vec3 vv = cross(uu, ww);
  vec3 rd = normalize(uv.x * uu + uv.y * vv + 2.0 * ww);

  float t = 0.0;
  vec2 h = vec2(0.0);
  bool hit = false;
  for (int i = 0; i < 110; i++) {
    h = map(ro + rd * t);
    if (h.x < 0.0015 * t) { hit = true; break; }
    t += h.x;
    if (t > 45.0) break;
  }
  if (!hit) { o = vec4(0.0, 0.0, 1.0, 1.0); return; }
  float depth = clamp(t / 45.0, 0.0, 1.0);

  vec3 p = ro + rd * t;
  vec3 n = normal(p);
  vec3 L = normalize(vec3(-0.55, 0.85, 0.6));
  float sh = shadow(p + n * 0.01, L);
  float ao = occlusion(p, n);

  if (h.y > 2.5) {
    // ground: only cast shadow and contact occlusion leave ink
    float fade = smoothstep(9.5, 3.5, length(p.xz - vec2(0.3, 0.6)));
    float ink = (1.0 - sh) * 0.5 + (1.0 - ao) * 0.45;
    o = vec4(clamp(ink, 0.0, 1.0) * fade, 0.75, depth, 1.0);
    return;
  }
  float dif = clamp(dot(n, L), 0.0, 1.0) * sh;
  float light = (0.34 + 0.16 * n.y) * ao + 0.72 * dif;
  float ink = 0.3 + 0.7 * clamp(1.0 - light, 0.0, 1.0);
  o = vec4(ink, h.y * 0.25, depth, 1.0);
}`;

const ASCII = `#version 300 es
precision highp float;
in vec2 vUv;
uniform sampler2D uScene;
uniform sampler2D uAtlas;
uniform vec2 uCells;
uniform vec2 uGrid;
uniform float uGlyphs;
uniform float uRamp;
uniform float uTime;
uniform float uIntro;
uniform float uMotion;
uniform float uText;
uniform vec2 uMouse;
uniform vec3 uInk;
uniform vec3 uAlt;
uniform vec3 uMute;
uniform vec3 uRead;
out vec4 o;

float hash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }

void main() {
  vec2 p = vUv * uCells;
  vec2 cell = floor(p);
  vec2 f = fract(p);
  vec4 s = texture(uScene, (cell + 0.5) / uGrid);
  float d = s.r;
  float mat = floor(s.g * 4.0 + 0.5);
  float h = hash(cell);
  float alpha = 1.0;

  if (uText > 0.5) {
    if (d > 0.0) {
      float wave = 0.62 + 0.38 * sin(uTime * 1.1 * uMotion + cell.x * 0.16 - cell.y * 0.35);
      d = mix(0.35, 1.0, d * wave);
    } else if (h < 0.07) {
      d = 0.12; mat = 1.0; alpha = 0.45;
    }
  }

  float idx = clamp(floor(d * (uRamp - 1.0) + 0.5), 0.0, uRamp - 1.0);
  if (mat > 0.5 && mat < 2.5 && d > 0.04) idx = max(idx, 1.0);

  // edges: where depth jumps between neighbouring cells, draw the outline's direction
  if (uText < 0.5 && mat > 0.5 && mat < 2.5) {
    float gx = 0.0, gy = 0.0;
    for (int j = -1; j <= 1; j++) for (int i = -1; i <= 1; i++) {
      float z = texture(uScene, (cell + vec2(i, j) + 0.5) / uGrid).b;
      float w = (i == 0 || j == 0) ? 2.0 : 1.0;
      gx += float(i) * w * z;
      gy += float(j) * w * z;
    }
    if (length(vec2(gx, gy)) > 0.05) {
      float ax = abs(gx), ay = abs(gy);
      idx = ax > 2.2 * ay ? 10.0 : (ay > 2.2 * ax ? 3.0 : (gx * gy > 0.0 ? 12.0 : 11.0));
    }
  }
  vec3 col = mat > 2.5 ? uMute : (mat > 1.5 ? uAlt : uInk);

  // cursor: scramble and darken glyphs near the pointer
  vec2 m = (cell + 0.5 - uMouse) * vec2(1.0, 1.75);
  float near = smoothstep(9.0, 2.0, length(m)) * uMotion;
  // scan line: a slow diagonal pass that "reads" the field
  float diag = cell.x / uCells.x * 0.7 + (1.0 - cell.y / uCells.y) * 0.3;
  float pos = fract(uTime / 9.0) * 1.6 - 0.3;
  float band = smoothstep(0.035, 0.0, abs(diag - pos)) * uMotion * (1.0 - uText);
  float tick = floor(uTime * 14.0);
  if (idx > 0.0 && (hash(cell + tick) < near * 0.85 || hash(cell - tick) < band * 0.9)) {
    idx = 1.0 + floor(hash(cell * 1.7 + tick) * (uRamp - 1.0));
    col = mix(col, uRead, max(near, band));
  }
  // intro: cells resolve out of noise in random order
  if (h > uIntro) {
    if (idx > 0.0) { idx = 1.0 + floor(hash(cell + tick * 0.5) * (uRamp - 1.0)); alpha *= 0.35; }
  }

  vec2 auv = vec2((idx + f.x) / uGlyphs, 1.0 - f.y);
  float a = texture(uAtlas, auv).r * alpha;
  o = vec4(col * a, a);
}`;

function hexToRgb(value: string): [number, number, number] {
  const hex = value.trim().replace("#", "");
  const full = hex.length === 3 ? [...hex].map((c) => c + c).join("") : hex;
  const n = Number.parseInt(full, 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

function compile(gl: WebGL2RenderingContext, vs: string, fs: string) {
  const prog = gl.createProgram()!;
  for (const [type, src] of [
    [gl.VERTEX_SHADER, vs],
    [gl.FRAGMENT_SHADER, fs],
  ] as const) {
    const sh = gl.createShader(type)!;
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh) ?? "shader");
    gl.attachShader(prog, sh);
  }
  gl.bindAttribLocation(prog, 0, "aPos");
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) ?? "link");
  return prog;
}

type Uniforms = Record<string, WebGLUniformLocation | null>;
const uniforms = (gl: WebGL2RenderingContext, prog: WebGLProgram, names: string[]): Uniforms =>
  Object.fromEntries(names.map((n) => [n, gl.getUniformLocation(prog, n)]));

export interface GlyphFieldProps {
  mode: "temple" | "text";
  text?: string;
  /** CSS custom properties (hex) for the main ink, the broken-column ink, ground ink and the scan color. */
  ink?: string;
  alt?: string;
  mute?: string;
  read?: string;
  cell?: [number, number];
  label: string;
  className?: string;
}

export function GlyphField({
  mode,
  text = "upheld",
  ink = "--accent-ink",
  alt = "--bad",
  mute = "--ink-3",
  read = "--ink",
  cell = [7, 12],
  label,
  className = "",
}: GlyphFieldProps) {
  const host = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [cw, ch] = cell;

  useEffect(() => {
    const el = host.current!;
    const canvas = canvasRef.current!;
    const gl = canvas.getContext("webgl2", { alpha: true, antialias: false, premultipliedAlpha: true });
    if (!gl) {
      el.dataset.fallback = "true";
      return;
    }
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    let disposed = false;
    let raf = 0;
    let visible = false;
    let start = performance.now();
    let cols = 1;
    let rows = 1;
    let cssW = 1;
    let cssH = 1;
    let dpr = 1;
    const mouse = { x: -999, y: -999 };
    const orbit = { offset: 0, vel: 0, dragging: false, lastX: 0 };
    let colors = { ink: [0, 0, 1], alt: [1, 0, 0], mute: [0.5, 0.5, 0.5], read: [0, 0, 0] } as Record<string, number[]>;

    let sceneProg: WebGLProgram | null = null;
    let asciiProg: WebGLProgram;
    try {
      if (mode === "temple") sceneProg = compile(gl, VERT, SCENE);
      asciiProg = compile(gl, VERT, ASCII);
    } catch (err) {
      console.error(err);
      el.dataset.fallback = "true";
      return;
    }
    const su = sceneProg ? uniforms(gl, sceneProg, ["uCells", "uCellPx", "uYaw", "uPitch", "uZoom"]) : {};
    const au = uniforms(gl, asciiProg, [
      "uScene", "uAtlas", "uCells", "uGrid", "uGlyphs", "uRamp", "uTime", "uIntro", "uMotion", "uText", "uMouse", "uInk", "uAlt", "uMute", "uRead",
    ]);

    const vao = gl.createVertexArray();
    gl.bindVertexArray(vao);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

    const sceneTex = gl.createTexture();
    const atlasTex = gl.createTexture();
    const fbo = gl.createFramebuffer();
    const setTex = (tex: WebGLTexture | null, filter: number) => {
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    };

    const buildAtlas = () => {
      const w = Math.round(cw * dpr);
      const h = Math.round(ch * dpr);
      const c = document.createElement("canvas");
      c.width = w * GLYPHS.length;
      c.height = h;
      const ctx = c.getContext("2d")!;
      ctx.fillStyle = "#fff";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.font = `500 ${Math.round(h * 0.82)}px "Geist Mono Variable", ui-monospace, monospace`;
      [...GLYPHS].forEach((g, i) => ctx.fillText(g, i * w + w / 2, h * 0.54));
      setTex(atlasTex, gl.LINEAR);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c);
    };

    const buildText = () => {
      // rasterize the word at one pixel per cell; cells are ~1.7x taller than wide
      const c = document.createElement("canvas");
      c.width = cols;
      c.height = rows;
      const ctx = c.getContext("2d")!;
      ctx.save();
      ctx.scale(1, cw / ch);
      const tall = (rows * ch) / cw;
      const size = Math.min(tall * 0.9, (cols / text.length) * 1.55);
      ctx.font = `800 ${size}px "Mona Sans Variable", system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "alphabetic";
      ctx.fillStyle = "#fff";
      // ascenders ~0.75em, descenders ~0.22em: centre that span vertically
      ctx.fillText(text, cols / 2, (tall - 0.97 * size) / 2 + 0.75 * size);
      ctx.restore();
      const src = ctx.getImageData(0, 0, cols, rows).data;
      const data = new Uint8Array(cols * rows * 4);
      for (let y = 0; y < rows; y++) {
        for (let x = 0; x < cols; x++) {
          const a = src[(y * cols + x) * 4 + 3];
          const o = ((rows - 1 - y) * cols + x) * 4; // flip so row 0 is the bottom
          data[o] = a;
          data[o + 1] = a > 0 ? 64 : 0;
          data[o + 3] = 255;
        }
      }
      setTex(sceneTex, gl.NEAREST);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, cols, rows, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
    };

    const readColors = () => {
      const cs = getComputedStyle(document.documentElement);
      colors = {
        ink: hexToRgb(cs.getPropertyValue(ink)),
        alt: hexToRgb(cs.getPropertyValue(alt)),
        mute: hexToRgb(cs.getPropertyValue(mute)),
        read: hexToRgb(cs.getPropertyValue(read)),
      };
    };

    const resize = () => {
      const r = el.getBoundingClientRect();
      cssW = Math.max(1, r.width);
      cssH = Math.max(1, r.height);
      const nextDpr = Math.min(window.devicePixelRatio || 1, 2);
      const dprChanged = nextDpr !== dpr;
      dpr = nextDpr;
      canvas.width = Math.round(cssW * dpr);
      canvas.height = Math.round(cssH * dpr);
      cols = Math.ceil(cssW / cw);
      rows = Math.ceil(cssH / ch);
      if (dprChanged || !atlasReady) buildAtlas();
      atlasReady = true;
      if (mode === "text") buildText();
      else {
        setTex(sceneTex, gl.NEAREST);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, cols, rows, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
        gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
        gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, sceneTex, 0);
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      }
    };
    let atlasReady = false;

    const draw = (now: number) => {
      const still = reduce.matches;
      const t = still ? 0 : (now - start) / 1000;
      const intro = still ? 1.1 : Math.min(1.1, Math.pow(t / 1.8, 0.8) * 1.1);

      if (!orbit.dragging) {
        orbit.offset += orbit.vel;
        orbit.vel *= 0.93;
      }
      if (sceneProg) {
        gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
        gl.viewport(0, 0, cols, rows);
        gl.useProgram(sceneProg);
        gl.uniform2f(su.uCells, cssW / cw, cssH / ch);
        gl.uniform2f(su.uCellPx, cw, ch);
        gl.uniform1f(su.uYaw, -0.38 + 0.26 * Math.sin(t * 0.12) + orbit.offset);
        gl.uniform1f(su.uPitch, 0.24);
        gl.uniform1f(su.uZoom, cssW / cssH < 1 ? 25 : 17);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      }

      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(asciiProg);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, sceneTex);
      gl.uniform1i(au.uScene, 0);
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, atlasTex);
      gl.uniform1i(au.uAtlas, 1);
      gl.uniform2f(au.uCells, cssW / cw, cssH / ch);
      gl.uniform2f(au.uGrid, cols, rows);
      gl.uniform1f(au.uGlyphs, GLYPHS.length);
      gl.uniform1f(au.uRamp, RAMP.length);
      gl.uniform1f(au.uTime, t);
      gl.uniform1f(au.uIntro, intro);
      gl.uniform1f(au.uMotion, still ? 0 : 1);
      gl.uniform1f(au.uText, mode === "text" ? 1 : 0);
      gl.uniform2f(au.uMouse, mouse.x, mouse.y);
      gl.uniform3fv(au.uInk, colors.ink);
      gl.uniform3fv(au.uAlt, colors.alt);
      gl.uniform3fv(au.uMute, colors.mute);
      gl.uniform3fv(au.uRead, colors.read);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    const loop = (now: number) => {
      raf = 0;
      if (disposed) return;
      draw(now);
      if (visible && !document.hidden && !reduce.matches) raf = requestAnimationFrame(loop);
    };
    const kick = () => {
      if (!raf && !disposed) raf = requestAnimationFrame(loop);
    };

    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      mouse.x = (e.clientX - r.left) / cw;
      mouse.y = (r.bottom - e.clientY) / ch;
      if (orbit.dragging && mode === "temple") {
        const dx = e.clientX - orbit.lastX;
        orbit.lastX = e.clientX;
        orbit.offset += dx * 0.006;
        orbit.vel = dx * 0.006;
      }
    };
    const onLeave = () => {
      mouse.x = mouse.y = -999;
    };
    const onDown = (e: PointerEvent) => {
      if (mode !== "temple") return;
      orbit.dragging = true;
      orbit.lastX = e.clientX;
      el.setPointerCapture(e.pointerId);
    };
    const onUp = () => {
      orbit.dragging = false;
    };
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onUp);

    const io = new IntersectionObserver(([entry]) => {
      const was = visible;
      visible = entry.isIntersecting;
      if (visible && !was && mode === "text") start = performance.now();
      if (visible) kick();
    });
    const ro = new ResizeObserver(() => {
      resize();
      kick();
    });
    const theme = new MutationObserver(() => {
      readColors();
      kick();
    });
    const onVis = () => kick();

    readColors();
    document.fonts.ready.then(() => {
      if (disposed) return;
      atlasReady = false;
      resize();
      start = performance.now();
      io.observe(el);
      ro.observe(el);
      theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
      document.addEventListener("visibilitychange", onVis);
      reduce.addEventListener("change", kick);
      kick();
    });

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      io.disconnect();
      ro.disconnect();
      theme.disconnect();
      document.removeEventListener("visibilitychange", onVis);
      reduce.removeEventListener("change", kick);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointercancel", onUp);
      // Free what this run made but keep the context: StrictMode remounts onto the same canvas.
      gl.deleteTexture(sceneTex);
      gl.deleteTexture(atlasTex);
      gl.deleteFramebuffer(fbo);
      gl.deleteBuffer(buf);
      gl.deleteVertexArray(vao);
      if (sceneProg) gl.deleteProgram(sceneProg);
      gl.deleteProgram(asciiProg);
    };
  }, [mode, text, ink, alt, mute, read, cw, ch]);

  return (
    <div
      ref={host}
      role="img"
      aria-label={label}
      className={`select-none ${mode === "temple" ? "cursor-grab touch-pan-y active:cursor-grabbing" : ""} ${className}`}
    >
      <canvas ref={canvasRef} className="absolute inset-0 size-full" />
    </div>
  );
}
