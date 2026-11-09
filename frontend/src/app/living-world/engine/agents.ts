import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { hashString, seeded } from "../model/rng";
import { pointAlong, routeLength, type Point } from "../model/routes";
import type { Archetype } from "../model/types";
import type { Tier } from "../model/scale";

/**
 * Inhabitants and vehicles (spec §6.2).
 *
 * Dual simulation rules:
 * 1. "Atrezzo" (filler ambient citizens and vehicles):
 *    - Rendered in pure architectural monochrome grayscale (concrete, slate, graphite).
 *    - Follow a 24-hour circadian city routine:
 *      • 07:30–09:30 (Hora punta mañana): Commuters briskly walking to work with backpacks/briefcases.
 *      • 09:30–17:30 (Jornada laboral): Most citizens remain inside or at workstations; streets quiet down to couriers & vans.
 *      • 17:30–21:30 (Tarde de ocio): Citizens head to plazas, parks, and retail avenues; social chatting clusters.
 *      • 21:30–07:30 (Noche): Low-density night strollers and maintenance crew.
 * 2. "Portfolio Company Staff":
 *    - Wear vibrant corporate colors and role accessories.
 *    - Stationed strictly at their corporate headquarters (plaza podium / courtyard).
 *    - Actions are EXCLUSIVELY driven by corporate financial events (rallies, drops, dividends, expansions).
 */

export type Role = "worker" | "manager" | "analyst" | "courier" | "visitor" | "crew";
export type AgentState =
  | "idle"
  | "working"
  | "walking"
  | "investigating"
  | "celebrating"
  | "concerned"
  | "delivering"
  | "returning";

export type CircadianPhase = "morning_rush" | "workday" | "evening_leisure" | "night";

export function getCircadianPhase(hour: number): CircadianPhase {
  if (hour >= 7.5 && hour < 9.5) return "morning_rush";
  if (hour >= 9.5 && hour < 17.5) return "workday";
  if (hour >= 17.5 && hour < 21.5) return "evening_leisure";
  return "night";
}

const ROLE_COLOR: Record<Role, number> = {
  worker: 0x3b82f6,
  manager: 0x7c3aed,
  analyst: 0x10b981,
  courier: 0xf59e0b,
  visitor: 0xec4899,
  crew: 0xf97316,
};
const SKIN = [0xf1c9a5, 0xd9a47e, 0xb97c56, 0x8d5a3b, 0xf6d9bf];

/** Architectural grayscale palette for ambient city inhabitants ("atrezzo"). */
const ATREZZO_BODY = [0x484d56, 0x5d636e, 0x727986, 0x8c93a0, 0xa5abb8];
const ATREZZO_HEAD = [0xd6dae0, 0xc4c9d0, 0xb1b7c0, 0x9ea4ad];
const ATREZZO_VAN = [0x8b919b, 0xa7adb8, 0xc2c7cf, 0x6e737c];

const AGENT_SCALE = 1.32;
const TEMP_SLOTS = 48;
const MAX_VANS = 28;

export interface SiteSpot {
  assetId: string;
  archetype: Archetype;
  x: number;
  z: number;
  rotationY: number;
  footprint: number;
  tier: Tier;
  accent?: number;
  walkRoute?: Point[];
}

interface Agent {
  active: boolean;
  temp: boolean;
  ambientCity: boolean;
  role: Role;
  state: AgentState;
  assetId: string | null;
  accent: number | null;
  // corporate plaza or sidewalk position
  cx: number;
  cz: number;
  radius: number;
  angle: number;
  angVel: number;
  frontAngle: number;
  walkRoute: Point[] | null;
  walkDistance: number;
  walkDirection: 1 | -1;
  // timers & event overrides
  until: number;
  override: AgentState | null;
  overrideUntil: number;
  // path mode (temporary actors)
  path: Point[] | null;
  dist: number;
  speed: number;
  phase: "in" | "hold" | "out";
  holdState: AgentState;
  holdUntil: number;
  holdMs: number;
  // pose
  x: number;
  z: number;
  heading: number;
  seed: number;
  rnd: () => number;
}

interface Van {
  active: boolean;
  path: Point[];
  dist: number;
  dir: 1 | -1;
  speed: number;
  hold: number;
  ambient: boolean;
  tint: number;
  x: number;
  z: number;
  heading: number;
  onDone: (() => void) | null;
}

