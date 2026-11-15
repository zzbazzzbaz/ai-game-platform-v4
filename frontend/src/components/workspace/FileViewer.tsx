import { useEffect, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { api } from '@/api/client';

interface Props {
  conversationId: string;
  path: string;
  name: string;
  onClose: () => void;
}

export function FileViewer({ conversationId, path, name, onClose }: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setContent(null);
    setError(null);
    api
      .readFile(conversationId, path)
      .then((text) => active && setContent(text))
      .catch((caught) => active && setError(caught instanceof Error ? caught.message : '读取失败'));
    return () => {
      active = false;
    };
  }, [conversationId, path]);

  return (
    <div className="flex h-full flex-col border-l border-ink-800 bg-ink-900">
      <div className="flex items-center justify-between border-b border-ink-800 px-3 py-2">
        <div className="min-w-0">
          <div className="truncate text-xs font-medium text-mist-200">{name}</div>
          <div className="truncate font-mono text-[10px] text-mist-400">{path}</div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1.5 text-mist-400 hover:bg-ink-800 hover:text-mist-200"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="flex-1 overflow-auto">
        {error ? (
          <div className="p-3 text-xs text-red-300">{error}</div>
        ) : content === null ? (
          <div className="flex items-center gap-2 p-4 text-xs text-mist-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            读取文件…
          </div>
        ) : (
          <pre className="whitespace-pre-wrap p-3 font-mono text-xs leading-relaxed text-mist-200">{content}</pre>
        )}
      </div>
    </div>
  );
}
