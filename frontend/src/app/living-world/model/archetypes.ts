import type { Archetype, AssetType, DistrictId } from "./types";

/** District each archetype lives in (spec §8.1). Broker never decides a district. */
export const ARCHETYPE_DISTRICT: Record<Archetype, DistrictId> = {
  retail: "retail",
  consumer: "retail",
  realestate: "retail",
  tech: "tech",
  semis: "tech",
  telecom: "tech",
  energy: "industry",
  mining: "industry",
  utilities: "industry",
  banking: "finance",
  health: "health",
  fund: "funds",
  crypto: "funds",
  cash: "treasury",
};

export const ARCHETYPE_LABEL: Record<Archetype, string> = {
  retail: "Comercio y moda",
  consumer: "Consumo y alimentación",
  realestate: "Inmobiliario",
  tech: "Tecnología",
  semis: "Semiconductores",
  telecom: "Telecomunicaciones",
  energy: "Energía",
  mining: "Minería e industria",
  utilities: "Servicios y renovables",
  banking: "Banca y finanzas",
  health: "Salud y farmacia",
  fund: "Fondo o ETF",
  crypto: "Cripto",
  cash: "Efectivo",
};

export const DISTRICT_LABEL: Record<DistrictId, string> = {
  retail: "Calle comercial y de consumo",
  tech: "Campus tecnológico y de comunicaciones",
  industry: "Industria, materiales y energía",
  finance: "Plaza financiera",
  health: "Barrio sanitario e investigador",
  funds: "Pabellón de fondos",
  treasury: "Tesorería",
};

/** Industry keywords win over the broad sector (a chip maker is "Technology" to Yahoo). */
const INDUSTRY_RULES: ReadonlyArray<readonly [RegExp, Archetype]> = [
  [/semiconductor/i, "semis"],
  [/apparel|retail|department store|specialty retail/i, "retail"],
  [/oil|gas|petroleum|refin/i, "energy"],
  [/mining|gold|copper|steel|aluminum|metals/i, "mining"],
  [/reit|real estate/i, "realestate"],
  [/telecom/i, "telecom"],
  [/bank|insurance|capital markets|asset management/i, "banking"],
  [/drug|biotech|pharma|medical|health/i, "health"],
  [/beverage|food|packaged|household|tobacco/i, "consumer"],
  [/utilit|renewable|solar|wind/i, "utilities"],
];

/**
 * Sector as Yahoo spells it. Industrials has no archetype of its own in the spec,
 * so it takes heavy industry (mining) — a deliberate, documented approximation.
 */
const SECTOR_RULES: ReadonlyArray<readonly [RegExp, Archetype]> = [
  [/technology/i, "tech"],
  [/communication/i, "telecom"],
  [/energy/i, "energy"],
  [/basic materials|materials/i, "mining"],
  [/industrial/i, "mining"],
  [/financial/i, "banking"],
  [/health/i, "health"],
  [/consumer cyclical/i, "retail"],
  [/consumer defensive|consumer staples/i, "consumer"],
  [/utilit/i, "utilities"],
  [/real estate/i, "realestate"],
];

/** Fallback for an operating company whose sector is unknown. */
const DEFAULT_COMPANY_ARCHETYPE: Archetype = "consumer";

export interface ClassifyInput {
  assetType: AssetType;
  sector: string | null;
  industry: string | null;
}

/**
 * Deterministic archetype. Order: asset type (fund/cash/crypto are never operating
 * companies) → explicit override → industry → sector → default.
 * An ETF is always the fund pavilion: it must not be drawn as an operating firm.
 */
export function classifyArchetype(
  input: ClassifyInput,
  override?: Archetype | null,
): Archetype {
  if (input.assetType === "etf" || input.assetType === "fund" || input.assetType === "bond") {
    return "fund";
  }
  if (input.assetType === "cash") return "cash";
  if (input.assetType === "crypto") return "crypto";
  if (override) return override;
  if (input.industry) {
    for (const [re, a] of INDUSTRY_RULES) if (re.test(input.industry)) return a;
  }
  if (input.sector) {
    for (const [re, a] of SECTOR_RULES) if (re.test(input.sector)) return a;
  }
  return DEFAULT_COMPANY_ARCHETYPE;
}
