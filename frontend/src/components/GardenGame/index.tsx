'use client';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type PointerEvent as ReactPointerEvent,
} from 'react';

import {
  DEFAULT_PALETTE,
  EFFECT_MS,
  drawBackdrop,
  drawBear,
  drawCoin,
  drawEffect,
  drawPlant,
  type Effect,
  type Palette,
} from '@/game/garden/scene';
import {
  STARTING_LIVES,
  buildField,
  createGame,
  groundAt,
  plantTop,
  resizeGame,
  step,
  tap,
  type GameEvent,
  type GameState,
} from '@/game/garden/sim';

import styles from './garden.module.css';

/**
 * The dividend garden under the landing hero, and the game it turns into.
 *
 * Until someone presses "Jugar" the simulation runs in demo mode: plants pay
 * coins, the coins are reinvested on their own and the garden fills up, which
 * is the landing page's whole argument drawn as a picture. Pressing the button
 * hands the same canvas to the player: catch the coins, shoo the bears.
 *
 * The simulation lives in refs, not React state: it changes sixty times a
 * second and nothing in the DOM depends on most of it. React state holds only
 * what the HUD shows, and is set when one of those numbers actually changes.
 */

const BEST_KEY = 'fv-garden-best';
/** A frame after a pause must not fast-forward the garden. */
const MAX_FRAME_MS = 50;

const CSS_VARS: Record<keyof Palette, string> = {
  paper: '--fv-paper',
  ink: '--fv-ink',
  ochre: '--fv-ochre',
  ochreDark: '--fv-ochre-dark',
  ochreSoft: '--fv-ochre-soft',
  leaf: '--fv-success',
  danger: '--fv-danger',
};

/** The site's colours as the browser resolves them now, light or dark. */
function readPalette(element: Element): Palette {
  const computed = getComputedStyle(element);
  const palette = { ...DEFAULT_PALETTE };
  (Object.keys(CSS_VARS) as (keyof Palette)[]).forEach((key) => {
    const value = computed.getPropertyValue(CSS_VARS[key]).trim();
    if (value) palette[key] = value;
  });
  return palette;
}

function readBest(): number {
  try {
    return Number(window.localStorage.getItem(BEST_KEY)) || 0;
  } catch {
    // Private mode or blocked storage: the game works, it just forgets.
    return 0;
  }
}

const BEST_EVENT = 'fv-garden-best-changed';

function saveBest(score: number): void {
  try {
    window.localStorage.setItem(BEST_KEY, String(score));
  } catch {
    // Same as above: nothing to do, and nothing lost that matters.
  }
  window.dispatchEvent(new Event(BEST_EVENT));
}

/**
 * The best score lives in localStorage, which the server render does not have.
 * Reading it as an external store gives 0 on the server and the stored value
 * on the client without a state update inside an effect.
 */
function subscribeBest(notify: () => void): () => void {
  window.addEventListener(BEST_EVENT, notify);
  window.addEventListener('storage', notify);
  return () => {
    window.removeEventListener(BEST_EVENT, notify);
    window.removeEventListener('storage', notify);
  };
}

function verdict(score: number): string {
  if (score <= 5) return 'El mercado bajista se merendó tu jardín.';
  if (score <= 20) return 'Buen intento. El oso también reinvierte, pero en tus plantas.';
  return 'Jardín de leyenda. La paciencia enriquece, y los reflejos también.';
}

