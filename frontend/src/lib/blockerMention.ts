export function blockerMention(source: string, cursor: number, inCode: boolean) {
  if (inCode || cursor < 0 || cursor > source.length || /[\s#]/.test(source[cursor] || '')) return null;
  const match = /(?:^|\s)#([^\s#]*)$/.exec(source.slice(0, cursor));
  return match ? { start: cursor - match[1].length - 1, query: match[1] } : null;
}
