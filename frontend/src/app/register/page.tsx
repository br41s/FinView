"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import styles from "./register.module.css";

function LogoMark() {
  return (
    <svg viewBox="0 0 64 64" width="36" height="36" fill="none" aria-hidden="true">
      <path d="M32 54 C32 42 32 34 32 22" stroke="var(--fv-ink,#1F1B16)" strokeWidth="3" strokeLinecap="round"/>
      <path d="M32 34 C22 34 14 28 12 18 C22 18 30 24 32 34 Z" fill="var(--fv-ochre,#9A6B1F)"/>
      <path d="M32 24 C42 24 50 18 52 10 C44 10 36 14 32 24 Z" fill="var(--fv-ochre,#9A6B1F)" opacity="0.6"/>
    </svg>
  );
}

export default function RegisterPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, name, password, accept_terms: acceptTerms }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => null);
      setError(data?.detail || "Error al registrarse");
      setLoading(false);
      return;
    }

    const result = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });

    setLoading(false);

    if (result?.error) {
      setError("Registro exitoso pero error al iniciar sesión. Prueba a entrar.");
    } else {
      router.push("/dashboard");
      router.refresh();
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>

        <div className={styles.brand}>
          <div className={styles.logoWrap}>
            <LogoMark />
          </div>
          <h1 className={styles.title}>finview</h1>
          <p className={styles.subtitle}>Crea tu cuenta gratis</p>
        </div>

        <div className={styles.card}>
          <form onSubmit={handleSubmit} className={styles.form}>
            <div className={styles.field}>
              <Label htmlFor="name">Nombre</Label>
              <Input
                id="name"
                type="text"
                placeholder="Tu nombre"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
              />
            </div>
            <div className={styles.field}>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="tu@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>
            <div className={styles.field}>
              <Label htmlFor="password">Contraseña</Label>
              <Input
                id="password"
                type="password"
                placeholder="Mínimo 8 caracteres"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </div>
            <label className={styles.consent}>
              <input
                type="checkbox"
                checked={acceptTerms}
                onChange={(e) => setAcceptTerms(e.target.checked)}
                required
              />
              <span>
                Soy mayor de 18 años, entiendo que FinView muestra datos y no presta
                asesoramiento financiero, y acepto las{" "}
                <Link href="/legal/condiciones" target="_blank" className={styles.footerLink}>
                  Condiciones de uso
                </Link>{" "}
                y la{" "}
                <Link href="/legal/privacidad" target="_blank" className={styles.footerLink}>
                  Política de privacidad
                </Link>
                .
              </span>
            </label>
            {error && <p className={styles.error}>{error}</p>}
            <Button type="submit" className="w-full" disabled={loading || !acceptTerms}>
              {loading ? "Creando cuenta..." : "Crear cuenta"}
            </Button>
          </form>
        </div>

        <p className={styles.footer}>
          ¿Ya tienes cuenta?{" "}
          <Link href="/login" className={styles.footerLink}>
            Inicia sesión
          </Link>
        </p>
      </div>
    </div>
  );
}
