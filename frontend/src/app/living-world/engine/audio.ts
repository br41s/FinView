/**
 * Procedural Web Audio synthesizer for FinView Living World.
 * Generates all town soundscapes in real time without external audio files:
 *  - Distant water murmur for the central plaza fountain (attenuated by camera distance)
 *  - Resonant town hall bell chime on clock hours
 *  - Smooth aerodynamic whoosh on camera fly / district jump
 *  - Celebratory bright arpeggio for dividends and positive earnings beats
 *  - Soft notification tone for technical / options signals
 */

export interface SoundEngine {
  isMuted(): boolean;
  setMuted(muted: boolean): void;
  toggleMute(): boolean;
  playChime(): void;
  playWhoosh(): void;
  playCelebration(): void;
  playAlert(): void;
  updateWater(cameraDistToPlaza: number): void;
  dispose(): void;
}

export function createSoundEngine(): SoundEngine {
  let ctx: AudioContext | null = null;
  let masterGain: GainNode | null = null;
  let muted = true; // Safe default for browsers; user toggles on click
  let waterGain: GainNode | null = null;
  let waterSource: AudioBufferSourceNode | null = null;

  function initContext(): AudioContext | null {
    if (typeof window === "undefined") return null;
    if (!ctx) {
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtx) return null;
      try {
        ctx = new AudioCtx();
        masterGain = ctx.createGain();
        masterGain.gain.setValueAtTime(muted ? 0 : 0.82, ctx.currentTime);
        masterGain.connect(ctx.destination);
        initWaterMurmur();
      } catch {
        return null;
      }
    }
    if (ctx && ctx.state === "suspended") {
      ctx.resume().catch(() => undefined);
    }
    return ctx;
  }

  function initWaterMurmur() {
    if (!ctx || !masterGain || waterSource) return;
    try {
      // 2 seconds of procedural pinkish/filtered noise looped for running water
      const bufferSize = ctx.sampleRate * 2;
      const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
      const data = buffer.getChannelData(0);
      let b0 = 0, b1 = 0, b2 = 0;
      for (let i = 0; i < bufferSize; i++) {
        const white = Math.random() * 2 - 1;
        b0 = 0.99886 * b0 + white * 0.0555179;
        b1 = 0.99332 * b1 + white * 0.0750759;
        b2 = 0.96900 * b2 + white * 0.1538520;
        data[i] = (b0 + b1 + b2 + white * 0.5362) * 0.07;
      }

      waterSource = ctx.createBufferSource();
      waterSource.buffer = buffer;
      waterSource.loop = true;

      const filter = ctx.createBiquadFilter();
      filter.type = "bandpass";
      filter.frequency.setValueAtTime(480, ctx.currentTime);
      filter.Q.setValueAtTime(1.6, ctx.currentTime);

      waterGain = ctx.createGain();
      waterGain.gain.setValueAtTime(0, ctx.currentTime);

      waterSource.connect(filter);
      filter.connect(waterGain);
      waterGain.connect(masterGain);
      waterSource.start(0);
    } catch {
      // Ignore audio synthesis errors on restricted platforms
    }
  }

  return {
    isMuted: () => muted,
    setMuted(m: boolean) {
      muted = m;
      const c = initContext();
      if (!c || !masterGain) return;
      if (c.state === "suspended") c.resume().catch(() => undefined);
      masterGain.gain.cancelScheduledValues(c.currentTime);
      masterGain.gain.setTargetAtTime(muted ? 0 : 0.82, c.currentTime, 0.04);
    },
    toggleMute() {
      this.setMuted(!muted);
      return muted;
    },
    playChime() {
      if (muted) return;
      const c = initContext();
      if (!c || !masterGain) return;

      const now = c.currentTime;
      // Resonant town bell with fundamental and harmonic frequencies
      const frequencies = [587.33, 1174.66, 1760.0];
      const gains = [0.28, 0.14, 0.06];

      frequencies.forEach((freq, idx) => {
        const osc = c.createOscillator();
        const g = c.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(freq, now);

        g.gain.setValueAtTime(gains[idx], now);
        g.gain.exponentialRampToValueAtTime(0.0001, now + 2.2);

        osc.connect(g);
        g.connect(masterGain!);
        osc.start(now);
        osc.stop(now + 2.3);
      });
    },
    playWhoosh() {
      if (muted) return;
      const c = initContext();
      if (!c || !masterGain) return;

      const now = c.currentTime;
      const bufferSize = Math.floor(c.sampleRate * 0.35);
      const buffer = c.createBuffer(1, bufferSize, c.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < bufferSize; i++) {
        data[i] = (Math.random() * 2 - 1) * 0.18;
      }

      const noise = c.createBufferSource();
      noise.buffer = buffer;

      const filter = c.createBiquadFilter();
      filter.type = "lowpass";
      filter.frequency.setValueAtTime(180, now);
      filter.frequency.exponentialRampToValueAtTime(950, now + 0.16);
      filter.frequency.exponentialRampToValueAtTime(140, now + 0.35);

      const g = c.createGain();
      g.gain.setValueAtTime(0.001, now);
      g.gain.linearRampToValueAtTime(0.24, now + 0.14);
      g.gain.exponentialRampToValueAtTime(0.0001, now + 0.35);

      noise.connect(filter);
      filter.connect(g);
      g.connect(masterGain);

      noise.start(now);
      noise.stop(now + 0.36);
    },
    playCelebration() {
      if (muted) return;
      const c = initContext();
      if (!c || !masterGain) return;

      const now = c.currentTime;
      // Bright major ascending arpeggio (C6, E6, G6, C7)
      const notes = [1046.5, 1318.5, 1567.98, 2093.0];
      notes.forEach((freq, i) => {
        const osc = c.createOscillator();
        const g = c.createGain();
        const start = now + i * 0.08;

        osc.type = "triangle";
        osc.frequency.setValueAtTime(freq, start);

        g.gain.setValueAtTime(0.001, start);
        g.gain.linearRampToValueAtTime(0.18, start + 0.015);
        g.gain.exponentialRampToValueAtTime(0.0001, start + 0.42);

        osc.connect(g);
        g.connect(masterGain!);
        osc.start(start);
        osc.stop(start + 0.44);
      });
    },
    playAlert() {
      if (muted) return;
      const c = initContext();
      if (!c || !masterGain) return;

      const now = c.currentTime;
      const osc = c.createOscillator();
      const g = c.createGain();

      osc.type = "sine";
      osc.frequency.setValueAtTime(880, now);
      osc.frequency.exponentialRampToValueAtTime(1320, now + 0.12);

      g.gain.setValueAtTime(0.16, now);
      g.gain.exponentialRampToValueAtTime(0.0001, now + 0.28);

      osc.connect(g);
      g.connect(masterGain);
      osc.start(now);
      osc.stop(now + 0.3);
    },
    updateWater(cameraDistToPlaza: number) {
      if (muted || !waterGain || !ctx) return;
      // Murmur volume smoothly fades when far away from the central plaza
      const normalized = Math.max(0, Math.min(1, 1 - (cameraDistToPlaza - 25) / 140));
      const targetVol = normalized * normalized * 0.22;
      waterGain.gain.setTargetAtTime(targetVol, ctx.currentTime, 0.1);
    },
    dispose() {
      if (waterSource) {
        try { waterSource.stop(); } catch { /* ignore */ }
        waterSource = null;
      }
      if (ctx) {
        ctx.close().catch(() => undefined);
        ctx = null;
      }
    },
  };
}