const blank = (): Agent => ({
  active: false, temp: false, ambientCity: false, role: "worker", state: "idle", assetId: null, accent: null,
  cx: 0, cz: 0, radius: 0, angle: 0, angVel: 0, frontAngle: 0,
  walkRoute: null, walkDistance: 0, walkDirection: 1,
  until: 0, override: null, overrideUntil: 0,
  path: null, dist: 0, speed: 0, phase: "in", holdState: "idle", holdUntil: 0, holdMs: 0,
  x: 0, z: 0, heading: 0, seed: 0, rnd: () => 0.5,
});

export class AgentSystem {
  readonly bodies: THREE.InstancedMesh;
  readonly heads: THREE.InstancedMesh;
  readonly vans: THREE.InstancedMesh;
  readonly helmets: THREE.InstancedMesh;
  readonly backpacks: THREE.InstancedMesh;
  readonly briefcases: THREE.InstancedMesh;
  readonly ties: THREE.InstancedMesh;
  readonly clipboards: THREE.InstancedMesh;
  readonly shoppingBags: THREE.InstancedMesh;
  private agents: Agent[] = [];
  private ambientCount = 0;
  private vanList: Van[] = [];
  private time = 0;
  private clockHour = 8.5; // Start in bustling morning rush hour
  private reduced = false;
  private m = new THREE.Matrix4();
  private q = new THREE.Quaternion();
  private p = new THREE.Vector3();
  private s = new THREE.Vector3();
  private up = new THREE.Vector3(0, 1, 0);
  private c = new THREE.Color();
  private ambientRoutes: Point[][] = [];
  private siteAccent = new Map<string, number>();
  private ground: (x: number, z: number) => number = () => 0;

  constructor(private capacity: number) {
    const total = capacity + TEMP_SLOTS;
    const bodyParts: THREE.BufferGeometry[] = [];
    const torso = new THREE.BoxGeometry(0.36, 0.43, 0.23);
    torso.translate(0, 0.37, 0);
    bodyParts.push(torso);
    const shoulders = new THREE.BoxGeometry(0.48, 0.14, 0.25);
    shoulders.translate(0, 0.57, 0);
    bodyParts.push(shoulders);
    for (const side of [-1, 1]) {
      const arm = new THREE.CylinderGeometry(0.065, 0.08, 0.34, 6);
      arm.rotateZ(side * 0.12);
      arm.translate(side * 0.24, 0.37, 0);
      bodyParts.push(arm);
      const leg = new THREE.CylinderGeometry(0.07, 0.08, 0.28, 6);
      leg.translate(side * 0.105, 0.1, 0);
      bodyParts.push(leg);
      const shoe = new THREE.BoxGeometry(0.15, 0.075, 0.24);
      shoe.translate(side * 0.105, 0.038, 0.045);
      bodyParts.push(shoe);
    }
    const bodyGeo = mergeGeometries(bodyParts, false);
    bodyParts.forEach((part) => part.dispose());
    const headGeo = new THREE.SphereGeometry(0.18, 10, 8);
    headGeo.translate(0, 0.79, 0);
    const flat = (vc: boolean) => new THREE.MeshLambertMaterial({ flatShading: true, vertexColors: vc });
    this.bodies = new THREE.InstancedMesh(bodyGeo, flat(false), total);
    this.heads = new THREE.InstancedMesh(headGeo, flat(false), total);
    this.bodies.castShadow = true;
    this.heads.castShadow = true;
    this.bodies.frustumCulled = false;
    this.heads.frustumCulled = false;

    const vb = new THREE.BoxGeometry(1.3, 0.55, 0.7);
    vb.translate(0, 0.45, 0);
    const cab = new THREE.BoxGeometry(0.5, 0.45, 0.66);
    cab.translate(0.78, 0.4, 0);
    const win = new THREE.BoxGeometry(0.06, 0.22, 0.5);
    win.translate(1.05, 0.5, 0);
    const wheels = [-0.45, 0.55].flatMap((x) => [-0.36, 0.36].map((z) => {
      const w = new THREE.CylinderGeometry(0.17, 0.17, 0.12, 8);
      w.rotateX(Math.PI / 2);
      w.translate(x, 0.17, z);
      return w;
    }));
    const paint = (g: THREE.BufferGeometry, hex: number) => {
      const col = new THREE.Color(hex);
      const n = g.getAttribute("position").count;
      const a = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) a.set([col.r, col.g, col.b], i * 3);
      g.setAttribute("color", new THREE.BufferAttribute(a, 3));
      g.deleteAttribute("uv");
    };
    paint(vb, 0xffffff);
    paint(cab, 0xf2f2f2);
    paint(win, 0x39424f);
    wheels.forEach((w) => paint(w, 0x2b2f38));
    const vanGeo = mergeGeometries([vb, cab, win, ...wheels], false);
    this.vans = new THREE.InstancedMesh(vanGeo, flat(true), MAX_VANS);
    this.vans.castShadow = true;
    this.vans.frustumCulled = false;
    this.vans.count = 0;

