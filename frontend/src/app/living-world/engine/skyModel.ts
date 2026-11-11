/**
 * The sky of the town as a pure function of the clock (no Three.js, so it is unit-tested).
 *
 * Keyframes are blended per channel and wrap at midnight, so dawn, noon, golden hour and night
 * are a continuous curve instead of four hard steps. The renderer smooths the result in time
 * (the clock can be set by hand), and reads `night` to turn the windows on.
 */

export type RGB = readonly [number, number, number];

export interface SkyState {
  /** Colour at the horizon; also the fog colour, so distant land melts into the sky. */
  horizon: RGB;
  /** Colour straight up. */
  zenith: RGB;
  sun: RGB;
  sunIntensity: number;
  hemiSky: RGB;
  hemiGround: RGB;
  hemiIntensity: number;
  /** 0 = broad daylight, 1 = full night. Drives lit windows and bloom. */
  night: number;
  /** Strength of the sky reflections on glass. */
  envIntensity: number;
  exposure: number;
}

const hex = (h: number): RGB => [((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255];

interface Key {
  hour: number;
  horizon: number;
  zenith: number;
  sun: number;
  sunIntensity: number;
  hemiSky: number;
  hemiGround: number;
  hemiIntensity: number;
  night: number;
  envIntensity: number;
  exposure: number;
}

const NIGHT: Omit<Key, "hour"> = {
  horizon: 0x24324f,
  zenith: 0x080d1e,
  sun: 0x93b4ea,
  sunIntensity: 0.95,
  hemiSky: 0x3a4f7c,
  hemiGround: 0x161d2e,
  hemiIntensity: 0.85,
  night: 1,
  envIntensity: 0.22,
  exposure: 1.2,
};

export const SKY_KEYS: readonly Key[] = [
  { hour: 0, ...NIGHT },
  { hour: 5, ...NIGHT },
  {
    hour: 6.5, horizon: 0xf9b99a, zenith: 0x5f86c4, sun: 0xffb27a, sunIntensity: 1.6,
    hemiSky: 0xe0e4f6, hemiGround: 0xb2c99a, hemiIntensity: 1.15, night: 0.6, envIntensity: 0.6, exposure: 1.12,
  },
  {
    hour: 8, horizon: 0xc2e4f6, zenith: 0x4a9be4, sun: 0xffe5c0, sunIntensity: 2.1,
    hemiSky: 0xe3f1ff, hemiGround: 0xb0d19e, hemiIntensity: 1.12, night: 0.05, envIntensity: 0.9, exposure: 1.1,
  },
  {
    hour: 12, horizon: 0xd2ecfa, zenith: 0x2f87e0, sun: 0xfff6e6, sunIntensity: 2.3,
    hemiSky: 0xe0f0ff, hemiGround: 0xb8d6a4, hemiIntensity: 1.2, night: 0, envIntensity: 1, exposure: 1.1,
  },
  {
    hour: 17, horizon: 0xdbeef6, zenith: 0x3b8de0, sun: 0xffeccc, sunIntensity: 2.15,
    hemiSky: 0xe4f0fb, hemiGround: 0xb6cfa0, hemiIntensity: 1.15, night: 0, envIntensity: 0.95, exposure: 1.1,
  },
  {
    hour: 19, horizon: 0xffb87c, zenith: 0x5a80c8, sun: 0xffb272, sunIntensity: 2.1,
    hemiSky: 0xffe2c4, hemiGround: 0xa4bc92, hemiIntensity: 1.2, night: 0.3, envIntensity: 0.65, exposure: 1.12,
  },
  {
    hour: 20.5, horizon: 0xcf7684, zenith: 0x2c3b7c, sun: 0xff8a5c, sunIntensity: 1.1,
    hemiSky: 0x8582b0, hemiGround: 0x2e3446, hemiIntensity: 0.85, night: 0.85, envIntensity: 0.35, exposure: 1.15,
  },
  { hour: 22, ...NIGHT },
  { hour: 24, ...NIGHT },
];

const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const mixRgb = (a: RGB, b: RGB, t: number): RGB => [mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)];

/** The sky at a clock hour (any real number; it wraps into [0, 24)). */
export function skyAt(hourIn: number): SkyState {
  const hour = ((hourIn % 24) + 24) % 24;
  let i = 0;
  while (i < SKY_KEYS.length - 2 && hour >= SKY_KEYS[i + 1].hour) i++;
  const a = SKY_KEYS[i];
  const b = SKY_KEYS[i + 1];
  const raw = (hour - a.hour) / (b.hour - a.hour);
  const t = raw * raw * (3 - 2 * raw);
  return {
    horizon: mixRgb(hex(a.horizon), hex(b.horizon), t),
    zenith: mixRgb(hex(a.zenith), hex(b.zenith), t),
    sun: mixRgb(hex(a.sun), hex(b.sun), t),
    sunIntensity: mix(a.sunIntensity, b.sunIntensity, t),
    hemiSky: mixRgb(hex(a.hemiSky), hex(b.hemiSky), t),
    hemiGround: mixRgb(hex(a.hemiGround), hex(b.hemiGround), t),
    hemiIntensity: mix(a.hemiIntensity, b.hemiIntensity, t),
    night: mix(a.night, b.night, t),
    envIntensity: mix(a.envIntensity, b.envIntensity, t),
    exposure: mix(a.exposure, b.exposure, t),
  };
}

/**
 * Sun (and, at night, moon) direction scaled to `radius`. It keeps a minimum elevation so shadows
 * stay long and soft but never go flat, and mirrors at night so the town is lit from a side.
 */
export function sunPosition(hour: number, radius: number): [number, number, number] {
  const phase = ((hour - 6) / 24) * Math.PI * 2;
  const elevation = Math.sin(phase);
  return [
    radius * Math.cos(phase) * 0.65,
    Math.max(radius * 0.3, radius * Math.abs(elevation) * 1.15),
    radius * Math.sin(phase) * 0.5,
  ];
}
