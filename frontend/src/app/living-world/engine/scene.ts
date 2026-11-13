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
import { routeToPlaza, sidewalkRoute, type Point } from "../model/routes";
import { approach, footprintFor, tierFor } from "../model/scale";
import type { Visibility, WorldAsset, WorldEvent } from "../model/types";
import { AgentSystem, getCircadianPhase, type CircadianPhase, type SiteSpot } from "./agents";
import { NOMINAL, accentFor, createRuins, createSite, disposeSite, specFor, type Site } from "./buildingFactory";
import { CameraController } from "./cameraController";
import { buildInfra, type InfraSystem } from "./infra";
import { VehicleSystem } from "./vehicles";
import { Choreographer } from "./choreography";
import type { DayMood } from "../model/eventTiming";
import { QUALITY, type Quality } from "./quality";
import { createLighting } from "./lighting";
import { createPost } from "./post";
import { buildTown, ribbon, type Town } from "./props";
import { toyShared } from "./toyMaterial";
import { createSoundEngine, type SoundEngine } from "./audio";

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
  onTourChange?(touring: boolean): void;
  onFollowTarget?(target: string | null): void;
}

export interface WorldStats {
  fps: number;
  drawCalls: number;
  triangles: number;
  agents: number;
  /** Road vehicles (traffic plus event vans). */
  vehicles: number;
  sites: number;
  distance: number;
  clockHour: number;
  circadianPhase: CircadianPhase;
  clockLabel: string;
  soundMuted: boolean;
}

function formatClockLabel(hour: number): string {
  const h = Math.floor(hour);
  const m = Math.floor((hour - h) * 60);
  const timeStr = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  const phase = getCircadianPhase(hour);
  const phaseName =
    phase === "morning_rush"
      ? "Hora punta"
      : phase === "workday"
        ? "Jornada laboral"
        : phase === "evening_leisure"
          ? "Tarde de ocio"
          : "Noche";
  return `${timeStr} · ${phaseName}`;
}

export interface WorldHandle {
  setAssets(assets: readonly WorldAsset[]): void;
  setVisibility(v: ReadonlyMap<string, Visibility>): void;
  select(id: string | null): void;
  focusAsset(id: string): void;
  followAsset(id: string): void;
  stopFollow(): void;
  followMonorail(): void;
  toggleSound(): boolean;
  isSoundMuted(): boolean;
  hero(): void;
  fit(): void;
  toggleTour(): boolean;
  setTour(active: boolean): void;
  isTouring(): boolean;
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
  /** Buildings living through an all-day event today, and how (see `Choreographer.setAllDay`). */
  setDayMoods(moods: ReadonlyMap<string, DayMood>): void;
  /** Jump the city clock (dev tools and screenshots). */
  setHour(h: number): void;
  /** Fly the camera to a ground point (dev tools and screenshots). */
  focusPoint(x: number, z: number, distance?: number): void;
  /** Where every holding stands (dev tools and screenshots). */
  sites(): Array<{ id: string; name: string; archetype: string; tier: string; family: string; x: number; z: number; asset: WorldAsset }>;
  /** Follow the ground train (it shuttles along the railway and stops at both termini). */
  followTrain(): void;
  /** Dev handle: third-person follow of one pavement walker or staff member (id from `crowd()`). */
  followAgent(id: number): void;
  /** Dev handle: where the visible pavement walkers and the vehicles are (screenshots, checks). */
  crowd(): { people: Array<{ id: number; x: number; z: number; profession: string; crowd: boolean }>; vehicles: Array<{ x: number; z: number; kind: string; v: number }>; trains: Array<{ x: number; y: number; z: number }> };
  stats(): WorldStats;
  dispose(): void;
}