    const helmetTop = new THREE.SphereGeometry(0.2, 8, 5, 0, Math.PI * 2, 0, Math.PI / 2);
    helmetTop.translate(0, 1.0, 0);
    const helmetBrim = new THREE.CylinderGeometry(0.23, 0.23, 0.045, 8);
    helmetBrim.translate(0, 0.96, 0);
    const helmetGeo = mergeGeometries([helmetTop, helmetBrim], false);
    helmetTop.dispose();
    helmetBrim.dispose();
    const backpackGeo = new THREE.BoxGeometry(0.28, 0.34, 0.16);
    backpackGeo.translate(0, 0.55, -0.21);
    const briefcaseBody = new THREE.BoxGeometry(0.28, 0.18, 0.09);
    briefcaseBody.translate(0.22, 0.43, 0.13);
    const briefcaseHandle = new THREE.BoxGeometry(0.12, 0.035, 0.045);
    briefcaseHandle.translate(0.22, 0.54, 0.13);
    const briefcaseGeo = mergeGeometries([briefcaseBody, briefcaseHandle], false);
    briefcaseBody.dispose();
    briefcaseHandle.dispose();
    const tieKnot = new THREE.BoxGeometry(0.1, 0.08, 0.07);
    tieKnot.translate(0, 0.59, 0.15);
    const tieTail = new THREE.ConeGeometry(0.075, 0.28, 4);
    tieTail.rotateX(Math.PI);
    tieTail.translate(0, 0.42, 0.16);
    const tieGeo = mergeGeometries([tieKnot, tieTail], false);
    tieKnot.dispose();
    tieTail.dispose();
    const clipboardBody = new THREE.BoxGeometry(0.2, 0.31, 0.035);
    clipboardBody.translate(-0.2, 0.5, 0.15);
    const clipboardClip = new THREE.BoxGeometry(0.075, 0.045, 0.045);
    clipboardClip.translate(-0.2, 0.67, 0.17);
    const clipboardGeo = mergeGeometries([clipboardBody, clipboardClip], false);
    clipboardBody.dispose();
    clipboardClip.dispose();
    const bagBox = new THREE.BoxGeometry(0.2, 0.26, 0.12);
    bagBox.translate(-0.24, 0.35, 0.08);
    const bagHandle = new THREE.BoxGeometry(0.1, 0.045, 0.04);
    bagHandle.translate(-0.24, 0.5, 0.08);
    const bagGeo = mergeGeometries([bagBox, bagHandle], false);
    bagBox.dispose();
    bagHandle.dispose();
    this.helmets = new THREE.InstancedMesh(helmetGeo, flat(false), total);
    this.backpacks = new THREE.InstancedMesh(backpackGeo, flat(false), total);
    this.briefcases = new THREE.InstancedMesh(briefcaseGeo, flat(false), total);
    this.ties = new THREE.InstancedMesh(tieGeo, flat(false), total);
    this.clipboards = new THREE.InstancedMesh(clipboardGeo, flat(false), total);
    this.shoppingBags = new THREE.InstancedMesh(bagGeo, flat(false), total);
    for (const prop of [this.helmets, this.backpacks, this.briefcases, this.ties, this.clipboards, this.shoppingBags]) {
      prop.castShadow = true;
      prop.frustumCulled = false;
    }

