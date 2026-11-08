import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { hashString, seeded } from "../model/rng";
import { pointAlong, routeLength, type Point } from "../model/routes";
import type { Archetype } from "../model/types";
import type { Tier } from "../model/scale";

/**
 * Inhabitants and vehicles (spec §6.2). Ambient life is seeded, not random, so the town
 * looks the same on every visit and an event is never lost in noise. All agents are two
 * InstancedMeshes (bodies, heads), however many there are.
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

const ROLE_COLOR: Record<Role, number> = {
  worker: 0x4f8cd6,
  manager: 0x7a5ad6,
  analyst: 0x2fa38a,
  courier: 0xe0a030,
  visitor: 0xd65f7a,
  crew: 0xf08a2a,
};
const SKIN = [0xf1c9a5, 0xd9a47e, 0xb97c56, 0x8d5a3b, 0xf6d9bf];
const AGENT_SCALE = 1.3;
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
  walkRoute?: Point[];
}

interface Agent {
  active: boolean;
  temp: boolean;
  role: Role;
  state: AgentState;
  assetId: string | null;
  // orbit (ambient) mode
  cx: number;
  cz: number;
  radius: number;
  angle: number;
  angVel: number;
  frontAngle: number;
  walkRoute: Point[] | null;
  walkDistance: number;
  walkDirection: 1 | -1;
  // timers
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
  active: false, temp: false, role: "worker", state: "idle", assetId: null,
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
  private agents: Agent[] = [];
  private ambientCount = 0;
  private vanList: Van[] = [];
  private time = 0;
  private reduced = false;
  private m = new THREE.Matrix4();
  private q = new THREE.Quaternion();
  private p = new THREE.Vector3();
  private s = new THREE.Vector3();
  private up = new THREE.Vector3(0, 1, 0);
  private c = new THREE.Color();
  private ambientRoutes: Point[][] = [];
  private ground: (x: number, z: number) => number = () => 0;

  constructor(private capacity: number) {
    const total = capacity + TEMP_SLOTS;
    // A compact low-poly body with shoulders, arms, legs and shoes reads as a person
    // at town zoom while staying in one instanced draw call.
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

    // Small role props make the crowd legible at town zoom: hard hats, delivery packs,
    // and professional folios. They remain instanced to keep draw calls bounded.
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
    this.helmets = new THREE.InstancedMesh(helmetGeo, flat(false), total);
    this.backpacks = new THREE.InstancedMesh(backpackGeo, flat(false), total);
    this.briefcases = new THREE.InstancedMesh(briefcaseGeo, flat(false), total);
    this.ties = new THREE.InstancedMesh(tieGeo, flat(false), total);
    this.clipboards = new THREE.InstancedMesh(clipboardGeo, flat(false), total);
    for (const prop of [this.helmets, this.backpacks, this.briefcases, this.ties, this.clipboards]) {
      prop.castShadow = true;
      prop.frustumCulled = false;
    }

    for (let i = 0; i < total; i++) this.agents.push(blank());
  }

  /** Height of the road or ground at a point, so people and vans follow hills and bridges. */
  setGround(fn: (x: number, z: number) => number) {
    this.ground = fn;
  }

  setReducedMotion(v: boolean) {
    this.reduced = v;
  }

  /** (Re)fill the ambient population: bigger sites get more people, never past capacity. */
  populate(sites: readonly SiteSpot[], routes: Point[][]) {
    this.ambientRoutes = routes;
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
    outer: for (let round = 0; round < 4; round++) {
      for (const s of order) {
        const want = 1 + ["outpost", "small", "campus", "major"].indexOf(s.tier);
        if (round >= want) continue;
        if (n >= this.capacity) break outer;
        const idx = n++;
        const a = this.agents[idx];
        const seed = hashString(`${s.assetId}:${round}`);
        const rnd = seeded(seed);
        a.active = true;
        a.assetId = s.assetId;
        const roles = roleMix[s.archetype];
        a.role = roles[Math.floor(rnd() * roles.length)];
        a.cx = s.x;
        a.cz = s.z;
        a.radius = s.footprint * 0.55 + 0.9 + rnd() * 0.5;
        a.angle = rnd() * Math.PI * 2;
        a.angVel = (0.25 + rnd() * 0.25) / Math.max(1, a.radius * 0.45) * (rnd() < 0.5 ? -1 : 1);
        a.frontAngle = Math.atan2(Math.cos(s.rotationY), Math.sin(s.rotationY));
        a.walkRoute = s.walkRoute && s.walkRoute.length > 1 ? s.walkRoute : null;
        a.walkDistance = 0;
        a.walkDirection = 1;
        a.state = rnd() < 0.5 ? "working" : "walking";
        a.until = 2000 + rnd() * 6000;
        a.seed = seed;
        a.rnd = rnd;
        this.place(a);
        this.paint(idx);
      }
    }
    this.ambientCount = n;
    this.syncVans();
    this.writeAll();
  }

  /** A few vans drive plaza ↔ district gates all day so the boulevards are never empty. */
  private syncVans() {
    this.vanList = this.vanList.filter((v) => !v.ambient);
    const k = Math.min(10, this.ambientRoutes.length, MAX_VANS - this.vanList.length);
    const r = seeded(0x7a11);
    for (let i = 0; i < k; i++) {
      const route = this.ambientRoutes[Math.floor(r() * this.ambientRoutes.length)];
      this.vanList.push({
        active: true, path: route, dist: r() * routeLength(route), dir: r() < 0.5 ? 1 : -1,
        speed: 2.2 + r() * 1.2, hold: 0, ambient: true, tint: 0xf6efe0, x: 0, z: 0, heading: 0, onDone: null,
      });
    }
  }

  /** Dispatch the site's own people for an event: they walk to the front door and react. */
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

  /** A temporary actor that walks `route` (already trimmed), performs, then walks back. */
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
      a.role = o.role;
      a.assetId = o.assetId;
      a.path = path;
      a.dist = 0;
      a.speed = o.speed ?? 2.4;
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

  /** Index of the first ambient inhabitant of a site, so the camera can follow them. */
  firstAgentOf(assetId: string): number {
    for (let i = 0; i < this.ambientCount; i++) if (this.agents[i].assetId === assetId) return i;
    return -1;
  }

  position(id: number): Point | null {
    const a = this.agents[id];
    return a?.active ? { x: a.x, z: a.z } : null;
  }

  /** Where an agent is, for the camera's follow mode and for tests of the state machine. */
  stateOf(id: number): AgentState | null {
    const a = this.agents[id];
    return a?.active ? (a.override ?? a.state) : null;
  }

  /** Colour depends only on role and seed, so it is written once, not every frame. */
  private paint(i: number) {
    const a = this.agents[i];
    this.bodies.setColorAt(i, this.c.set(ROLE_COLOR[a.role]));
    this.heads.setColorAt(i, this.c.set(SKIN[a.seed % SKIN.length]));
    this.helmets.setColorAt(i, this.c.set(a.role === "crew" ? 0xf28b24 : 0xf0c84e));
    this.backpacks.setColorAt(i, this.c.set(a.role === "courier" ? 0xe3a437 : 0x6b7884));
    this.briefcases.setColorAt(i, this.c.set(a.role === "analyst" ? 0x345f91 : 0x433e52));
    this.ties.setColorAt(i, this.c.set(0xb94e57));
    this.clipboards.setColorAt(i, this.c.set(0x9eafbc));
    for (const mesh of [this.bodies, this.heads, this.helmets, this.backpacks, this.briefcases, this.ties, this.clipboards]) {
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }
  }

  /** Inhabitants currently on stage (ambient plus event actors). */
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
    for (const a of this.agents) {
      if (!a.active) continue;
      if (a.temp) this.stepTemp(a, dt);
      else this.stepAmbient(a, dtMs, dt);
    }
    this.stepVans(dt);
    this.writeAll();
  }

  private stepAmbient(a: Agent, dtMs: number, dt: number) {
    // Reduced motion: the town stands still; only event actors (temp) move.
    if (this.reduced) return;
    if (a.override && this.time >= a.overrideUntil) a.override = null;
    const st = a.override ?? a.state;
    if (a.override) {
      // Walk the ring to the front door, then stand there facing the building.
      const door = a.frontAngle + (((a.seed % 7) - 3) * 0.09);
      let d = door - a.angle;
      d = Math.atan2(Math.sin(d), Math.cos(d));
      const step = Math.abs(a.angVel) * 2.4 * dt;
      if (Math.abs(d) > step) a.angle += Math.sign(d) * step;
      else a.angle = door;
      this.place(a);
      a.heading = Math.atan2(a.cx - a.x, a.cz - a.z);
      return;
    }
    a.until -= dtMs;
    if (a.until <= 0) {
      const roll = a.rnd();
      a.state = roll < 0.42 ? "walking" : roll < 0.82 ? "working" : "idle";
      a.until = 2600 + a.rnd() * 7600;
    }
    const current = a.override ?? a.state;
    if (current === "walking" && a.walkRoute && a.walkRoute.length > 1) {
      const length = routeLength(a.walkRoute);
      a.walkDistance += a.walkDirection * (1.25 + a.rnd() * 0.35) * dt;
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
    } else if (current === "walking") {
      a.angle += a.angVel * dt;
      this.place(a);
      a.heading = Math.atan2(-Math.sin(a.angle) * Math.sign(a.angVel), Math.cos(a.angle) * Math.sign(a.angVel));
    } else if (current === "idle") {
      this.place(a);
      a.heading = Math.atan2(a.cx - a.x, a.cz - a.z) + Math.sin(this.time / 1700 + a.seed) * 0.12;
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
            // A dispatched van delivers, waits, and drives home.
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
        continue;
      }
      const st = a.override ?? a.state;
      const moving = st === "walking" || st === "delivering" || st === "returning";
      const ph = t * (moving ? 7 : 2.2) + a.seed;
      let y = this.ground(a.x, a.z);
      let sy = 1;
      let yaw = a.heading;
      if (!this.reduced) {
        if (moving) y += Math.abs(Math.sin(ph)) * 0.07;
        else if (st === "working") y += Math.abs(Math.sin(ph * 1.6)) * 0.05;
        else if (st === "celebrating") y += Math.abs(Math.sin(t * 6 + a.seed)) * 0.38;
        else if (st === "concerned") {
          sy = 0.93;
          yaw += Math.sin(t * 1.4 + a.seed) * 0.45;
        }
        else if (st === "investigating") yaw += Math.sin(t * 1.1 + a.seed) * 0.5;
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
      // Restore the shared pose matrix scales before the next agent.
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

    this.vans.count = this.vanList.length;
    this.vanList.forEach((v, i) => {
      this.q.setFromAxisAngle(this.up, v.heading - Math.PI / 2);
      this.p.set(v.x, this.ground(v.x, v.z) + 0.1, v.z);
      this.s.set(1.1, 1.1, 1.1);
      this.m.compose(this.p, this.q, this.s);
      this.vans.setMatrixAt(i, this.m);
      this.vans.setColorAt(i, this.c.set(v.tint));
    });
    this.vans.instanceMatrix.needsUpdate = true;
    if (this.vans.instanceColor) this.vans.instanceColor.needsUpdate = true;
  }

  dispose() {
    for (const m of [this.bodies, this.heads, this.vans, this.helmets, this.backpacks, this.briefcases, this.ties, this.clipboards]) {
      m.geometry.dispose();
      (m.material as THREE.Material).dispose();
      m.dispose();
    }
  }
}
