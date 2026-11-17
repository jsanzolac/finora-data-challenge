"use client";

import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as Tooltip from "@radix-ui/react-tooltip";
import { ApiError } from "@/lib/api/client";
import { AuthProvider } from "@/lib/auth/store";
import { FullPageLoader } from "@/components/ui/FullPageLoader";
// `@finora/voice` is the voice UI only when NEXT_PUBLIC_VOICE=1; otherwise an inert stub (next.config.ts).
import { VoiceProvider } from "@finora/voice";

const MOCKS_ENABLED = process.env.NEXT_PUBLIC_DQ_MOCKS === "1";

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          // 4xx answers are final (401 and 403 are handled by the API client). Retry the rest once.
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
          return failureCount < 1;
        },
      },
    },
  });
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(makeQueryClient);
  // In mock mode the fetch adapter must be in place before the first API call.
  const [ready, setReady] = useState(!MOCKS_ENABLED);

  useEffect(() => {
    if (!MOCKS_ENABLED) return;
    let cancelled = false;
    // `@dq/mock-install` is resolved by next.config.ts: to dashboard/mocks/install.ts
    // in mock mode, and to a stub otherwise, so the mocks are never in a real build.
    if (process.env.NEXT_PUBLIC_DQ_MOCKS === "1") {
      void import("@dq/mock-install").then(({ installMockApi }) => {
        installMockApi();
        if (!cancelled) setReady(true);
      });
    }
    return () => {
      cancelled = true;
    };
  }, []);

  if (!ready) return <FullPageLoader label="Starting mock mode" />;

  return (
    <QueryClientProvider client={queryClient}>
      <Tooltip.Provider delayDuration={200} skipDelayDuration={300}>
        <AuthProvider>
          <VoiceProvider>{children}</VoiceProvider>
        </AuthProvider>
      </Tooltip.Provider>
    </QueryClientProvider>
  );
}
