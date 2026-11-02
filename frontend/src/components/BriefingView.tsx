import { ackItem, fmtT, type BotOutputView } from "../api";
import { Markdown } from "../markdown";

const VIA: Record<string, string> = { webhook: "Grok Bot · webhook", dropbox: "Grok Bot · shared folder", fallback: "Fallback · xAI API" };
const LLM: Record<string, string> = { grok: "Grok", cache: "cached Grok", canned: "template" };

interface Props {
  outputs: BotOutputView[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export default function BriefingView({ outputs, selectedId, onSelect }: Props) {
  const current = outputs.find((o) => o.id === selectedId) ?? outputs[outputs.length - 1];
  if (!current) return <div className="p-4 text-xs text-green-800">No Bot output yet. Run the sim — the Briefing Bot reports at shift start.</div>;
  const isRelief = current.kind === "relief_briefing" && current.checklist.length > 0;

  return (
    <div className="flex h-full min-h-0">
      <div className="w-56 shrink-0 overflow-y-auto border-r border-edge">
        {[...outputs].reverse().map((o) => (
          <button key={o.id} onClick={() => onSelect(o.id)}
            className={`block w-full border-b border-edge px-2 py-1.5 text-left ${o.id === current.id ? "bg-green-900/30" : "hover:bg-green-950/40"}`}>
            <div className="truncate text-[11px] font-bold text-green-200">{o.title}</div>
            <div className="text-[10px] text-green-700">{o.role} · {fmtT(o.t_sim)}</div>
          </button>
        ))}
      </div>
      <div className="min-w-0 flex-1 overflow-y-auto p-3">
        <div className="mb-2 flex flex-wrap items-center gap-2 text-[10px]">
          <span className="rounded border border-violet-600 px-1 text-violet-300">{VIA[current.via] ?? current.via}{current.llm_source ? ` · ${LLM[current.llm_source] ?? current.llm_source}` : ""}</span>
          <span className="text-green-700">{fmtT(current.t_sim)}</span>
          {isRelief && <span className="text-cyan-400">{current.acked.length}/{current.checklist.length} acknowledged</span>}
          <span className="ml-auto flex gap-2">
            <a className="text-cyan-400 underline" href={`/api/bots/outputs/${current.id}/export.md`}>Export .md</a>
            <a className="text-cyan-400 underline" href={`/api/bots/outputs/${current.id}/export.pdf`}>Export .pdf</a>
          </span>
        </div>
        <Markdown source={current.body_markdown} acked={current.acked} onAck={isRelief ? (i) => ackItem(current.id, i) : undefined} />
        {current.sources.length > 0 && (
          <div className="mt-3 border-t border-edge pt-2 text-[10px] text-green-700">
            Sources: {current.sources.map((s, i) => (
              <span key={i}>{i > 0 && " · "}{s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="text-cyan-600 underline">{s.title}</a> : s.title}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
