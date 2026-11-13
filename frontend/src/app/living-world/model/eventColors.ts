import type { EventType } from "./types";

/**
 * One colour per kind of event, so a flashing plot says what happened from anywhere in the
 * town: up is green, down red, dividends gold, signals violet/blue.
 */
export const EVENT_FLASH_COLOR: Record<EventType, number> = {
  price_move_up: 0x22c55e,
  price_move_down: 0xef4444,
  week52_high: 0xfacc15,
  week52_low: 0x64748b,
  volume_spike: 0x14b8a6,
  earnings_beat: 0x10b981,
  earnings_miss: 0xf97316,
  dividend_declared: 0xfde047,
  dividend_paid: 0xeab308,
  dividend_raised: 0xf59e0b,
  dividend_cut: 0xb45309,
  site_expansion: 0x0ea5e9,
  stock_split: 0x38bdf8,
  shares_received: 0x06b6d4,
  annual_report: 0x3b82f6,
  technical_signal: 0x6366f1,
  options_alert: 0xa855f7,
  geo_alert: 0x8b5cf6,
  position_added: 0x84cc16,
  position_reduced: 0xfb923c,
  position_closed: 0x94a3b8,
};

/** The colour of the latest event in the list; white when there is none. */
export function flashColorFor(types: readonly EventType[]): number {
  const last = types[types.length - 1];
  return last ? EVENT_FLASH_COLOR[last] : 0xffffff;
}