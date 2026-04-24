'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { HorizonArt } from './HorizonArt';
import { PublicNav } from '@/components/PublicNav';

const rise = (delay: number): React.CSSProperties => ({
  animation: `fv-rise 800ms cubic-bezier(0.2,0.8,0.2,1) ${delay}ms both`,
});

export function FinviewIntro() {
  const router = useRouter();
  const [replayCount, setReplayCount] = useState(0);
  const textKey = `intro-${replayCount}`;

  useEffect(() => {
    setReplayCount(c => c + 1);
  }, []);

  const goToLogin = () => router.push('/login');

  return (
    <div style={{ background: 'var(--fv-paper)', color: 'var(--fv-ink)', minHeight: '100vh', fontFamily: 'var(--fv-font-sans)' }}>
      <PublicNav />

      {/* ── Horizonte ── */}
      <main key={textKey} style={{
        maxWidth: 1320, margin: '0 auto',
        padding: '80px 32px 160px',
        textAlign: 'center',
        minHeight: 'calc(100vh - 57px)',
        display: 'flex', flexDirection: 'column', alignItems: 'center',
      }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 10,
          fontFamily: 'var(--fv-font-sans)', fontSize: 11, fontWeight: 500,
          textTransform: 'uppercase', letterSpacing: '0.18em', color: 'var(--fv-ink-40)',
          ...rise(200),
        }}>
          <span style={{ width: 6, height: 6, borderRadius: 999, background: 'var(--fv-ochre)', display: 'inline-block' }} />
          FINVIEW · DIVIDENDOS · CAPÍTULO UNO
        </span>

        <h1 style={{
          fontFamily: 'var(--fv-font-display)', fontWeight: 400,
          fontSize: 'clamp(3.5rem, 9vw, 8rem)',
          lineHeight: 0.96, letterSpacing: '-0.03em',
          margin: '32px 0 24px', maxWidth: '14ch', color: 'var(--fv-ink)',
        }}>
          <span style={{ display: 'inline-block', ...rise(600) }}>La paciencia</span>{' '}
          <span style={{ display: 'inline-block', ...rise(1000) }}>
            <em style={{ color: 'var(--fv-ochre)', fontStyle: 'italic', fontWeight: 400 }}>enriquece</em>
          </span>
        </h1>

        <p style={{
          fontSize: 20, lineHeight: 1.5, color: 'var(--fv-ink-70)',
          maxWidth: 460, margin: '0 0 48px',
          ...rise(1800),
        }}>
          Siembra una semilla. Reinvierte cada dividendo.
          Vuelve en diez años y encontrarás un jardín.
        </p>

        <div style={{ position: 'relative', width: '100%', maxWidth: 1100, aspectRatio: '1100/360', margin: '24px 0 56px' }}>
          <HorizonArt replaying={replayCount} />
        </div>

        <div style={{ display: 'flex', gap: 16, alignItems: 'center', ...rise(4600) }}>
          <button type="button" onClick={goToLogin} style={{
            background: 'var(--fv-ochre)', color: 'var(--fv-paper)',
            border: 0, borderRadius: 'var(--fv-r-pill)', padding: '14px 24px',
            fontSize: 15, fontFamily: 'var(--fv-font-sans)', fontWeight: 500, cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center', gap: 8,
          }}>
            Ir a tu panel →
          </button>
          <a href="/features" style={{
            background: 'transparent', color: 'var(--fv-ink)',
            border: '1px solid var(--fv-ink-15)', borderRadius: 'var(--fv-r-pill)',
            padding: '14px 24px', fontSize: 15,
            fontFamily: 'var(--fv-font-sans)', fontWeight: 500, cursor: 'pointer',
            textDecoration: 'none', display: 'inline-block',
          }}>
            Ver cómo funciona
          </a>
        </div>
      </main>

      {/* ── Replay button ── */}
      <button
        type="button"
        onClick={() => setReplayCount(c => c + 1)}
        style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 50,
          background: 'rgba(245,241,232,0.92)', backdropFilter: 'blur(12px)',
          border: '1px solid var(--fv-ink-15)', borderRadius: 999,
          padding: '8px 16px', fontSize: 13,
          fontFamily: 'var(--fv-font-sans)', color: 'var(--fv-ink-70)',
          cursor: 'pointer', boxShadow: 'var(--fv-shadow-md)',
          display: 'inline-flex', alignItems: 'center', gap: 6,
        }}
      >
        ↺ repetir
      </button>
    </div>
  );
}
