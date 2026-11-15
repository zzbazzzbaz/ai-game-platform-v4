import { useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toolMeta, toolNameFromPartType } from '@/lib/tool-meta';
import type { ToolPart } from './ToolCallCard';

interface Props {
  part: ToolPart;
  onRespond: (id: string, approved: boolean, reason?: string) => void;
}

export function ApprovalDialog({ part, onRespond }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [reason, setReason] = useState('');
  const toolName = part.type === 'dynamic-tool' ? (part.toolName ?? 'tool') : toolNameFromPartType(part.type);
  const meta = toolMeta(toolName);
  const approval = part.approval;
  const requestReason = approval?.requestReason;

  if (!approval) return null;

  return (
    <div className="fixed inset-x-0 bottom-6 z-40 mx-auto w-[min(680px,calc(100vw-2rem))]">
      <div className="overflow-hidden rounded-2xl border border-amber-400/30 bg-ink-900/95 shadow-panel backdrop-blur">
        <div className="flex items-start gap-3 border-b border-ink-700 px-4 py-3">
          <div className="mt-0.5 rounded-lg bg-amber-400/10 p-1.5">
            <ShieldAlert className="h-4 w-4 text-amber-300" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium text-mist-200">需要你的批准</div>
            <div className="mt-0.5 flex items-center gap-1.5 text-xs text-mist-400">
              <meta.Icon className="h-3.5 w-3.5" />
              {meta.title}
            </div>
            {requestReason && <div className="mt-1 text-xs text-amber-200/80">{requestReason}</div>}
          </div>
        </div>

        <div className="space-y-2 px-4 py-3">
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-ink-950 px-3 py-2 font-mono text-xs text-mist-200">
            {JSON.stringify(part.input ?? {}, null, 2)}
          </pre>
          {expanded && (
            <input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="拒绝原因（可选，会回传给模型）"
              className="w-full rounded-lg border border-ink-600 bg-ink-950 px-3 py-2 text-xs text-mist-200 outline-none placeholder:text-mist-400/60 focus:border-accent-500"
            />
          )}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-ink-700 px-4 py-3">
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="mr-auto text-xs text-mist-400 hover:text-mist-200"
          >
            {expanded ? '收起原因' : '添加拒绝原因'}
          </button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onRespond(approval.id, false, reason.trim() || undefined)}
          >
            拒绝
          </Button>
          <Button size="sm" onClick={() => onRespond(approval.id, true)}>
            批准并继续
          </Button>
        </div>
      </div>
    </div>
  );
}
