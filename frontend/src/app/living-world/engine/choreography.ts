import * as THREE from "three";
import type { Performance } from "../model/director";
import type { Point } from "../model/routes";
import type { DayMood } from "../model/eventTiming";
import type { EventType } from "../model/types";
import type { AgentState, AgentSystem, Role } from "./agents";
import { Builder } from "./buildingFactory";

/**
 * Event → scene (spec §6.1, Appendix B). The visual grammar is consistent and kept apart:
 *  - market moves  : an arrow over the sign (green up / red down) and onlookers
 *  - operating     : a flag on a pole, staff reacting, delivery vans
 *  - dividends     : a notice board; a gold van drives to the bank when paid
 *  - signals       : a blue chart board (technical), a violet diamond (options)
 *  - portfolio     : a crane and a crew (bought), crates (sold), a cross (closed)
 * Important and Critical events also raise a beacon, which is what makes a 100-site town
 * readable from far away. Nothing here changes a fact; it only acts out an event.
 */

export interface SiteInfo {
  x: number;
  z: number;
  /** Ground height under the building (plateau sites sit above the plain). */
  groundY: number;
  /** Y above the roof where markers float. */
  markerY: number;
  /** Door-to-plaza route (already computed from the layout). */
  route: Point[];
  /** Half the building's footprint on the ground. */
  radius: number;
}

/**
 * How a building lives through an all-day event (see `model/eventTiming.ts`): it is acted out
 * from midnight to midnight, not once.
 *  - party     : string lights and balloons, confetti now and then, staff celebrating outside
 *                and visitors arriving (dividends, good results, an expansion)
 *  - work      : a crane and crates by the door and a crew coming and going (a buy or a sale)
 *  - concerned : no decoration; staff gather outside worried and an analyst comes to look
 */

interface Festivity {
  mood: DayMood;
  meshes: THREE.Mesh[];
  balloons: THREE.Mesh | null;
  nextStaff: number;
  nextVisitors: number;
  nextConfetti: number;
}

const BULBS = [0xffd166, 0xff6b6b, 0x4dd6ff, 0x7bd88f, 0xc792ea, 0xffffff];
const BALLOONS = [0xff4d6d, 0xffc300, 0x3a86ff, 0x2ec4b6, 0xff7b00];

/** String lights on four posts over the entrance, at human height. Local to the door. */
function garland(): THREE.BufferGeometry {
  const b = new Builder();
  const r = 1.5;
  const corners: Array<[number, number]> = [[r, r], [-r, r], [-r, -r], [r, -r]];
  for (const [x, z] of corners) {
    b.cyl(0.05, 0.05, 1.9, x, 0, z, 0x4a4f5a, 5);
    b.sphere(0.12, x, 1.9, z, 0xfff3c4);
  }
  for (let k = 0; k < 4; k++) {
    const [x0, z0] = corners[k];
    const [x1, z1] = corners[(k + 1) % 4];
    const n = 9;
    for (let i = 1; i < n; i++) {
      const t = i / n;
      const sag = Math.sin(t * Math.PI) * 0.35;
      b.box(0.14, 0.14, 0.14, x0 + (x1 - x0) * t, 1.8 - sag, z0 + (z1 - z0) * t, BULBS[(k * n + i) % BULBS.length]);
    }
  }
  return b.build();
}

/** A bunch of balloons on strings, tied by the door. Local to the door. */
function balloonBunch(): THREE.BufferGeometry {
  const b = new Builder();
  const x = 1.7;
  for (let i = 0; i < 5; i++) {
    const a = (i / 5) * Math.PI * 2;
    const bx = x + Math.cos(a) * 0.35;
    const bz = Math.sin(a) * 0.35;
    const h = 2.3 + (i % 3) * 0.35;
    b.cyl(0.012, 0.012, h, bx, 0, bz, 0xdddddd, 3);
    b.ico(0.3, bx, h + 0.28, bz, BALLOONS[i], 1);
  }
  return b.build();
}

export interface Stage {
  site(assetId: string): SiteInfo | null;
  bank: Point;
  agents: AgentSystem;
  scene: THREE.Object3D;
}

type MarkerKind =
  | "arrowUp" | "arrowDown" | "flagGood" | "flagBad" | "notice" | "coin" | "board" | "diamond"
  | "crane" | "crates" | "cross" | "beaconImportant" | "beaconCritical" | "beaconBeam";

const GOLD = 0xe6b422;

