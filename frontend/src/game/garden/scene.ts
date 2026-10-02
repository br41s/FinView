/**
 * Drawing for the dividend garden. No rules live here: `sim.ts` decides what
 * exists and where, this file only turns that into ink on a canvas.
 *
 * Everything is drawn with paths rather than images, in the site's own
 * palette, so the illustration matches the rest of the landing page, follows
 * the light and dark themes, and adds nothing to download.
 */

import {
  COIN_LIFE_MS,
  groundAt,
  plantHeight,
  type Bear,
  type Coin,
  type Field,
  type Plant,
  type Point,
} from './sim';

export interface Palette {
  paper: string;
  ink: string;
  ochre: string;
  ochreDark: string;
  ochreSoft: string;
  leaf: string;
  danger: string;
}

/** Used until the page's CSS variables can be read, and in tests. */
export const DEFAULT_PALETTE: Palette = {
  paper: '#F5F1E8',
  ink: '#1F1B16',
  ochre: '#9A6B1F',
  ochreDark: '#825416',
  ochreSoft: '#D4B07A',
  leaf: '#6B7A3A',
  danger: '#9B3D2C',
};

/** A short text that floats up and fades: "+1", "¡Fuera!", "Ñam". */
export interface Effect {
  at: Point;
  text: string;
  color: keyof Palette;
  ageMs: number;
}

export const EFFECT_MS = 1100;

const TAU = Math.PI * 2;

function alpha(ctx: CanvasRenderingContext2D, value: number, draw: () => void): void {
  const previous = ctx.globalAlpha;
  ctx.globalAlpha = previous * Math.max(0, Math.min(1, value));
  draw();
  ctx.globalAlpha = previous;
}

function cloud(ctx: CanvasRenderingContext2D, x: number, y: number, s: number): void {
  ctx.beginPath();
  ctx.arc(x, y, s, 0, TAU);
  ctx.arc(x + s * 1.1, y - s * 0.45, s * 1.25, 0, TAU);
  ctx.arc(x + s * 2.4, y, s * 1.05, 0, TAU);
  ctx.rect(x, y - s * 0.1, s * 2.4, s * 1.1);
  ctx.fill();
}

