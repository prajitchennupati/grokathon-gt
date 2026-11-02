import { decideApproval, type ApprovalView } from "../api";

const WHO: Record<string, string> = { coordination: "The Coordination helper", paperwork: "The Paperwork helper", briefing: "The Briefing helper", relief: "The Handover helper" };

/** One Bot action waiting for a yes/no. */
export function ApprovalCard({ approval: a }: { approval: ApprovalView }) {
  const message = a.action.type === "send_message";
  return (
    <div className="rounded-xl border-2 border-violet-500 bg-violet-950/60 p-4">
      <div className="text-xs font-bold uppercase tracking-wider text-violet-300">
        {message ? "✉ Message ready to send" : a.action.type === "file_report" ? "✎ Report ready to file" : "Needs approval"}
      </div>
      <div className="mt-1 text-sm text-violet-100">
        {WHO[a.role] ?? "A helper"} wants to {message ? <>send this to <b>{a.action.to}</b></> : a.action.summary.toLowerCase()}:
      </div>
      <div className="mt-2 rounded-lg bg-black/50 p-3 text-sm leading-snug text-white">{a.action.body || a.action.summary}</div>
      <div className="mt-3 flex gap-2">
        <button onClick={() => decideApproval(a.id, "approve")} className="flex-1 rounded-lg bg-violet-400 py-2.5 text-sm font-bold text-black hover:bg-violet-300">
          {message ? "✓ Send it" : "✓ Approve"}
        </button>
        <button onClick={() => decideApproval(a.id, "decline")} className="rounded-lg border-2 border-violet-400 px-4 py-2.5 text-sm font-bold text-violet-200 hover:bg-violet-900/60">
          Don't send
        </button>
      </div>
    </div>
  );
}
