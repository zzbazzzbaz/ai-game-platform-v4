import { useState, type FormEvent } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import { api } from '@/api/client';
import type { User } from '@/api/types';
import { Button } from '@/components/ui/button';

export function LoginPage({ onLogin }: { onLogin: (user: User) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      onLogin(await api.login(email, password));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-500/15 ring-1 ring-accent-500/25">
            <Sparkles className="h-5 w-5 text-accent-400" />
          </div>
          <h1 className="text-lg font-semibold text-mist-100">Pydantic Agent</h1>
          <p className="mt-1 text-xs text-mist-400">云端沙箱里的通用编程智能体</p>
        </div>

        <form
          onSubmit={submit}
          className="space-y-3 rounded-2xl border border-ink-700 bg-ink-900 p-5 shadow-panel"
        >
          <label className="block">
            <span className="mb-1 block text-[11px] text-mist-400">邮箱</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="w-full rounded-lg border border-ink-600 bg-ink-950 px-3 py-2 text-sm text-mist-200 outline-none focus:border-accent-500/60"
              autoComplete="email"
              required
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] text-mist-400">密码</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-lg border border-ink-600 bg-ink-950 px-3 py-2 text-sm text-mist-200 outline-none focus:border-accent-500/60"
              autoComplete="current-password"
              required
            />
          </label>
          {error && <div className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>}
          <Button type="submit" className="w-full" disabled={loading}>
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            登录
          </Button>
        </form>
      </div>
    </div>
  );
}
