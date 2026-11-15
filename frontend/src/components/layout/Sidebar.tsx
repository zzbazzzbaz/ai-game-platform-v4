import { LogOut, MessageSquare, Plus, Sparkles, Trash2 } from 'lucide-react';
import type { Conversation, User } from '@/api/types';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

interface Props {
  user: User;
  conversations: Conversation[];
  activeId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onLogout: () => void;
}

export function Sidebar({
  user,
  conversations,
  activeId,
  loading,
  onSelect,
  onCreate,
  onDelete,
  onLogout,
}: Props) {
  return (
    <aside className="flex w-[260px] shrink-0 flex-col border-r border-ink-800 bg-ink-900/60">
      <div className="flex items-center gap-2 px-4 pb-3 pt-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent-500/15 ring-1 ring-accent-500/25">
          <Sparkles className="h-4 w-4 text-accent-400" />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold text-mist-100">Pydantic Agent</div>
          <div className="truncate text-[10px] text-mist-400">云端沙箱 · DeepSeek</div>
        </div>
      </div>

      <div className="px-3 pb-3">
        <Button className="w-full" onClick={onCreate}>
          <Plus className="h-4 w-4" />
          新会话
        </Button>
      </div>

      <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {loading && (
          <div className="px-3 py-4 text-xs text-mist-400">
            <div className="h-3 w-24 animate-pulse rounded bg-ink-700" />
          </div>
        )}
        {!loading && conversations.length === 0 && (
          <div className="px-3 py-6 text-center text-xs leading-relaxed text-mist-400/70">
            还没有会话
            <br />
            点击上方开始
          </div>
        )}
        {conversations.map((conversation) => {
          const active = conversation.id === activeId;
          return (
            <div
              key={conversation.id}
              className={cn(
                'group flex items-center gap-2 rounded-lg px-2.5 py-2 transition-colors',
                active ? 'bg-ink-700/80 text-mist-100' : 'text-mist-300 hover:bg-ink-800/70',
              )}
            >
              <button
                type="button"
                onClick={() => onSelect(conversation.id)}
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
              >
                <MessageSquare className={cn('h-3.5 w-3.5 shrink-0', active ? 'text-accent-400' : 'text-mist-400')} />
                <span className="truncate text-xs">{conversation.title}</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  if (window.confirm(`删除会话「${conversation.title}」及其沙箱？`)) onDelete(conversation.id);
                }}
                className="rounded-md p-1 text-mist-400/50 opacity-0 transition-opacity hover:bg-ink-600 hover:text-red-300 group-hover:opacity-100"
                title="删除会话"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          );
        })}
      </div>

      <div className="border-t border-ink-800 px-3 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-ink-700 text-[11px] font-medium text-mist-200">
            {user.email.slice(0, 1).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[11px] text-mist-200">{user.email}</div>
            <div className="text-[10px] text-mist-400/70">demo 用户</div>
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="rounded-md p-1.5 text-mist-400 hover:bg-ink-800 hover:text-mist-200"
            title="退出登录"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}
