'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { PublicNav } from '@/components/PublicNav';
import { PublicFooter } from '@/components/PublicFooter';
import { api } from '@/lib/api';

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
      <div style={{ background: 'var(--fv-paper)', minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <p style={{ color: 'var(--fv-ink-40)', fontFamily: 'var(--fv-font-sans)' }}>Cargando...</p>
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
    <div style={{ background: 'var(--fv-paper)', color: 'var(--fv-ink)', minHeight: '100vh', fontFamily: 'var(--fv-font-sans)' }}>
      <PublicNav />

      {/* ── Hero ── */}
      <section style={{ maxWidth: 1320, margin: '0 auto', padding: '80px 32px 64px', textAlign: 'center' }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 8,
          fontSize: 11, fontWeight: 500, textTransform: 'uppercase',
          letterSpacing: '0.18em', color: 'var(--fv-ink-40)', marginBottom: 24,
        }}>
          <span style={{ width: 6, height: 6, borderRadius: 999, background: 'var(--fv-ochre)', display: 'inline-block' }} />
          Precios
        </span>
        <h1 style={{
          fontFamily: 'var(--fv-font-display)', fontWeight: 400,
          fontSize: 'clamp(2.4rem, 5vw, 4.5rem)', lineHeight: 1.05,
          letterSpacing: '-0.02em', color: 'var(--fv-ink)',
          margin: '0 0 20px',
        }}>
          Transparente, sin{' '}
          <em style={{ color: 'var(--fv-ochre)', fontStyle: 'italic' }}>letra pequeña</em>
        </h1>
        <p style={{ fontSize: 18, lineHeight: 1.6, color: 'var(--fv-ink-70)', maxWidth: 440, margin: '0 auto' }}>
          Empieza gratis. Actualiza solo si necesitas más. Sin permanencia, sin sorpresas.
        </p>
      </section>

      {/* ── Alerts ── */}
      {(success || canceled) && (
        <div style={{ maxWidth: 600, margin: '0 auto 24px', padding: '0 32px' }}>
          {success && (
            <div style={{
              background: 'rgba(107,122,58,0.08)', border: '1px solid rgba(107,122,58,0.2)',
              borderRadius: 12, padding: '16px 20px', color: 'var(--fv-success)', fontSize: 14,
            }}>
              ¡Suscripción activada! Redirigiendo al panel...
            </div>
          )}
          {canceled && (
            <div style={{
              background: 'rgba(154,107,31,0.08)', border: '1px solid rgba(154,107,31,0.2)',
              borderRadius: 12, padding: '16px 20px', color: 'var(--fv-ochre)', fontSize: 14,
            }}>
              Pago cancelado. Puedes elegir un plan cuando quieras.
            </div>
          )}
        </div>
      )}

      {/* ── Plans ── */}
      <section style={{ maxWidth: 1100, margin: '0 auto', padding: '0 32px 96px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20, alignItems: 'start' }}>
          {PLANS.map((plan) => (
            <div key={plan.tier} style={{
              background: plan.highlight ? 'var(--fv-ink)' : 'var(--fv-paper)',
              border: plan.highlight ? 'none' : '1px solid var(--fv-ink-15)',
              borderRadius: 20, padding: '40px 32px', position: 'relative',
              boxShadow: plan.highlight ? 'var(--fv-shadow-lg)' : 'none',
            }}>
              {plan.highlight && (
                <span style={{
                  position: 'absolute', top: -12, left: '50%', transform: 'translateX(-50%)',
                  background: 'var(--fv-ochre)', color: 'var(--fv-paper)',
                  fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.12em',
                  borderRadius: 999, padding: '5px 14px',
                }}>
                  Más popular
                </span>
              )}
              <p style={{
                fontSize: 13, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em',
                color: plan.highlight ? 'rgba(245,241,232,0.5)' : 'var(--fv-ink-40)', margin: '0 0 12px',
              }}>
                {plan.name}
              </p>
              <div style={{ marginBottom: 8 }}>
                <span style={{
                  fontFamily: 'var(--fv-font-display)', fontSize: 40,
                  color: plan.highlight ? 'var(--fv-paper)' : 'var(--fv-ink)', lineHeight: 1,
                }}>
                  {plan.price}
                </span>
                <span style={{ fontSize: 15, color: plan.highlight ? 'rgba(245,241,232,0.6)' : 'var(--fv-ink-60)', marginLeft: 4 }}>
                  {plan.period}
                </span>
              </div>
              <p style={{
                fontSize: 13, lineHeight: 1.5,
                color: plan.highlight ? 'rgba(245,241,232,0.65)' : 'var(--fv-ink-60)',
                margin: '0 0 28px', minHeight: 40,
              }}>
                {plan.desc}
              </p>
              <button
                type="button"
                disabled={loading === plan.tier}
                onClick={() => handleCheckout(plan.priceId ?? '', plan.tier, plan.href)}
                style={{
                  width: '100%',
                  background: plan.highlight ? 'var(--fv-ochre)' : 'transparent',
                  color: plan.highlight ? 'var(--fv-paper)' : 'var(--fv-ink)',
                  border: plan.highlight ? 'none' : '1px solid var(--fv-ink-30)',
                  borderRadius: 'var(--fv-r-pill)', padding: '13px',
                  fontSize: 14, fontFamily: 'var(--fv-font-sans)', fontWeight: 600,
                  cursor: loading === plan.tier ? 'default' : 'pointer',
                  marginBottom: 28, opacity: loading === plan.tier ? 0.6 : 1,
                }}
              >
                {loading === plan.tier ? 'Redirigiendo...' : plan.cta}
              </button>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
                {plan.features.map((f) => (
                  <li key={f} style={{
                    display: 'flex', alignItems: 'flex-start', gap: 10,
                    fontSize: 13, color: plan.highlight ? 'rgba(245,241,232,0.8)' : 'var(--fv-ink-70)',
                  }}>
                    <span style={{ marginTop: 1, flexShrink: 0 }}>
                      <CheckIcon inverted={plan.highlight} />
                    </span>
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* ── FAQ ── */}
      <section style={{ background: 'var(--fv-ink-05)', padding: '80px 0' }}>
        <div style={{ maxWidth: 720, margin: '0 auto', padding: '0 32px' }}>
          <h2 style={{
            fontFamily: 'var(--fv-font-display)', fontWeight: 400,
            fontSize: 'clamp(1.8rem, 3.5vw, 2.6rem)', letterSpacing: '-0.02em',
            color: 'var(--fv-ink)', marginBottom: 40, textAlign: 'center',
          }}>
            Preguntas frecuentes
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {FAQ.map(({ q, a }, i) => (
              <div key={q} style={{ borderBottom: '1px solid var(--fv-ink-10)' }}>
                <button
                  type="button"
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  style={{
                    width: '100%', textAlign: 'left', background: 'none', border: 'none',
                    padding: '20px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    fontSize: 15, fontWeight: 500, color: 'var(--fv-ink)',
                    fontFamily: 'var(--fv-font-sans)', cursor: 'pointer', gap: 16,
                  }}
                >
                  {q}
                  <span style={{
                    color: 'var(--fv-ink-40)', fontSize: 20, lineHeight: 1, flexShrink: 0,
                    transform: openFaq === i ? 'rotate(45deg)' : 'none',
                    transition: 'transform 200ms', display: 'inline-block',
                  }}>+</span>
                </button>
                {openFaq === i && (
                  <p style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--fv-ink-70)', margin: '0 0 20px', paddingRight: 32 }}>
                    {a}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer CTA ── */}
      <section style={{ maxWidth: 1320, margin: '0 auto', padding: '80px 32px', textAlign: 'center' }}>
        <p style={{ fontSize: 17, color: 'var(--fv-ink-70)', margin: '0 0 24px' }}>
          ¿Tienes dudas? Escríbenos a{' '}
          <a href="mailto:hola@finview.app" style={{ color: 'var(--fv-ochre)', textDecoration: 'none' }}>hola@finview.app</a>
        </p>
        <a href="/register" style={{
          background: 'var(--fv-ochre)', color: 'var(--fv-paper)',
          borderRadius: 'var(--fv-r-pill)', padding: '14px 28px',
          fontSize: 15, fontWeight: 500, textDecoration: 'none', display: 'inline-block',
        }}>
          Empezar gratis →
        </a>
      </section>

      <PublicFooter />
    </div>
  );
}
