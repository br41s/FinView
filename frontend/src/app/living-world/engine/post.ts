import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { SMAAPass } from "three/addons/postprocessing/SMAAPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { N8AOPass } from "n8ao";
import type { PostSettings } from "./quality";

/**
 * Post-processing chain: N8AO ambient occlusion (renders the scene itself) -> bloom of the lit
 * windows (only while it is night) -> OutputPass (ACES tone mapping + sRGB) -> SMAA.
 *
 * With no settings (the "low" tier) it is a plain `renderer.render`, and the composer, its float
 * render targets and the AO buffers do not exist at all. The chain is created on demand, rebuilt
 * on a tier change and disposed with the world.
 */
export interface PostFx {
  /** Apply a tier's settings; `null` tears the chain down. */
  setSettings(s: PostSettings | null): void;
  /** CSS pixels and the pixel ratio the renderer already uses. */
  setSize(width: number, height: number, pixelRatio: number): void;
  /** 0 = day .. 1 = night; bloom fades in with it and is skipped by day. */
  setNight(night: number): void;
  render(): void;
  dispose(): void;
}

const BLOOM_MAX = 0.55;

export function createPost(renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.Camera): PostFx {
  let settings: PostSettings | null = null;
  let chain: {
    composer: EffectComposer;
    ao: N8AOPass;
    bloom: UnrealBloomPass;
    output: OutputPass;
    smaa: SMAAPass | null;
  } | null = null;
  let w = 1;
  let h = 1;
  let pr = 1;
  let night = 0;

  const destroy = () => {
    if (!chain) return;
    chain.ao.dispose();
    chain.bloom.dispose();
    chain.output.dispose();
    chain.smaa?.dispose();
    chain.composer.dispose();
    chain = null;
  };

  const build = (s: PostSettings) => {
    const composer = new EffectComposer(renderer);
    composer.setPixelRatio(pr);
    composer.setSize(w, h);
    const ao = new N8AOPass(scene, camera, w * pr, h * pr);
    const c = ao.configuration;
    c.gammaCorrection = false; // OutputPass owns tone mapping and the sRGB encode
    c.aoRadius = 6.5;
    c.distanceFalloff = 1.5;
    c.intensity = 4.5;
    c.color = new THREE.Color(0x0d1a33);
    c.halfRes = s.aoHalfRes;
    c.aoSamples = s.aoSamples;
    c.denoiseSamples = s.aoDenoiseSamples;
    composer.addPass(ao);
    const bloom = new UnrealBloomPass(new THREE.Vector2(w * pr, h * pr), 0, 0.7, 1.15);
    bloom.enabled = false;
    composer.addPass(bloom);
    const output = new OutputPass();
    composer.addPass(output);
    let smaa: SMAAPass | null = null;
    if (s.smaa) {
      smaa = new SMAAPass();
      composer.addPass(smaa);
    }
    chain = { composer, ao, bloom, output, smaa };  };

  const applyBloom = () => {
    if (!chain || !settings) return;
    const on = settings.bloom && night > 0.04;
    chain.bloom.enabled = on;
    chain.bloom.strength = BLOOM_MAX * night;
  };

  return {
    setSettings(s) {
      const same = s === settings;
      settings = s;
      if (same) return;
      destroy();
      if (s) {
        build(s);
        applyBloom();
      }
    },
    setSize(width, height, pixelRatio) {
      w = width;
      h = height;
      pr = pixelRatio;
      if (!chain) return;
      chain.composer.setPixelRatio(pr);
      chain.composer.setSize(w, h);
    },
    setNight(n) {
      night = n;
      applyBloom();
    },
    render() {
      if (chain) chain.composer.render();
      else renderer.render(scene, camera);
    },
    dispose() {
      destroy();
      settings = null;
    },
  };
}
