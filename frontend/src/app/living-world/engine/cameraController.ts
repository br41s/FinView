import * as THREE from "three";

/**
 * Orbit-style diorama camera (spec §7.1). A target point on the ground, a yaw, a pitch
 * and a distance; input only edits the *desired* values and `update` eases the camera
 * toward them, so focus fly-ins, wheel zoom and drag all share one smoothing path.
 * With reduced motion, desired values are applied instantly instead of eased.
 */

interface View {
  tx: number;
  tz: number;
  yaw: number;
  pitch: number;
  dist: number;
}

const PITCH_MIN = 0.35;
const PITCH_MAX = 1.25;
const DRAG_PX = 4;

export interface CameraOptions {
  /** Radius of the town, for the fit view and the pan/zoom limits. */
  radius: () => number;
  /** Ground height at a point, so the camera orbits the terrain rather than sea level. */
  groundY?: (x: number, z: number) => number;
  reducedMotion: () => boolean;
  onClick: (clientX: number, clientY: number) => void;
  /** The user took the camera: cancels follow mode, never auto-focus. */
  onUserMove: () => void;
  onFocusKey: () => void;
  /** Notified when cinematic tour mode starts or stops. */
  onTourChange?: (touring: boolean) => void;
}

export class CameraController {
  private cur: View;
  private want: View;
  private history: View[] = [];
  private gy = 0;
  private pointers = new Map<number, { x: number; y: number }>();
  private downAt: { x: number; y: number; button: number } | null = null;
  private moved = false;
  private pinch: { d: number; a: number } | null = null;
  private keys = new Set<string>();
  private follower: (() => { x: number; z: number } | null) | null = null;
  private tourActive = false;
  private tourTime = 0;
  private ray = new THREE.Raycaster();
  private plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  private hit = new THREE.Vector3();
  private ndc = new THREE.Vector2();
  private disposers: Array<() => void> = [];
  private anchor: THREE.Vector3 | null = null;
  private lastZoomAt = 0;

  constructor(
    private camera: THREE.PerspectiveCamera,
    private dom: HTMLElement,
    private o: CameraOptions,
  ) {
    this.want = { tx: 0, tz: 0, yaw: Math.PI / 4, pitch: 0.74, dist: 110 };
    this.cur = { ...this.want };
    this.hero(true);
    this.bind();
  }

  // --- public commands --------------------------------------------------------

  /** Hero framing: attractive isometric diorama overlooking the lively central plaza & landmarks. */
  hero(instant = false) {
    this.stopTour();
    this.set({ tx: 0, tz: 0, yaw: Math.PI / 4, pitch: 0.74, dist: 110 }, instant);
  }

  /** Frame the whole town comfortably without blowing up camera distance. */
  fit(instant = false) {
    this.stopTour();
    const r = this.o.radius();
    const fov = (this.camera.fov * Math.PI) / 180;
    const targetDist = (r * 0.76) / Math.tan(fov / 2) / Math.min(1, this.camera.aspect * 0.88 + 0.12);
    const dist = Math.min(240, Math.max(90, targetDist));
    this.set({ tx: 0, tz: 0, yaw: this.want.yaw, pitch: 0.76, dist }, instant);
  }

  /** Fly to a ground point; remembers where we were so `back()` can return. */
  focus(x: number, z: number, dist = 26) {
    this.stopTour();
    this.history.push({ ...this.want });
    if (this.history.length > 20) this.history.shift();
    this.set({ ...this.want, tx: x, tz: z, dist: Math.max(this.minDist(), dist) });
  }

  back() {
    this.stopTour();
    const v = this.history.pop();
    if (v) this.set(v);
    return v !== undefined;
  }

  canGoBack() {
    return this.history.length > 0;
  }

  follow(getter: (() => { x: number; z: number } | null) | null) {
    this.stopTour();
    this.follower = getter;
    if (getter) this.want.dist = Math.min(this.want.dist, 24);
  }

  isFollowing() {
    return this.follower !== null;
  }

  // --- cinematic tour mode ----------------------------------------------------

  isTouring() {
    return this.tourActive;
  }

  toggleTour(): boolean {
    return this.setTour(!this.tourActive);
  }

  setTour(active: boolean): boolean {
    if (this.tourActive === active) return this.tourActive;
    this.tourActive = active;
    if (active) {
      this.tourTime = 0;
      this.follower = null;
    }
    this.o.onTourChange?.(this.tourActive);
    return this.tourActive;
  }

  stopTour() {
    if (this.tourActive) {
      this.tourActive = false;
      this.o.onTourChange?.(false);
    }
  }

  rotate(dYaw: number) {
    this.stopTour();
    this.want.yaw += dYaw;
  }

  zoomBy(factor: number) {
    this.stopTour();
    this.want.dist = this.clampDist(this.want.dist * factor);
  }

  get distance() {
    return this.cur.dist;
  }

