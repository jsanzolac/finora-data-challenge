import type { Metadata } from "next";
import { Suspense } from "react";
import { RequireAuth } from "@/components/providers/AuthGate";
import { AcquisitionScreen } from "@/components/acq/AcquisitionScreen";
import { FullPageLoader } from "@/components/ui/FullPageLoader";

export const metadata: Metadata = {
  title: "Acquisition · Finora",
  description: "New customers, the estimated funnel and what spend does and doesn't explain.",
};

export default function AcquisitionPage() {
  return (
    <Suspense fallback={<FullPageLoader label="Loading" />}>
      <RequireAuth>
        <AcquisitionScreen />
      </RequireAuth>
    </Suspense>
  );
}
