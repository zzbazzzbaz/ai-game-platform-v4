import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { UIMessage } from 'ai';
import { FolderTree, Globe, ListTodo, Loader2, Sparkles, X } from 'lucide-react';
import { ApiError, api } from '@/api/client';
import type { ConversationDetail } from '@/api/types';
import { useAgentChat } from '@/hooks/useAgentChat';
import { cn } from '@/lib/utils';
import { MessageList } from './MessageList';
import { Composer } from './Composer';
import { ApprovalDialog } from '@/components/tools/ApprovalDialog';
import { findApprovalPart } from './MessageItem';
import { PlanPanel } from '@/components/plan/PlanPanel';
import { FileTree } from '@/components/workspace/FileTree';
import { FileViewer } from '@/components/workspace/FileViewer';
import { PreviewPane } from '@/components/workspace/PreviewPane';

type DockTab = 'plan' | 'files' | 'preview';

interface Props {
  conversationId: string;
  title: string;
  onUnauthorized: () => void;
  onNotFound: () => void;
  onConversationChanged: () => void;
  onTitleHint: (id: string, title: string) => void;
}

function statusLabel(status: string, hasApproval: boolean) {
  if (hasApproval) return { text: '等待审批', tone: 'text-amber-300' };
  if (status === 'submitted' || status === 'streaming') return { text: '运行中', tone: 'text-accent-400' };
  if (status === 'error') return { text: '出错', tone: 'text-red-300' };
  return { text: '就绪', tone: 'text-mist-400' };
}

