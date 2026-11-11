import type { FillerKind } from "../model/townLayout";

/**
 * Colours of the background buildings. Each kind has its own family so neighbourhoods read as
 * varied: cool coloured glass for the high-rises, warm masonry with a coloured roof for the homes.
 * Pure data and one pure pick, so the choice is deterministic and tested.
 */
export interface FillerColours {
  /** Spandrels, podiums and walls. */
  wall: number;
  /** Curtain-wall glass; also the roof/accent colour of the low buildings. */
  glass: number;
}

const PALETTES: Record<FillerKind, readonly FillerColours[]> = {
  skyscraper: [
    { wall: 0xe8eef8, glass: 0x2f98ff },
    { wall: 0xe4f0f3, glass: 0x10bfc9 },
    { wall: 0xece8f8, glass: 0x7a5cff },
    { wall: 0xe6ecfa, glass: 0x3a68f0 },
    { wall: 0xf2ecee, glass: 0xe0508f },
    { wall: 0xe9f1ee, glass: 0x19c08a },
  ],
  tower: [
    { wall: 0xf3efe6, glass: 0x1fc4aa },
    { wall: 0xf1ecf4, glass: 0x8a5cf2 },
    { wall: 0xf6ede9, glass: 0xff6f61 },
    { wall: 0xeaf0f6, glass: 0x29a8f0 },
    { wall: 0xf4f1e4, glass: 0xf2a428 },
  ],
  block: [
    { wall: 0xf3a56e, glass: 0x4f9de8 },
    { wall: 0xe8795a, glass: 0x3fb7b0 },
    { wall: 0xf5d276, glass: 0x5a86e0 },
    { wall: 0xe96d78, glass: 0x45c0d6 },
    { wall: 0xc98ae0, glass: 0x56a8f0 },
    { wall: 0x8fd3b0, glass: 0x3f8fe0 },
  ],
  house: [
    { wall: 0xf8dca8, glass: 0xe2574c },
    { wall: 0xf3b0a6, glass: 0x2f9a9a },
    { wall: 0xb0e0cc, glass: 0xf0894a },
    { wall: 0xc2cdf6, glass: 0xe0526b },
    { wall: 0xfbf0d0, glass: 0x3a82e0 },
    { wall: 0xf7c6d8, glass: 0x7a5cd8 },
  ],
  villa: [
    { wall: 0xfdf8ee, glass: 0x1fb8c8 },
    { wall: 0xfaf3e6, glass: 0xff7a59 },
    { wall: 0xf4f7fb, glass: 0x4a7df0 },
  ],
  shed: [
    { wall: 0xa9c4e6, glass: 0xff8a3d },
    { wall: 0xe0c08c, glass: 0x3d8fff },
    { wall: 0xb5d8c8, glass: 0xf2c230 },
  ],
};

/** Pick a colour pair for a building of this kind; `tone` is the layout's stable 0..1 value. */
export function fillerColours(kind: FillerKind, tone: number): FillerColours {
  const list = PALETTES[kind];
  const t = Math.min(0.999999, Math.max(0, tone));
  return list[Math.floor(t * list.length)];
}

export function fillerPalette(kind: FillerKind): readonly FillerColours[] {
  return PALETTES[kind];
}
