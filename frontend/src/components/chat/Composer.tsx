import { useRef, useState } from 'react';
import { ArrowUp, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface Props {
  status: 'submitted' | 'streaming' | 'ready' | 'error';
  onSend: (text: string) => void;
  onStop: () => void;
  disabled?: boolean;
  placeholder?: string;
}

export function Composer({ status, onSend, onStop, disabled, placeholder }: Props) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const busy = status === 'submitted' || status === 'streaming';

  const submit = () => {
    const text = value.trim();
    if (!text || busy || disabled) return;
    onSend(text);
    setValue('');
    requestAnimationFrame(() => {
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
    });
  };

  return (
    <div className="border-t border-ink-800 bg-ink-950/80 px-3 py-3 backdrop-blur sm:px-6">
      <div className="mx-auto max-w-3xl">
        <div
          className={cn(
            'flex items-end gap-2 rounded-2xl border border-ink-600 bg-ink-900 px-3 py-2 shadow-panel transition-colors focus-within:border-accent-500/60',
            disabled && 'opacity-60',
          )}
        >
          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            disabled={disabled}
            placeholder={placeholder ?? '描述你要完成的任务…'}
            onChange={(event) => {
              setValue(event.target.value);
              const element = event.currentTarget;
              element.style.height = 'auto';
              element.style.height = `${Math.min(element.scrollHeight, 200)}px`;
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                submit();
              }
            }}
            className="max-h-[200px] flex-1 resize-none bg-transparent py-1.5 text-sm leading-relaxed text-mist-200 outline-none placeholder:text-mist-400/60"
          />
          {busy ? (
            <Button variant="outline" size="icon" onClick={onStop} title="停止">
              <Square className="h-3.5 w-3.5 fill-current" />
            </Button>
          ) : (
            <Button size="icon" onClick={submit} disabled={!value.trim() || disabled} title="发送">
              <ArrowUp className="h-4 w-4" />
            </Button>
          )}
        </div>
        <div className="mt-1.5 flex items-center justify-between px-1 text-[10px] text-mist-400/70">
          <span>Enter 发送 · Shift + Enter 换行</span>
          <span>DeepSeek deepseek-flash · E2B 沙箱</span>
        </div>
      </div>
    </div>
  );
}
