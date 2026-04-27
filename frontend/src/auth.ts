import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Credentials({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const res = await fetch(`${backendUrl}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: credentials?.email,
            password: credentials?.password,
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

      // Everything else (including /dashboard) requires auth
      return isLoggedIn;
    },
  },
});