function ChatSession({
  detail,
  title,
  onUnauthorized,
  onNotFound,
  onConversationChanged,
  onTitleHint,
}: {
  detail: ConversationDetail;
  title: string;
  onUnauthorized: () => void;
  onNotFound: () => void;
  onConversationChanged: () => void;
  onTitleHint: (id: string, title: string) => void;
}) {
  const [serverBusy, setServerBusy] = useState(false);
  const chat = useAgentChat({
    conversationId: detail.id,
    initialMessages: detail.messages,
    onFinish: onConversationChanged,
    onUnauthorized,
    onNotFound,
    onBusy: () => setServerBusy(true),
  });
  const [tab, setTab] = useState<DockTab>('plan');
  const [openFile, setOpenFile] = useState<{ path: string; name: string } | null>(null);

  const stopRef = useRef(chat.stop);
  stopRef.current = chat.stop;
  const statusRef = useRef(chat.status);
  statusRef.current = chat.status;
  useEffect(
    () => () => {
      if (statusRef.current === 'submitted' || statusRef.current === 'streaming') {
        void stopRef.current();
      }
    },
    [],
  );

  const waitingApproval = detail.last_run?.status === 'waiting_approval';
  const approvalPart = useMemo(() => {
    if (!waitingApproval) return undefined;
    return findApprovalPart(chat.messages[chat.messages.length - 1]);
  }, [chat.messages, waitingApproval]);

  const status = statusLabel(chat.status, Boolean(approvalPart));

  const send = (text: string) => {
    if (chat.messages.length === 0) onTitleHint(detail.id, text.slice(0, 40));
    setServerBusy(false);
    void chat.sendMessage({ text });
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-ink-800 px-4 sm:px-5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-medium text-mist-200">{title}</span>
          <span className={cn('flex items-center gap-1.5 text-[10px]', status.tone)}>
            <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse-dot" />
            {status.text}
          </span>
        </div>
        <div className="ml-auto hidden items-center gap-2 font-mono text-[10px] text-mist-400/70 sm:flex">
          <span>{detail.id.slice(0, 8)}</span>
          <span className="text-ink-600">·</span>
          <span>{detail.last_run?.model ?? '—'}</span>
          {detail.last_run?.usage && (
            <>
              <span className="text-ink-600">·</span>
              <span>
                {Number(detail.last_run.usage.input_tokens ?? 0)} in /{' '}
                {Number(detail.last_run.usage.output_tokens ?? 0)} out
              </span>
            </>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <MessageList messages={chat.messages} />
          {chat.error && (
            <div className="mx-4 mb-2 flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-300 sm:mx-6">
              <span className="flex-1">{chat.error.message || '请求失败'}</span>
              {serverBusy && (
                <button
                  type="button"
                  onClick={() => {
                    setServerBusy(false);
                    chat.clearError();
                  }}
                  className="text-red-200 underline underline-offset-2"
                >
                  重试
                </button>
              )}
              <button type="button" onClick={() => chat.clearError()} className="text-red-300/70 hover:text-red-200">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          <Composer
            status={chat.status}
            onSend={send}
            onStop={() => void chat.stopRun()}
            disabled={Boolean(approvalPart) || serverBusy}
            placeholder={
              approvalPart
                ? '请先处理上方的审批请求…'
                : undefined
            }
          />
        </div>

        <div className="hidden w-[320px] shrink-0 flex-col border-l border-ink-800 bg-ink-900/40 md:flex">
          {openFile ? (
            <FileViewer
              conversationId={detail.id}
              path={openFile.path}
              name={openFile.name}
              onClose={() => setOpenFile(null)}
            />
          ) : (
            <>
              <div className="flex shrink-0 items-center gap-1 border-b border-ink-800 px-2 py-1.5">
                {(
                  [
                    ['plan', 'Plan', ListTodo],
                    ['files', 'Files', FolderTree],
                    ['preview', 'Preview', Globe],
                  ] as const
                ).map(([key, label, Icon]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setTab(key)}
                    className={cn(
                      'flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] transition-colors',
                      tab === key
                        ? 'bg-ink-700 text-mist-100'
                        : 'text-mist-400 hover:bg-ink-800 hover:text-mist-200',
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {label}
                  </button>
                ))}
              </div>
              <div className="min-h-0 flex-1">
                {tab === 'plan' && <PlanPanel messages={chat.messages} />}
                {tab === 'files' && (
                  <FileTree conversationId={detail.id} onOpen={(path, name) => setOpenFile({ path, name })} />
                )}
                {tab === 'preview' && <PreviewPane conversationId={detail.id} />}
              </div>
            </>
          )}
        </div>
      </div>

      {approvalPart && (
        <ApprovalDialog
          key={approvalPart.approval?.id}
          part={approvalPart}
          onRespond={(id, approved, reason) =>
            void chat.addToolApprovalResponse({ id, approved, reason })
          }
        />
      )}
    </div>
  );
}

export function ChatPanel({
  conversationId,
  title,
  onUnauthorized,
  onNotFound,
  onConversationChanged,
  onTitleHint,
}: Props) {
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const conversationRef = useRef(conversationId);
  conversationRef.current = conversationId;
  const callbacksRef = useRef({ onUnauthorized, onNotFound, onConversationChanged });
  callbacksRef.current = { onUnauthorized, onNotFound, onConversationChanged };

  const reloadDetail = useCallback(async () => {
    const target = conversationRef.current;
    try {
      const next = await api.getConversation(target);
      if (conversationRef.current === target) setDetail(next);
    } catch {
      // 会话列表仍会刷新，失败时保留已有详情
    }
    callbacksRef.current.onConversationChanged();
  }, []);

  useEffect(() => {
    let active = true;
    setDetail(null);
    setError(null);
    api
      .getConversation(conversationId)
      .then((result) => {
        if (active) setDetail(result);
      })
      .catch((caught) => {
        if (!active) return;
        if (caught instanceof ApiError && caught.status === 401) {
          callbacksRef.current.onUnauthorized();
          return;
        }
        if (caught instanceof ApiError && caught.status === 404) {
          callbacksRef.current.onNotFound();
          return;
        }
        setError(caught instanceof Error ? caught.message : '加载会话失败');
      });
    return () => {
      active = false;
    };
  }, [conversationId, reloadDetail]);

  const current = detail?.id === conversationId ? detail : null;

  if (error) {
    return <div className="p-6 text-sm text-red-300">{error}</div>;
  }

  if (!current) {
    return (
      <div className="flex flex-1 items-center justify-center gap-2 text-sm text-mist-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        加载会话…
      </div>
    );
  }

  return (
    <ChatSession
      key={conversationId}
      detail={current}
      title={title}
      onUnauthorized={onUnauthorized}
      onNotFound={onNotFound}
      onConversationChanged={() => void reloadDetail()}
      onTitleHint={onTitleHint}
    />
  );
}

export function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-ink-800 ring-1 ring-ink-600">
        <Sparkles className="h-6 w-6 text-accent-400" />
      </div>
      <h2 className="text-base font-medium text-mist-200">开始一个新会话</h2>
      <p className="mt-2 max-w-sm text-sm leading-relaxed text-mist-400">
        每个会话拥有独立的云端沙箱，可以读写文件、执行命令、运行服务。
      </p>
      <button
        type="button"
        onClick={onCreate}
        className="mt-5 rounded-lg bg-accent-500 px-4 py-2 text-sm font-medium text-ink-950 transition-colors hover:bg-accent-400"
      >
        新建会话
      </button>
    </div>
  );
}
