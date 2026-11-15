import { useMemo } from 'react';
import { useChat } from '@ai-sdk/react';
import {
  DefaultChatTransport,
  lastAssistantMessageIsCompleteWithApprovalResponses,
  type UIMessage,
} from 'ai';
import { api } from '@/api/client';

interface Options {
  conversationId: string;
  initialMessages: UIMessage[];
  onFinish?: () => void;
  onUnauthorized?: () => void;
}

export function useAgentChat({ conversationId, initialMessages, onFinish, onUnauthorized }: Options) {
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: '/api/chat',
        credentials: 'same-origin',
      }),
    [],
  );

  const chat = useChat({
    id: conversationId,
    messages: initialMessages,
    transport,
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithApprovalResponses,
    onFinish: () => onFinish?.(),
    onError: (error) => {
      const status = (error as Error & { status?: number }).status;
      if (status === 401) onUnauthorized?.();
    },
  });

  const stopRun = async () => {
    try {
      await api.cancelRun(conversationId);
    } catch {
      // 后端可能已经结束，仍然停止本地流
    }
    chat.stop();
  };

  return { ...chat, stopRun };
}