  get target() {
    return { x: this.cur.tx, z: this.cur.tz };
  }

  /** Ground point under a screen position, or null when the ray misses the ground. */
  groundAt(clientX: number, clientY: number): THREE.Vector3 | null {
    const r = this.dom.getBoundingClientRect();
    this.ndc.set(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1);
    this.ray.setFromCamera(this.ndc, this.camera);
    return this.ray.ray.intersectPlane(this.plane, this.hit) ? this.hit.clone() : null;
  }

  // --- per frame --------------------------------------------------------------

  update(dtMs: number) {
    const dt = dtMs / 1000;
    this.applyKeys(dt);

    if (this.tourActive) {
      this.tourTime += dt;
      // Gentle continuous diorama orbit
      this.want.yaw += dt * 0.085;
      // Soft breathing elevation & distance between 95 and 130
      this.want.dist = 112 + Math.sin(this.tourTime * 0.22) * 16;
      this.want.pitch = 0.73 + Math.sin(this.tourTime * 0.17) * 0.06;
      // Slow gentle target drift around the central boulevard
      this.want.tx = Math.sin(this.tourTime * 0.1) * 10;
      this.want.tz = Math.cos(this.tourTime * 0.1) * 10;
    }

    if (this.follower) {
      const p = this.follower();
      if (p) {
        this.want.tx = p.x;
        this.want.tz = p.z;
      } else this.follower = null;
    }
    this.clampWant();

    const instant = this.o.reducedMotion();
    const k = instant ? 1 : 1 - Math.pow(0.5, dtMs / 90);
    const c = this.cur;
    const w = this.want;
    c.tx += (w.tx - c.tx) * k;
    c.tz += (w.tz - c.tz) * k;
    c.yaw += (w.yaw - c.yaw) * k;
    c.pitch += (w.pitch - c.pitch) * k;
    c.dist += (w.dist - c.dist) * k;

    const gy = this.o.groundY ? Math.max(0, this.o.groundY(c.tx, c.tz)) : 0;
    this.gy += (gy - this.gy) * k;
    const cp = Math.cos(c.pitch);
    this.camera.position.set(
      c.tx + Math.sin(c.yaw) * cp * c.dist,
      this.gy + Math.sin(c.pitch) * c.dist,
      c.tz + Math.cos(c.yaw) * cp * c.dist,
    );
    this.camera.lookAt(c.tx, this.gy, c.tz);
  }

  // --- internals --------------------------------------------------------------

  private set(v: View, instant = false) {
    this.want = { ...v };
    if (instant || this.o.reducedMotion()) this.cur = { ...v };
  }

  private minDist() {
    return 9;
  }
  private maxDist() {
    return Math.max(60, Math.min(420, this.o.radius() * 2.2));
  }
  private clampDist(d: number) {
    return Math.min(this.maxDist(), Math.max(this.minDist(), d));
  }

  private clampWant() {
    const w = this.want;
    w.pitch = Math.min(PITCH_MAX, Math.max(PITCH_MIN, w.pitch));
    w.dist = this.clampDist(w.dist);
    const lim = this.o.radius() + 10;
    const len = Math.hypot(w.tx, w.tz);
    if (len > lim) {
      w.tx *= lim / len;
      w.tz *= lim / len;
    }
  }

  /** World units per screen pixel at the target, horizontally. */
  private pxToWorld() {
    const h = this.dom.clientHeight || 1;
    return (2 * this.cur.dist * Math.tan((this.camera.fov * Math.PI) / 360)) / h;
  }

  private panBy(dxPx: number, dyPx: number) {
    const s = this.pxToWorld();
    const { yaw, pitch } = this.want;
    const rx = Math.cos(yaw);
    const rz = -Math.sin(yaw);
    const fx = -Math.sin(yaw);
    const fz = -Math.cos(yaw);
    const sv = s / Math.max(0.3, Math.sin(pitch));
    this.want.tx += -rx * dxPx * s + fx * dyPx * sv;
    this.want.tz += -rz * dxPx * s + fz * dyPx * sv;
  }

  /**
   * Zoom keeping the ground point under the cursor fixed. A wheel gesture is many events
   * while the camera is still easing, so the anchor is taken once, when the gesture starts,
   * not re-read from a camera that has not caught up yet (that drifted toward the centre).
   */
  private zoomAt(clientX: number, clientY: number, factor: number) {
    const t = performance.now();
    if (t - this.lastZoomAt > 250 || !this.anchor) this.anchor = this.groundAt(clientX, clientY);
    this.lastZoomAt = t;
    const before = this.anchor;
    const oldD = this.want.dist;
    const newD = this.clampDist(oldD * factor);
    this.want.dist = newD;
    if (before) {
      const f = 1 - newD / oldD;
      this.want.tx += (before.x - this.want.tx) * f;
      this.want.tz += (before.z - this.want.tz) * f;
    }
  }

