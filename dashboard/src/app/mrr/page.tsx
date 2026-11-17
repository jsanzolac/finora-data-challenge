import type { Metadata } from "next";
import { Suspense } from "react";
import { RequireAuth } from "@/components/providers/AuthGate";
import { MrrScreen } from "@/components/mrr/MrrScreen";
import { FullPageLoader } from "@/components/ui/FullPageLoader";

export const metadata: Metadata = {
  title: "MRR · Finora",
  description: "Why MRR changed: customer behaviour, pricing, discounts and the timing of payments.",
};

export default function MrrPage() {
  return (
    <Suspense fallback={<FullPageLoader label="Loading" />}>
      <RequireAuth>
        <MrrScreen />
      </RequireAuth>
    </Suspense>
  );
}