/** One-shot geometry factory: run the recipe on a fresh Builder and merge it. */
const geo = (fn: (b: Builder) => void) => () => {
  const b = new Builder();
  fn(b);
  return b.build();
};
const GEOMETRY: Record<MarkerKind, () => THREE.BufferGeometry> = {
  arrowUp: geo((b) => b.cone(0.55, 1.1, 0, 0, 0, 0x37b36b, 4)),
  arrowDown: geo((b) => b.cone(0.55, 1.1, 0, 0, 0, 0xe0504a, 4)),
  flagGood: () => flag(0x37b36b),
  flagBad: () => flag(0xe8a33a),
  notice: geo((b) => {
    b.cyl(0.04, 0.04, 1.0, 0, 0, 0, 0x4a4f5a, 5);
    b.box(0.9, 0.62, 0.07, 0, 0.9, 0, 0xfff7e0);
    b.cyl(0.17, 0.17, 0.05, 0, 1.0, 0.06, GOLD, 10);
  }),
  coin: geo((b) => b.cyl(0.4, 0.4, 0.1, 0, 0, 0, GOLD, 14)),
  board: geo((b) => {
    b.cyl(0.04, 0.04, 0.9, 0, 0, 0, 0x4a4f5a, 5);
    b.box(1.0, 0.7, 0.07, 0, 0.9, 0, 0x2e5fa3);
    b.tilted(0.5, 0.05, 0.05, -0.15, 1.1, 0.06, 0xbfe3ff, 0.5);
    b.tilted(0.4, 0.05, 0.05, 0.25, 1.15, 0.06, 0xbfe3ff, -0.4);
  }),
  diamond: geo((b) => b.box(0.55, 0.55, 0.55, 0, 0, 0, 0x9b59e0, Math.PI / 4)),
  crane: geo((b) => {
    b.box(0.25, 2.2, 0.25, 0, 0, 0, 0xf08a2a);
    b.box(2.0, 0.18, 0.18, 0.7, 2.2, 0, 0xf08a2a);
    b.cyl(0.02, 0.02, 0.8, 1.5, 1.4, 0, 0x4a4f5a, 4);
    b.box(0.3, 0.3, 0.3, 1.5, 1.1, 0, 0x8d6e4b);
  }),
  crates: geo((b) => {
    b.box(0.6, 0.5, 0.6, 0, 0, 0, 0x8d6e4b);
    b.box(0.5, 0.45, 0.5, 0.55, 0, 0.1, 0xa88359);
    b.box(0.45, 0.4, 0.45, 0.2, 0.5, 0, 0xa88359);
  }),
  cross: geo((b) => {
    b.tilted(1.2, 0.18, 0.18, 0, 0.6, 0, 0x6b6f7a, Math.PI / 4);
    b.tilted(1.2, 0.18, 0.18, 0, 0.6, 0, 0x6b6f7a, -Math.PI / 4);
  }),
  beaconImportant: geo((b) => b.cyl(0.35, 0.35, 12, 0, 0, 0, 0xf2b23a, 8)),
  beaconCritical: geo((b) => b.cyl(0.5, 0.5, 18, 0, 0, 0, 0xe0504a, 8)),
  beaconBeam: geo((b) => {
    b.cyl(0.42, 0.42, 28, 0, 14, 0, 0x48c2e0, 10);
    b.sphere(0.85, 0, 0.4, 0, 0xffffff);
  }),
};

function flag(hex: number): THREE.BufferGeometry {
  const b = new Builder();
  b.cyl(0.05, 0.05, 2.0, 0, 0, 0, 0x4a4f5a, 5);
  b.box(0.95, 0.55, 0.05, 0.5, 1.4, 0, hex);
  return b.build();
}

interface Marker {
  mesh: THREE.Mesh;
  key: string;
  ttl: number;
  spin: boolean;
  baseY: number;
  glow: boolean;
  kind: MarkerKind;
}

interface SitePulse {
  key: string;
  light: THREE.PointLight;
  ttl: number;
  duration: number;
  intensity: number;
  phase: number;
}

interface FloatingBadge {
  sprite: THREE.Sprite;
  key: string;
  baseX: number;
  startY: number;
  baseZ: number;
  ttl: number;
  duration: number;
}

const geoCache = new Map<MarkerKind, THREE.BufferGeometry>();

