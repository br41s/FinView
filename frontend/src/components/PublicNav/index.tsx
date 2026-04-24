'use client';

import { usePathname } from 'next/navigation';

function LogoMark() {
  return (
    <svg viewBox="0 0 64 64" width="28" height="28" fill="none" aria-hidden="true">
      <path d="M32 54 C32 42 32 34 32 22" stroke="var(--fv-ink, #1F1B16)" strokeWidth="3" strokeLinecap="round"/>
      <path d="M32 34 C22 34 14 28 12 18 C22 18 30 24 32 34 Z" fill="var(--fv-ochre, #9A6B1F)"/>
      <path d="M32 24 C42 24 50 18 52 10 C44 10 36 14 32 24 Z" fill="var(--fv-ochre, #9A6B1F)" opacity="0.6"/>
    </svg>
  );
}

const NAV_LINKS = [
  { label: 'Panel', href: '/dashboard' },
  { label: 'Funcionalidades', href: '/features' },
  { label: 'Precios', href: '/pricing' },
  { label: 'Más información', href: '/blog' },
];

export function PublicNav() {
  const pathname = usePathname();

  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 10,
      background: 'var(--fv-paper)',
      borderBottom: '1px solid var(--fv-ink-10)',
    }}>
      <nav style={{
        maxWidth: 1320, margin: '0 auto',
        padding: '16px 32px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <a href="/" style={{
          display: 'flex', alignItems: 'center', gap: 10,
          fontFamily: 'var(--fv-font-display)', fontSize: 22,
          color: 'var(--fv-ink)', textDecoration: 'none',
        }}>
          <LogoMark />
          finview
        </a>

        <div style={{ display: 'flex', gap: 28, fontSize: 15 }}>
          {NAV_LINKS.map(({ label, href }) => (
            <a key={href} href={href} style={{
              color: pathname === href ? 'var(--fv-ink)' : 'var(--fv-ink-70)',
              textDecoration: 'none',
              fontWeight: pathname === href ? 500 : 400,
              paddingBottom: 2,
              borderBottom: pathname === href
                ? '1.5px solid var(--fv-ochre)'
                : '1.5px solid transparent',
            }}>
              {label}
            </a>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          <a href="/login" style={{ fontSize: 15, color: 'var(--fv-ink-70)', textDecoration: 'none' }}>
            acceder
          </a>
          <a href="/dashboard" style={{
            background: 'var(--fv-ink)', color: 'var(--fv-paper)',
            border: 0, borderRadius: 'var(--fv-r-pill)', padding: '10px 18px',
            fontSize: 14, fontFamily: 'var(--fv-font-sans)', fontWeight: 500,
            textDecoration: 'none', display: 'inline-block',
          }}>
            Ir a tu panel
          </a>
        </div>
      </nav>
    </header>
  );
}