interface SiteEntry {
  asset: WorldAsset;
  lot: Lot;
  site: Site;
  footprint: number;
  /** Ground height under the building. */
  groundY: number;
  scale: number;
  scaleFrom: number;
  scaleTarget: number;
  scaleElapsedMs: number;
  scaleDelayMs: number;
  scaleDurationMs: number;
  opacity: number;
  /** Last opacity written to the material, so a jump (reduced motion) is still applied. */
  applied: number;
  targetOpacity: number;
  route: Point[];
}

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
  renderer.shadowMap.type = THREE.PCFShadowMap;
  // Khronos PBR Neutral keeps hue and saturation (ACES shifts and mutes them): toy colours stay toy colours.
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = 1.0;
  // The post chain renders several times per frame: count them all, reset once per frame.
  renderer.info.autoReset = false;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 1, 3000);
  const lighting = createLighting(scene, renderer);
  const post = createPost(renderer, scene, camera);
  post.setSettings(QUALITY[quality].post);

  let layout: WorldLayout = computeLayout([]);
  let town: Town | null = null;
  let infra: InfraSystem | null = null;
  let vehicles: VehicleSystem | null = null;
  let agents = new AgentSystem(QUALITY[quality].maxAgents, QUALITY[quality].maxWalkers);
  agents.setReducedMotion(reduced);
  agents.setGround(layout.terrain.roadY);
  scene.add(...agents.objects);
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

  const hoverRing = new THREE.Mesh(
    new THREE.RingGeometry(0.82, 0.94, 48),
    new THREE.MeshBasicMaterial({ color: 0x48b9d1, side: THREE.DoubleSide, transparent: true, opacity: 0.82, depthWrite: false }),
  );
  hoverRing.rotation.x = -Math.PI / 2;
  hoverRing.position.y = 0.34;
  hoverRing.visible = false;
  hoverRing.renderOrder = 3;
  scene.add(hoverRing);

  let routeMesh: THREE.Mesh | null = null;
  const routeMat = new THREE.MeshBasicMaterial({
    transparent: true,
    opacity: 0.85,
    depthWrite: false,
    toneMapped: false,
    side: THREE.DoubleSide,
  });

  const clearRouteHighlight = () => {
    if (routeMesh) {
      scene.remove(routeMesh);
      routeMesh.geometry.dispose();
      routeMesh = null;
    }
  };

  const updateRouteHighlight = (assetId: string | null) => {
    clearRouteHighlight();
    if (!assetId) return;
    const e = sites.get(assetId);
    if (!e || e.route.length < 2) return;
    const accent = accentFor(e.asset.id, e.asset);
    routeMat.color.setHex(accent);
    const geo = ribbon(e.route, 1.45, 0.22, accent, layout.terrain.roadY);
    routeMesh = new THREE.Mesh(geo, routeMat);
    routeMesh.renderOrder = 4;
    scene.add(routeMesh);
  };

  const stage = {
    scene,
    agents,
    bank: { x: 0, z: 0 } as Point,
    site(id: string) {
      const e = sites.get(id);
      return e
        ? { x: e.lot.x, z: e.lot.z, groundY: e.groundY, markerY: e.groundY + e.site.signTop * e.scale + 1.1, route: e.route, radius: e.footprint * 0.5 }
        : null;
    },
  };
  let choreo = new Choreographer(stage);
  choreo.setReducedMotion(reduced);
  // Kept so a rebuilt stage (new choreographer, new sites) picks the day's festivities up again.
  let dayMoods: ReadonlyMap<string, DayMood> = new Map();
  const sound = createSoundEngine();

  const ctrl = new CameraController(camera, canvas, {
    radius: () => layout.radius,
    groundY: (x, z) => layout.terrain.heightAt(x, z),
    reducedMotion: () => reduced,
    onClick: (x, y) => pick(x, y),
    onUserMove: () => undefined,
    onFocusKey: () => cb.onFocusKey(),
    onTourChange: (active) => cb.onTourChange?.(active),
    onFollowChange: (following) => {
      if (!following) cb.onFollowTarget?.(null);
    },
  });

  // --- sizing ------------------------------------------------------------------
  const resize = () => {
    const w = canvas.clientWidth || 1;
    const h = canvas.clientHeight || 1;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, QUALITY[quality].maxPixelRatio));
    renderer.setSize(w, h, false);
    post.setSize(w, h, renderer.getPixelRatio());
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  resize();

  const applyShadows = () => {
    const q = QUALITY[quality];
    lighting.setShadows(q.shadows, q.shadowMapSize);
    scene.traverse((o: THREE.Object3D) => {
      const m = (o as THREE.Mesh).material as THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(m)) m.forEach((x) => (x.needsUpdate = true));
      else if (m) m.needsUpdate = true;
    });
  };

  const frameSun = () => lighting.frame(layout.radius);

  // --- building the town ---------------------------------------------------------
  const clearSites = () => {
    clearRouteHighlight();
    hovered = null;
    hoverRing.visible = false;
    for (const e of sites.values()) {
      scene.remove(e.site.group);
      disposeSite(e.site);
    }
    sites.clear();
    siteMeshes.length = 0;
  };

  /** Road traffic for the current layout and quality tier (the lane network is cached per graph). */
  const buildVehicles = () => {
    if (vehicles) {
      scene.remove(vehicles.group);
      vehicles.dispose();
    }
    vehicles = new VehicleSystem(layout, {
      maxVehicles: QUALITY[quality].maxVehicles,
      crossingClosed: (node) => infra?.crossingClosed(node) ?? false,
      ground: layout.terrain.roadY,
    });
    vehicles.setReducedMotion(reduced);
    scene.add(vehicles.group);
  };

  const rebuildAgents = () => {
    scene.remove(...agents.objects);
    const clockHour = agents.hour;
    agents.dispose();
    agents = new AgentSystem(QUALITY[quality].maxAgents, QUALITY[quality].maxWalkers);
    agents.setHour(clockHour); // a quality change must not rewind the city's day
    agents.setReducedMotion(reduced);
    agents.setWorld({ graph: layout.graph, roads: layout.roads, ground: layout.terrain.roadY });
    agents.setVehicles(vehicles);
    scene.add(...agents.objects);
    stage.agents = agents;
    choreo.dispose();
    choreo = new Choreographer(stage);
    choreo.setReducedMotion(reduced);
    const spots: SiteSpot[] = [...sites.values()].filter((e) => !e.asset.closed).map((e) => ({
      assetId: e.asset.id,
      archetype: e.asset.archetype,
      x: e.lot.x,
      z: e.lot.z,
      rotationY: e.lot.rotationY,
      footprint: e.footprint,
      tier: tierFor(e.asset.weightPct),
      accent: accentFor(e.asset.id, e.asset),
      walkRoute: sidewalkRoute(e.route, layout.roads, e.asset.id.length % 2 === 0 ? 1 : -1),
    }));
    // One representative route per district, for the vans that always drive the boulevards.
    const perDistrict = new Map<string, Point[]>();
    for (const e of sites.values()) if (!perDistrict.has(e.lot.district)) perDistrict.set(e.lot.district, e.route);
    agents.populate(spots, [...perDistrict.values()]);
    // Scenes still running in the director would otherwise vanish with the old stage.
    for (const p of director.active) choreo.start(p);
    choreo.setAllDay(dayMoods);
  };

  const setAssets = (assets: readonly WorldAsset[]) => {
    const previousScales = new Map<string, number>([...sites.values()].map((e) => [e.asset.id, e.scale] as const));
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
    buildVehicles();
    const bank = town.civic.get("bank");
    stage.bank = bank ? { x: bank.x, z: bank.z } : { x: 0, z: 0 };

    for (const [assetIndex, asset] of assets.entries()) {
      const lot = layout.lots.get(asset.id)!;
      const d = layout.districts.find((x) => x.id === lot.district)!;
      const tier = tierFor(asset.weightPct);
      // A position sold out of stands in ruins: same lot, same data, nobody inside.
      const site = asset.closed ? createRuins(asset, tier) : createSite(asset, tier, asset.marketValueEur === null);
      const footprint = footprintFor(asset.weightPct);
      // Portfolio holdings are the landmarks; give them extra visual mass and vertical presence.
      const targetScale = (footprint / NOMINAL[tier]) * 1.28;
      const previousScale = previousScales.get(asset.id);
      const shouldAnimate = !reduced && (previousScale === undefined || Math.abs(previousScale - targetScale) > 0.015);
      const startScale = reduced ? targetScale : previousScale ?? targetScale * 0.52;
      const groundY = layout.terrain.heightAt(lot.x, lot.z);
      site.group.position.set(lot.x, groundY, lot.z);
      site.group.rotation.y = lot.rotationY;
      site.group.scale.setScalar(startScale);
      site.mesh.userData.assetId = asset.id;
      site.brandPlate.userData.assetId = asset.id;
      scene.add(site.group);
      siteMeshes.push(site.mesh, site.brandPlate);

      sites.set(asset.id, {
        asset,
        lot,
        site,
        footprint,
        groundY,
        scale: startScale,
        scaleFrom: startScale,
        scaleTarget: targetScale,
        scaleElapsedMs: shouldAnimate ? 0 : 900,
        scaleDelayMs: shouldAnimate && previousScale === undefined ? (assetIndex % 16) * 42 : 0,
        scaleDurationMs: 900,
        opacity: 1,
        applied: 1,
        targetOpacity: 1,
        route: routeToPlaza(lot, d, layout),
      });
    }
    frameSun();
    applyShadows();
    rebuildAgents();
    ctrl.hero(true);
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

  const syncHighlights = () => {
    for (const s of sites.values()) {
      const active = s.asset.id === selected;
      const over = s.asset.id === hovered;
      s.site.material.emissive.setHex(active ? 0x302714 : over ? 0x1d5f7a : 0x000000);
      if (!over) s.site.material.emissiveIntensity = 1;
    }
    const e = hovered && hovered !== selected ? sites.get(hovered) : null;
    hoverRing.visible = !!e;
    if (e) {
      hoverRing.position.set(e.lot.x, e.groundY + 0.34, e.lot.z);
      hoverRing.userData.base = e.footprint * 0.86;
      hoverRing.scale.setScalar(e.footprint * 0.86);
    }
  };

  function select(id: string | null) {
    selected = id;
    const e = id ? sites.get(id) : null;
    selectRing.visible = !!e;
    if (e) {
      selectRing.position.set(e.lot.x, e.groundY + 0.3, e.lot.z);
      selectRing.scale.setScalar(e.footprint * 0.78);
    }
    updateRouteHighlight(id);
    syncHighlights();
  }

  function pick(cx: number, cy: number) {
    const id = siteAt(cx, cy);
    if (id) {
      select(id);
      cb.onSelect(id);
      return;
    }
    setRay(cx, cy);
    if (infra) {
      const hitTrain = ray.intersectObject(infra.monoCars, false)[0];
      if (hitTrain) {
        cb.onFollowTarget?.("SkyTrain Monorraíl");
        sound.playWhoosh();
        ctrl.follow(() => infra!.getMonorailPosition(0));
        return;
      }
    }
    if (town && town.districtLabels.length > 0) {
      const visibleLabels = town.districtLabels.filter((l) => l.visible);
      const hitLabel = ray.intersectObjects(visibleLabels, false)[0];
      if (hitLabel && hitLabel.object.userData.district) {
        const distId = hitLabel.object.userData.district as string;
        const d = layout.districts.find((x) => x.id === distId);
        if (d) {
          sound.playWhoosh();
          ctrl.focus(d.cx, d.cz, Math.max(d.halfW, d.halfH) * 2.6 + 22);
          return;
        }
      }
    }
    const idx = agents.pickAgent(ray);
    if (idx >= 0) {
      const assetId = agents.assetOf(idx);
      const role = agents.roleOf(idx);
      let desc = "ciudadano";
      if (assetId) {
        const ent = sites.get(assetId);
        desc = ent?.asset.name ? `empleado de ${ent.asset.name}` : `empleado de ${assetId}`;
      } else if (role === "courier") {
        desc = "repartidor";
      } else if (role === "manager") {
        desc = "gestor";
      }
      cb.onFollowTarget?.(desc);
      sound.playWhoosh();
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
      syncHighlights();
      cb.onHover(id);
    }
  };
  const onLeave = () => {
    hovered = null;
    canvas.style.cursor = "grab";
    syncHighlights();
    cb.onHover(null);
  };
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerleave", onLeave);
  canvas.style.cursor = "grab";

  // --- loop ------------------------------------------------------------------------
  let raf = 0;
  let last = 0;
  let onScreen = true;
  let frames = 0;
  let acc = 0;
  let fps = 0;
  let drawCalls = 0;
  let triangles = 0;
  let lastLod = -1;
  let canBack = false;
  let lastChimeHour = -1;
  const focusedPerf = new Set<string>();

  const lod = (dist: number) => {
    if (town) {
      for (const s of town.districtLabels) {
        s.visible = dist > 55;
        const h = Math.min(7, Math.max(2.2, dist * 0.028));
        s.scale.set(s.userData.aspect * h, h, 1);
      }
    }
    const near = dist < 320;
    agents.setVisible(near);
  };

  const frame = (now: number) => {
    raf = 0;
    if (disposed) return;
    if (document.hidden || !onScreen) {
      last = 0;
      return;
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
        const hasCelebration = p.events.some(
          (e) => e.eventType === "dividend_paid" || e.eventType === "price_move_up" || e.eventType === "earnings_beat"
        );
        if (hasCelebration) sound.playCelebration();
        else sound.playAlert();
        if (p.requestFocus && p.assetId) {
          focusedPerf.add(p.id);
          focusAsset(p.assetId);
        }
      }
      for (const p of r.merged) {
        choreo.extend(p, director.clock);
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
      // The walk shader swings limbs from this clock; it advances with the simulation, so a paused town stands still.
      toyShared.uTime.value += simDt / 1000;
      infra?.update(simDt);
      vehicles?.update(simDt, agents.hour);
      town?.update?.(simDt);
      choreo.update(simDt);
    }

    // Hover: the building under the pointer breathes (glow and ring), so it reads as clickable
    // at any distance and at night. Runs while paused too: the pointer still moves.
    if (hovered && hovered !== selected) {
      const e = sites.get(hovered);
      const beat = reduced ? 0 : Math.sin(performance.now() / 160);
      if (e) e.site.material.emissiveIntensity = 1.6 + 0.6 * beat;
      const base = (hoverRing.userData.base as number | undefined) ?? 1;
      hoverRing.scale.setScalar(base * (1 + 0.05 * beat));
      (hoverRing.material as THREE.MeshBasicMaterial).opacity = 0.7 + 0.25 * beat;
    }

    // Circadian lighting & atmosphere based on the city's 24-hour clock
    const hour = agents.hour;
    const currentHourInt = Math.floor(hour);
    if (lastChimeHour >= 0 && currentHourInt !== lastChimeHour) {
      sound.playChime();
    }
    lastChimeHour = currentHourInt;

    sound.updateWater(ctrl.distance);

    lighting.update(hour, dt, layout.radius, camera);
    post.setNight(lighting.night);

    if (routeMesh) {
      routeMat.opacity = 0.62 + 0.32 * Math.sin(now * 0.0055);
    }

    for (const e of sites.values()) {
      if (e.scaleElapsedMs < e.scaleDurationMs) {
        if (e.scaleDelayMs > 0) {
          e.scaleDelayMs = Math.max(0, e.scaleDelayMs - dt);
        } else {
          e.scaleElapsedMs = Math.min(e.scaleDurationMs, e.scaleElapsedMs + dt);
          const t = e.scaleElapsedMs / e.scaleDurationMs;
          const eased = 1 - Math.pow(1 - t, 3);
          e.scale = e.scaleFrom + (e.scaleTarget - e.scaleFrom) * eased;
          e.site.group.scale.setScalar(e.scale);
        }
      }
    }

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
        m.needsUpdate = true;
      }
      m.depthWrite = next > 0.5;
      const brand = e.site.brandMaterial;
      brand.opacity = next;
      if (brand.transparent !== transparent) {
        brand.transparent = transparent;
        brand.needsUpdate = true;
      }
      brand.depthWrite = next > 0.5;
      e.site.group.visible = e.targetOpacity > 0 || next > 0.01;
    }

    const dist = ctrl.distance;
    if (Math.abs(dist - lastLod) > dist * 0.04 || lastLod < 0) {
      lastLod = dist;
      lod(dist);
    }
    // Thin the fog on a zoomed-out camera so the whole town stays readable.
    if (scene.fog instanceof THREE.FogExp2) scene.fog.density = 0.0008 * Math.min(1, 420 / Math.max(1, ctrl.distance));
    renderer.info.reset();
    post.render();
    drawCalls = renderer.info.render.calls;
    triangles = renderer.info.render.triangles;
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
    if (!disposed) cb.onContextLost();
  };
  canvas.addEventListener("webglcontextlost", onLost);
  applyShadows();
  wake();

  // --- public handle -----------------------------------------------------------------
  function focusAsset(id: string) {
    const e = sites.get(id);
    if (e) {
      sound.playWhoosh();
      ctrl.focus(e.lot.x, e.lot.z, e.footprint * 2.4 + 16);
    }
  }

  function stats(): WorldStats {
    const hour = agents.hour;
    return {
      fps,
      drawCalls,
      triangles,
      agents: agents.activeCount(),
      vehicles: vehicles?.count ?? 0,
      sites: sites.size,
      distance: ctrl.distance,
      clockHour: hour,
      circadianPhase: getCircadianPhase(hour),
      clockLabel: formatClockLabel(hour),
      soundMuted: sound.isMuted(),
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
      if (i >= 0) {
        const e = sites.get(id);
        const name = e?.asset.name ? `empleado de ${e.asset.name}` : `empleado de ${id}`;
        cb.onFollowTarget?.(name);
        ctrl.follow(() => agents.position(i));
      }
    },
    stopFollow: () => {
      ctrl.stopFollow();
      cb.onFollowTarget?.(null);
    },
    followMonorail: () => {
      if (infra) {
        cb.onFollowTarget?.("SkyTrain Monorraíl");
        sound.playWhoosh();
        ctrl.follow(() => infra!.getMonorailPosition(0));
      }
    },
    toggleSound: () => sound.toggleMute(),
    isSoundMuted: () => sound.isMuted(),
    hero: () => ctrl.hero(),
    fit: () => ctrl.fit(),
    toggleTour: () => ctrl.toggleTour(),
    setTour: (a) => ctrl.setTour(a),
    isTouring: () => ctrl.isTouring(),
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
      post.setSettings(QUALITY[q].post);
      resize();
      applyShadows();
      town?.setTreeCount(QUALITY[q].trees);
      town?.fillers.setDensity(QUALITY[q].fillerDensity);
      if (infra) buildVehicles();
      rebuildAgents();
    },
    setHour(h) {
      agents.setHour(h);
    },
    followTrain() {
      if (infra) {
        cb.onFollowTarget?.("Tren de cercanías");
        ctrl.follow(() => infra!.getGroundTrainPosition());
      }
    },
    followAgent(id) {
      const a = agents.professionOf(id);
      cb.onFollowTarget?.(a === "worker" ? "obrero" : a === "executive" ? "ejecutivo" : a === "courier" ? "repartidor" : "analista");
      ctrl.follow(() => agents.position(id));
    },
    crowd: () => ({ people: agents.snapshot(), vehicles: vehicles?.snapshot() ?? [], trains: infra ? [infra.getMonorailPosition(0), infra.getMonorailPosition(1), infra.getGroundTrainPosition()] : [] }),
    focusPoint(x, z, distance) {
      ctrl.focus(x, z, distance);
    },
    sites() {
      return [...sites.values()].map((e) => ({ id: e.asset.id, name: e.asset.name, archetype: e.asset.archetype, tier: tierFor(e.asset.weightPct), family: specFor(e.asset, tierFor(e.asset.weightPct)).main.family, x: e.lot.x, z: e.lot.z, asset: e.asset }));
    },
    setDayMoods(moods) {
      dayMoods = moods;
      choreo.setAllDay(moods);
    },
    setReducedMotion(v) {
      if (v === reduced) return;
      reduced = v;
      choreo.setReducedMotion(v);
      agents.setReducedMotion(v);
      infra?.setReducedMotion(v);
      vehicles?.setReducedMotion(v);
      if (v) {
        for (const e of sites.values()) {
          e.scale = e.scaleTarget;
          e.scaleElapsedMs = e.scaleDurationMs;
          e.scaleDelayMs = 0;
          e.site.group.scale.setScalar(e.scaleTarget);
        }
      }
    },
    stats,
    dispose() {
      disposed = true;
      cancelAnimationFrame(raf);
      io.disconnect();
      ro.disconnect();
      document.removeEventListener("visibilitychange", wake);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
      canvas.removeEventListener("webglcontextlost", onLost);
      ctrl.dispose();
      sound.dispose();
      clearSites();
      clearRouteHighlight();
      routeMat.dispose();
      post.dispose();
      lighting.dispose();
      choreo.dispose();
      town?.dispose();
      infra?.dispose();
      vehicles?.dispose();
      agents.dispose();
      selectRing.geometry.dispose();
      (selectRing.material as THREE.Material).dispose();
      hoverRing.geometry.dispose();
      (hoverRing.material as THREE.Material).dispose();
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
  return handle;
}
