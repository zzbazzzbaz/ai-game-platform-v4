import { useMemo } from 'react';
import { diffLines } from 'diff';

interface Props {
  filename: string;
  before: string;
  after: string;
}

export function FileDiff({ filename, before, after }: Props) {
  const rows = useMemo(
    () =>
      diffLines(before, after).flatMap((chunk) =>
        chunk.value
          .replace(/\n$/, '')
          .split('\n')
          .map((text) => ({ text, added: chunk.added, removed: chunk.removed })),
      ),
    [before, after],
  );

  const added = rows.filter((row) => row.added).length;
  const removed = rows.filter((row) => row.removed).length;

  return (
    <div className="overflow-hidden rounded-lg border border-ink-700 bg-ink-950 font-mono text-xs">
      <div className="flex items-center justify-between border-b border-ink-700 bg-ink-850 px-3 py-1.5 text-[11px] text-mist-400">
        <span className="truncate">{filename}</span>
        <span>
          +{added} / -{removed}
        </span>
      </div>
      <div className="max-h-80 overflow-auto py-1">
        {rows.map((row, index) => {
          const tone = row.added
            ? 'bg-emerald-500/10 text-emerald-300'
            : row.removed
              ? 'bg-red-500/10 text-red-300'
              : 'text-mist-300';
          return (
            <div key={index} className={`whitespace-pre-wrap px-3 py-0.5 ${tone}`}>
              <span className="mr-2 select-none text-mist-400/60">
                {row.added ? '+' : row.removed ? '-' : ' '}
              </span>
              {row.text || ' '}
            </div>
          );
        })}
      </div>
    </div>
  );
}
