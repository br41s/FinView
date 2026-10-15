'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';
import { api } from '@/lib/api';
import { LEGAL } from '@/lib/legal';
import styles from './pricing.module.css';

// Feature lists state only what the backend enforces (PLAN_LIMITS in
// backend/services/billing_service.py): an advertised feature that does not
// exist is misleading advertising, not marketing. The paid plans are not on
// sale — there is no Stripe account — and the note under the hero says so; the
// Free limits here must match the table in /legal/condiciones.
const PLANS = [
  {
    tier: 'FREE',
    name: 'Gratis',
    price: '0 €',
    period: 'para siempre',
    desc: 'Para empezar a organizar tus dividendos sin compromiso.',
    features: [
      'Hasta 2 cuentas de bróker',
      'Hasta 5 importaciones de archivos al mes',
      'Todas las funciones de la aplicación',
      'FIFO cross-broker automático',
      'Casillas IRPF y exportación CSV',
    ],
    cta: 'Crear cuenta gratis',
    href: '/register',
    priceId: null,
    highlight: false,
  },
  {
    tier: 'PRO',
    name: 'Pro',
    price: '9,99 €',
    period: '/mes',
    desc: 'Para el inversor serio que quiere control total sobre su cartera.',
    features: [
      'Hasta 10 cuentas de bróker',
      'Hasta 50 importaciones de archivos al mes',
      'Todas las funciones de la aplicación',
      'FIFO cross-broker automático',
      'Casillas IRPF y exportación CSV',
    ],
    cta: 'Empezar con Pro',
    href: '/register?plan=PRO',
    priceId: process.env.NEXT_PUBLIC_STRIPE_PRICE_PRO || '',
    highlight: true,
  },
  {
    tier: 'UNLIMITED',
    name: 'Unlimited',
    price: '19,99 €',
    period: '/mes',
    desc: 'Para asesores y familias que gestionan múltiples carteras.',
    features: [
      'Todo lo de Pro',
      'Cuentas de bróker sin límite',
      'Importaciones sin límite',
    ],
    cta: 'Empezar con Unlimited',
    href: '/register?plan=UNLIMITED',
    priceId: process.env.NEXT_PUBLIC_STRIPE_PRICE_UNLIMITED || '',
    highlight: false,
  },
];

const FAQ = [
  {
    q: '¿Cuánto cuesta FinView?',
    a: 'Hoy es gratuito. Los planes Pro y Unlimited todavía no se pueden contratar; si se ponen a la venta, publicaremos antes sus condiciones y nada cambiará para ti hasta que decidas contratarlos.',
  },
  {
    q: '¿Mis datos fiscales están seguros?',
    a: 'Los archivos que subes se procesan en servidores ubicados en la Unión Europea y se eliminan al terminar la importación: solo se guardan los datos extraídos. No vendemos ni cedemos tus datos. Puedes descargarlos o eliminar tu cuenta y todos tus datos en cualquier momento desde Facturación.',
  },
  {
    q: '¿FinView es compatible con mi broker?',
    a: 'Actualmente soportamos Trade Republic (Tax Report PDF o CSV), DEGIRO (Informe Anual PDF), Interactive Brokers (Activity Statement CSV), ING (Información Fiscal PDF), BBVA (PDF) y eToro (Account Statement XLSX).',
  },
  {
    q: '¿Los cálculos del IRPF son fiables?',
    a: 'Nuestro motor FIFO cross-broker aplica la normativa española del IRPF a los datos de todos tus brokers, cruzando compras y ventas entre cuentas para estimar las casillas del Modelo 100 y 714. Son estimaciones orientativas, no asesoramiento fiscal: revísalas siempre antes de presentar tu declaración.',
  },
];