function geometry(kind: MarkerKind): THREE.BufferGeometry {
  let g = geoCache.get(kind);
  if (!g) {
    g = GEOMETRY[kind]();
    if (kind === "arrowDown") {
      g.rotateX(Math.PI);
      g.translate(0, 1.1, 0);
    }
    geoCache.set(kind, g);
  }
  return g;
}

const ACTORS: Partial<Record<EventType, { role: Role; hold: AgentState; n: number }>> = {
  price_move_up: { role: "visitor", hold: "celebrating", n: 2 },
  price_move_down: { role: "analyst", hold: "investigating", n: 2 },
  earnings_beat: { role: "manager", hold: "celebrating", n: 1 },
  earnings_miss: { role: "analyst", hold: "investigating", n: 1 },
  dividend_declared: { role: "manager", hold: "investigating", n: 1 },
  dividend_paid: { role: "courier", hold: "delivering", n: 1 },
  site_expansion: { role: "crew", hold: "working", n: 3 },
  technical_signal: { role: "analyst", hold: "investigating", n: 1 },
  options_alert: { role: "analyst", hold: "investigating", n: 1 },
  position_added: { role: "crew", hold: "working", n: 3 },
  position_reduced: { role: "crew", hold: "working", n: 2 },
  position_closed: { role: "manager", hold: "concerned", n: 1 },
};

const SITE_REACTION: Partial<Record<EventType, AgentState>> = {
  price_move_up: "celebrating",
  price_move_down: "concerned",
  earnings_beat: "celebrating",
  earnings_miss: "concerned",
  position_closed: "concerned",
};

const MARKERS: Partial<Record<EventType, MarkerKind>> = {
  price_move_up: "arrowUp",
  price_move_down: "arrowDown",
  earnings_beat: "flagGood",
  earnings_miss: "flagBad",
  dividend_declared: "notice",
  dividend_paid: "coin",
  site_expansion: "crane",
  technical_signal: "board",
  options_alert: "diamond",
  position_added: "crane",
  position_reduced: "crates",
  position_closed: "cross",
};

const BADGE_CONFIG: Partial<Record<EventType, { text: string; bg: string; fg: string; border: string }>> = {
  price_move_up: { text: "▲ SUBIDA", bg: "#10b981", fg: "#ffffff", border: "#34d399" },
  price_move_down: { text: "▼ BAJADA", bg: "#ef4444", fg: "#ffffff", border: "#f87171" },
  earnings_beat: { text: "★ RESULTADOS +", bg: "#059669", fg: "#ffffff", border: "#34d399" },
  earnings_miss: { text: "▼ RESULTADOS -", bg: "#d97706", fg: "#ffffff", border: "#fbbf24" },
  dividend_declared: { text: "DIVIDENDO ANUNCIADO", bg: "#eab308", fg: "#3f2e00", border: "#fef08a" },
  dividend_paid: { text: "💰 DIVIDENDO ABONADO", bg: "#ca8a04", fg: "#ffffff", border: "#fef08a" },
  site_expansion: { text: "EXPANSIÓN", bg: "#0284c7", fg: "#ffffff", border: "#38bdf8" },
  technical_signal: { text: "SEÑAL TÉCNICA", bg: "#2563eb", fg: "#ffffff", border: "#60a5fa" },
  options_alert: { text: "OPCIONES", bg: "#7c3aed", fg: "#ffffff", border: "#a78bfa" },
  position_added: { text: "+ COMPRA EN CARTERA", bg: "#10b981", fg: "#ffffff", border: "#34d399" },
  position_reduced: { text: "- VENTA EN CARTERA", bg: "#ea580c", fg: "#ffffff", border: "#fb923c" },
  position_closed: { text: "POSICIÓN CERRADA", bg: "#475569", fg: "#ffffff", border: "#94a3b8" },
};

function makeBadgeSprite(cfg: { text: string; bg: string; fg: string; border: string }): THREE.Sprite {
  const canvas = document.createElement("canvas");
  canvas.width = 380;
  canvas.height = 96;
  const ctx = canvas.getContext("2d")!;

  ctx.fillStyle = cfg.border;
  ctx.beginPath();
  ctx.roundRect(4, 4, 372, 88, 26);
  ctx.fill();

  ctx.fillStyle = cfg.bg;
  ctx.beginPath();
  ctx.roundRect(8, 8, 364, 80, 22);
  ctx.fill();

  ctx.fillStyle = cfg.fg;
  ctx.font = "800 36px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(cfg.text, 190, 48, 340);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false, toneMapped: false });
  const sprite = new THREE.Sprite(mat);
  sprite.userData.aspect = 380 / 96;
  sprite.scale.set(sprite.userData.aspect * 1.1, 1.1, 1);
  sprite.renderOrder = 14;
  return sprite;
}

