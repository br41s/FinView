import * as THREE from "three";
import type { CityGraph } from "../model/cityGraph";
import { WalkerSim, crowdLevel, getWalkNet, type Profession, type Walker } from "../model/pedestrians";
import { hashString } from "../model/rng";
import { pointAlong, routeLength, sidewalkRoute, type Point } from "../model/routes";
import type { Tier } from "../model/scale";
import type { RoadSegment } from "../model/townLayout";
import type { Archetype } from "../model/types";
import { PeopleRenderer } from "./people";
import type { VehicleSystem } from "./vehicles";

/**
 * Inhabitants (spec §6.2), drawn by `people.ts`.
 *
 * Two kinds of people:
 * 1. Portfolio company staff: stationed at their company's plaza/courtyard, and acting out the
 *    company's financial events (rallies, drops, dividends, expansions) when told to.
 * 2. City walkers: the crowd of the pavements (`model/pedestrians.ts`). Each has one of four
 *    professions (worker, executive, courier, analyst) chosen by the district they set out in, and the
 *    number out and about follows the hour: crowds at the rush hours, a few at night.
 *
 * Event actors (visitors, crews) walk the street route on the pavement. Event vans are driven by
 * `vehicles.ts`, which keeps them on their lane and lets the traffic give way to them.
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

const ROLE_PROFESSION: Record<Role, Profession> = {
  worker: "worker",
  crew: "worker",
  manager: "executive",
  analyst: "analyst",
  courier: "courier",
  visitor: "analyst",
};

const PERSON_SCALE = 1.3;
const TEMP_SLOTS = 48;

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

/** What the agent system needs of the town to place its crowd. */
export interface AgentWorld {
  graph: CityGraph;
  roads: readonly RoadSegment[];
  ground: (x: number, z: number) => number;
}

interface Agent {
  active: boolean;
  temp: boolean;
  /** Part of the pavement crowd (driven by the walker simulation). */
  crowd: Walker | null;
  role: Role;
  prof: Profession;
  state: AgentState;
  assetId: string | null;
  accent: number | null;
  /** 0..1: fades in and out as the crowd swells and thins. */
  vis: number;
  // corporate plaza position
  cx: number;
  cz: number;
  radius: number;
  angle: number;
  frontAngle: number;
  // timers & event overrides
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
}

const blank = (): Agent => ({
  active: false, temp: false, crowd: null, role: "worker", prof: "worker", state: "idle", assetId: null, accent: null, vis: 1,
  cx: 0, cz: 0, radius: 0, angle: 0, frontAngle: 0,
  override: null, overrideUntil: 0,
  path: null, dist: 0, speed: 0, phase: "in", holdState: "idle", holdUntil: 0, holdMs: 0,
  x: 0, z: 0, heading: 0, seed: 0,
});

export class AgentSystem {
  /** Staff + crowd capacity; temporary actors come on top. */
  private readonly people: PeopleRenderer;
  private agents: Agent[] = [];
  private ambientCount = 0;
  private time = 0;
  private clockHour = 8.5; // Start in bustling morning rush hour
  private reduced = false;
  private siteAccent = new Map<string, number>();
  private ground: (x: number, z: number) => number = () => 0;
  private roads: readonly RoadSegment[] = [];
  private walkSim: WalkerSim | null = null;
  private vehicles: VehicleSystem | null = null;
  private spawned = 0;

  constructor(private capacity: number, private crowdCapacity = 0) {
    const total = capacity + crowdCapacity + TEMP_SLOTS;
    this.people = new PeopleRenderer(total);
    for (let i = 0; i < total; i++) this.agents.push(blank());
  }

  /** The instanced meshes to add to the scene. */
  get objects(): THREE.Object3D[] {
    return this.people.meshes;
  }

  setVisible(v: boolean) {
    this.people.setVisible(v);
  }

  /** The agent index under a pointer ray, or -1. */
  pickAgent(raycaster: THREE.Raycaster): number {
    return this.people.pick(raycaster);
  }

  setGround(fn: (x: number, z: number) => number) {
    this.ground = fn;
  }

  /** Streets and pavements: where the crowd walks and the event actors keep to. */
  setWorld(w: AgentWorld) {
    this.ground = w.ground;
    this.roads = w.roads;
    this.walkSim = new WalkerSim(getWalkNet(w.graph), 0x5eed);
  }

