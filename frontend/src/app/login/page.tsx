"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

function LogoMark() {
  return (
    <svg viewBox="0 0 64 64" width="36" height="36" fill="none" aria-hidden="true">
      <path d="M32 54 C32 42 32 34 32 22" stroke="var(--fv-ink,#1F1B16)" strokeWidth="3" strokeLinecap="round"/>
      <path d="M32 34 C22 34 14 28 12 18 C22 18 30 24 32 34 Z" fill="var(--fv-ochre,#9A6B1F)"/>
      <path d="M32 24 C42 24 50 18 52 10 C44 10 36 14 32 24 Z" fill="var(--fv-ochre,#9A6B1F)" opacity="0.6"/>
    </svg>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const result = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });

    setLoading(false);

    if (result?.error) {
      setError("Email o contraseña incorrectos");
    } else {
      router.push("/dashboard");
      router.refresh();
    }
  }

  return (
    <div style={{
      background: "var(--fv-paper,#F5F1E8)",
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontFamily: "var(--fv-font-sans,system-ui)",
      padding: "24px",
    }}>
      <div style={{ width: "100%", maxWidth: 400 }}>

        {/* Brand mark */}
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 14 }}>
            <LogoMark />
          </div>
          <h1 style={{
            fontFamily: "var(--fv-font-display,Georgia,serif)",
            fontSize: 30, fontWeight: 400,
            letterSpacing: "-0.02em",
            color: "var(--fv-ink,#1F1B16)",
            margin: "0 0 6px",
          }}>
            finview
          </h1>
          <p style={{ fontSize: 14, color: "var(--fv-ink-60,rgba(31,27,22,0.6))", margin: 0 }}>
            Inicia sesión en tu cuenta
          </p>
        </div>

        {/* Form */}
        <div style={{
          background: "var(--card,#FEFCF5)",
          border: "1px solid var(--fv-ink-15,rgba(31,27,22,0.15))",
          borderRadius: 16,
          padding: "32px",
          boxShadow: "var(--fv-shadow-md,0 4px 16px rgba(31,27,22,0.08))",
        }}>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
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
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <Label htmlFor="password">Contraseña</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </div>
            {error && (
              <p style={{ fontSize: 13, color: "var(--fv-danger,#9B3D2C)", margin: 0 }}>
                {error}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Entrando..." : "Entrar"}
            </Button>
          </form>
        </div>

        <p style={{
          marginTop: 24, textAlign: "center",
          fontSize: 14, color: "var(--fv-ink-60,rgba(31,27,22,0.6))",
        }}>
          ¿No tienes cuenta?{" "}
          <Link href="/register" style={{ color: "var(--fv-ochre,#9A6B1F)", textDecoration: "none", fontWeight: 500 }}>
            Regístrate
          </Link>
        </p>
      </div>
    </div>
  );
}
