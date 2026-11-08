import type { LivingWorldAsset, LivingWorldResponse } from "@/lib/types";
import { classifyArchetype } from "./archetypes";
import { ARCHETYPES, type Archetype, type AssetType, type WorldAsset } from "./types";

const ASSET_TYPES: readonly AssetType[] = ["equity", "etf", "fund", "bond", "cash", "crypto", "alternative"];

const isArchetype = (v: string | null): v is Archetype => !!v && (ARCHETYPES as readonly string[]).includes(v);
const isAssetType = (v: string): v is AssetType => (ASSET_TYPES as readonly string[]).includes(v);

/**
 * API row → the town's asset. Unknown stays null (a cost of `null` is not a cost of 0).
 * An archetype override the frontend does not know is ignored, never trusted blindly;
 * an asset type it does not know is drawn as an (unclassified) company.
 */
export function toWorldAsset(a: LivingWorldAsset): WorldAsset {
  const assetType: AssetType = isAssetType(a.asset_type) ? a.asset_type : "equity";
  const override = isArchetype(a.archetype_override) ? a.archetype_override : null;
  return {
    id: a.isin,
    isin: a.isin,
    ticker: a.ticker,
    name: a.name,
    country: a.country,
    assetType,
    sector: a.sector,
    industry: null,
    archetype: classifyArchetype({ assetType, sector: a.sector, industry: null }, override),
    classified: a.classified,
    brokers: a.brokers,
    marketValueEur: a.market_value_eur,
    weightPct: a.weight_pct,
    dayChangePct: a.day_change_pct,
    totalCostEur: a.total_cost_eur,
    unrealizedPlEur: a.unrealized_pl_eur,
    favourite: false,
  };
}

export const toWorldAssets = (res: LivingWorldResponse): WorldAsset[] => res.assets.map(toWorldAsset);

/**
 * What the 3D scene depends on. The scene is rebuilt only when this changes, so a price
 * refresh that moves a weight by a few hundredths does not tear the town down (the layout
 * is already a pure function of ids; this keeps the renderer from rebuilding for nothing).
 * Weight is rounded to 0.1 point: a building grows ~0.08 units per point at the bottom
 * of the scale, which is below what the eye can tell.
 */
export function sceneSignature(assets: readonly WorldAsset[]): string {
  return assets
    .map((a) =>
      [a.id, a.name, a.archetype, a.assetType, a.weightPct === null ? "?" : a.weightPct.toFixed(1)].join("|"),
    )
    .sort()
    .join("\n");
}
