/**
 * Minimal Markdown renderer for Bot outputs: headings, paragraphs, lists, task lists,
 * tables, blockquotes, rules, **bold**, _italic_, `code` and [links](url). Task-list
 * items are numbered in document order so the relief checklist can be acknowledged.
 */
import type { ReactNode } from "react";

interface Opts {
  acked?: number[];
  onAck?: (index: number) => void;
}

export function Markdown({ source, acked = [], onAck }: { source: string } & Opts) {
  return <div className="md space-y-2 text-[12px] leading-relaxed text-green-100">{render(source, { acked, onAck })}</div>;
}

function render(src: string, opts: Opts): ReactNode[] {
  const lines = src.replace(/\r/g, "").split("\n");
  const out: ReactNode[] = [];
  let task = 0;
  let i = 0;
  const key = () => out.length;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const size = ["text-base", "text-sm", "text-[13px]", "text-xs"][h[1].length - 1];
      out.push(<div key={key()} className={`${size} font-bold text-target ${h[1].length > 1 ? "mt-3 border-b border-edge pb-0.5" : ""}`}>{inline(h[2])}</div>);
      i++;
      continue;
    }
    if (/^(-{3,}|\*{3,})$/.test(line.trim())) { out.push(<hr key={key()} className="border-edge" />); i++; continue; }

    if (line.startsWith(">")) {
      const buf: string[] = [];
      while (i < lines.length && lines[i].startsWith(">")) buf.push(lines[i++].replace(/^>\s?/, ""));
      out.push(<div key={key()} className="border-l-2 border-amber-600 pl-2 text-amber-300/90">{inline(buf.join(" "))}</div>);
      continue;
    }

    if (line.trim().startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        const cells = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells);
        i++;
      }
      const [head, ...body] = rows;
      out.push(
        <table key={key()} className="w-full border-collapse text-[11px]">
          <thead><tr>{head.map((c, j) => <th key={j} className="border border-edge px-1.5 py-0.5 text-left text-green-400">{inline(c)}</th>)}</tr></thead>
          <tbody>{body.map((r, k) => <tr key={k}>{r.map((c, j) => <td key={j} className="border border-edge px-1.5 py-0.5 align-top">{inline(c)}</td>)}</tr>)}</tbody>
        </table>,
      );
      continue;
    }

    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const items: ReactNode[] = [];
      const ordered = /^\s*\d+\./.test(line);
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
        const raw = lines[i].replace(/^\s*([-*]|\d+\.)\s+/, "");
        const t = /^\[([ xX])\]\s+(.*)$/.exec(raw);
        if (t) {
          const idx = task++;
          const done = opts.acked?.includes(idx) || t[1] !== " ";
          items.push(
            <li key={items.length} className="flex list-none items-start gap-2">
              <button
                disabled={done || !opts.onAck}
                onClick={() => opts.onAck?.(idx)}
                className={`mt-0.5 shrink-0 rounded border px-1 text-[10px] font-bold ${done ? "border-green-600 bg-green-700/40 text-green-200" : "border-cyan-600 text-cyan-300 hover:bg-cyan-900/40"}`}
              >
                {done ? "✓ ACK" : "ACK"}
              </button>
              <span className={done ? "text-green-600" : ""}>{inline(t[2])}</span>
            </li>,
          );
        } else {
          items.push(<li key={items.length}>{inline(raw)}</li>);
        }
        i++;
      }
      out.push(ordered
        ? <ol key={key()} className="list-decimal space-y-0.5 pl-5">{items}</ol>
        : <ul key={key()} className="list-disc space-y-1 pl-5">{items}</ul>);
      continue;
    }

    const buf: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|>|\||\s*([-*]|\d+\.)\s+)/.test(lines[i])) buf.push(lines[i++]);
    out.push(<p key={key()}>{inline(buf.join(" "))}</p>);
  }
  return out;
}

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|_[^_]+_|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) out.push(text.slice(last, m.index));
    const t = m[0];
    const k = out.length;
    if (t.startsWith("**")) out.push(<strong key={k} className="text-white">{t.slice(2, -2)}</strong>);
    else if (t.startsWith("`")) out.push(<code key={k} className="rounded bg-black px-1 text-cyan-300">{t.slice(1, -1)}</code>);
    else if (t.startsWith("_")) out.push(<em key={k}>{t.slice(1, -1)}</em>);
    else {
      const l = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(t)!;
      out.push(<a key={k} href={l[2]} target="_blank" rel="noreferrer" className="text-cyan-400 underline">{l[1]}</a>);
    }
    last = m.index! + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
