'use client';

import { useState, useEffect } from 'react';
import { HorizonArt } from './HorizonArt';
import { PublicNav } from '@/components/PublicNav';
import styles from './intro.module.css';

export function FinviewIntro() {
  const [replayCount, setReplayCount] = useState(0);
  const textKey = `intro-${replayCount}`;

  useEffect(() => {
    setReplayCount(c => c + 1);
  }, []);

  return (
    <div className={styles.page}>
      <PublicNav />

      <main key={textKey} className={styles.main}>
        <span className={styles.eyebrow}>
          <span className={styles.dot} />
          FINVIEW · DIVIDENDOS · CAPÍTULO UNO
        </span>

        <h1 className={styles.headline}>
          <span className={styles.wordPatience}>La paciencia</span>{' '}
          <span className={styles.wordEnrich}>
            <em className={styles.em}>enriquece</em>
          </span>
        </h1>

        <p className={styles.lead}>
          Siembra una semilla. Reinvierte cada dividendo.
          Vuelve en diez años y encontrarás un jardín.
        </p>

        <div className={styles.artWrap}>
          <HorizonArt replaying={replayCount} />
        </div>

        <div className={styles.ctas}>
          <a href="/dashboard" className={styles.ctaPrimary}>
            Ir a tu panel →
          </a>
          <a href="/features" className={styles.ctaSecondary}>
            Ver cómo funciona
          </a>
        </div>
      </main>

      <button
        type="button"
        onClick={() => setReplayCount(c => c + 1)}
        className={styles.replay}
      >
        ↺ repetir
      </button>
    </div>
  );
}
