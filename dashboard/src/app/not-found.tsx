import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh items-center justify-center p-6">
      <div className="flex max-w-sm flex-col gap-4">
        <h1 className="text-3xl font-semibold">Page not found</h1>
        <p className="text-base text-ink-2">This address doesn&apos;t exist.</p>
        <Link href="/" className="btn-primary self-start">
          Go to the overview
        </Link>
      </div>
    </main>
  );
}
