interface Props {
  output: string;
  running?: boolean;
}

export function ShellOutput({ output, running }: Props) {
  if (!output && !running) return null;
  const exit =
    /\[exit code:\s*(-?\d+)\]/.exec(output) ??
    /"exit_code":\s*(-?\d+)/.exec(output) ??
    /===\s*exit:\s*(-?\d+)\s*===/.exec(output);
  const failed = exit ? Number(exit[1]) !== 0 : false;

  return (
    <div className="overflow-hidden rounded-lg border border-ink-700 bg-black/40">
      <div className="flex items-center justify-between border-b border-ink-700 px-3 py-1.5 text-[11px] text-mist-400">
        <span>terminal</span>
        {running ? (
          <span className="flex items-center gap-1.5 text-accent-400">
            <span className="h-1.5 w-1.5 rounded-full bg-accent-400 animate-pulse-dot" />
            运行中
          </span>
        ) : exit ? (
          <span className={failed ? 'text-red-400' : 'text-emerald-400'}>
            exit {exit[1]}
          </span>
        ) : null}
      </div>
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap px-3 py-2 font-mono text-xs leading-relaxed text-mist-200">
        {output || '…'}
      </pre>
    </div>
  );
}
