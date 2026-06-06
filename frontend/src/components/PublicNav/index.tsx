'use client';

import { useState } from 'react';
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

function MenuIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
      <path d="M3 6h16M3 11h16M3 16h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
      <path d="M5 5l12 12M17 5L5 17" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
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
  const [open, setOpen] = useState(false);

  return (
    <header className={styles.header}>
      <nav className={styles.nav}>
        <a href="/" className={styles.brand}>
          <LogoMark />
          finview
        </a>

        {/* Desktop links */}
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

        {/* Mobile hamburger */}
        <button
          className={styles.hamburger}
          onClick={() => setOpen(o => !o)}
          aria-label={open ? 'Cerrar menú' : 'Abrir menú'}
          aria-expanded={open}
        >
          {open ? <CloseIcon /> : <MenuIcon />}
        </button>
      </nav>

      {/* Mobile dropdown */}
      {open && (
        <div className={styles.mobileMenu} onClick={() => setOpen(false)}>
          {NAV_LINKS.map(({ label, href }) => (
            <a
              key={href}
              href={href}
              className={`${styles.mobileLink} ${pathname === href ? styles.mobileLinkActive : ''}`}
            >
              {label}
            </a>
          ))}
          <div className={styles.mobileDivider} />
          <a href="/login" className={styles.mobileSignIn}>acceder</a>
          <a href="/dashboard" className={styles.mobileCta}>Ir a tu panel →</a>
        </div>
      )}
    </header>
  );
}
