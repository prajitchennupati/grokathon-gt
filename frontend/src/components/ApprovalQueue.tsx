import { decideApproval, type ApprovalView } from "../api";

/** One Bot action waiting for the controller. */
export function ApprovalCard({ approval: a }: { approval: ApprovalView }) {
  const message = a.action.type === "send_message";
  return (
    <div className="rounded-lg border-2 border-violet-700 bg-violet-950/40 p-4">
      <div className="text-xs font-bold uppercase tracking-wider text-violet-300">
        {message ? `☏ Message to ${a.action.to ?? "facility"}` : a.action.type === "file_report" ? "✎ File report" : a.action.summary}
      </div>
      <div className="mt-2 text-sm leading-snug text-white">{a.action.body || a.action.summary}</div>
      <div className="mt-3 flex gap-2">
        <button onClick={() => decideApproval(a.id, "approve")}
          className="flex-1 rounded-md bg-violet-500 py-2 text-sm font-bold text-black hover:bg-violet-400">
          {message ? "Send" : "Approve"}
        </button>
        <button onClick={() => decideApproval(a.id, "decline")}
          className="rounded-md border-2 border-violet-700 px-4 py-2 text-sm font-bold text-violet-300 hover:bg-violet-900/50">
          Skip
        </button>
      </div>
    </div>
  );
}
