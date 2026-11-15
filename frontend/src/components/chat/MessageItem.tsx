import { memo } from 'react';
import type { UIMessage } from 'ai';
import { Bot, Sparkles } from 'lucide-react';
import { Markdown } from '@/lib/markdown';
import { ToolCallCard, type ToolPart } from '@/components/tools/ToolCallCard';

function isToolPart(type: string) {
  return type === 'dynamic-tool' || type.startsWith('tool-');
}

export const MessageItem = memo(function MessageItem({ message }: { message: UIMessage }) {
  const parts = message.parts as unknown as Array<Record<string, unknown>>;
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end px-4 py-2 sm:px-6">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent-500/12 px-4 py-2.5 text-sm leading-relaxed text-mist-200 ring-1 ring-accent-500/20">
          {parts.map((part, index) => {
            const text = String(part.text ?? '');
            if (part.type !== 'text' || text.trimStart().startsWith('<plan_reminder>')) return null;
            return (
              <div key={index} className="whitespace-pre-wrap">
                {text}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 px-4 py-3 sm:px-6">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-ink-800 ring-1 ring-ink-600">
        <Sparkles className="h-3.5 w-3.5 text-accent-400" />
      </div>
      <div className="min-w-0 flex-1">
        {parts.map((part, index) => {
          const type = String(part.type ?? '');
          if (type === 'text') {
            const text = String(part.text ?? '');
            if (text.trimStart().startsWith('<plan_reminder>')) return null;
            return (
              <div key={index} className="text-mist-200">
                <Markdown>{text}</Markdown>
              </div>
            );
          }
          if (type === 'reasoning') {
            return (
              <details key={index} className="group my-2 rounded-lg border border-ink-700/70 bg-ink-900/50">
                <summary className="flex cursor-pointer items-center gap-1.5 px-3 py-1.5 text-[11px] text-mist-400">
                  <Bot className="h-3 w-3" />
                  推理过程
                </summary>
                <div className="whitespace-pre-wrap border-t border-ink-700/60 px-3 py-2 text-xs leading-relaxed text-mist-400">
                  {String(part.text ?? '')}
                </div>
              </details>
            );
          }
          if (isToolPart(type)) {
            return <ToolCallCard key={index} part={part as unknown as ToolPart} />;
          }
          return null;
        })}
        {message.parts.length === 0 && (
          <div className="flex items-center gap-2 text-xs text-mist-400">
            <span className="h-1.5 w-1.5 rounded-full bg-accent-400 animate-pulse-dot" />
            正在思考…
          </div>
        )}
      </div>
    </div>
  );
});

export function findApprovalPart(message: UIMessage) {
  const parts = message.parts as unknown as Array<Record<string, unknown>>;
  return parts.find(
    (part) => part.state === 'approval-requested' && isToolPart(String(part.type ?? '')),
  ) as unknown as ToolPart | undefined;
}
