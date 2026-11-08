import type {
  AssetType,
  Confidence,
  Direction,
  EventCategory,
  EventType,
  Severity,
  TimeWindow,
} from "../model/types";

export const EVENT_TYPE_LABEL: Record<EventType, string> = {
  price_move_up: "Subida de precio",
  price_move_down: "Bajada de precio",
  earnings_beat: "Resultados sobre previsión",
  earnings_miss: "Resultados bajo previsión",
  dividend_declared: "Dividendo anunciado",
  dividend_paid: "Dividendo cobrado",
  site_expansion: "Nueva ampliación",
  technical_signal: "Señal técnica",
  options_alert: "Alerta de opciones",
  position_added: "Compra",
  position_reduced: "Venta parcial",
  position_closed: "Posición cerrada",
};

export const CATEGORY_LABEL: Record<EventCategory, string> = {
  market: "Mercado",
  corporate: "Corporativo",
  portfolio: "Cartera",
  technical: "Técnico",
  options: "Opciones",
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  normal: "Normal",
  important: "Importante",
  critical: "Crítico",
};

export const DIRECTION_LABEL: Record<Direction, string> = {
  positive: "Al alza",
  negative: "A la baja",
  neutral: "Neutral",
};

/** Arrows are text, not colour alone, so direction is readable without colour. */
export const DIRECTION_MARK: Record<Direction, string> = { positive: "▲", negative: "▼", neutral: "●" };

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  verified: "Verificado",
  reported: "Comunicado por la fuente",
  derived: "Derivado",
  demo: "Demostración (ficticio)",
};

export const ASSET_TYPE_LABEL: Record<AssetType, string> = {
  equity: "Acciones",
  etf: "ETF",
  fund: "Fondos",
  bond: "Bonos",
  cash: "Efectivo",
  crypto: "Cripto",
  alternative: "Alternativas",
};

export const WINDOW_LABEL: Record<TimeWindow, string> = { live: "En vivo", "24h": "24 h", "7d": "7 días" };

export const SOURCE_LABEL: Record<string, string> = {
  price_cache: "Caché de precios",
  ledger: "Libro de operaciones",
  zonas_clave: "Zonas Clave",
  options_monitor: "Monitor de opciones",
  demo_filing: "Documento de demostración",
};

export const METRIC_LABEL: Record<string, string> = {
  change_pct: "Variación (%)",
  price: "Precio",
  currency: "Divisa",
  period: "Periodo",
  actual: "Resultado",
  estimate: "Consenso",
  surprise_pct: "Sorpresa (%)",
  unit: "Unidad",
  dps: "Dividendo por acción",
  ex_date: "Fecha ex-dividendo",
  pay_date: "Fecha de pago",
  gross_eur: "Bruto (€)",
  withholding_eur: "Retención (€)",
  net_eur: "Neto (€)",
  site: "Centro",
  region: "Región",
  zone: "Zona",
  distance_pct: "Distancia (%)",
  score: "Puntuación",
  alert: "Alerta",
  strike: "Strike",
  volume_ratio: "Volumen relativo",
  quantity: "Cantidad",
  value_eur: "Importe (€)",
  account: "Cuenta",
};
