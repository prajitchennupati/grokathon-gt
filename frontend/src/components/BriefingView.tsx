import { ackItem, fmtT, type BotOutputView } from "../api";
import { Markdown } from "../markdown";

const VIA: Record<string, string> = { webhook: "Grok Bot", dropbox: "Grok Bot (shared folder)", fallback: "built-in version (xAI API)" };
const HELPER: Record<string, string> = { briefing: "Briefing", relief: "Handover", coordination: "Coordination", paperwork: "Paperwork" };

interface Props {
  outputs: BotOutputView[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onClose: () => void;
}

/** Slide-over reader for Bot documents. */
export default function BriefingView({ outputs, selectedId, onSelect, onClose }: Props) {
  const current = outputs.find((o) => o.id === selectedId) ?? outputs[outputs.length - 1];
  if (!current) return null;
  const isRelief = current.kind === "relief_briefing" && current.checklist.length > 0;
  const allAcked = isRelief && current.acked.length === current.checklist.length;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-edge px-4 py-2">
        <select
          value={current.id}
          onChange={(e) => onSelect(Number(e.target.value))}
          className="min-w-0 flex-1 truncate rounded border border-edge bg-black px-2 py-1 text-sm text-green-200"
        >
          {[...outputs].reverse().map((o) => <option key={o.id} value={o.id}>{o.title} · {fmtT(o.t_sim)}</option>)}
        </select>
        <a className="text-xs text-cyan-400 hover:underline" href={`/api/bots/outputs/${current.id}/export.pdf`}>PDF</a>
        <a className="text-xs text-cyan-400 hover:underline" href={`/api/bots/outputs/${current.id}/export.md`}>MD</a>
        <button onClick={onClose} className="ml-1 rounded px-2 text-lg text-green-600 hover:text-white" title="Close (Esc)">✕</button>
      </div>

      {isRelief && (
        <div className={`px-4 py-2 text-sm font-bold ${allAcked ? "bg-green-800/40 text-green-200" : "bg-cyan-900/30 text-cyan-200"}`}>
          {allAcked ? "✓ Handover complete" : `New controller: tap ✓ on each line to confirm you've read it (${current.acked.length}/${current.checklist.length})`}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <Markdown source={current.body_markdown} acked={current.acked} onAck={isRelief ? (i) => ackItem(current.id, i) : undefined} />
        <div className="mt-4 border-t border-edge pt-2 text-[11px] text-green-800">
          Written by the {HELPER[current.role] ?? current.role} helper{current.via !== "fallback" ? ` (${VIA[current.via] ?? current.via})` : ""} at {fmtT(current.t_sim)}.
          {current.sources.length > 0 && (
            <> Sources: {current.sources.map((s, i) => (
              <span key={i}>{i > 0 && ", "}<a href={s.url} target="_blank" rel="noreferrer" className="text-cyan-700 underline">{s.title}</a></span>
            ))}</>
          )}
        </div>
      </div>
    </div>
  );
}
