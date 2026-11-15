import { useCallback, useEffect, useRef, useState } from 'react';
import type { User } from '@/api/types';
import { useConversations } from '@/hooks/useConversations';
import { Sidebar } from './Sidebar';
import { ChatPanel, EmptyState } from '@/components/chat/ChatPanel';

export function AppShell({ user, onLogout }: { user: User; onLogout: () => void }) {
  const { conversations, loading, create, remove, refresh, renameLocal } = useConversations(onLogout);
  const [activeId, setActiveId] = useState<string | null>(null);
  const initialized = useRef(false);

  useEffect(() => {
    if (!initialized.current && conversations.length > 0) {
      initialized.current = true;
      setActiveId(conversations[0].id);
    }
  }, [conversations]);

  const handleCreate = useCallback(async () => {
    const created = await create();
    if (created) setActiveId(created.id);
  }, [create]);

  const handleDelete = useCallback(
    async (id: string) => {
      await remove(id);
      if (activeId === id) setActiveId(null);
    },
    [activeId, remove],
  );

  const handleNotFound = useCallback(() => {
    setActiveId(null);
    void refresh();
  }, [refresh]);

  const activeConversation = conversations.find((item) => item.id === activeId);

  return (
    <div className="flex h-full">
      <Sidebar
        user={user}
        conversations={conversations}
        activeId={activeId}
        loading={loading}
        onSelect={setActiveId}
        onCreate={() => void handleCreate()}
        onDelete={(id) => void handleDelete(id)}
        onLogout={onLogout}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        {activeId ? (
          <ChatPanel
            conversationId={activeId}
            title={activeConversation?.title ?? '新会话'}
            onUnauthorized={onLogout}
            onNotFound={handleNotFound}
            onConversationChanged={() => void refresh()}
            onTitleHint={renameLocal}
          />
        ) : (
          <EmptyState onCreate={() => void handleCreate()} />
        )}
      </main>
    </div>
  );
}
