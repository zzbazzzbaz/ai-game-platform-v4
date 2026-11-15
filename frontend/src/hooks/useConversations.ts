import { useCallback, useEffect, useState } from 'react';
import { ApiError, api } from '@/api/client';
import type { Conversation } from '@/api/types';

export function useConversations(onUnauthorized: () => void) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await api.listConversations();
      setConversations(list);
      setError(null);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        onUnauthorized();
        return;
      }
      setError(caught instanceof Error ? caught.message : '加载会话失败');
    } finally {
      setLoading(false);
    }
  }, [onUnauthorized]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = useCallback(async (): Promise<Conversation | null> => {
    try {
      const created = await api.createConversation();
      setConversations((current) => [created, ...current]);
      return created;
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        onUnauthorized();
        return null;
      }
      setError(caught instanceof Error ? caught.message : '新建会话失败');
      return null;
    }
  }, [onUnauthorized]);

  const remove = useCallback(
    async (id: string) => {
      try {
        await api.deleteConversation(id);
        setConversations((current) => current.filter((item) => item.id !== id));
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 401) {
          onUnauthorized();
          return;
        }
        setError(caught instanceof Error ? caught.message : '删除会话失败');
      }
    },
    [onUnauthorized],
  );

  const renameLocal = useCallback((id: string, title: string) => {
    setConversations((current) =>
      current.map((item) => (item.id === id ? { ...item, title, updated_at: new Date().toISOString() } : item)),
    );
  }, []);

  return { conversations, loading, error, refresh, create, remove, renameLocal };
}
