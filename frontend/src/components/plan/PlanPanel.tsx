import type { UIMessage } from 'ai';
import { Circle, CircleCheck, CircleDot, CircleSlash, ListTodo } from 'lucide-react';
import { cn } from '@/lib/utils';

interface PlanTask {
  id?: string;
  content: string;
  status: string;
  activeForm?: string;
}

const STATUS_ICON: Record<string, typeof Circle> = {
  pending: Circle,
  in_progress: CircleDot,
  completed: CircleCheck,
  cancelled: CircleSlash,
  blocked: CircleSlash,
};

function asTasks(value: unknown): PlanTask[] | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  const list = (record.tasks ?? record.plan ?? record.items) as unknown;
  if (!Array.isArray(list)) return null;
  const tasks = list
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    .map((item) => ({
      id: item.id == null ? undefined : String(item.id),
      content: String(item.content ?? item.title ?? item.subject ?? ''),
      status: String(item.status ?? 'pending'),
      activeForm: item.active_form == null ? undefined : String(item.active_form),
    }))
    .filter((task) => task.content);
  return tasks.length > 0 ? tasks : null;
}

function parseJson(value: unknown): unknown {
  if (typeof value !== 'string') return value;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

const REMINDER_STATUS: Record<string, string> = {
  x: 'completed',
  '~': 'in_progress',
  '-': 'cancelled',
  '!': 'blocked',
  ' ': 'pending',
};

function parseReminder(text: string): PlanTask[] | null {
  if (!text.includes('<plan_reminder>')) return null;
  const tasks: PlanTask[] = [];
  for (const line of text.split('\n')) {
    const match = /^\s*\d+\.\s+\[([ x~\-!])\]\s+(.*)$/.exec(line);
    if (!match) continue;
    tasks.push({
      content: match[2].trim(),
      status: REMINDER_STATUS[match[1]] ?? 'pending',
    });
  }
  return tasks.length > 0 ? tasks : null;
}

function planFromMessages(messages: UIMessage[]): PlanTask[] | null {
  // 优先解析计划工具返回的 <plan_reminder>，它包含最新状态。
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== 'assistant') continue;
    const parts = message.parts as unknown as Array<Record<string, unknown>>;
    for (let partIndex = parts.length - 1; partIndex >= 0; partIndex -= 1) {
      const part = parts[partIndex];
      const type = String(part.type ?? '');
      if (!/plan|task/.test(type)) continue;
      if (typeof part.output === 'string') {
        const parsed = parseReminder(part.output);
        if (parsed) return parsed;
      }
    }
  }
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== 'assistant') continue;
    const parts = message.parts as unknown as Array<Record<string, unknown>>;
    for (let partIndex = parts.length - 1; partIndex >= 0; partIndex -= 1) {
      const part = parts[partIndex];
      const type = String(part.type ?? '');
      if (!/plan|task/.test(type)) continue;
      const fromInput = asTasks(part.input);
      if (fromInput) return fromInput;
      const fromOutput = asTasks(parseJson(part.output));
      if (fromOutput) return fromOutput;
    }
  }
  return null;
}

export function PlanPanel({ messages }: { messages: UIMessage[] }) {
  const tasks = planFromMessages(messages);
  const completed = tasks?.filter((task) => task.status === 'completed').length ?? 0;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-ink-800 px-4 py-2.5">
        <div className="flex items-center gap-2 text-xs font-medium text-mist-300">
          <ListTodo className="h-3.5 w-3.5" />
          任务计划
        </div>
        {tasks && (
          <span className="text-[10px] text-mist-400">
            {completed}/{tasks.length}
          </span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        {!tasks ? (
          <div className="mt-10 px-3 text-center text-xs leading-relaxed text-mist-400/70">
            智能体还没有创建计划。
            <br />
            当它使用任务计划工具时，会显示在这里。
          </div>
        ) : (
          <ol className="space-y-1.5">
            {tasks.map((task, index) => {
              const Icon = STATUS_ICON[task.status] ?? Circle;
              return (
                <li
                  key={task.id ?? index}
                  className="flex items-start gap-2 rounded-lg border border-ink-800 bg-ink-900/60 px-2.5 py-2"
                >
                  <Icon
                    className={cn(
                      'mt-0.5 h-3.5 w-3.5 shrink-0',
                      task.status === 'completed'
                        ? 'text-emerald-400'
                        : task.status === 'in_progress'
                          ? 'text-accent-400'
                          : task.status === 'cancelled' || task.status === 'blocked'
                            ? 'text-red-400'
                            : 'text-mist-400',
                    )}
                  />
                  <div className="min-w-0">
                    <div
                      className={cn(
                        'text-xs leading-relaxed',
                        task.status === 'completed' ? 'text-mist-400 line-through' : 'text-mist-200',
                      )}
                    >
                      {task.status === 'in_progress' && task.activeForm ? task.activeForm : task.content}
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
