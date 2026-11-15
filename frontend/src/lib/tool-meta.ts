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
}

const TOOL_META: Record<string, ToolMeta> = {
  shell: { title: 'Shell', Icon: Terminal },
  run_command: { title: 'Run command', Icon: Terminal },
  start_command: { title: 'Start command', Icon: Terminal },
  read_file: { title: 'Read file', Icon: FileText },
  write_file: { title: 'Write file', Icon: FilePlus },
  edit_file: { title: 'Edit file', Icon: FilePen },
  list_files: { title: 'List files', Icon: FolderTree },
  create_directory: { title: 'Create directory', Icon: FolderTree },
  grep: { title: 'Search', Icon: Search },
  delegate_task: { title: 'Delegate task', Icon: Bot },
  write_plan: { title: 'Update plan', Icon: ListTodo },
  update_task_status: { title: 'Update plan', Icon: ListTodo },
  update_task_statuses: { title: 'Update plan', Icon: ListTodo },
  read_plan: { title: 'Read plan', Icon: ListTodo },
};

export function toolMeta(name: string): ToolMeta {
  return TOOL_META[name] ?? { title: name, Icon: Wrench };
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
  const text = JSON.stringify(output, null, 2);
  return text.length > 20000 ? `${text.slice(0, 20000)}\n…（已截断）` : text;
}