function CheckIcon({ inverted }: { inverted?: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="8" fill={inverted ? 'rgba(154,107,31,0.25)' : 'var(--fv-ochre-ghost)'}/>
      <path d="M4.5 8l2.5 2.5 4-4"
        stroke={inverted ? 'var(--fv-ochre-soft)' : 'var(--fv-ochre)'}
        strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

export default function PricingPage() {
  return (
    <Suspense fallback={
      <div className={styles.loading}>
        <p className={styles.loadingText}>Cargando...</p>
      </div>
    }>
      <PricingContent />
    </Suspense>
  );
}

function PricingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const success = searchParams.get('success');
  const canceled = searchParams.get('canceled');
  const [loading, setLoading] = useState<string | null>(null);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  useEffect(() => {
    if (!success) return;
    const t = setTimeout(() => router.push('/dashboard'), 2000);
    return () => clearTimeout(t);
  }, [success, router]);

  async function handleCheckout(priceId: string, tier: string, href: string) {
    if (!priceId) {
      router.push(href);
      return;
    }
    setLoading(tier);
    try {
      const { url } = await api.billing.checkout(priceId);
      window.location.assign(url);
    } catch {
      router.push(href);
    }
  }

  return (
    <div className={styles.page}>
      <PublicNav />

      {/* ── Hero ── */}
      <section className={styles.hero}>
        <span className={styles.eyebrow}>
          <span className={styles.dot} />
          Precios
        </span>
        <h1 className={styles.h1}>
          Transparente, sin{' '}
          <em className={styles.em}>letra pequeña</em>
        </h1>
        <p className={styles.lead}>
          Empieza gratis. Actualiza solo si necesitas más. Sin permanencia, sin sorpresas.
        </p>
        <p className={styles.lead} style={{ fontSize: 14 }}>
          Hoy FinView es gratuito: los planes Pro y Unlimited todavía no están a la venta y no te
          pediremos ningún medio de pago. El uso se rige por las{' '}
          <a href="/legal/condiciones" className={styles.footerCtaLink}>Condiciones de uso</a>.
        </p>
      </section>

      {/* ── Alerts ── */}
      {(success || canceled) && (
        <div className={styles.alertWrap}>
          {success && <div className={styles.alertSuccess}>¡Suscripción activada! Redirigiendo al panel...</div>}
          {canceled && <div className={styles.alertCanceled}>Pago cancelado. Puedes elegir un plan cuando quieras.</div>}
        </div>
      )}

      {/* ── Plans ── */}
      <section className={styles.plansSection}>
        <div className={styles.plansGrid}>
          {PLANS.map((plan) => {
            const isHighlight = plan.highlight;
            const btnCls = [
              isHighlight ? styles.planBtnHighlight : styles.planBtn,
              loading === plan.tier ? styles.planBtnLoading : '',
            ].filter(Boolean).join(' ');

            return (
              <div key={plan.tier} className={isHighlight ? styles.planCardHighlight : styles.planCard}>
                {isHighlight && <span className={styles.planBadge}>Más popular</span>}
                <p className={isHighlight ? styles.planNameHighlight : styles.planName}>{plan.name}</p>
                <div className={styles.planPriceRow}>
                  <span className={isHighlight ? styles.planPriceHighlight : styles.planPrice}>{plan.price}</span>
                  <span className={isHighlight ? styles.planPeriodHighlight : styles.planPeriod}>{plan.period}</span>
                </div>
                <p className={isHighlight ? styles.planDescHighlight : styles.planDesc}>{plan.desc}</p>
                <button
                  type="button"
                  disabled={loading === plan.tier}
                  onClick={() => handleCheckout(plan.priceId ?? '', plan.tier, plan.href)}
                  className={btnCls}
                >
                  {loading === plan.tier ? 'Redirigiendo...' : plan.cta}
                </button>
                <ul className={styles.planFeatures}>
                  {plan.features.map((f) => (
                    <li key={f} className={isHighlight ? styles.planFeatureHighlight : styles.planFeature}>
                      <span className={styles.featureIcon}><CheckIcon inverted={isHighlight} /></span>
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── FAQ ── */}
      <section className={styles.faqBg}>
        <div className={styles.faqInner}>
          <h2 className={styles.h2}>Preguntas frecuentes</h2>
          <div className={styles.faqList}>
            {FAQ.map(({ q, a }, i) => (
              <div key={q} className={styles.faqItem}>
                <button
                  type="button"
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className={styles.faqBtn}
                >
                  {q}
                  <span className={`${styles.faqToggle}${openFaq === i ? ` ${styles.faqToggleOpen}` : ''}`}>+</span>
                </button>
                {openFaq === i && <p className={styles.faqAnswer}>{a}</p>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer CTA ── */}
      <section className={styles.footerCta}>
        <p className={styles.footerCtaText}>
          ¿Tienes dudas? Escríbenos a{' '}
          <a href={`mailto:${LEGAL.email}`} className={styles.footerCtaLink}>{LEGAL.email}</a>
        </p>
        <a href="/register" className={styles.ctaPrimary}>Empezar gratis →</a>
      </section>

      <PublicFooter />
    </div>
  );
}
