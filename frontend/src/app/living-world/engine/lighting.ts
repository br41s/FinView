import * as THREE from "three";
import { SkyBackdrop, createSkyEnvironment, facadeShared, setFacadeEnvIntensity, setFacadeNight } from "./materials";
import { skyAt, sunPosition, type RGB } from "./skyModel";

/**
 * Sky, fog, hemisphere light, the sun with its shadow, and the reflection environment of the glass.
 * Everything follows the city clock through `skyAt` (smoothed, since the clock can be set by hand).
 */
export interface Lighting {
  readonly sun: THREE.DirectionalLight;
  /** 0 (day) .. 1 (night) after smoothing; the post-processing bloom follows it. */
  readonly night: number;
  /** Fit the shadow frustum to a town of this radius. */
  frame(radius: number): void;
  /** Turn shadows on or off and (re)size the shadow map. */
  setShadows(on: boolean, mapSize: number): void;
  update(hour: number, dtMs: number, radius: number, camera: THREE.Camera): void;
  dispose(): void;
}

const toColor = (rgb: RGB, out: THREE.Color) => out.setRGB(rgb[0], rgb[1], rgb[2], THREE.SRGBColorSpace);
const _dir = new THREE.Vector3();

export function createLighting(scene: THREE.Scene, renderer: THREE.WebGLRenderer): Lighting {
  const horizon = new THREE.Color();
  const zenith = new THREE.Color();
  const backdrop = new SkyBackdrop();
  scene.background = backdrop.texture;
  scene.fog = new THREE.FogExp2(0xc5e3f4, 0.0008);

  const hemi = new THREE.HemisphereLight(0xe4f2ff, 0xb7cfa6, 1.2);
  const sun = new THREE.DirectionalLight(0xfff3db, 2.2);
  sun.shadow.radius = 3;
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.45;
  scene.add(hemi, sun, sun.target);

  const env = createSkyEnvironment(renderer);
  facadeShared.envMap = env;

  let night = 0;
  let fresh = true;
  let sunIntensity = 2.2;
  let hemiIntensity = 1.2;
  let envIntensity = 1;
  const sunCol = new THREE.Color();
  const hemiSky = new THREE.Color();
  const hemiGround = new THREE.Color();
  const target = new THREE.Color();

  return {
    sun,
    get night() {
      return night;
    },
    frame(radius) {
      const r = radius + 30;
      sun.target.position.set(0, 0, 0);
      const c = sun.shadow.camera;
      c.left = -r;
      c.right = r;
      c.top = r;
      c.bottom = -r;
      c.near = 1;
      c.far = r * 3.2;
      c.updateProjectionMatrix();
    },
    setShadows(on, mapSize) {
      sun.castShadow = on;
      renderer.shadowMap.enabled = on;
      if (on) {
        sun.shadow.mapSize.set(mapSize, mapSize);
        sun.shadow.map?.dispose();
        sun.shadow.map = null;
      }
    },
    update(hour, dtMs, radius, camera) {
      const s = skyAt(hour);
      const k = fresh ? 1 : Math.min(1, (dtMs / 1000) * 2.5);
      fresh = false;

      horizon.lerp(toColor(s.horizon, target), k);
      zenith.lerp(toColor(s.zenith, target), k);
      sunCol.lerp(toColor(s.sun, target), k);
      hemiSky.lerp(toColor(s.hemiSky, target), k);
      hemiGround.lerp(toColor(s.hemiGround, target), k);
      sunIntensity += (s.sunIntensity - sunIntensity) * k;
      hemiIntensity += (s.hemiIntensity - hemiIntensity) * k;
      envIntensity += (s.envIntensity - envIntensity) * k;
      night += (s.night - night) * k;

      // Where the horizon sits on screen (from the top), from the camera's pitch.
      camera.getWorldDirection(_dir);
      const pitch = Math.asin(THREE.MathUtils.clamp(-_dir.y, -1, 1));
      const tanHalf = Math.tan(THREE.MathUtils.degToRad((camera as THREE.PerspectiveCamera).fov / 2));
      backdrop.update(horizon, zenith, 0.5 - Math.tan(Math.min(pitch, 1.5)) / tanHalf / 2);

      (scene.fog as THREE.FogExp2).color.copy(horizon);
      sun.color.copy(sunCol);
      sun.intensity = sunIntensity;
      hemi.color.copy(hemiSky);
      hemi.groundColor.copy(hemiGround);
      hemi.intensity = hemiIntensity;
      renderer.toneMappingExposure = s.exposure * 0.97;

      const [x, y, z] = sunPosition(hour, radius + 30);
      sun.position.set(x, y, z);

      setFacadeNight(night);
      setFacadeEnvIntensity(envIntensity);
    },
    dispose() {
      backdrop.dispose();
      if (facadeShared.envMap === env) facadeShared.envMap = null;
      env.dispose();
      scene.remove(hemi, sun, sun.target);
      sun.shadow.map?.dispose();
    },
  };
}
