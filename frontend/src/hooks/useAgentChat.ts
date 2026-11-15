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
  onNotFound?: () => void;
  onBusy?: () => void;
}

type StatusError = Error & { status?: number };

async function fetchWithStatus(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init);
  if (response.ok) return response;
  const body = (await response
    .clone()
    .json()
    .catch(() => null)) as { detail?: unknown } | null;
  const message =
    typeof body?.detail === 'string' ? body.detail : `请求失败（${response.status}）`;
  throw Object.assign(new Error(message), { status: response.status }) as StatusError;
}

export function useAgentChat({
  conversationId,
  initialMessages,
  onFinish,
  onUnauthorized,
  onNotFound,
  onBusy,
}: Options) {
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: '/api/chat',
        credentials: 'same-origin',
        fetch: fetchWithStatus,
      }),
    [],
  );

  const chat = useChat({
    id: conversationId,
    messages: initialMessages,
    transport,
    experimental_throttle: 100,
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithApprovalResponses,
    onFinish: () => onFinish?.(),
    onError: (error) => {
      const status = (error as StatusError).status;
      if (status === 401) onUnauthorized?.();
      else if (status === 404) onNotFound?.();
      else if (status === 409) onBusy?.();
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