    for (let i = 0; i < total; i++) this.agents.push(blank());
  }

  setGround(fn: (x: number, z: number) => number) {
    this.ground = fn;
  }

  setReducedMotion(v: boolean) {
    this.reduced = v;
  }

  get hour(): number {
    return this.clockHour;
  }

  setHour(h: number) {
    this.clockHour = (h % 24 + 24) % 24;
  }

  /** (Re)fill the population: portfolio company workers in color + ambient city walkers in grayscale. */
  populate(sites: readonly SiteSpot[], routes: Point[][]) {
    this.ambientRoutes = routes;
    this.siteAccent.clear();
    for (const s of sites) {
      if (s.accent !== undefined) this.siteAccent.set(s.assetId, s.accent);
    }
    for (let i = 0; i < this.agents.length; i++) this.agents[i] = blank();
    const order = [...sites].sort((a, b) => b.footprint - a.footprint || (a.assetId < b.assetId ? -1 : 1));
    let n = 0;
    const roleMix: Record<Archetype, Role[]> = {
      retail: ["worker", "visitor", "visitor", "manager", "courier"],
      consumer: ["worker", "worker", "visitor", "courier"],
      tech: ["analyst", "manager", "worker", "courier"],
      semis: ["crew", "worker", "analyst", "crew"],
      energy: ["crew", "worker", "courier", "manager"],
      mining: ["crew", "crew", "worker", "courier"],
      banking: ["manager", "analyst", "analyst", "visitor"],
      health: ["worker", "analyst", "manager", "worker"],
      telecom: ["crew", "analyst", "courier"],
      utilities: ["crew", "worker", "courier"],
      realestate: ["manager", "worker", "visitor"],
      fund: ["manager", "analyst", "visitor"],
      cash: ["manager", "courier"],
      crypto: ["analyst", "courier", "manager"],
    };
    const allWalkRoutes = sites.map((s) => s.walkRoute).filter((r): r is Point[] => !!r && r.length > 1);

    // 1. Portfolio Company Staff: stationed directly at their corporate site podium.
    // They wear vivid corporate colours and only act out company-related events.
    for (const s of order) {
      const companyStaffCount = 1 + ["outpost", "small", "campus", "major"].indexOf(s.tier);
      for (let k = 0; k < companyStaffCount && n < this.capacity; k++) {
        const idx = n++;
        const a = this.agents[idx];
        const seed = hashString(`${s.assetId}:staff:${k}`);
        const rnd = seeded(seed);
        a.active = true;
        a.ambientCity = false;
        a.assetId = s.assetId;
        a.accent = s.accent ?? null;
        const roles = roleMix[s.archetype];
        a.role = roles[k % roles.length];
        a.cx = s.x;
        a.cz = s.z;
        // Positioned neatly on the corporate plaza podium / courtyard
        a.radius = s.footprint * 0.44 + (k * 0.48);
        a.frontAngle = Math.atan2(Math.cos(s.rotationY), Math.sin(s.rotationY));
        a.angle = a.frontAngle + ((k - (companyStaffCount - 1) / 2) * 0.42);
        a.angVel = 0;
        a.walkRoute = null;
        a.walkDistance = 0;
        a.walkDirection = 1;
        // In normal state, staff are at their post (working or idle), facing the plaza entrance
        a.state = k === 0 ? "working" : "idle";
        a.until = 4000 + rnd() * 8000;
        a.seed = seed;
        a.rnd = rnd;
        this.place(a);
        a.heading = Math.atan2(s.x - a.x, s.z - a.z);
        this.paint(idx);
      }
    }

    // 2. Grayscale Ambient City Inhabitants ("Atrezzo"): walking the sidewalks and blocks.
    const fillerRng = seeded(0x82a4);
    let routeIdx = 0;
    while (n < this.capacity && allWalkRoutes.length > 0) {
      const idx = n++;
      const a = this.agents[idx];
      const route = allWalkRoutes[routeIdx % allWalkRoutes.length];
      routeIdx++;
      const seed = hashString(`atrezzo:${idx}`);
      const rnd = seeded(seed);
      a.active = true;
      a.ambientCity = true;
      a.assetId = null;
      a.accent = null;
      a.role = (["worker", "visitor", "manager", "courier"] as const)[idx % 4];
      a.walkRoute = route;
      const rLen = routeLength(route);
      a.walkDistance = fillerRng() * rLen;
      a.walkDirection = fillerRng() < 0.5 ? 1 : -1;
      a.state = "walking";
      a.until = 3000 + rnd() * 6000;
      a.seed = seed;
      a.rnd = rnd;
      const point = pointAlong(route, a.walkDistance);
      a.x = point.x;
      a.z = point.z;
      a.heading = a.walkDirection === 1 ? point.heading : point.heading + Math.PI;
      this.paint(idx);
    }
    this.ambientCount = n;
    this.syncVans();
    this.writeAll();
  }

  /** Ambient vans drive plaza ↔ district avenues in grayscale ("atrezzo"). */
  private syncVans() {
    this.vanList = this.vanList.filter((v) => !v.ambient);
    const k = Math.min(10, this.ambientRoutes.length, MAX_VANS - this.vanList.length);
    const r = seeded(0x7a11);
    for (let i = 0; i < k; i++) {
      const route = this.ambientRoutes[Math.floor(r() * this.ambientRoutes.length)];
      const tint = ATREZZO_VAN[i % ATREZZO_VAN.length];
      this.vanList.push({
        active: true, path: route, dist: r() * routeLength(route), dir: r() < 0.5 ? 1 : -1,
        speed: 2.2 + r() * 1.2, hold: 0, ambient: true, tint, x: 0, z: 0, heading: 0, onDone: null,
      });
    }
  }

  /** Dispatch the site's own corporate staff for an event reaction. */
  dispatch(assetId: string, state: AgentState, durationMs: number, max = 3) {
    let k = 0;
    for (let i = 0; i < this.ambientCount && k < max; i++) {
      const a = this.agents[i];
      if (a.assetId !== assetId || !a.active) continue;
      a.override = state;
      a.overrideUntil = this.time + durationMs;
      k++;
    }
    return k;
  }

  /** A temporary actor that walks `route`, performs event action, then walks back. */
  spawnActor(o: {
    role: Role;
    route: Point[];
    speed?: number;
    holdState: AgentState;
    holdMs: number;
    assetId: string | null;
    offsetX?: number;
    offsetZ?: number;
  }): number {
    for (let i = this.capacity; i < this.agents.length; i++) {
      const a = this.agents[i];
      if (a.active) continue;
      Object.assign(a, blank());
      const path = o.route.map((p, j, arr) =>
        j === arr.length - 1 ? { x: p.x + (o.offsetX ?? 0), z: p.z + (o.offsetZ ?? 0) } : p);
      a.active = true;
      a.temp = true;
      a.ambientCity = false;
      a.role = o.role;
      a.assetId = o.assetId;
      a.accent = o.assetId ? (this.siteAccent.get(o.assetId) ?? null) : null;
      a.path = path;
      a.dist = 0;
      a.speed = o.speed ?? 2.5;
      a.phase = "in";
      a.state = "walking";
      a.holdState = o.holdState;
      a.holdMs = o.holdMs;
      a.seed = hashString(`${i}:${this.time}`);
      a.rnd = seeded(a.seed);
      a.x = path[0].x;
      a.z = path[0].z;
      this.paint(i);
      return i;
    }
    return -1;
  }

  sendVan(route: Point[], tint: number, speed = 3.4, onDone?: () => void) {
    if (this.vanList.length >= MAX_VANS) {
      const i = this.vanList.findIndex((v) => v.ambient);
      if (i < 0) return;
      this.vanList.splice(i, 1);
    }
    this.vanList.push({
      active: true, path: route, dist: 0, dir: 1, speed, hold: 0, ambient: false, tint, x: route[0].x, z: route[0].z,
      heading: 0, onDone: onDone ?? null,
    });
  }

  firstAgentOf(assetId: string): number {
    for (let i = 0; i < this.ambientCount; i++) if (this.agents[i].assetId === assetId) return i;
    return -1;
  }

  position(id: number): Point | null {
    const a = this.agents[id];
    return a?.active ? { x: a.x, z: a.z } : null;
  }

  stateOf(id: number): AgentState | null {
    const a = this.agents[id];
    return a?.active ? (a.override ?? a.state) : null;
  }

  private paint(i: number) {
    const a = this.agents[i];
    if (a.ambientCity) {
      this.bodies.setColorAt(i, this.c.set(ATREZZO_BODY[a.seed % ATREZZO_BODY.length]));
      this.heads.setColorAt(i, this.c.set(ATREZZO_HEAD[a.seed % ATREZZO_HEAD.length]));
      this.helmets.setColorAt(i, this.c.set(0x767c86));
      this.backpacks.setColorAt(i, this.c.set(0x4f545e));
      this.briefcases.setColorAt(i, this.c.set(0x383c44));
      this.ties.setColorAt(i, this.c.set(0x656a73));
      this.clipboards.setColorAt(i, this.c.set(0x9ca2ac));
    } else {
      const bodyHex = a.accent ?? ROLE_COLOR[a.role];
      this.bodies.setColorAt(i, this.c.set(bodyHex));
      this.heads.setColorAt(i, this.c.set(SKIN[a.seed % SKIN.length]));
      this.helmets.setColorAt(i, this.c.set(a.role === "crew" ? 0xf97316 : 0xfacc15));
      this.backpacks.setColorAt(i, this.c.set(a.role === "courier" ? 0xf59e0b : (a.accent ?? 0x3b82f6)));
      this.briefcases.setColorAt(i, this.c.set(a.accent ?? 0x1d4ed8));
      this.ties.setColorAt(i, this.c.set(0xe11d48));
      this.clipboards.setColorAt(i, this.c.set(0xf8fafc));
    }
    const bagPalette = [0xf97316, 0x06b6d4, 0x8b5cf6, 0xec4899, 0xeab308];
    this.shoppingBags.setColorAt(i, this.c.set(bagPalette[a.seed % bagPalette.length]));
    for (const mesh of [this.bodies, this.heads, this.helmets, this.backpacks, this.briefcases, this.ties, this.clipboards, this.shoppingBags]) {
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }
  }

  activeCount(): number {
    let n = 0;
    for (const a of this.agents) if (a.active) n++;
    return n;
  }

  private place(a: Agent) {
    a.x = a.cx + Math.cos(a.angle) * a.radius;
    a.z = a.cz + Math.sin(a.angle) * a.radius;
  }

  update(dtMs: number) {
    this.time += dtMs;
    const dt = dtMs / 1000;
    // Advance simulated city clock (smooth 24-hour cycle)
    this.clockHour = (this.clockHour + dt / 45) % 24;

    for (const a of this.agents) {
      if (!a.active) continue;
      if (a.temp) this.stepTemp(a, dt);
      else this.stepAmbient(a, dtMs, dt);
    }
    this.stepVans(dt);
    this.writeAll();
  }

  private stepAmbient(a: Agent, dtMs: number, dt: number) {
    if (this.reduced) return;
    if (a.override && this.time >= a.overrideUntil) a.override = null;

    // 1. Corporate Company Staff: Event-driven only.
    if (!a.ambientCity && a.assetId !== null) {
      if (a.override) {
        // Active event reaction: face forward into the courtyard/plaza, celebrate or react
        const door = a.frontAngle;
        let d = door - a.angle;
        d = Math.atan2(Math.sin(d), Math.cos(d));
        const step = 2.2 * dt;
        if (Math.abs(d) > step) a.angle += Math.sign(d) * step;
        else a.angle = door;
        this.place(a);
        a.heading = Math.atan2(a.cx - a.x, a.cz - a.z);
        return;
      }
      // Normal state: stationary at the corporate headquarters plaza
      this.place(a);
      a.heading = Math.atan2(a.cx - a.x, a.cz - a.z);
      a.state = "idle";
      return;
    }

    // 2. Grayscale Ambient City Inhabitants ("Atrezzo"): Follow Circadian Routine
    const phase = getCircadianPhase(this.clockHour);
    if (a.walkRoute && a.walkRoute.length > 1) {
      const length = routeLength(a.walkRoute);
      let speedMult = 1.0;

      if (phase === "morning_rush") {
        // Brisk commute to work
        speedMult = 1.65;
        a.state = "walking";
      } else if (phase === "workday") {
        // Mostly working indoors; couriers keep delivering, others take brief walks
        if (a.role === "courier") {
          speedMult = 1.35;
          a.state = "delivering";
        } else if (a.seed % 3 === 0) {
          speedMult = 0.9;
          a.state = "walking";
        } else {
          // Stationary working / outside office entrance
          a.state = "working";
          speedMult = 0;
        }
      } else if (phase === "evening_leisure") {
        // Relaxed stroll to plaza, shopping, socializing
        speedMult = 1.1;
        a.state = a.seed % 4 === 0 ? "idle" : "walking";
      } else {
        // Night stillness
        speedMult = a.seed % 4 === 0 ? 0.75 : 0;
        a.state = speedMult === 0 ? "idle" : "walking";
      }

      if (speedMult > 0) {
        a.walkDistance += a.walkDirection * (1.18 + a.rnd() * 0.35) * speedMult * dt;
        if (a.walkDistance >= length) {
          a.walkDistance = length;
          a.walkDirection = -1;
        } else if (a.walkDistance <= 0) {
          a.walkDistance = 0;
          a.walkDirection = 1;
        }
        const point = pointAlong(a.walkRoute, a.walkDistance);
        a.x = point.x;
        a.z = point.z;
        a.heading = a.walkDirection === 1 ? point.heading : point.heading + Math.PI;
      }
      return;
    }

    // Fallback circular orbit for non-route ambient
    a.until -= dtMs;
    if (a.until <= 0) {
      a.state = a.rnd() < 0.5 ? "walking" : "idle";
      a.until = 3000 + a.rnd() * 6000;
    }
    if (a.state === "walking") {
      a.angle += a.angVel * dt;
      this.place(a);
      a.heading = Math.atan2(-Math.sin(a.angle), Math.cos(a.angle));
    } else {
      this.place(a);
      a.heading = Math.atan2(a.cx - a.x, a.cz - a.z);
    }
  }

  private stepTemp(a: Agent, dt: number) {
    const path = a.path!;
    const len = routeLength(path);
    if (a.phase === "in") {
      a.dist += a.speed * dt;
      if (a.dist >= len) {
        a.phase = "hold";
        a.state = a.holdState;
        a.holdUntil = this.time + a.holdMs;
      }
    } else if (a.phase === "hold") {
      if (this.time >= a.holdUntil) {
        a.phase = "out";
        a.state = "returning";
      }
    } else {
      a.dist -= a.speed * dt;
      if (a.dist <= 0) {
        a.active = false;
        return;
      }
    }
    const pt = pointAlong(path, a.dist);
    a.x = pt.x;
    a.z = pt.z;
    if (a.phase === "in") a.heading = pt.heading;
    else if (a.phase === "out") a.heading = pt.heading + Math.PI;
  }

  private stepVans(dt: number) {
    for (const v of this.vanList) {
      if (!v.active || (this.reduced && v.ambient)) continue;
      const len = routeLength(v.path);
      if (v.hold > 0) {
        v.hold -= dt;
        if (v.hold <= 0) {
          if (v.ambient) v.dir = (v.dir === 1 ? -1 : 1);
          else {
            v.dir = -1;
          }
        }
      } else {
        v.dist += v.dir * v.speed * dt;
        if (v.dist >= len || v.dist <= 0) {
          v.dist = Math.min(len, Math.max(0, v.dist));
          if (!v.ambient && v.dir === -1) {
            v.active = false;
            v.onDone?.();
            continue;
          }
          v.hold = v.ambient ? 1.5 : 1.6;
          if (!v.ambient && v.dir === 1) v.onDone?.();
        }
      }
      const pt = pointAlong(v.path, v.dist);
      v.x = pt.x;
      v.z = pt.z;
      v.heading = v.dir === 1 ? pt.heading : pt.heading + Math.PI;
    }
    this.vanList = this.vanList.filter((v) => v.active);
  }

  private writeAll() {
    const t = this.time / 1000;
    for (let i = 0; i < this.agents.length; i++) {
      const a = this.agents[i];
      if (!a.active) {
        this.p.set(0, -50, 0);
        this.s.set(0, 0, 0);
        this.q.identity();
        this.m.compose(this.p, this.q, this.s);
        this.bodies.setMatrixAt(i, this.m);
        this.heads.setMatrixAt(i, this.m);
        this.helmets.setMatrixAt(i, this.m);
        this.backpacks.setMatrixAt(i, this.m);
        this.briefcases.setMatrixAt(i, this.m);
        this.ties.setMatrixAt(i, this.m);
        this.clipboards.setMatrixAt(i, this.m);
        this.shoppingBags.setMatrixAt(i, this.m);
        continue;
      }
      const st = a.override ?? a.state;
      const moving = st === "walking" || st === "delivering" || st === "returning";
      const ph = t * (moving ? 7.2 : 2.4) + a.seed;
      let y = this.ground(a.x, a.z);
      let sy = 1;
      let yaw = a.heading;
      if (!this.reduced) {
        if (moving) y += Math.abs(Math.sin(ph)) * 0.08;
        else if (st === "working") y += Math.abs(Math.sin(ph * 1.6)) * 0.05;
        else if (st === "celebrating") {
          y += Math.abs(Math.sin(t * 6.8 + a.seed)) * 0.42;
          yaw += Math.sin(t * 4 + a.seed) * 0.28;
        }
        else if (st === "concerned") {
          sy = 0.92;
          yaw += Math.sin(t * 1.5 + a.seed) * 0.42;
        }
        else if (st === "investigating") yaw += Math.sin(t * 1.2 + a.seed) * 0.48;
      }
      this.q.setFromAxisAngle(this.up, yaw);
      this.p.set(a.x, y, a.z);
      this.s.set(AGENT_SCALE, AGENT_SCALE * sy, AGENT_SCALE);
      this.m.compose(this.p, this.q, this.s);
      this.bodies.setMatrixAt(i, this.m);
      this.heads.setMatrixAt(i, this.m);
      this.helmets.setMatrixAt(i, this.m);
      this.backpacks.setMatrixAt(i, this.m);
      this.briefcases.setMatrixAt(i, this.m);

      const helmetRole = a.role === "worker" || a.role === "crew";
      const courierRole = a.role === "courier";
      const managerRole = a.role === "manager";
      const analystRole = a.role === "analyst";
      const professionalRole = managerRole || analystRole;
      this.s.set(helmetRole ? AGENT_SCALE : 0, helmetRole ? AGENT_SCALE : 0, helmetRole ? AGENT_SCALE : 0);
      this.m.compose(this.p, this.q, this.s);
      this.helmets.setMatrixAt(i, this.m);
      this.s.set(courierRole ? AGENT_SCALE : 0, courierRole ? AGENT_SCALE : 0, courierRole ? AGENT_SCALE : 0);
      this.m.compose(this.p, this.q, this.s);
      this.backpacks.setMatrixAt(i, this.m);
      this.s.set(professionalRole ? AGENT_SCALE : 0, professionalRole ? AGENT_SCALE : 0, professionalRole ? AGENT_SCALE : 0);
      this.m.compose(this.p, this.q, this.s);
      this.briefcases.setMatrixAt(i, this.m);
      this.s.set(managerRole ? AGENT_SCALE : 0, managerRole ? AGENT_SCALE : 0, managerRole ? AGENT_SCALE : 0);
      this.m.compose(this.p, this.q, this.s);
      this.ties.setMatrixAt(i, this.m);
      this.s.set(analystRole ? AGENT_SCALE : 0, analystRole ? AGENT_SCALE : 0, analystRole ? AGENT_SCALE : 0);
      this.m.compose(this.p, this.q, this.s);
      this.clipboards.setMatrixAt(i, this.m);

      const isEvening = getCircadianPhase(this.clockHour) === "evening_leisure";
      const hasBag = isEvening && a.ambientCity && a.walkRoute && (a.seed % 2 === 0);
      this.s.set(hasBag ? AGENT_SCALE : 0, hasBag ? AGENT_SCALE : 0, hasBag ? AGENT_SCALE : 0);
      this.m.compose(this.p, this.q, this.s);
      this.shoppingBags.setMatrixAt(i, this.m);

      this.s.set(AGENT_SCALE, AGENT_SCALE * sy, AGENT_SCALE);
      this.m.compose(this.p, this.q, this.s);
    }
    this.bodies.instanceMatrix.needsUpdate = true;
    this.heads.instanceMatrix.needsUpdate = true;
    this.helmets.instanceMatrix.needsUpdate = true;
    this.backpacks.instanceMatrix.needsUpdate = true;
    this.briefcases.instanceMatrix.needsUpdate = true;
    this.ties.instanceMatrix.needsUpdate = true;
    this.clipboards.instanceMatrix.needsUpdate = true;
    this.shoppingBags.instanceMatrix.needsUpdate = true;

    this.vans.count = this.vanList.length;
    this.vanList.forEach((v, i) => {
      this.q.setFromAxisAngle(this.up, v.heading - Math.PI / 2);
      this.p.set(v.x, this.ground(v.x, v.z) + 0.1, v.z);
      this.s.set(1.12, 1.12, 1.12);
      this.m.compose(this.p, this.q, this.s);
      this.vans.setMatrixAt(i, this.m);
      this.vans.setColorAt(i, this.c.set(v.tint));
    });
    this.vans.instanceMatrix.needsUpdate = true;
    if (this.vans.instanceColor) this.vans.instanceColor.needsUpdate = true;
  }

  dispose() {
    for (const m of [this.bodies, this.heads, this.vans, this.helmets, this.backpacks, this.briefcases, this.ties, this.clipboards, this.shoppingBags]) {
      m.geometry.dispose();
      (m.material as THREE.Material).dispose();
      m.dispose();
    }
  }

  assetOf(id: number): string | null {
    const a = this.agents[id];
    return a?.active ? a.assetId : null;
  }

  roleOf(id: number): Role {
    const a = this.agents[id];
    return a?.active ? a.role : "worker";
  }
}
