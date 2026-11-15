import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, File, Folder, Loader2, RefreshCw } from 'lucide-react';
import { api } from '@/api/client';
import type { FileEntry } from '@/api/types';
import { cn } from '@/lib/utils';

interface Props {
  conversationId: string;
  onOpen: (path: string, name: string) => void;
}

function parentOf(path: string) {
  const normalized = path.replace(/\/+$/, '');
  const index = normalized.lastIndexOf('/');
  return index <= 0 ? '/' : normalized.slice(0, index);
}

export function FileTree({ conversationId, onOpen }: Props) {
  const [path, setPath] = useState<string | undefined>(undefined);
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [root, setRoot] = useState<string>('');
  const [sandbox, setSandbox] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeq = useRef(0);

  const load = useCallback(
    async (target?: string) => {
      const token = ++requestSeq.current;
      setLoading(true);
      setError(null);
      try {
        const result = await api.listFiles(conversationId, target);
        if (token !== requestSeq.current) return;
        setRoot(result.path);
        setSandbox(result.sandbox);
        setEntries(
          [...result.entries].sort((a, b) =>
            a.is_dir === b.is_dir ? a.name.localeCompare(b.name) : a.is_dir ? -1 : 1,
          ),
        );
        setPath(target ?? result.path);
      } catch (caught) {
        if (token !== requestSeq.current) return;
        setError(caught instanceof Error ? caught.message : '读取目录失败');
        setEntries([]);
      } finally {
        if (token === requestSeq.current) setLoading(false);
      }
    },
    [conversationId],
  );

  useEffect(() => {
    void load(undefined);
  }, [load]);

  const current = path ?? root;
  const visible = entries.filter((entry) => !entry.name.startsWith('.'));

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-ink-800 px-2 py-2">
        <button
          type="button"
          onClick={() => void load(parentOf(current))}
          disabled={loading || !current || current === root}
          className="rounded-md p-1.5 text-mist-400 hover:bg-ink-800 hover:text-mist-200 disabled:opacity-30"
          title="上一级"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
        </button>
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-mist-400">{current || '/'}</span>
        <button
          type="button"
          onClick={() => void load(current)}
          disabled={loading}
          className="rounded-md p-1.5 text-mist-400 hover:bg-ink-800 hover:text-mist-200"
          title="刷新"
        >
          <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-1.5">
        {loading && entries.length === 0 && (
          <div className="flex items-center justify-center gap-2 py-8 text-xs text-mist-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            加载目录…
          </div>
        )}
        {error && <div className="px-2 py-3 text-xs text-red-300">{error}</div>}
        {!loading && !error && visible.length === 0 && (
          <div className="px-3 py-8 text-center text-xs text-mist-400/70">
            {sandbox ? '目录为空' : '还没有沙箱。发送一条消息后会创建。'}
          </div>
        )}
        {visible.map((entry) => (
          <button
            key={entry.path}
            type="button"
            onClick={() => (entry.is_dir ? void load(entry.path) : onOpen(entry.path, entry.name))}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-mist-300 transition-colors hover:bg-ink-800 hover:text-mist-100"
          >
            {entry.is_dir ? (
              <Folder className="h-3.5 w-3.5 shrink-0 text-accent-400/80" />
            ) : (
              <File className="h-3.5 w-3.5 shrink-0 text-mist-400" />
            )}
            <span className="min-w-0 flex-1 truncate">{entry.name}</span>
            {entry.size != null && !entry.is_dir && (
              <span className="shrink-0 text-[10px] text-mist-400/60">{entry.size}B</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
