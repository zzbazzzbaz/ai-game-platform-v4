import type { Conversation, ConversationDetail, FileList, User } from './types';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = (await response.json()) as { detail?: string; error?: string };
      message = body.detail ?? body.error ?? message;
    } catch {
      // ignore non-JSON error bodies
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  me: () => apiFetch<User>('/api/me'),

  login: (email: string, password: string) =>
    apiFetch<User>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  demoLogin: () => apiFetch<User>('/api/auth/demo', { method: 'POST' }),

  logout: () => apiFetch<void>('/api/auth/logout', { method: 'POST' }),

  listConversations: () => apiFetch<Conversation[]>('/api/conversations'),

  createConversation: () => apiFetch<Conversation>('/api/conversations', { method: 'POST' }),

  getConversation: (id: string) => apiFetch<ConversationDetail>(`/api/conversations/${id}`),

  deleteConversation: (id: string) =>
    apiFetch<void>(`/api/conversations/${id}`, { method: 'DELETE' }),

  cancelRun: (id: string) =>
    apiFetch<{ run_id: string }>(`/api/conversations/${id}/cancel`, { method: 'POST' }),


  listFiles: (conversationId: string, path?: string) =>
    apiFetch<FileList>(
      `/api/conversations/${conversationId}/sandbox/files${path ? `?path=${encodeURIComponent(path)}` : ''}`,
    ),

  readFile: async (conversationId: string, path: string): Promise<string> => {
    const response = await fetch(
      `/api/conversations/${conversationId}/sandbox/file?path=${encodeURIComponent(path)}`,
      { credentials: 'same-origin' },
    );
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      throw new ApiError(response.status, body.detail ?? '读取文件失败');
    }
    return response.text();
  },

  preview: (conversationId: string, port: number) =>
    apiFetch<{ url: string }>(`/api/conversations/${conversationId}/sandbox/preview/${port}`, {
      method: 'POST',
    }),

};
