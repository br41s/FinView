import "next-auth";

declare module "next-auth" {
  interface Session {
    accessToken: string;
    user: {
      id: string;
      email: string;
      name: string;
      subscription_tier?: string;
    };
  }

  interface User {
    accessToken?: string;
    subscriptionTier?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string;
    userId?: string;
    subscriptionTier?: string;
  }
}
