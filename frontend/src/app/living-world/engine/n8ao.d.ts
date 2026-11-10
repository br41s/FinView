// `n8ao` ships no type declarations; this is the part of its API the post chain uses.
declare module "n8ao" {
  import type { Camera, Color, Scene, WebGLRenderer } from "three";
  import type { Pass } from "three/addons/postprocessing/Pass.js";

  export interface N8AOConfiguration {
    aoSamples: number;
    aoRadius: number;
    denoiseSamples: number;
    denoiseRadius: number;
    distanceFalloff: number;
    intensity: number;
    denoiseIterations: number;
    color: Color;
    gammaCorrection: boolean;
    halfRes: boolean;
    screenSpaceRadius: boolean;
    depthAwareUpsampling: boolean;
  }

  export class N8AOPass extends Pass {
    constructor(scene: Scene, camera: Camera, width?: number, height?: number);
    configuration: N8AOConfiguration;
    setSize(width: number, height: number): void;
    dispose(): void;
    render(renderer: WebGLRenderer, writeBuffer: unknown, readBuffer: unknown, deltaTime?: number, maskActive?: boolean): void;
  }
}
