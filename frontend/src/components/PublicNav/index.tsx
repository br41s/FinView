'use client';

import { usePathname } from 'next/navigation';
import styles from './index.module.css';

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
    <header className={styles.header}>
      <nav className={styles.nav}>
        <a href="/" className={styles.brand}>
          <LogoMark />
          finview
        </a>

        <div className={styles.links}>
          {NAV_LINKS.map(({ label, href }) => (
            <a
              key={href}
              href={href}
              className={`${styles.link} ${pathname === href ? styles.linkActive : ''}`}
            >
              {label}
            </a>
          ))}
        </div>

        <div className={styles.actions}>
          <a href="/login" className={styles.signIn}>acceder</a>
          <a href="/dashboard" className={styles.cta}>Ir a tu panel</a>
        </div>
      </nav>
    </header>
  );
}
