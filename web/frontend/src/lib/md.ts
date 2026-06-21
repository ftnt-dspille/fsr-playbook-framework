/**
 * Tiny markdown renderer for chat messages. Marked + DOMPurify so we
 * don't trust assistant output. Returns sanitized HTML; the consumer
 * passes it to {@html ...}.
 */
import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({
  gfm: true,
  breaks: true
});

export function renderMarkdown(src: string): string {
  if (!src) return '';
  const html = marked.parse(src, { async: false }) as string;
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'p', 'br', 'hr', 'strong', 'em', 'code', 'pre', 'a',
      'ul', 'ol', 'li',
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'blockquote', 'span', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
    ],
    ALLOWED_ATTR: ['href', 'title', 'class', 'target', 'rel']
  });
}
