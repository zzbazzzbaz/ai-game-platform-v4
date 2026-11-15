import {
  Bot,
  FilePen,
  FilePlus,
  FileText,
  FolderTree,
  ListTodo,
  Search,
  Terminal,
  Wrench,
  type LucideIcon,
} from 'lucide-react';

export interface ToolMeta {
  title: string;
  Icon: LucideIcon;
  tone?: 'shell' | 'file' | 'search' | 'plan' | 'agent' | 'default';
}

const TOOL_META: Record<string, ToolMeta> = {
  shell: { title: 'Shell', Icon: Terminal, tone: 'shell' },
  run_command: { title: 'Run command', Icon: Terminal, tone: 'shell' },
  start_command: { title: 'Start command', Icon: Terminal, tone: 'shell' },
  read_file: { title: 'Read file', Icon: FileText, tone: 'file' },
  write_file: { title: 'Write file', Icon: FilePlus, tone: 'file' },
  edit_file: { title: 'Edit file', Icon: FilePen, tone: 'file' },
  list_files: { title: 'List files', Icon: FolderTree, tone: 'file' },
  create_directory: { title: 'Create directory', Icon: FolderTree, tone: 'file' },
  grep: { title: 'Search', Icon: Search, tone: 'search' },
  delegate_task: { title: 'Delegate task', Icon: Bot, tone: 'agent' },
  write_plan: { title: 'Update plan', Icon: ListTodo, tone: 'plan' },
  update_task_status: { title: 'Update plan', Icon: ListTodo, tone: 'plan' },
  read_plan: { title: 'Read plan', Icon: ListTodo, tone: 'plan' },
};

export function toolMeta(name: string): ToolMeta {
  return TOOL_META[name] ?? { title: name, Icon: Wrench, tone: 'default' };
}

export function toolNameFromPartType(type: string): string {
  if (type === 'dynamic-tool') return 'tool';
  return type.startsWith('tool-') ? type.slice('tool-'.length) : type;
}

export function summarizeInput(input: unknown): string {
  if (input == null) return '';
  if (typeof input === 'string') return input;
  if (typeof input === 'object') {
    const record = input as Record<string, unknown>;
    for (const key of ['command', 'path', 'file_path', 'pattern', 'prompt', 'query']) {
      const value = record[key];
      if (typeof value === 'string' && value.trim()) return value.trim();
    }
  }
  const json = JSON.stringify(input);
  return json.length > 120 ? `${json.slice(0, 120)}…` : json;
}

export function outputText(output: unknown): string {
  if (output == null) return '';
  if (typeof output === 'string') return output;
  if (typeof output === 'object') {
    const record = output as Record<string, unknown>;
    if (typeof record.output === 'string') return record.output;
    if (typeof record.text === 'string') return record.text;
    if (typeof record.content === 'string') return record.content;
  }
  return JSON.stringify(output, null, 2);
}
