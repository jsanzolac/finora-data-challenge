/**
 * Rule descriptions come from docs/approved_data_rules.md, where column names,
 * codes and patterns are wrapped in backticks. They render as inline code.
 * This is plain text splitting: nothing is parsed as HTML.
 */
export function RichText({ text }: { text: string }) {
  const parts = text.split("`");
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <code key={index} className="rounded bg-surface-2 px-1 py-px font-mono text-[0.85em] text-ink">
            {part}
          </code>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}
