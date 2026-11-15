import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { api } from '@/api/client';
import type { User } from '@/api/types';
import { LoginPage } from '@/components/auth/LoginPage';
import { AppShell } from '@/components/layout/AppShell';

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, []);

  const logout = () => {
    void api.logout().catch(() => undefined);
    setUser(null);
  };

  if (checking) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-mist-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        加载中…
      </div>
    );
  }

  if (!user) {
    return <LoginPage onLogin={setUser} />;
  }

  return <AppShell key={user.id} user={user} onLogout={logout} />;
}