/** Sky, sun, drifting clouds and the hill the garden sits on. */
export function drawBackdrop(ctx: CanvasRenderingContext2D, field: Field, palette: Palette, timeMs: number): void {
  const { width, height, unit } = field;
  ctx.clearRect(0, 0, width, height);

  // Sun, with a slow halo.
  const sun = { x: width * 0.86, y: height * 0.2 };
  const pulse = 1 + Math.sin(timeMs / 1800) * 0.04;
  ctx.fillStyle = palette.ochreSoft;
  alpha(ctx, 0.25, () => {
    ctx.beginPath();
    ctx.arc(sun.x, sun.y, unit * 9 * pulse, 0, TAU);
    ctx.fill();
  });
  alpha(ctx, 0.9, () => {
    ctx.beginPath();
    ctx.arc(sun.x, sun.y, unit * 5.2, 0, TAU);
    ctx.fill();
  });

  // Clouds drift left to right and wrap around.
  ctx.fillStyle = palette.ink;
  const span = width + unit * 40;
  [
    { y: 0.16, s: 2.6, speed: 0.9, offset: 0.1 },
    { y: 0.3, s: 1.9, speed: 0.55, offset: 0.55 },
    { y: 0.1, s: 1.5, speed: 0.7, offset: 0.8 },
  ].forEach((c) => {
    const x = ((c.offset * span + (timeMs / 1000) * c.speed * unit) % span) - unit * 20;
    alpha(ctx, 0.07, () => cloud(ctx, x, height * c.y, unit * c.s));
  });

  // A far hill, then the garden's own.
  ctx.fillStyle = palette.ochre;
  alpha(ctx, 0.1, () => {
    ctx.beginPath();
    ctx.moveTo(0, height * 0.74);
    ctx.quadraticCurveTo(width * 0.28, height * 0.52, width * 0.6, height * 0.7);
    ctx.quadraticCurveTo(width * 0.82, height * 0.8, width, height * 0.62);
    ctx.lineTo(width, height);
    ctx.lineTo(0, height);
    ctx.closePath();
    ctx.fill();
  });

  ctx.beginPath();
  ctx.moveTo(0, height);
  for (let x = 0; x <= width; x += Math.max(4, width / 80)) ctx.lineTo(x, groundAt(field, x));
  ctx.lineTo(width, groundAt(field, width));
  ctx.lineTo(width, height);
  ctx.closePath();
  ctx.fillStyle = palette.leaf;
  alpha(ctx, 0.2, () => ctx.fill());

  ctx.beginPath();
  for (let x = 0; x <= width; x += Math.max(4, width / 80)) {
    const y = groundAt(field, x);
    if (x === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.lineTo(width, groundAt(field, width));
  ctx.strokeStyle = palette.ink;
  ctx.lineWidth = Math.max(1, unit * 0.22);
  alpha(ctx, 0.45, () => ctx.stroke());

  // A mound of soil at every plot, planted or not.
  ctx.fillStyle = palette.ochreDark;
  for (const x of field.slots) {
    const y = groundAt(field, x);
    alpha(ctx, 0.35, () => {
      ctx.beginPath();
      ctx.ellipse(x, y + unit * 0.2, unit * 2.6, unit * 0.9, 0, Math.PI, TAU);
      ctx.fill();
    });
  }
}

/** Ease-out with a small overshoot, for things that pop into place. */
function pop(t: number): number {
  const x = Math.max(0, Math.min(1, t));
  const c = 1.70158;
  return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2);
}

export function drawPlant(
  ctx: CanvasRenderingContext2D,
  field: Field,
  palette: Palette,
  slot: number,
  plant: Plant,
  timeMs: number,
): void {
  const { unit } = field;
  const x = field.slots[slot];
  const base = groundAt(field, x);
  const grow = pop(plant.ageMs / 450);
  const h = plantHeight(field, plant.level) * grow;
  const sway = Math.sin(timeMs / 900 + slot * 1.7) * unit * 0.7;
  const top = { x: x + sway, y: base - h };

  // Stem.
  ctx.strokeStyle = palette.leaf;
  ctx.lineWidth = Math.max(1.5, unit * 0.55);
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(x, base);
  ctx.quadraticCurveTo(x - sway * 0.6, base - h * 0.55, top.x, top.y);
  ctx.stroke();

  // Leaves: one pair per level.
  ctx.fillStyle = palette.leaf;
  for (let i = 0; i < plant.level; i += 1) {
    const t = 0.3 + (i * 0.45) / Math.max(1, plant.level);
    const lx = x + sway * t * 0.8;
    const ly = base - h * t;
    const size = unit * (1.5 + plant.level * 0.25);
    for (const side of [-1, 1]) {
      ctx.save();
      ctx.translate(lx, ly);
      ctx.rotate(side * (0.75 + Math.sin(timeMs / 1100 + i + slot) * 0.08));
      ctx.beginPath();
      ctx.ellipse(0, -size * 0.9, size * 0.42, size, 0, 0, TAU);
      ctx.fill();
      ctx.restore();
    }
  }

  // Flower: a bud on a seedling, more and larger petals as it grows.
  const petals = plant.level === 1 ? 0 : plant.level === 2 ? 5 : 8;
  const r = unit * (0.9 + plant.level * 0.55) * grow;
  if (petals === 0) {
    ctx.fillStyle = palette.ochreSoft;
    ctx.beginPath();
    ctx.ellipse(top.x, top.y - r * 0.4, r * 0.7, r, 0, 0, TAU);
    ctx.fill();
    return;
  }
  ctx.fillStyle = palette.ochreSoft;
  for (let i = 0; i < petals; i += 1) {
    ctx.save();
    ctx.translate(top.x, top.y);
    ctx.rotate((TAU / petals) * i + timeMs / 6000);
    ctx.beginPath();
    ctx.ellipse(0, -r, r * 0.42, r * 0.95, 0, 0, TAU);
    ctx.fill();
    ctx.restore();
  }
  ctx.fillStyle = palette.ochre;
  ctx.beginPath();
  ctx.arc(top.x, top.y, r * 0.55, 0, TAU);
  ctx.fill();
}

export function drawCoin(ctx: CanvasRenderingContext2D, field: Field, palette: Palette, coin: Coin): void {
  const { unit } = field;
  const life = coin.ageMs / COIN_LIFE_MS;
  const r = unit * 2.1 * pop(coin.ageMs / 260);
  // It blinks out over its last quarter, which is the cue to hurry.
  const fade = life < 0.75 ? 1 : 1 - (life - 0.75) / 0.25;
  // Turning on its axis: the width breathes.
  const turn = 0.72 + 0.28 * Math.abs(Math.cos(coin.ageMs / 260 + coin.id));

  alpha(ctx, fade, () => {
    ctx.fillStyle = palette.ochre;
    ctx.beginPath();
    ctx.ellipse(coin.x, coin.y, r * turn, r, 0, 0, TAU);
    ctx.fill();
    ctx.strokeStyle = palette.ochreSoft;
    ctx.lineWidth = Math.max(1, unit * 0.35);
    ctx.beginPath();
    ctx.ellipse(coin.x, coin.y, r * turn * 0.72, r * 0.72, 0, 0, TAU);
    ctx.stroke();
    ctx.fillStyle = palette.paper;
    ctx.font = `600 ${Math.round(r * 1.15)}px system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('€', coin.x, coin.y + r * 0.06);
  });
}

/**
 * The bear market, as a small round bear. It waddles when it walks, opens its
 * mouth when it eats, and sweats when it runs away.
 */
export function drawBear(
  ctx: CanvasRenderingContext2D,
  field: Field,
  palette: Palette,
  bear: Bear,
  timeMs: number,
): void {
  const { unit } = field;
  const ground = groundAt(field, bear.x);
  const moving = bear.state !== 'eating';
  const pace = bear.state === 'fleeing' ? 70 : 150;
  const bob = moving ? Math.abs(Math.sin(timeMs / pace + bear.id)) * unit * 0.5 : 0;
  const leg = moving ? Math.sin(timeMs / pace + bear.id) * unit * 0.7 : 0;

  ctx.save();
  ctx.translate(bear.x, ground - bob);
  ctx.scale(bear.dir, 1);

  ctx.fillStyle = palette.ochreDark;
  // Legs.
  for (const [dx, phase] of [[-1.7, 1], [1.5, -1]] as const) {
    ctx.beginPath();
    ctx.ellipse(dx * unit + leg * phase, -unit * 0.7, unit * 0.85, unit * 1.1, 0, 0, TAU);
    ctx.fill();
  }
  // Body and head.
  ctx.beginPath();
  ctx.ellipse(0, -unit * 3, unit * 3.3, unit * 2.4, 0, 0, TAU);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(unit * 2.6, -unit * 4.6, unit * 1.75, 0, TAU);
  ctx.fill();
  // Ears.
  for (const dx of [1.6, 3.5]) {
    ctx.beginPath();
    ctx.arc(unit * dx, -unit * 6.1, unit * 0.62, 0, TAU);
    ctx.fill();
  }
  // Snout, nose, eye.
  ctx.fillStyle = palette.ochreSoft;
  ctx.beginPath();
  ctx.ellipse(unit * 3.6, -unit * 4.2, unit * 0.95, unit * 0.75, 0, 0, TAU);
  ctx.fill();
  ctx.fillStyle = palette.ink;
  ctx.beginPath();
  ctx.arc(unit * 4.25, -unit * 4.45, unit * 0.28, 0, TAU);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(unit * 2.75, -unit * 5.05, unit * 0.24, 0, TAU);
  ctx.fill();
  if (bear.state === 'eating') {
    ctx.beginPath();
    ctx.arc(unit * 3.75, -unit * 3.85, unit * 0.42, 0, Math.PI);
    ctx.fill();
  }
  if (bear.state === 'fleeing') {
    ctx.fillStyle = palette.paper;
    ctx.strokeStyle = palette.ink;
    ctx.lineWidth = Math.max(1, unit * 0.15);
    for (const [dx, dy] of [[-0.2, -6.6], [0.9, -7.2]] as const) {
      ctx.beginPath();
      ctx.ellipse(unit * dx, unit * dy, unit * 0.28, unit * 0.48, -0.5, 0, TAU);
      ctx.fill();
      ctx.stroke();
    }
  }
  ctx.restore();
}

export function drawEffect(ctx: CanvasRenderingContext2D, field: Field, palette: Palette, effect: Effect): void {
  const t = effect.ageMs / EFFECT_MS;
  if (t >= 1) return;
  ctx.fillStyle = palette[effect.color];
  ctx.font = `600 ${Math.round(field.unit * 3)}px system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  alpha(ctx, 1 - t * t, () => ctx.fillText(effect.text, effect.at.x, effect.at.y - t * field.unit * 6));
}
