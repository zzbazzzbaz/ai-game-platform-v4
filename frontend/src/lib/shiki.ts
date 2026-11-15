import { createHighlighter, type Highlighter } from 'shiki/bundle/web';

const LANGS = [
  'bash',
  'css',
  'diff',
  'html',
  'javascript',
  'json',
  'markdown',
  'python',
  'shell',
  'sql',
  'text',
  'tsx',
  'typescript',
  'yaml',
];

let highlighterPromise: Promise<Highlighter> | null = null;

function getHighlighter(): Promise<Highlighter> {
  highlighterPromise ??= createHighlighter({
    themes: ['github-dark'],
    langs: LANGS,
  });
  return highlighterPromise;
}

export async function highlightCode(code: string, lang: string): Promise<string> {
  const highlighter = await getHighlighter();
  const supported = highlighter.getLoadedLanguages();
  const language = supported.includes(lang) ? lang : 'text';
  return highlighter.codeToHtml(code, { lang: language, theme: 'github-dark' });
}
