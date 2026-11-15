import { useEffect, useState, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { highlightCode } from './shiki';

function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    highlightCode(code, lang)
      .then((result) => {
        if (active) setHtml(result);
      })
      .catch(() => {
        if (active) setHtml(null);
      });
    return () => {
      active = false;
    };
  }, [code, lang]);

  if (!html) {
    return (
      <pre className="overflow-x-auto rounded-lg bg-ink-850 p-4 font-mono text-xs leading-relaxed text-mist-200">
        <code>{code}</code>
      </pre>
    );
  }

  return (
    <div
      className="shiki-wrap overflow-hidden rounded-lg border border-ink-700"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => <>{children as ReactNode}</>,
          code: ({ className, children }) => {
            const match = /language-([\w-]+)/.exec(className ?? '');
            const text = String(children ?? '').replace(/\n$/, '');
            if (match) {
              return <CodeBlock code={text} lang={match[1]} />;
            }
            return <code className={className}>{children as ReactNode}</code>;
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