  private applyKeys(dt: number) {
    if (this.keys.size === 0) return;
    const speed = this.cur.dist * 0.9 * dt;
    const { yaw } = this.want;
    const f = (this.keys.has("w") || this.keys.has("arrowup") ? 1 : 0) - (this.keys.has("s") || this.keys.has("arrowdown") ? 1 : 0);
    const r = (this.keys.has("d") || this.keys.has("arrowright") ? 1 : 0) - (this.keys.has("a") || this.keys.has("arrowleft") ? 1 : 0);
    if (f || r) {
      this.want.tx += (-Math.sin(yaw) * f + Math.cos(yaw) * r) * speed;
      this.want.tz += (-Math.cos(yaw) * f - Math.sin(yaw) * r) * speed;
      this.userMoved();
    }
    const rot = (this.keys.has("e") ? 1 : 0) - (this.keys.has("q") ? 1 : 0);
    if (rot) {
      this.want.yaw += rot * 1.6 * dt;
      this.userMoved();
    }
    if (this.keys.has("+") || this.keys.has("=")) this.want.dist = this.clampDist(this.want.dist * (1 - 1.4 * dt));
    if (this.keys.has("-") || this.keys.has("_")) this.want.dist = this.clampDist(this.want.dist * (1 + 1.4 * dt));
  }

  private userMoved() {
    this.stopTour();
    if (this.follower) this.follower = null;
    this.o.onUserMove();
  }

  private bind() {
    const el = this.dom;
    const on = <K extends keyof HTMLElementEventMap>(t: K, fn: (e: HTMLElementEventMap[K]) => void, opts?: AddEventListenerOptions) => {
      el.addEventListener(t, fn as EventListener, opts);
      this.disposers.push(() => el.removeEventListener(t, fn as EventListener));
    };

    on("pointerdown", (e) => {
      el.focus({ preventScroll: true });
      el.setPointerCapture(e.pointerId);
      this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (this.pointers.size === 1) {
        this.downAt = { x: e.clientX, y: e.clientY, button: e.button };
        this.moved = false;
      } else if (this.pointers.size === 2) {
        const [a, b] = [...this.pointers.values()];
        this.pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), a: Math.atan2(b.y - a.y, b.x - a.x) };
        this.moved = true;
      }
    });

    on("pointermove", (e) => {
      const p = this.pointers.get(e.pointerId);
      if (!p) return;
      const dx = e.clientX - p.x;
      const dy = e.clientY - p.y;
      p.x = e.clientX;
      p.y = e.clientY;

      if (this.pointers.size === 2 && this.pinch) {
        const [a, b] = [...this.pointers.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        const ang = Math.atan2(b.y - a.y, b.x - a.x);
        if (this.pinch.d > 0 && d > 0) this.zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2, this.pinch.d / d);
        this.want.yaw -= ang - this.pinch.a;
        this.pinch = { d, a: ang };
        this.panBy(dx / 2, dy / 2);
        this.userMoved();
        return;
      }
      if (!this.downAt) return;
      if (!this.moved && Math.hypot(e.clientX - this.downAt.x, e.clientY - this.downAt.y) < DRAG_PX) return;
      this.moved = true;
      const rotating = this.downAt.button === 2 || e.shiftKey || e.ctrlKey;
      if (rotating) {
        this.want.yaw -= dx * 0.006;
        this.want.pitch += dy * 0.004;
      } else {
        this.panBy(dx, dy);
      }
      this.userMoved();
    });

    const up = (e: PointerEvent) => {
      this.pointers.delete(e.pointerId);
      if (this.pointers.size < 2) this.pinch = null;
      if (this.pointers.size === 0) {
        const d = this.downAt;
        if (d && !this.moved && d.button === 0 && e.type === "pointerup") this.o.onClick(e.clientX, e.clientY);
        this.downAt = null;
      }
    };
    on("pointerup", up);
    on("pointercancel", up);
    on("contextmenu", (e) => e.preventDefault());

    on(
      "wheel",
      (e) => {
        e.preventDefault();
        const unit = e.deltaMode === 1 ? 16 : 1;
        this.zoomAt(e.clientX, e.clientY, Math.exp(e.deltaY * unit * 0.0012));
        this.userMoved();
      },
      { passive: false },
    );

    on("keydown", (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "c") return void this.toggleTour();
      if (k === "home") return void (this.userMoved(), this.fit());
      if (k === "f") return void this.o.onFocusKey();
      if (["w", "a", "s", "d", "q", "e", "+", "=", "-", "_", "arrowup", "arrowdown", "arrowleft", "arrowright"].includes(k)) {
        this.keys.add(k);
        e.preventDefault();
      }
    });
    on("keyup", (e) => this.keys.delete(e.key.toLowerCase()));
    on("blur", () => this.keys.clear());
  }

  dispose() {
    this.disposers.forEach((d) => d());
    this.disposers = [];
  }
}
