/**
 * Quality presets (spec §11). The renderer reads these; nothing else decides cost.
 * Antialiasing is fixed when the WebGL context is created, everything else can change live.
 */
export type Quality = "low" | "medium" | "high";

/** Post-processing of one tier. `null` = the scene is drawn straight to the canvas. */
export interface PostSettings {
  /** Ambient occlusion at half resolution (N8AO upsamples it depth-aware). */
  aoHalfRes: boolean;
  aoSamples: number;
  aoDenoiseSamples: number;
  /** Soft glow of lit windows at night. */
  bloom: boolean;
  /** SMAA after tone mapping; the post chain renders to float targets, which have no MSAA. */
  smaa: boolean;
}

export interface QualitySettings {
  maxPixelRatio: number;
  shadows: boolean;
  shadowMapSize: number;
  post: PostSettings | null;
  /** Ambient inhabitants across the whole town. */
  maxAgents: number;
  /** Decorative trees. */
  trees: number;
  /** Share of the generic buildings (homes, offices) that are drawn. */
  fillerDensity: number;
  /** Frame cap in ms; the loop skips frames that arrive earlier. 0 = uncapped. */
  minFrameMs: number;
}

export const QUALITY: Record<Quality, QualitySettings> = {
  low: { maxPixelRatio: 1, shadows: false, shadowMapSize: 0, post: null, maxAgents: 80, trees: 90, fillerDensity: 0.45, minFrameMs: 33 },
  medium: {
    maxPixelRatio: 1.5, shadows: true, shadowMapSize: 1024,
    post: { aoHalfRes: true, aoSamples: 8, aoDenoiseSamples: 4, bloom: false, smaa: true },
    maxAgents: 220, trees: 260, fillerDensity: 1, minFrameMs: 0,
  },
  high: {
    maxPixelRatio: 2, shadows: true, shadowMapSize: 2048,
    post: { aoHalfRes: true, aoSamples: 16, aoDenoiseSamples: 8, bloom: true, smaa: true },
    maxAgents: 420, trees: 520, fillerDensity: 1, minFrameMs: 0,
  },
};

export const QUALITY_LABEL: Record<Quality, string> = { low: "Baja", medium: "Media", high: "Alta" };
