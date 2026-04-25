'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';
import { api } from '@/lib/api';
import styles from './pricing.module.css';

const PLANS = [
  {
    tier: 'FREE',
    name: 'Gratis',
    price: '0 €',
    period: 'para siempre',
    desc: 'Para empezar a organizar tus dividendos sin compromiso.',
    features: [
      'Hasta 10 posiciones en cartera',
      '1 broker conectado',
      'Importación manual de archivos',
      'Dashboard de dividendos básico',
      'Casillas IRPF (Modelo 100)',
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
      'Posiciones ilimitadas',
      'Hasta 3 brokers conectados',
      'Importaciones ilimitadas',
      'Dashboard fiscal completo',
      'FIFO cross-broker automático',
      'Exportación CSV de datos',
      'Comparativa anual de dividendos',
      'Modelo 100 y Modelo 714',
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
      'Brokers ilimitados',
      'API de acceso a datos',
      'Soporte prioritario por email',
      'Acceso anticipado a nuevas funciones',
      'Exportación PDF declaración IRPF',
    ],
    cta: 'Empezar con Unlimited',
    href: '/register?plan=UNLIMITED',
    priceId: process.env.NEXT_PUBLIC_STRIPE_PRICE_UNLIMITED || '',
    highlight: false,
  },
];

const FAQ = [
  {
    q: '¿Puedo cambiar de plan en cualquier momento?',
    a: 'Sí. Puedes subir o bajar de plan desde el dashboard sin penalización. El ajuste se aplica desde el siguiente ciclo de facturación.',
  },
  {
    q: '¿Mis datos fiscales están seguros?',
    a: 'Todos los archivos que subes se procesan en nuestros servidores seguros y nunca se comparten con terceros. Puedes eliminar tu cuenta y todos tus datos en cualquier momento.',
  },
  {
    q: '¿FinView es compatible con mi broker?',
    a: 'Actualmente soportamos Trade Republic (Tax Report PDF), DEGIRO (CSV de transacciones y cuenta) e IBKR (Activity Statement CSV). Próximamente más brokers.',
  },
  {
    q: '¿Los cálculos del IRPF son fiables?',
    a: 'Validamos nuestro motor FIFO contra los cálculos pre-computados que Trade Republic incluye en su Tax Report. Los resultados son idénticos para los datos de TR.',
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
      window.location.href = url;
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
          <a href="mailto:hola@finview.app" className={styles.footerCtaLink}>hola@finview.app</a>
        </p>
        <a href="/register" className={styles.ctaPrimary}>Empezar gratis →</a>
      </section>

      <PublicFooter />
    </div>
  );
}