  setVehicles(v: VehicleSystem | null) {
    this.vehicles = v;
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

  /** (Re)fill the population: portfolio company staff + the pavement crowd. */
  populate(sites: readonly SiteSpot[], _routes: Point[][] = []) {
    void _routes;
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

    // 1. Portfolio company staff: stationed directly at their corporate site podium.
    for (const s of order) {
      const companyStaffCount = 1 + ["outpost", "small", "campus", "major"].indexOf(s.tier);
      for (let k = 0; k < companyStaffCount && n < this.capacity; k++) {
        const idx = n++;
        const a = this.agents[idx];
        const seed = hashString(`${s.assetId}:staff:${k}`);
        a.active = true;
        a.assetId = s.assetId;
        a.accent = s.accent ?? null;
        const roles = roleMix[s.archetype];
        a.role = roles[k % roles.length];
        a.prof = ROLE_PROFESSION[a.role];
        a.cx = s.x;
        a.cz = s.z;
        // Positioned neatly on the corporate plaza podium / courtyard
        a.radius = s.footprint * 0.44 + (k * 0.48);
        a.frontAngle = Math.atan2(Math.cos(s.rotationY), Math.sin(s.rotationY));
        a.angle = a.frontAngle + ((k - (companyStaffCount - 1) / 2) * 0.42);
        // In normal state, staff are at their post (working or idle), facing the plaza entrance
        a.state = k === 0 ? "working" : "idle";
        a.seed = seed;
        a.x = a.cx + Math.cos(a.angle) * a.radius;
        a.z = a.cz + Math.sin(a.angle) * a.radius;
        a.heading = Math.atan2(s.x - a.x, s.z - a.z);
      }
    }

    // 2. The pavement crowd.
    if (this.walkSim && this.crowdCapacity > 0) {
      this.walkSim.populate(this.crowdCapacity);
      for (const w of this.walkSim.walkers) {
        const a = this.agents[n++];
        a.active = true;
        a.crowd = w;
        a.prof = w.profession;
        a.role = w.profession === "worker" ? "worker" : w.profession === "executive" ? "manager" : w.profession === "courier" ? "courier" : "analyst";
        a.state = "walking";
        a.seed = w.seed;
        a.x = w.x;
        a.z = w.z;
        a.heading = w.heading;
        a.vis = 0;
      }
    }
    this.ambientCount = n;
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

  /** A temporary actor that walks `route` (on the pavement), performs event action, then walks back. */
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
    const first = this.capacity + this.crowdCapacity;
    for (let i = first; i < this.agents.length; i++) {
      const a = this.agents[i];
      if (a.active) continue;
      Object.assign(a, blank());
      const side = this.spawned++ % 2 === 0 ? 1 : -1;
      const walk = this.roads.length > 0 ? sidewalkRoute(o.route, this.roads, side) : o.route;
      const path = walk.map((p, j, arr) =>
        j === arr.length - 1 ? { x: p.x + (o.offsetX ?? 0), z: p.z + (o.offsetZ ?? 0) } : p);
      a.active = true;
      a.temp = true;
      a.role = o.role;
      a.prof = ROLE_PROFESSION[o.role];
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
      a.x = path[0].x;
      a.z = path[0].z;
      return i;
    }
    return -1;
  }

  /** An event van: it drives the street route on its lane, and the traffic gives way to it. */
  sendVan(route: Point[], tint: number, speed = 3.4, onDone?: () => void) {
    if (this.vehicles) this.vehicles.sendVan(route, tint, speed, onDone);
    else onDone?.();
  }

  firstAgentOf(assetId: string): number {
    for (let i = 0; i < this.ambientCount; i++) if (this.agents[i].assetId === assetId) return i;
    return -1;
  }

  position(id: number): Point | null {
    const a = this.agents[id];
    return a?.active && a.vis > 0.05 ? { x: a.x, z: a.z } : null;
  }

  stateOf(id: number): AgentState | null {
    const a = this.agents[id];
    return a?.active ? (a.override ?? a.state) : null;
  }

  activeCount(): number {
    let n = 0;
    for (const a of this.agents) if (a.active && a.vis > 0.5) n++;
    return n;
  }

  update(dtMs: number) {
    this.time += dtMs;
    const dt = dtMs / 1000;
    // Advance simulated city clock (smooth 24-hour cycle)
    this.clockHour = (this.clockHour + dt / 45) % 24;

    if (this.walkSim && !this.reduced) this.walkSim.step(dt, crowdLevel(this.clockHour));
    for (const a of this.agents) {
      if (!a.active) continue;
      if (a.temp) this.stepTemp(a, dt);
      else if (a.crowd) this.stepCrowd(a, dt);
      else this.stepStaff(a, dt);
    }
    this.writeAll();
  }

  private stepCrowd(a: Agent, dt: number) {
    const w = a.crowd!;
    a.x = w.x;
    a.z = w.z;
    a.heading = w.heading;
    const target = w.moving ? 1 : 0;
    a.vis += Math.sign(target - a.vis) * Math.min(Math.abs(target - a.vis), dt * 2.5);
  }

  private stepStaff(a: Agent, dt: number) {
    if (this.reduced) return;
    if (a.override && this.time >= a.overrideUntil) a.override = null;
    if (a.override) {
      // Active event reaction: face forward into the courtyard/plaza, celebrate or react
      const door = a.frontAngle;
      let d = door - a.angle;
      d = Math.atan2(Math.sin(d), Math.cos(d));
      const step = 2.2 * dt;
      if (Math.abs(d) > step) a.angle += Math.sign(d) * step;
      else a.angle = door;
    }
    // Staff stand at their post at the headquarters plaza
    a.x = a.cx + Math.cos(a.angle) * a.radius;
    a.z = a.cz + Math.sin(a.angle) * a.radius;
    a.heading = Math.atan2(a.cx - a.x, a.cz - a.z);
    if (!a.override) a.state = a.state === "working" ? "working" : "idle";
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

  private writeAll() {
    const t = this.time / 1000;
    this.people.begin();
    for (let i = 0; i < this.agents.length; i++) {
      const a = this.agents[i];
      if (!a.active || a.vis < 0.03) continue;
      const st = a.override ?? a.state;
      const moving = a.crowd ? true : st === "walking" || st === "delivering" || st === "returning";
      const ph = t * 7.4;
      let y = this.ground(a.x, a.z);
      let scale = PERSON_SCALE * (a.vis < 1 ? 0.4 + 0.6 * a.vis : 1);
      let yaw = a.heading;
      if (!this.reduced) {
        if (st === "working") y += Math.abs(Math.sin(ph * 0.22 + a.seed)) * 0.05;
        else if (st === "celebrating") {
          y += Math.abs(Math.sin(t * 6.8 + a.seed)) * 0.5;
          yaw += Math.sin(t * 4 + a.seed) * 0.28;
        } else if (st === "concerned") {
          scale *= 0.94;
          yaw += Math.sin(t * 1.5 + a.seed) * 0.42;
        } else if (st === "investigating") yaw += Math.sin(t * 1.2 + a.seed) * 0.48;
      }
      this.people.add(a.prof, {
        x: a.x, y, z: a.z, yaw, scale,
        skin: a.seed % 6,
        walk: moving && !this.reduced ? 1 : 0,
        phase: (a.seed % 628) / 100,
        owner: i,
      });
    }
    this.people.end();
  }

  dispose() {
    this.people.dispose();
  }

  assetOf(id: number): string | null {
    const a = this.agents[id];
    return a?.active ? a.assetId : null;
  }

  roleOf(id: number): Role {
    const a = this.agents[id];
    return a?.active ? a.role : "worker";
  }

  /** Dev handle: every visible person with their profession. */
  snapshot(): Array<{ id: number; x: number; z: number; profession: string; crowd: boolean }> {
    const out: Array<{ id: number; x: number; z: number; profession: string; crowd: boolean }> = [];
    this.agents.forEach((a, id) => {
      if (a.active && a.vis > 0.5) out.push({ id, x: a.x, z: a.z, profession: a.prof, crowd: !!a.crowd });
    });
    return out;
  }

  professionOf(id: number): Profession {
    const a = this.agents[id];
    return a?.active ? a.prof : "worker";
  }
}
