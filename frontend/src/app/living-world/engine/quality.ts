/**
 * Quality presets (spec §11). The renderer reads these; nothing else decides cost.
 * Antialiasing is fixed when the WebGL context is created, everything else can change live.
 */
export type Quality = "low" | "medium" | "high";

export interface QualitySettings {
  maxPixelRatio: number;
  shadows: boolean;
  shadowMapSize: number;
  /** Ambient inhabitants across the whole town. */
  maxAgents: number;
  /** Decorative trees. */
  trees: number;
  /** Frame cap in ms; the loop skips frames that arrive earlier. 0 = uncapped. */
  minFrameMs: number;
}

export const QUALITY: Record<Quality, QualitySettings> = {
  low: { maxPixelRatio: 1, shadows: false, shadowMapSize: 0, maxAgents: 80, trees: 90, minFrameMs: 33 },
  medium: { maxPixelRatio: 1.5, shadows: true, shadowMapSize: 1024, maxAgents: 220, trees: 260, minFrameMs: 0 },
  high: { maxPixelRatio: 2, shadows: true, shadowMapSize: 2048, maxAgents: 420, trees: 520, minFrameMs: 0 },
};

export const QUALITY_LABEL: Record<Quality, string> = { low: "Baja", medium: "Media", high: "Alta" };
