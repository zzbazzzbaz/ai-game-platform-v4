import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { outputText, summarizeInput, toolMeta, toolNameFromPartType } from '@/lib/tool-meta';
import { ShellOutput } from './ShellOutput';
import { FileDiff } from './FileDiff';

export interface ToolPart {
  type: string;
  toolCallId?: string;
  toolName?: string;
  state?: string;
  input?: unknown;
  output?: unknown;
  errorText?: string;
  approval?: {
    id: string;
    approved?: boolean;
    reason?: string;
    requestReason?: string;
    isAutomatic?: boolean;
  };
}

const STATE_LABEL: Record<string, { label: string; className: string }> = {
  'input-streaming': { label: '准备中', className: 'text-mist-400 bg-ink-700/60' },
  'input-available': { label: '运行中', className: 'text-accent-400 bg-accent-500/10' },
  'approval-requested': { label: '等待审批', className: 'text-amber-300 bg-amber-400/10' },
  'approval-responded': { label: '已审批', className: 'text-accent-400 bg-accent-500/10' },
  'output-available': { label: '完成', className: 'text-emerald-300 bg-emerald-500/10' },
  'output-error': { label: '失败', className: 'text-red-300 bg-red-500/10' },
  'output-denied': { label: '已拒绝', className: 'text-red-300 bg-red-500/10' },
};

export function ToolCallCard({ part }: { part: ToolPart }) {
  const toolName = part.type === 'dynamic-tool' ? (part.toolName ?? 'tool') : toolNameFromPartType(part.type);
  const meta = toolMeta(toolName);
  const state = part.state ?? 'input-available';
  const badge = STATE_LABEL[state] ?? { label: state, className: 'text-mist-400 bg-ink-700/60' };
  const [open, setOpen] = useState(state === 'output-error' || state === 'approval-requested' || state === 'input-available');
  const input = (part.input ?? {}) as Record<string, unknown>;
  const output = outputText(part.output);
  const busy = state === 'input-streaming' || state === 'input-available' || state === 'approval-responded';
  const summary = summarizeInput(part.input);

  const isShell = toolName === 'shell' || toolName === 'run_command' || toolName === 'start_command';
  const isWrite = toolName === 'write_file';
  const isEdit = toolName === 'edit_file';
  const isRead = toolName === 'read_file';

  return (
    <div className="my-2 overflow-hidden rounded-xl border border-ink-700 bg-ink-900/80 shadow-panel">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-ink-800/60"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-mist-400" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-mist-400" />
        )}
        <meta.Icon className="h-4 w-4 shrink-0 text-accent-400" />
        <span className="text-sm font-medium text-mist-200">{meta.title}</span>
        {summary && (
          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-mist-400">{summary}</span>
        )}
        <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium', badge.className)}>
          {badge.label}
        </span>
      </button>

      {open && (
        <div className="space-y-2 border-t border-ink-700/80 px-3 py-3">
          {isShell ? (
            <>
              <pre className="overflow-x-auto rounded-lg bg-ink-950 px-3 py-2 font-mono text-xs text-accent-400">
                $ {String(input.command ?? '')}
              </pre>
              <ShellOutput output={output} running={busy} />
            </>
          ) : isWrite ? (
            <>
              <div className="font-mono text-[11px] text-mist-400">{String(input.path ?? '')}</div>
              <FileDiff filename={String(input.path ?? 'file')} before="" after={String(input.content ?? '')} />
            </>
          ) : isEdit ? (
            <>
              <div className="font-mono text-[11px] text-mist-400">{String(input.path ?? '')}</div>
              <FileDiff
                filename={String(input.path ?? 'file')}
                before={String(input.old_text ?? input.old_string ?? '')}
                after={String(input.new_text ?? input.new_string ?? '')}
              />
            </>
          ) : isRead ? (
            <>
              <div className="font-mono text-[11px] text-mist-400">{String(input.path ?? '')}</div>
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-ink-950 px-3 py-2 font-mono text-xs text-mist-200">
                {output || '…'}
              </pre>
            </>
          ) : (
            <>
              {part.input != null && (
                <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-ink-950 px-3 py-2 font-mono text-[11px] text-mist-300">
                  {JSON.stringify(part.input, null, 2)}
                </pre>
              )}
              {output && (
                <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-ink-950 px-3 py-2 font-mono text-xs text-mist-200">
                  {output}
                </pre>
              )}
            </>
          )}

          {state === 'output-error' && part.errorText && (
            <pre className="whitespace-pre-wrap rounded-lg bg-red-500/10 px-3 py-2 font-mono text-xs text-red-300">
              {part.errorText}
            </pre>
          )}
          {state === 'output-denied' && (
            <div className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">
              已拒绝执行{part.approval?.reason ? `：${part.approval.reason}` : '。'}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
