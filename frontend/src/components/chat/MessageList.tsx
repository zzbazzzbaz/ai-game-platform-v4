import { useEffect, useRef } from 'react';
import type { UIMessage } from 'ai';
import { MessageItem } from './MessageItem';

interface Props {
  messages: UIMessage[];
}

export function MessageList({ messages }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const atBottomRef = useRef(true);

  const handleScroll = () => {
    const element = containerRef.current;
    if (!element) return;
    atBottomRef.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
  };

  useEffect(() => {
    const element = containerRef.current;
    if (!element || !atBottomRef.current) return;
    element.scrollTop = element.scrollHeight;
  }, [messages]);

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto pb-4 pt-2"
    >
      {messages.length === 0 ? (
        <div className="mx-auto mt-20 max-w-md px-6 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-ink-800 ring-1 ring-ink-600">
            <span className="text-lg">✳</span>
          </div>
          <h2 className="text-base font-medium text-mist-200">在云端沙箱里开始一个任务</h2>
          <p className="mt-2 text-sm leading-relaxed text-mist-400">
            让智能体读写文件、运行命令、搜索代码。每一步工具调用都会显示在这里。
          </p>
        </div>
      ) : (
        messages.map((message) => (
          <MessageItem key={message.id} message={message} />
        ))
      )}
    </div>
  );
}
