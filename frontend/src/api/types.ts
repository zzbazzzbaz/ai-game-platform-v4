import type { UIMessage } from 'ai';

export interface User {
  id: string;
  email: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface RunUsage {
  input_tokens?: number;
  output_tokens?: number;
  cache_read_tokens?: number;
  requests?: number;
  tool_calls?: number;
  cost?: number | string | null;
  [key: string]: unknown;
}

export interface RunOut {
  id: string;
  status: 'running' | 'waiting_approval' | 'completed' | 'cancelled' | 'failed';
  model: string;
  started_at: string;
  finished_at: string | null;
  usage: RunUsage;
  error: Record<string, unknown> | null;
}

export interface ConversationDetail extends Conversation {
  messages: UIMessage[];
  usage: RunUsage;
  deferred_tool_requests: unknown;
  last_run: RunOut | null;
}

export interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
}

export interface FileList {
  root: string;
  path: string;
  sandbox: string | null;
  entries: FileEntry[];
}
