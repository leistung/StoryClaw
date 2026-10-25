/** Preserve paragraph boundaries for API-generated plain text and existing rich text. */
export function toEditorContent(content: string): string {
  if (!content) return ''
  if (/<\/?(?:p|h[1-6]|ul|ol|li|blockquote|pre|br|div)\b[^>]*>/i.test(content)) return content
  const escape = (text: string) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return content.trim().split(/\n\s*\n|\r?\n/).filter(text => text.trim()).map(text => `<p>${escape(text.trim())}</p>`).join('')
}