const MAX_CONFETTI = 180;
interface ConfettiParticle {
  active: boolean;
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  rx: number;
  ry: number;
  rz: number;
  rotSpeed: number;
  life: number;
  maxLife: number;
  scale: number;
}

class ConfettiSystem {
  private mesh: THREE.InstancedMesh;
  private particles: ConfettiParticle[] = [];
  private dummy = new THREE.Object3D();
  private color = new THREE.Color();

  constructor(scene: THREE.Object3D) {
    const geo = new THREE.BoxGeometry(0.16, 0.09, 0.02);
    const mat = new THREE.MeshBasicMaterial({ side: THREE.DoubleSide, toneMapped: false });
    this.mesh = new THREE.InstancedMesh(geo, mat, MAX_CONFETTI);
    this.mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(MAX_CONFETTI * 3), 3);
    this.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.mesh.renderOrder = 8;
    this.mesh.visible = true;

    for (let i = 0; i < MAX_CONFETTI; i++) {
      this.particles.push({
        active: false,
        x: 0,
        y: -100,
        z: 0,
        vx: 0,
        vy: 0,
        vz: 0,
        rx: 0,
        ry: 0,
        rz: 0,
        rotSpeed: 0,
        life: 0,
        maxLife: 1,
        scale: 0.8,
      });
      this.dummy.position.set(0, -100, 0);
      this.dummy.scale.set(0, 0, 0);
      this.dummy.updateMatrix();
      this.mesh.setMatrixAt(i, this.dummy.matrix);
      this.color.setHex(0xffffff);
      this.mesh.setColorAt(i, this.color);
    }
    this.mesh.instanceMatrix.needsUpdate = true;
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
    scene.add(this.mesh);
  }

  burst(
    x: number,
    y: number,
    z: number,
    count = 28,
    colors: readonly number[] = [0xf1c40f, 0x2ecc71, 0x00d2d3, 0xff7675, 0x9b59b6, 0xffffff],
  ) {
    let spawned = 0;
    for (let i = 0; i < MAX_CONFETTI && spawned < count; i++) {
      const p = this.particles[i];
      if (!p.active) {
        p.active = true;
        p.x = x + (Math.random() - 0.5) * 0.9;
        p.y = y;
        p.z = z + (Math.random() - 0.5) * 0.9;
        const angle = Math.random() * Math.PI * 2;
        const speedH = 1.0 + Math.random() * 2.4;
        p.vx = Math.cos(angle) * speedH;
        p.vy = 3.6 + Math.random() * 3.8;
        p.vz = Math.sin(angle) * speedH;
        p.rx = Math.random() * Math.PI;
        p.ry = Math.random() * Math.PI;
        p.rz = Math.random() * Math.PI;
        p.rotSpeed = (Math.random() - 0.5) * 14.0;
        p.life = 2.2 + Math.random() * 1.4;
        p.maxLife = p.life;
        p.scale = 0.7 + Math.random() * 0.5;
        const hexColor = colors[Math.floor(Math.random() * colors.length)];
        this.color.setHex(hexColor);
        this.mesh.setColorAt(i, this.color);
        spawned++;
      }
    }
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
  }

  update(dtMs: number, timeSec: number) {
    const dt = dtMs / 1000;
    let anyActive = false;
    for (let i = 0; i < MAX_CONFETTI; i++) {
      const p = this.particles[i];
      if (!p.active) continue;
      p.life -= dt;
      if (p.life <= 0) {
        p.active = false;
        this.dummy.position.set(0, -100, 0);
        this.dummy.scale.set(0, 0, 0);
        this.dummy.updateMatrix();
        this.mesh.setMatrixAt(i, this.dummy.matrix);
        continue;
      }
      anyActive = true;
      p.vy -= 6.2 * dt;
      p.vx *= Math.pow(0.88, dt * 60);
      p.vz *= Math.pow(0.88, dt * 60);
      p.x += (p.vx + Math.sin(timeSec * 7 + i) * 0.45) * dt;
      p.y += p.vy * dt;
      p.z += (p.vz + Math.cos(timeSec * 7 + i) * 0.45) * dt;
      p.rx += p.rotSpeed * dt;
      p.ry += p.rotSpeed * 0.7 * dt;

      const progress = p.life / p.maxLife;
      const fade = Math.min(1, progress * 3.5);
      const sc = p.scale * fade;

      this.dummy.position.set(p.x, p.y, p.z);
      this.dummy.rotation.set(p.rx, p.ry, p.rz);
      this.dummy.scale.set(sc, sc, sc);
      this.dummy.updateMatrix();
      this.mesh.setMatrixAt(i, this.dummy.matrix);
    }
    if (anyActive) {
      this.mesh.instanceMatrix.needsUpdate = true;
    }
  }

  dispose(scene: THREE.Object3D) {
    scene.remove(this.mesh);
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
    this.mesh.instanceMatrix.dispose();
    this.mesh.instanceColor?.dispose();
    this.mesh.dispose();
  }
}

