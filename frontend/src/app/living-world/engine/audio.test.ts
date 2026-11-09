import { describe, expect, it } from "vitest";
import { createSoundEngine } from "./audio";

describe("createSoundEngine", () => {
  it("initializes in muted state by default", () => {
    const audio = createSoundEngine();
    expect(audio.isMuted()).toBe(true);
  });

  it("toggles muted state cleanly", () => {
    const audio = createSoundEngine();
    expect(audio.isMuted()).toBe(true);
    const state1 = audio.toggleMute();
    expect(state1).toBe(false);
    expect(audio.isMuted()).toBe(false);
    const state2 = audio.toggleMute();
    expect(state2).toBe(true);
    expect(audio.isMuted()).toBe(true);
  });

  it("handles sound trigger calls safely without throwing in test environment", () => {
    const audio = createSoundEngine();
    expect(() => {
      audio.playChime();
      audio.playWhoosh();
      audio.playCelebration();
      audio.playAlert();
      audio.updateWater(50);
      audio.dispose();
    }).not.toThrow();
  });
});
