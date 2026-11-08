import * as THREE from "three";
import {
  createDirector,
  enqueue,
  replay as replayEvent,
  setConfig,
  setPaused,
  tick,
  type DirectorConfig,
  type DirectorState,
  type Performance,
} from "../model/director";
import { computeLayout, type Lot, type WorldLayout } from "../model/townLayout";
import { routeToPlaza, type Point } from "../model/routes";
import { approach, footprintFor, tierFor } from "../model/scale";
import type { Visibility, WorldAsset, WorldEvent } from "../model/types";
import { AgentSystem, type SiteSpot } from "./agents";
import { NOMINAL, createSite, disposeSite, type Site } from "./buildingFactory";
import { CameraController } from "./cameraController";
import { buildInfra, type InfraSystem } from "./infra";
import { Choreographer } from "./choreography";
import { QUALITY, type Quality } from "./quality";
import { buildTown, disposeLabel, makeLabel, type Town } from "./props";

/**
 * The renderer. React owns controls and cards; everything that changes per frame lives
 * here and never goes through React state (spec §9.1, §11).
 */

export interface WorldCallbacks {
  onSelect(assetId: string | null): void;
  onHover(assetId: string | null): void;
  onFocusKey(): void;
  onPerformance(kind: "start" | "end", p: Performance): void;
  onContextLost(): void;
  onStats(s: WorldStats): void;
  /** Whether "back" has somewhere to go; pushed when it changes so the UI never polls the engine. */
  onCanBack(can: boolean): void;
}

export interface WorldStats {
  fps: number;
  drawCalls: number;
  triangles: number;
  agents: number;
  sites: number;
  distance: number;
}

export interface WorldHandle {
  setAssets(assets: readonly WorldAsset[]): void;
  setVisibility(v: ReadonlyMap<string, Visibility>): void;
  select(id: string | null): void;
  focusAsset(id: string): void;
  followAsset(id: string): void;
  fit(): void;
  back(): void;
  canGoBack(): boolean;
  rotate(dir: -1 | 1): void;
  zoom(factor: number): void;
  enqueue(events: readonly WorldEvent[]): void;
  replay(e: WorldEvent): void;
  setDirector(patch: Partial<DirectorConfig>): void;
  setPaused(paused: boolean): void;
  setQuality(q: Quality): void;
  setReducedMotion(v: boolean): void;
  stats(): WorldStats;
  dispose(): void;
}

interface SiteEntry {
  asset: WorldAsset;
  lot: Lot;
  site: Site;
  label: THREE.Sprite;
  footprint: number;
  /** Ground height under the building. */
  groundY: number;
  scale: number;
  opacity: number;
  /** Last opacity written to the material, so a jump (reduced motion) is still applied. */
  applied: number;
  targetOpacity: number;
  route: Point[];
}

const SKY = 0xbfe3f5;

