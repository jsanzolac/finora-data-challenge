import type { Metadata } from "next";
import { Suspense } from "react";
import { RequireAuth } from "@/components/providers/AuthGate";
import { ChangePasswordForm } from "@/components/auth/ChangePasswordForm";
import { FullPageLoader } from "@/components/ui/FullPageLoader";

export const metadata: Metadata = { title: "Change password · Data quality · Finora" };

export default function ChangePasswordPage() {
  return (
    <Suspense fallback={<FullPageLoader label="Loading" />}>
      <RequireAuth allowPasswordChangePending>
        <ChangePasswordForm />
      </RequireAuth>
    </Suspense>
  );
}
