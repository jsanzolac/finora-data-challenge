import { Suspense } from "react";
import { RequireAuth } from "@/components/providers/AuthGate";
import { OverviewScreen } from "@/components/overview/OverviewScreen";
import { FullPageLoader } from "@/components/ui/FullPageLoader";

export default function OverviewPage() {
  return (
    <Suspense fallback={<FullPageLoader label="Loading" />}>
      <RequireAuth>
        <OverviewScreen />
      </RequireAuth>
    </Suspense>
  );
}
