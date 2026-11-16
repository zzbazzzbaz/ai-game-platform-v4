import { useEffect, useState } from 'react';
import { ExternalLink, Globe, Loader2 } from 'lucide-react';
import { api } from '@/api/client';
import { Button } from '@/components/ui/button';

export function PreviewPane({ conversationId }: { conversationId: string }) {
  const [port, setPort] = useState('3000');
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const portNumber = Number(port);
  const validPort = Number.isInteger(portNumber) && portNumber >= 1 && portNumber <= 65535;

  useEffect(() => {
    if (!url) return;
    const timer = window.setInterval(() => {
      void api.touchSandbox(conversationId).catch(() => undefined);
    }, 240_000);
    return () => window.clearInterval(timer);
  }, [conversationId, url]);

  const open = async () => {
    if (!validPort) {
      setError('端口需在 1–65535 之间');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api.preview(conversationId, portNumber);
      setUrl(result.url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '获取预览地址失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-ink-800 px-3 py-2">
        <Globe className="h-3.5 w-3.5 text-mist-400" />
        <input
          value={port}
          onChange={(event) => setPort(event.target.value.replace(/\D/g, ''))}
          className="w-20 rounded-md border border-ink-700 bg-ink-950 px-2 py-1 font-mono text-[11px] text-mist-200 outline-none focus:border-accent-500/60"
          placeholder="端口"
        />
        <Button size="sm" variant="outline" onClick={() => void open()} disabled={loading || !validPort}>
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : '打开'}
        </Button>
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="ml-auto rounded-md p-1.5 text-mist-400 hover:bg-ink-800 hover:text-mist-200"
            title="新窗口打开"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
      </div>
      <div className="flex-1 overflow-hidden bg-ink-950">
        {error && <div className="p-3 text-xs text-red-300">{error}</div>}
        {!url && !error && (
          <div className="px-5 py-10 text-center text-xs leading-relaxed text-mist-400/70">
            输入沙箱中服务监听的端口，打开预览。
            <br />
            预览地址由阿里云沙箱提供。
          </div>
        )}
        {url && (
          <iframe
            key={url}
            src={url}
            title="沙箱预览"
            className="h-full w-full border-0 bg-white"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
          />
        )}
      </div>
    </div>
  );
}