export class Choreographer {
  private markers: Marker[] = [];
  private badges: FloatingBadge[] = [];
  private pulses = new Map<string, SitePulse>();
  private mat = new THREE.MeshBasicMaterial({ vertexColors: true, fog: false });
  private beaconMat = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.32, depthWrite: false, fog: false });
  private time = 0;
  private confetti: ConfettiSystem;
  private festivities = new Map<string, Festivity>();
  private reduced = false;

  constructor(private stage: Stage) {
    this.confetti = new ConfettiSystem(stage.scene);
  }

  start(p: Performance) {
    if (!p.assetId) return;
    const site = this.stage.site(p.assetId);
    if (!site) return;
    const ms = Math.max(4000, p.endsAt - p.startedAt);
    const types = [...new Set(p.events.map((e) => e.eventType))];

    this.pulse(p, site, ms);
    for (const t of types) this.act(p, t, site, ms);

    if (p.severity !== "normal") this.beacon(p, site, ms);
  }

  setReducedMotion(v: boolean) {
    this.reduced = v;
  }

  /**
   * The buildings living through an all-day event right now, and how. Called whenever that
   * set changes (an event arrives, the day turns); a building not in it goes back to normal.
   */
  setAllDay(moods: ReadonlyMap<string, DayMood>) {
    for (const [assetId, f] of this.festivities) {
      if (moods.get(assetId) === f.mood) continue;
      this.endFestivity(assetId);
    }
    for (const [assetId, mood] of moods) {
      if (this.festivities.has(assetId)) continue;
      const site = this.stage.site(assetId);
      if (!site) continue;
      const meshes: THREE.Mesh[] = [];
      let balloons: THREE.Mesh | null = null;
      // Everything happens at the entrance, where the staff come out: a big complex would
      // otherwise swallow decorations placed around its centre.
      // route[0] is the lot's centre and route[1] the kerb in front: the entrance is just short of it.
      const c = site.route[0] ?? { x: site.x, z: site.z };
      const f = site.route[1] ?? { x: site.x + site.radius + 2.2, z: site.z };
      const d = Math.hypot(f.x - c.x, f.z - c.z) || 1;
      const k = Math.max(0, d - 2.2) / d;
      const door = { x: c.x + (f.x - c.x) * k, z: c.z + (f.z - c.z) * k };
      const place = (g: THREE.BufferGeometry, y = site.groundY) => {
        const m = new THREE.Mesh(g, this.mat);
        m.position.set(door.x, y, door.z);
        m.renderOrder = 6;
        this.stage.scene.add(m);
        meshes.push(m);
        return m;
      };
      if (mood === "party") {
        place(garland());
        balloons = place(balloonBunch());
      } else if (mood === "work") {
        place(geometry("crane"), site.groundY).position.x += 1.2;
        place(geometry("crates"), site.groundY).position.z += 1.0;
      }
      // Staggered, so a dozen celebrating buildings do not pulse in step.
      const jitter = (assetId.length * 977) % 3000;
      this.festivities.set(assetId, {
        mood, meshes, balloons,
        nextStaff: this.time + jitter * 0.3,
        nextVisitors: this.time + 1500 + jitter,
        nextConfetti: this.time + 800 + jitter,
      });
    }
  }

  private endFestivity(assetId: string) {
    const f = this.festivities.get(assetId);
    if (!f) return;
    for (const m of f.meshes) {
      this.stage.scene.remove(m);
      // The crane and crates share the marker geometry cache; only the party's own are freed.
      if (f.mood === "party") m.geometry.dispose();
    }
    this.festivities.delete(assetId);
  }

  private liveFestivities(t: number) {
    const a = this.stage.agents;
    for (const [assetId, f] of this.festivities) {
      const site = this.stage.site(assetId);
      if (!site) continue;
      if (f.balloons) f.balloons.position.y = site.groundY + Math.sin(t * 1.3 + assetId.length) * 0.08;
      if (this.time >= f.nextStaff) {
        const state: AgentState = f.mood === "party" ? "celebrating" : f.mood === "work" ? "working" : "concerned";
        a.dispatch(assetId, state, 9000, 6);
        f.nextStaff = this.time + 7000;
      }
      if (this.time >= f.nextVisitors) {
        const route = site.route.slice(1, -1).reverse();
        if (route.length >= 2) {
          const who: { role: Role; hold: AgentState; n: number } =
            f.mood === "party"
              ? { role: "visitor", hold: "celebrating", n: 2 }
              : f.mood === "work"
                ? { role: "crew", hold: "working", n: 2 }
                : { role: "analyst", hold: "investigating", n: 1 };
          for (let i = 0; i < who.n; i++) {
            a.spawnActor({
              role: who.role, route, speed: 2.6, holdState: who.hold, holdMs: 14000, assetId,
              offsetX: (i - (who.n - 1) / 2) * 0.8, offsetZ: 0.5,
            });
          }
        }
        f.nextVisitors = this.time + 24000;
      }
      if (f.mood === "party" && !this.reduced && this.time >= f.nextConfetti) {
        this.confetti.burst(site.x, site.markerY, site.z, 14);
        f.nextConfetti = this.time + 6500;
      }
    }
  }

  /** One beacon per performance; an escalation swaps a weaker one for the stronger kind. */
  private beacon(p: Performance, site: SiteInfo, ms: number) {
    const kind: MarkerKind = p.severity === "critical" ? "beaconCritical" : "beaconImportant";
    const have = this.markers.find((m) => m.key === p.id && m.glow);
    if (have?.kind === kind) {
      have.ttl = Math.max(have.ttl, ms);
      return;
    }
    if (have) have.ttl = 0;
    this.addMarker(kind, p.id, site.x, site.groundY, site.z, ms, { beacon: true });
  }

  /**
   * A performance absorbed another event of the same company: act the new one too.
   * `clock` is the director's clock (the one `endsAt` is on), and a performance that
   * escalated to Important/Critical gets the beacon it did not have when it started.
   */
  extend(p: Performance, clock: number) {
    if (!p.assetId) return;
    const site = this.stage.site(p.assetId);
    const last = p.events[p.events.length - 1];
    if (!site || !last) return;
    const ms = Math.max(4000, p.endsAt - clock);
    this.pulse(p, site, ms);
    this.act(p, last.eventType, site, ms);
    if (p.severity !== "normal") this.beacon(p, site, ms);
  }

  stop(id: string) {
    for (const m of this.markers) if (m.key === id) m.ttl = Math.min(m.ttl, 400);
    for (const b of this.badges) if (b.key.startsWith(id)) b.ttl = Math.min(b.ttl, 400);
    const pulse = this.pulses.get(id);
    if (pulse) pulse.ttl = Math.min(pulse.ttl, 400);
  }

  /** Event light washes the affected headquarters, not the surrounding city. */
  private pulse(p: Performance, site: SiteInfo, ms: number) {
    const latest = p.events[p.events.length - 1];
    const negative = p.events.some((e) => e.direction === "negative");
    const positive = p.events.some((e) => e.direction === "positive");
    const color = negative ? 0xe35b50 : positive ? 0x6bc78c : 0x66b9df;
    const intensity = p.severity === "critical" ? 4.2 : p.severity === "important" ? 3.0 : 2.0;
    const existing = this.pulses.get(p.id);
    if (existing) {
      existing.ttl = Math.max(existing.ttl, ms);
      existing.duration = Math.max(existing.duration, ms);
      existing.intensity = Math.max(existing.intensity, intensity);
      existing.light.color.setHex(color);
      return;
    }
    const light = new THREE.PointLight(color, 0, 22, 1.6);
    light.position.set(site.x, Math.max(site.groundY + 1.8, site.markerY - 1.1), site.z);
    this.stage.scene.add(light);
    this.pulses.set(p.id, {
      key: p.id,
      light,
      ttl: ms,
      duration: ms,
      intensity,
      phase: (latest?.id.length ?? 1) * 0.31,
    });
  }

  private pulseBank(key: string, ms: number) {
    const light = new THREE.PointLight(0xffd700, 3.8, 26, 1.8);
    light.position.set(this.stage.bank.x, 3.6, this.stage.bank.z);
    this.stage.scene.add(light);
    this.pulses.set(key, {
      key,
      light,
      ttl: ms,
      duration: ms,
      intensity: 3.8,
      phase: 0,
    });
  }

  private act(p: Performance, t: EventType, site: SiteInfo, ms: number) {
    const a = this.stage.agents;
    const reaction = SITE_REACTION[t];
    if (reaction && p.assetId) a.dispatch(p.assetId, reaction, ms * 0.8);

    const kind = MARKERS[t];
    if (kind) this.addMarker(kind, p.id, site.x, site.markerY, site.z, ms, { spin: kind === "diamond" });

    // Floating RPG-style event badges over the rooftop
    const badgeCfg = BADGE_CONFIG[t];
    if (badgeCfg && typeof document !== "undefined") {
      this.addBadge(badgeCfg, `${p.id}:${t}`, site.x, site.markerY + 0.8, site.z, Math.min(ms, 5500));
    }

    // Volumetric beacon beam on rooftop for financial results & technical signals
    if (t === "earnings_beat" || t === "technical_signal" || t === "options_alert") {
      this.addMarker("beaconBeam", `beam:${p.id}:${t}`, site.x, site.markerY, site.z, Math.min(ms, 6000), { beacon: true });
    }

    // Construction crates beside the crane for expansions and portfolio buys
    if (t === "site_expansion" || t === "position_added") {
      this.addMarker("crates", `crates:${p.id}:${t}`, site.x + 0.85, site.markerY, site.z + 0.85, ms);
    }

    // Festive confetti particle bursts for notable financial moments
    if (t === "price_move_up" || t === "earnings_beat" || t === "site_expansion" || t === "position_added") {
      this.confetti.burst(site.x, site.markerY + 0.5, site.z, 32);
    }
    if (t === "dividend_paid") {
      this.confetti.burst(site.x, site.markerY + 0.5, site.z, 28, [0xf1c40f, 0xffd700, 0xffffff, 0xe6b422]);
    }

    const actors = ACTORS[t];
    if (actors) {
      const route = site.route.slice(1, -1).reverse();
      if (route.length >= 2) {
        const len = pathLen(route);
        const speed = clamp(len / Math.max(1.5, (ms * 0.3) / 1000), 2.5, 14);
        for (let i = 0; i < actors.n; i++) {
          a.spawnActor({
            role: actors.role, route, speed, holdState: actors.hold, holdMs: ms * 0.55, assetId: p.assetId,
            offsetX: (i - (actors.n - 1) / 2) * 0.7, offsetZ: (i - (actors.n - 1) / 2) * 0.5,
          });
        }
      }
    }

    // Deliveries: staff exits and production picks up (beat), dividend caravan travels to the bank.
    const full = [...site.route, this.stage.bank];
    if (t === "earnings_beat" || t === "site_expansion") {
      a.sendVan(full.slice(0, -1), 0xc79a63, clamp(pathLen(full) / Math.max(2, (ms * 0.4) / 1000), 4, 16));
    }
    if (t === "dividend_paid") {
      const speed = clamp(pathLen(full) / Math.max(2, (ms * 0.4) / 1000), 4, 16);
      a.sendVan(full, GOLD, speed, () => {
        this.addMarker("coin", `bank:${p.id}`, this.stage.bank.x, 3.2, this.stage.bank.z, 2600, { spin: true });
        this.confetti.burst(this.stage.bank.x, 3.2, this.stage.bank.z, 36, [0xf1c40f, 0xffd700, 0xffffff, 0xe6b422]);
        this.pulseBank(`bank:${p.id}`, 2600);
      });
      // Escort van traveling in tandem for the dividend convoy
      a.sendVan(full, 0xf59e0b, speed * 0.92);
    }
  }

  private addBadge(cfg: { text: string; bg: string; fg: string; border: string }, key: string, x: number, y: number, z: number, ttlMs: number) {
    if (this.badges.some((b) => b.key === key)) return;
    const sprite = makeBadgeSprite(cfg);
    sprite.position.set(x, y, z);
    this.stage.scene.add(sprite);
    this.badges.push({
      sprite,
      key,
      baseX: x,
      startY: y,
      baseZ: z,
      ttl: ttlMs,
      duration: ttlMs,
    });
  }

  private addMarker(kind: MarkerKind, key: string, x: number, y: number, z: number, ttlMs: number, o: { spin?: boolean; beacon?: boolean } = {}) {
    const mesh = new THREE.Mesh(geometry(kind), o.beacon ? this.beaconMat : this.mat);
    mesh.position.set(x, y, z);
    mesh.renderOrder = o.beacon ? 5 : 6;
    this.stage.scene.add(mesh);
    this.markers.push({ mesh, key, ttl: ttlMs, spin: !!o.spin, baseY: y, glow: !!o.beacon, kind });
  }

  update(dtMs: number) {
    this.time += dtMs;
    const t = this.time / 1000;

    for (const [key, pulse] of this.pulses) {
      pulse.ttl -= dtMs;
      const progress = Math.max(0, Math.min(1, pulse.ttl / pulse.duration));
      const beat = 0.58 + 0.42 * Math.sin(t * 7.2 + pulse.phase);
      const fade = Math.min(1, progress * 3.5);
      pulse.light.intensity = pulse.intensity * beat * fade;
      if (pulse.ttl <= 0) {
        this.stage.scene.remove(pulse.light);
        this.pulses.delete(key);
      }
    }

    for (const m of this.markers) {
      m.ttl -= dtMs;
      if (m.kind === "beaconBeam") {
        const pulse = 1 + Math.sin(t * 4.6) * 0.18;
        m.mesh.scale.set(pulse, 1, pulse);
        m.mesh.rotation.y = t * 1.8;
      } else if (m.kind === "crane") {
        m.mesh.position.y = m.baseY + Math.sin(t * 1.5) * 0.04;
        m.mesh.rotation.y = Math.sin(t * 1.4) * 0.72;
        const fade = Math.min(1, Math.max(0, m.ttl / 400));
        m.mesh.scale.setScalar(fade);
      } else if (m.glow) {
        const s = 1 + Math.sin(t * 3) * 0.12;
        m.mesh.scale.set(s, 1, s);
      } else {
        m.mesh.position.y = m.baseY + Math.sin(t * 2.4 + m.baseY) * 0.12;
        if (m.spin) m.mesh.rotation.y = t * 2;
        const fade = Math.min(1, Math.max(0, m.ttl / 400));
        m.mesh.scale.setScalar(fade);
      }
    }
    for (const m of this.markers.filter((x) => x.ttl <= 0)) this.stage.scene.remove(m.mesh);
    this.markers = this.markers.filter((m) => m.ttl > 0);

    for (const b of this.badges) {
      b.ttl -= dtMs;
      const progress = 1 - Math.max(0, b.ttl / b.duration);
      const rise = Math.min(2.8, progress * 3.4);
      b.sprite.position.y = b.startY + rise + Math.sin(t * 3.2 + b.startY) * 0.1;
      const scaleEase = Math.min(1, progress * 5.0);
      const alpha = Math.min(1, Math.max(0, b.ttl / 600));
      b.sprite.material.opacity = alpha;
      const currentScale = 1.1 * scaleEase;
      b.sprite.scale.set(b.sprite.userData.aspect * currentScale, currentScale, 1);
    }
    for (const b of this.badges.filter((x) => x.ttl <= 0)) {
      this.stage.scene.remove(b.sprite);
      b.sprite.material.map?.dispose();
      b.sprite.material.dispose();
    }
    this.badges = this.badges.filter((b) => b.ttl > 0);

    this.liveFestivities(t);
    this.confetti.update(dtMs, t);
  }

  dispose() {
    for (const id of [...this.festivities.keys()]) this.endFestivity(id);
    for (const m of this.markers) this.stage.scene.remove(m.mesh);
    this.markers = [];
    for (const b of this.badges) {
      this.stage.scene.remove(b.sprite);
      b.sprite.material.map?.dispose();
      b.sprite.material.dispose();
    }
    this.badges = [];
    for (const pulse of this.pulses.values()) this.stage.scene.remove(pulse.light);
    this.pulses.clear();
    this.mat.dispose();
    this.beaconMat.dispose();
    geoCache.forEach((g) => g.dispose());
    geoCache.clear();
    this.confetti.dispose(this.stage.scene);
  }
}

function pathLen(p: readonly Point[]): number {
  let s = 0;
  for (let i = 1; i < p.length; i++) s += Math.hypot(p[i].x - p[i - 1].x, p[i].z - p[i - 1].z);
  return s;
}
const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x));
