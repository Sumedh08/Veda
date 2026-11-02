export function linkifyCitationMarkers(markdown: string): string {
  return markdown.replace(/\[(S\d+)\](?!\()/g, (_match, citation: string) =>
    `[${citation}](#veda-citation-${citation})`,
  );
}
