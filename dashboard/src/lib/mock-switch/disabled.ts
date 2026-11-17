/**
 * What `@dq/mock-install` resolves to in every build without NEXT_PUBLIC_DQ_MOCKS=1
 * (see next.config.ts). It keeps dashboard/mocks/ out of the module graph, so no
 * fixture, demo account or fetch adapter can reach the deployable export.
 */
export function installMockApi(): void {
  throw new Error("Mock mode is not part of this build.");
}
