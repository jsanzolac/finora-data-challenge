import type { Metadata } from "next";
import { Suspense } from "react";
import { RequireSignedOut } from "@/components/providers/AuthGate";
import { LoginForm } from "@/components/auth/LoginForm";
import { FullPageLoader } from "@/components/ui/FullPageLoader";

export const metadata: Metadata = { title: "Sign in · Data quality · Finora" };

export default function LoginPage() {
  return (
    <Suspense fallback={<FullPageLoader label="Loading" />}>
      <RequireSignedOut>
        <LoginForm />
      </RequireSignedOut>
    </Suspense>
  );
}
