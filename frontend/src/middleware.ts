export { auth as middleware } from "@/auth";

export const config = {
  matcher: [
    // Run middleware on all routes except API, static files, and images
    "/((?!api|_next/static|_next/image|favicon.ico).*)",
  ],
};