export function createWorld(
  canvas: HTMLCanvasElement,
  init: { quality: Quality; reducedMotion: boolean },
  cb: WorldCallbacks,
): WorldHandle {
  let quality = init.quality;
  let reduced = init.reducedMotion;
  let paused = false;
  let disposed = false;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: quality !== "low", powerPreference: "high-performance" });
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(SKY);
  const camera = new THREE.PerspectiveCamera(32, 1, 1, 3000);

  scene.add(new THREE.HemisphereLight(0xdff0ff, 0xb9d79a, 1.15));
  const sun = new THREE.DirectionalLight(0xfff0d2, 2.1);
  scene.add(sun, sun.target);

  let layout: WorldLayout = computeLayout([]);
  let town: Town | null = null;
  let infra: InfraSystem | null = null;
  let agents = new AgentSystem(QUALITY[quality].maxAgents);
  agents.setReducedMotion(reduced);
  agents.setGround(layout.terrain.roadY);
  scene.add(agents.bodies, agents.heads, agents.vans);
  const sites = new Map<string, SiteEntry>();
  const siteMeshes: THREE.Mesh[] = [];
  let director: DirectorState = createDirector();
  let selected: string | null = null;
  let hovered: string | null = null;

  const selectRing = new THREE.Mesh(
    new THREE.RingGeometry(0.88, 1, 48),
    new THREE.MeshBasicMaterial({ color: 0xfff2b3, side: THREE.DoubleSide, transparent: true, opacity: 0.95, depthWrite: false }),
  );
  selectRing.rotation.x = -Math.PI / 2;
  selectRing.position.y = 0.3;
  selectRing.visible = false;
  selectRing.renderOrder = 4;
  scene.add(selectRing);

  const stage = {
    scene,
    agents,
    bank: { x: 0, z: 0 } as Point,
    site(id: string) {
      const e = sites.get(id);
      return e ? { x: e.lot.x, z: e.lot.z, groundY: e.groundY, markerY: e.groundY + e.site.top * e.scale + 1.6, route: e.route } : null;
    },
  };
  let choreo = new Choreographer(stage);

  const ctrl = new CameraController(camera, canvas, {
    radius: () => layout.radius,
    groundY: (x, z) => layout.terrain.heightAt(x, z),
    reducedMotion: () => reduced,
    onClick: (x, y) => pick(x, y),
    onUserMove: () => undefined,
    onFocusKey: () => cb.onFocusKey(),
  });

  // --- sizing ------------------------------------------------------------------
  const resize = () => {
    const w = canvas.clientWidth || 1;
    const h = canvas.clientHeight || 1;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, QUALITY[quality].maxPixelRatio));
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  resize();

  const applyShadows = () => {
    const q = QUALITY[quality];
    renderer.shadowMap.enabled = q.shadows;
    sun.castShadow = q.shadows;
    if (q.shadows) {
      sun.shadow.mapSize.set(q.shadowMapSize, q.shadowMapSize);
      sun.shadow.map?.dispose();
      sun.shadow.map = null;
    }
    scene.traverse((o) => {
      const m = (o as THREE.Mesh).material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(m)) m.forEach((x) => (x.needsUpdate = true));
      else if (m) m.needsUpdate = true;
    });
  };

  const frameSun = () => {
    const r = layout.radius + 30;
    sun.position.set(r * 0.55, r * 1.1, r * 0.4);
    sun.target.position.set(0, 0, 0);
    const c = sun.shadow.camera;
    c.left = -r;
    c.right = r;
    c.top = r;
    c.bottom = -r;
    c.near = 1;
    c.far = r * 3;
    c.updateProjectionMatrix();
    sun.shadow.bias = -0.0006;
  };

  // --- building the town ---------------------------------------------------------
  const clearSites = () => {
    for (const e of sites.values()) {
      scene.remove(e.site.group, e.label);
      disposeSite(e.site);
      disposeLabel(e.label);
    }
    sites.clear();
    siteMeshes.length = 0;
  };

  const rebuildAgents = () => {
    scene.remove(agents.bodies, agents.heads, agents.vans);
    agents.dispose();
    agents = new AgentSystem(QUALITY[quality].maxAgents);
    agents.setReducedMotion(reduced);
    agents.setGround(layout.terrain.roadY);
    scene.add(agents.bodies, agents.heads, agents.vans);
    stage.agents = agents;
    choreo.dispose();
    choreo = new Choreographer(stage);
    const spots: SiteSpot[] = [...sites.values()].map((e) => ({
      assetId: e.asset.id, x: e.lot.x, z: e.lot.z, rotationY: e.lot.rotationY, footprint: e.footprint, tier: tierFor(e.asset.weightPct),
    }));
    // One representative route per district, for the vans that always drive the boulevards.
    const perDistrict = new Map<string, Point[]>();
    for (const e of sites.values()) if (!perDistrict.has(e.lot.district)) perDistrict.set(e.lot.district, e.route);
    agents.populate(spots, [...perDistrict.values()]);
    // Scenes still running in the director would otherwise vanish with the old stage.
    for (const p of director.active) choreo.start(p);
  };

  const setAssets = (assets: readonly WorldAsset[]) => {
    clearSites();
    if (town) {
      scene.remove(town.group);
      town.dispose();
    }
    layout = computeLayout(assets);
    town = buildTown(layout, QUALITY[quality].trees);
    town.setTreeCount(QUALITY[quality].trees);
    town.fillers.setDensity(QUALITY[quality].fillerDensity);
    scene.add(town.group);
    if (infra) {
      scene.remove(infra.group);
      infra.dispose();
    }
    infra = buildInfra(layout);
    infra.setReducedMotion(reduced);
    scene.add(infra.group);
    const bank = town.civic.get("bank");
    stage.bank = bank ? { x: bank.x, z: bank.z } : { x: 0, z: 0 };

    for (const asset of assets) {
      const lot = layout.lots.get(asset.id)!;
      const d = layout.districts.find((x) => x.id === lot.district)!;
      const tier = tierFor(asset.weightPct);
      const site = createSite(asset, tier, asset.marketValueEur === null);
      const footprint = footprintFor(asset.weightPct);
      const scale = footprint / NOMINAL[tier];
      const groundY = layout.terrain.heightAt(lot.x, lot.z);
      site.group.position.set(lot.x, groundY, lot.z);
      site.group.rotation.y = lot.rotationY;
      site.group.scale.setScalar(scale);
      site.mesh.userData.assetId = asset.id;
      scene.add(site.group);
      siteMeshes.push(site.mesh);

      const label = makeLabel(asset.name, { font: 28 });
      label.position.set(lot.x, groundY + site.top * scale + 1.1, lot.z);
      scene.add(label);
      sites.set(asset.id, {
        asset, lot, site, label, footprint, groundY, scale, opacity: 1, applied: 1, targetOpacity: 1, route: routeToPlaza(lot, d),
      });
    }
    frameSun();
    applyShadows();
    rebuildAgents();
    ctrl.fit(true);
    if (selected && !sites.has(selected)) select(null);
    else select(selected);
  };

  // --- selection and picking ------------------------------------------------------
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const setRay = (cx: number, cy: number) => {
    const r = canvas.getBoundingClientRect();
    ndc.set(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
  };
  const siteAt = (cx: number, cy: number): string | null => {
    setRay(cx, cy);
    const live = siteMeshes.filter((m) => m.parent?.visible);
    const hit = ray.intersectObjects(live, false)[0];
    return hit ? (hit.object.userData.assetId as string) : null;
  };

  function select(id: string | null) {
    selected = id;
    const e = id ? sites.get(id) : null;
    selectRing.visible = !!e;
    if (e) {
      selectRing.position.set(e.lot.x, e.groundY + 0.3, e.lot.z);
      selectRing.scale.setScalar(e.footprint * 0.78);
    }
    for (const s of sites.values()) s.site.material.emissive.setHex(s.asset.id === id ? 0x2a2410 : 0x000000);
  }

  function pick(cx: number, cy: number) {
    const id = siteAt(cx, cy);
    if (id) {
      select(id);
      cb.onSelect(id);
      return;
    }
    // Inhabitants can be followed: a click on a person picks them up.
    setRay(cx, cy);
    // Raycasting ignores `visible`: zoomed out (LOD hides people) a click must not pick one.
    const hit = agents.bodies.visible ? ray.intersectObject(agents.bodies, false)[0] : undefined;
    if (hit && hit.instanceId !== undefined) {
      const idx = hit.instanceId;
      ctrl.follow(() => agents.position(idx));
      return;
    }
    select(null);
    cb.onSelect(null);
  }

  let lastHover = 0;
  const onMove = (e: PointerEvent) => {
    if (e.buttons !== 0 || e.timeStamp - lastHover < 70) return;
    lastHover = e.timeStamp;
    const id = siteAt(e.clientX, e.clientY);
    if (id !== hovered) {
      hovered = id;
      canvas.style.cursor = id ? "pointer" : "grab";
      cb.onHover(id);
    }
  };
  canvas.addEventListener("pointermove", onMove);
  canvas.style.cursor = "grab";

  // --- loop ------------------------------------------------------------------------
  let raf = 0;
  let last = 0;
  let onScreen = true;
  let frames = 0;
  let acc = 0;
  let fps = 0;
  let lastLod = -1;
  let canBack = false;
  /** Performances the camera was already sent to, so a merge does not fly there twice. */
  const focusedPerf = new Set<string>();

  const lod = (dist: number) => {
    if (town) {
      for (const s of town.districtLabels) {
        s.visible = dist > 55;
        const h = Math.min(7, Math.max(2.2, dist * 0.028));
        s.scale.set(s.userData.aspect * h, h, 1);
      }
    }
    const h = Math.min(2.4, Math.max(0.8, dist * 0.02));
    for (const e of sites.values()) {
      const tier = tierFor(e.asset.weightPct);
      const bigEnough = dist > 95 ? false : dist > 55 ? tier === "campus" || tier === "major" : dist > 35 ? tier !== "outpost" : true;
      e.label.visible = bigEnough && e.site.group.visible;
      e.label.scale.set(e.label.userData.aspect * h, h, 1);
    }
    const near = dist < 140;
    agents.bodies.visible = near;
    agents.heads.visible = near;
    agents.vans.visible = near;
  };

  const frame = (now: number) => {
    raf = 0;
    if (disposed) return;
    if (document.hidden || !onScreen) {
      last = 0;
      return; // resumes from the visibility handlers; a hidden scene costs nothing
    }
    raf = requestAnimationFrame(frame);
    const minMs = QUALITY[quality].minFrameMs;
    if (last && now - last < minMs) return;
    const dt = last ? Math.min(50, now - last) : 16;
    last = now;

    acc += dt;
    frames++;
    if (acc >= 500) {
      fps = Math.round((frames * 1000) / acc);
      frames = 0;
      acc = 0;
      cb.onStats(stats());
    }

    ctrl.update(dt);
    const back = ctrl.canGoBack();
    if (back !== canBack) {
      canBack = back;
      cb.onCanBack(back);
    }
    const simDt = paused ? 0 : dt;
    if (simDt > 0) {
      const r = tick(director, simDt);
      director = r.state;
      for (const p of r.started) {
        choreo.start(p);
        cb.onPerformance("start", p);
        if (p.requestFocus && p.assetId) {
          focusedPerf.add(p.id);
          focusAsset(p.assetId);
        }
      }
      for (const p of r.merged) {
        choreo.extend(p, director.clock);
        // An escalation to Critical after the scene began still earns its focus, once.
        if (p.requestFocus && p.assetId && !focusedPerf.has(p.id)) {
          focusedPerf.add(p.id);
          focusAsset(p.assetId);
        }
      }
      for (const p of r.ended) {
        choreo.stop(p.id);
        focusedPerf.delete(p.id);
        cb.onPerformance("end", p);
      }
      agents.update(simDt);
      infra?.update(simDt);
      choreo.update(simDt);
    }

    // Muting fades; hidden sites switch off once fully transparent.
    for (const e of sites.values()) {
      const next = reduced ? e.targetOpacity : approach(e.opacity, e.targetOpacity, dt, 120);
      if (next === e.applied) continue;
      e.opacity = next;
      e.applied = next;
      const m = e.site.material;
      m.opacity = next;
      const transparent = next < 0.999;
      if (m.transparent !== transparent) {
        m.transparent = transparent;
        // Opaque materials compile with alpha forced to 1; flipping the flag needs a recompile.
        m.needsUpdate = true;
      }
      m.depthWrite = next > 0.5;
      e.site.group.visible = e.targetOpacity > 0 || next > 0.01;
      e.label.material.opacity = Math.max(0.25, next);
    }

    const dist = ctrl.distance;
    if (Math.abs(dist - lastLod) > dist * 0.04 || lastLod < 0) {
      lastLod = dist;
      lod(dist);
    }
    renderer.render(scene, camera);
  };

  const wake = () => {
    if (!raf && !disposed && !document.hidden && onScreen) raf = requestAnimationFrame(frame);
  };
  const io = new IntersectionObserver((entries) => {
    onScreen = entries.some((e) => e.isIntersecting);
    wake();
  });
  io.observe(canvas);
  document.addEventListener("visibilitychange", wake);
  const onLost = (e: Event) => {
    e.preventDefault();
    // Our own dispose() forces a context loss; only an unexpected one is an error.
    if (!disposed) cb.onContextLost();
  };
  canvas.addEventListener("webglcontextlost", onLost);
  applyShadows();
  wake();

  // --- public handle -----------------------------------------------------------------
  function focusAsset(id: string) {
    const e = sites.get(id);
    if (e) ctrl.focus(e.lot.x, e.lot.z, e.footprint * 2.4 + 16);
  }

  function stats(): WorldStats {
    return {
      fps,
      drawCalls: renderer.info.render.calls,
      triangles: renderer.info.render.triangles,
      agents: agents.activeCount(),
      sites: sites.size,
      distance: ctrl.distance,
    };
  }

  const handle: WorldHandle = {
    setAssets,
    setVisibility(v) {
      for (const [id, e] of sites) {
        const vis = v.get(id) ?? "match";
        e.targetOpacity = vis === "match" ? 1 : vis === "muted" ? 0.22 : 0;
      }
      lastLod = -1;
    },
    select(id) {
      select(id);
    },
    focusAsset,
    followAsset(id) {
      const i = agents.firstAgentOf(id);
      if (i >= 0) ctrl.follow(() => agents.position(i));
    },
    fit: () => ctrl.fit(),
    back: () => void ctrl.back(),
    canGoBack: () => ctrl.canGoBack(),
    rotate: (dir) => ctrl.rotate(dir * (Math.PI / 8)),
    zoom: (f) => ctrl.zoomBy(f),
    enqueue(events) {
      director = enqueue(director, events);
    },
    replay(e) {
      const r = replayEvent(director, e);
      director = r.state;
      for (const p of r.started) {
        choreo.start(p);
        cb.onPerformance("start", p);
      }
      for (const p of r.merged) choreo.extend(p, director.clock);
    },
    setDirector(patch) {
      director = setConfig(director, patch);
    },
    setPaused(p) {
      paused = p;
      director = setPaused(director, p);
    },
    setQuality(q) {
      if (q === quality) return;
      quality = q;
      resize();
      applyShadows();
      town?.setTreeCount(QUALITY[q].trees);
      town?.fillers.setDensity(QUALITY[q].fillerDensity);
      rebuildAgents();
    },
    setReducedMotion(v) {
      if (v === reduced) return;
      reduced = v;
      agents.setReducedMotion(v);
      infra?.setReducedMotion(v);
    },
    stats,
    dispose() {
      disposed = true;
      cancelAnimationFrame(raf);
      io.disconnect();
      ro.disconnect();
      document.removeEventListener("visibilitychange", wake);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("webglcontextlost", onLost);
      ctrl.dispose();
      clearSites();
      choreo.dispose();
      town?.dispose();
      infra?.dispose();
      agents.dispose();
      selectRing.geometry.dispose();
      (selectRing.material as THREE.Material).dispose();
      renderer.dispose();
      // Frees the GPU context now instead of waiting for GC; React strict mode remounts.
      renderer.forceContextLoss();
    },
  };
  return handle;
}