export function GardenGame() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const gameRef = useRef<GameState | null>(null);
  const effectsRef = useRef<Effect[]>([]);
  const paletteRef = useRef<Palette>(DEFAULT_PALETTE);
  const visibleRef = useRef(true);

  const [playing, setPlaying] = useState(false);
  const [over, setOver] = useState(false);
  const [score, setScore] = useState(0);
  const [lives, setLives] = useState(STARTING_LIVES);
  const best = useSyncExternalStore(subscribeBest, readBest, () => 0);

  /** Turn what the rules report into floating words and HUD numbers. */
  const absorb = useCallback((events: GameEvent[]) => {
    const game = gameRef.current;
    if (!game || events.length === 0) return;
    const { field } = game;
    const say = (at: { x: number; y: number }, text: string, color: keyof Palette) =>
      effectsRef.current.push({ at, text, color, ageMs: 0 });
    const aboveSlot = (slot: number) => {
      const x = field.slots[slot];
      return { x, y: groundAt(field, x) - field.unit * 9 };
    };

    for (const event of events) {
      if (event.type === 'collect') say(event.at, '+1', 'ochre');
      else if (event.type === 'bonus') say(event.at, '+2', 'ochre');
      else if (event.type === 'plant') say(plantTop(field, event.slot, 1), 'Reinvertido', 'leaf');
      else if (event.type === 'grow') say(aboveSlot(event.slot), 'Crece', 'leaf');
      else if (event.type === 'shoo') say(event.at, '¡Fuera!', 'ink');
      else if (event.type === 'bite') say(aboveSlot(event.slot), 'Ñam', 'danger');
    }

    if (game.mode !== 'play') return;
    setScore(game.score);
    setLives(game.lives);
    if (events.some((e) => e.type === 'over')) {
      setOver(true);
      if (game.score > readBest()) saveBest(game.score);
    }
  }, []);

  // Canvas size, palette, visibility and the frame loop.
  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!wrap || !canvas || !ctx) return;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let frameId = 0;
    let last = 0;
    let clock = 0;

    const draw = () => {
      const game = gameRef.current;
      if (!game) return;
      const palette = paletteRef.current;
      drawBackdrop(ctx, game.field, palette, clock);
      game.plants.forEach((plant, slot) => {
        if (plant) drawPlant(ctx, game.field, palette, slot, plant, clock);
      });
      for (const bear of game.bears) drawBear(ctx, game.field, palette, bear, clock);
      for (const coin of game.coins) drawCoin(ctx, game.field, palette, coin);
      for (const effect of effectsRef.current) drawEffect(ctx, game.field, palette, effect);
    };

    const fit = () => {
      const { width, height } = wrap.getBoundingClientRect();
      if (width < 1 || height < 1) return;
      const ratio = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      const field = buildField(width, height);
      if (gameRef.current) resizeGame(gameRef.current, field);
      else gameRef.current = createGame(field, 'demo');
      paletteRef.current = readPalette(wrap);
      draw();
    };

    const frame = (now: number) => {
      frameId = window.requestAnimationFrame(frame);
      const dt = last ? Math.min(MAX_FRAME_MS, now - last) : 0;
      last = now;
      const game = gameRef.current;
      if (!game || !visibleRef.current) return;
      // With reduced motion the idle garden is a still picture; a game the
      // visitor chose to start still moves.
      if (reducedMotion && game.mode === 'demo') return;
      clock += dt;
      absorb(step(game, dt));
      effectsRef.current = effectsRef.current.filter((effect) => {
        effect.ageMs += dt;
        return effect.ageMs < EFFECT_MS;
      });
      draw();
    };

    fit();
    frameId = window.requestAnimationFrame(frame);

    const resizer = new ResizeObserver(fit);
    resizer.observe(wrap);

    // Off screen or in a background tab, the garden waits.
    const onScreen = new IntersectionObserver(([entry]) => {
      visibleRef.current = entry.isIntersecting && !document.hidden;
    });
    onScreen.observe(wrap);
    const onVisibility = () => {
      if (document.hidden) visibleRef.current = false;
      else onScreen.takeRecords();
      last = 0;
    };
    document.addEventListener('visibilitychange', onVisibility);

    // The theme toggle changes the CSS variables the palette is read from.
    const themeWatcher = new MutationObserver(() => {
      paletteRef.current = readPalette(wrap);
      draw();
    });
    themeWatcher.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style', 'data-theme'] });

    return () => {
      window.cancelAnimationFrame(frameId);
      resizer.disconnect();
      onScreen.disconnect();
      themeWatcher.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [absorb]);

  const start = useCallback((mode: 'play' | 'demo') => {
    const current = gameRef.current;
    if (!current) return;
    gameRef.current = createGame(current.field, mode);
    effectsRef.current = [];
    setPlaying(mode === 'play');
    setOver(false);
    setScore(0);
    setLives(STARTING_LIVES);
  }, []);

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLCanvasElement>) => {
      const game = gameRef.current;
      if (!game || game.mode !== 'play') return;
      const box = event.currentTarget.getBoundingClientRect();
      absorb(tap(game, { x: event.clientX - box.left, y: event.clientY - box.top }));
    },
    [absorb],
  );

  return (
    <section className={styles.section} aria-labelledby="garden-title">
      <div className={styles.head}>
        <span className={styles.eyebrow}>Un descanso</span>
        <h2 id="garden-title" className={styles.title}>
          Mientras esperas, cuida el jardín
        </h2>
        <p className={styles.lead}>
          Cada planta paga dividendos. Atrápalos antes de que se escapen: cada tres, una planta
          nueva. Y que no se acerque el oso del mercado bajista.
        </p>
      </div>

      <div className={styles.hud} aria-live="polite">
        {playing ? (
          <>
            <span>
              Reinvertidos <strong>{score}</strong>
            </span>
            <span aria-label={`${lives} vidas`}>
              {Array.from({ length: STARTING_LIVES }, (_, i) => (
                <span key={i} className={i < lives ? styles.life : styles.lifeLost}>
                  ❀
                </span>
              ))}
            </span>
          </>
        ) : (
          <span>El jardín crece solo. ¿Lo haces tú mejor?</span>
        )}
        <span>
          Mejor <strong>{best}</strong>
        </span>
      </div>

      <div ref={wrapRef} className={`${styles.stage} ${playing && !over ? styles.stagePlaying : ''}`}>
        <canvas
          ref={canvasRef}
          className={styles.canvas}
          onPointerDown={onPointerDown}
          role="img"
          aria-label="Ilustración animada de un jardín: las plantas sueltan monedas que flotan hacia arriba y un oso se acerca a comérselas."
        />

        {!playing && (
          <button type="button" className={styles.play} onClick={() => start('play')}>
            Jugar
          </button>
        )}

        {over && (
          <div className={styles.over} role="status">
            <p className={styles.overTitle}>{verdict(score)}</p>
            <p className={styles.overScore}>
              Reinvertiste <strong>{score}</strong> {score === 1 ? 'dividendo' : 'dividendos'}.
              {score > 0 && score >= best ? ' Nuevo récord.' : ''}
            </p>
            <div className={styles.overActions}>
              <button type="button" className={styles.play} onClick={() => start('play')}>
                Otra vez
              </button>
              <button type="button" className={styles.quit} onClick={() => start('demo')}>
                Salir
              </button>
            </div>
          </div>
        )}
      </div>

      <p className={styles.small}>
        {playing && !over ? (
          <button type="button" className={styles.quit} onClick={() => start('demo')}>
            Salir del juego
          </button>
        ) : (
          'Es solo un juego. Aquí tampoco hay consejos de inversión.'
        )}
      </p>
    </section>
  );
}
