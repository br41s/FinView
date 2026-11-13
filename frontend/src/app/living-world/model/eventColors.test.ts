import { describe, expect, it } from "vitest";
import { EVENT_FLASH_COLOR, flashColorFor } from "./eventColors";
import { EVENT_TYPE_CATEGORY } from "./types";
import type { EventType } from "./types";

describe("event flash colours", () => {
  it("gives every kind of event a colour", () => {
    for (const type of Object.keys(EVENT_TYPE_CATEGORY) as EventType[]) {
      expect(EVENT_FLASH_COLOR[type], type).toBeTypeOf("number");
    }
  });

  it("keeps up green, down red and dividends apart", () => {
    expect(EVENT_FLASH_COLOR.price_move_up).not.toBe(EVENT_FLASH_COLOR.price_move_down);
    expect(EVENT_FLASH_COLOR.dividend_paid).not.toBe(EVENT_FLASH_COLOR.price_move_up);
    expect(EVENT_FLASH_COLOR.dividend_paid).not.toBe(EVENT_FLASH_COLOR.price_move_down);
  });

  it("uses the latest event's colour, or white when there is none", () => {
    expect(flashColorFor(["price_move_down", "price_move_up"])).toBe(EVENT_FLASH_COLOR.price_move_up);
    expect(flashColorFor(["dividend_paid"])).toBe(EVENT_FLASH_COLOR.dividend_paid);
    expect(flashColorFor([])).toBe(0xffffff);
  });
});