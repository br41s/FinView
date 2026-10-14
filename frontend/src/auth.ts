import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

import { decodeExp, shouldRefresh } from "@/lib/tokenExpiry";

const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";

// Keep the backend token alive while the session is in use. It is only minted
// at login and lived exactly 90 days, while this cookie rolls forward on
// activity, so a session used daily still went dark on day 90 with a 401 on
// every call (production, 2026-10-14). Runs server-side in the jwt callback;
// a failed refresh keeps the old token and waits an hour before trying again,
// so a backend outage costs one call per hour, not one per request.
const REFRESH_RETRY_SECONDS = 60 * 60;

async function refreshAccessToken(accessToken: string): Promise<string | null> {
  try {
    const res = await fetch(`${backendUrl}/api/auth/refresh`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { token?: unknown };
    return typeof data.token === "string" && data.token ? data.token : null;
  } catch {
    return null;
  }
}

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Credentials({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
        turnstileToken: { label: "Turnstile", type: "text" },
      },
      async authorize(credentials) {
        const res = await fetch(`${backendUrl}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: credentials?.email,
            password: credentials?.password,
            turnstile_token: credentials?.turnstileToken,
          }),
        });

        if (!res.ok) return null;

        const data = await res.json();
        return {
          id: String(data.user.id),
          email: data.user.email,
          name: data.user.name,
          accessToken: data.token,
          subscriptionTier: data.user.subscription_tier || "FREE",
        };
      },
    }),
  ],
  pages: {
    signIn: "/login",
  },
  session: { strategy: "jwt", maxAge: 60 * 60 * 24 * 90 }, // 90 days
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.accessToken = (user as { accessToken: string }).accessToken;
        token.userId = user.id;
        token.subscriptionTier = (
          user as { subscriptionTier: string }
        ).subscriptionTier;
        return token;
      }
      const now = Math.floor(Date.now() / 1000);
      const current = token.accessToken as string | undefined;
      const retryAfter = (token.refreshAfter as number | undefined) ?? 0;
      if (current && shouldRefresh(decodeExp(current), now) && retryAfter <= now) {
        const fresh = await refreshAccessToken(current);
        if (fresh) {
          token.accessToken = fresh;
          delete token.refreshAfter;
        } else {
          token.refreshAfter = now + REFRESH_RETRY_SECONDS;
        }
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken as string;
      if (session.user) {
        session.user.id = token.userId as string;
        (session.user as { subscription_tier?: string }).subscription_tier =
          (token.subscriptionTier as string) || "FREE";
      }
      return session;
    },
    authorized({ auth, request: { nextUrl } }) {
      const isLoggedIn = !!auth?.user;
      const { pathname } = nextUrl;

      // Landing page: public, but redirect logged-in users straight to the dashboard
      if (pathname === "/") {
        if (isLoggedIn) return Response.redirect(new URL("/dashboard", nextUrl));
        return true;
      }

      // Auth pages: redirect logged-in users to dashboard
      const isAuthPage =
        pathname.startsWith("/login") || pathname.startsWith("/register");
      if (isAuthPage) {
        if (isLoggedIn) return Response.redirect(new URL("/dashboard", nextUrl));
        return true;
      }

      // Public marketing pages
      if (pathname.startsWith("/pricing")) return true;
      if (pathname.startsWith("/features")) return true;
      if (pathname.startsWith("/blog")) return true;
      // Legal documents must be readable before an account exists.
      if (pathname.startsWith("/legal")) return true;

      // Everything else (including /dashboard) requires auth
      return isLoggedIn;
    },
  },
});
