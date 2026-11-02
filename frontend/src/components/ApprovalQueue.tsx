import { decideApproval, fmtT, type ApprovalView } from "../api";

const TYPE_LABEL: Record<string, string> = { send_message: "MESSAGE", file_report: "REPORT" };

export default function ApprovalQueue({ approvals, onOpen }: { approvals: ApprovalView[]; onOpen: (outputId: number) => void }) {
  const pending = approvals.filter((a) => a.status === "pending");
  const decided = approvals.filter((a) => a.status !== "pending").slice(-4).reverse();

  return (
    <section className="rounded border border-edge">
      <div className="flex items-center justify-between border-b border-edge px-3 py-2">
        <div className="text-xs uppercase tracking-wider text-green-700">Approval queue</div>
        {pending.length > 0 && <span className="rounded bg-amber-500 px-1.5 text-[10px] font-bold text-black">{pending.length}</span>}
      </div>
      {pending.length === 0 && <div className="px-3 py-3 text-xs text-green-800">Nothing waiting. Bot actions appear here and do nothing until approved.</div>}
      {pending.map((a) => (
        <div key={a.id} className="border-b border-edge p-3">
          <div className="flex items-center gap-2 text-[10px]">
            <span className="rounded border border-violet-500 px-1 font-bold text-violet-300">{TYPE_LABEL[a.action.type] ?? a.action.type.toUpperCase()}</span>
            <span className="text-green-700">{a.role} · {fmtT(a.t_sim)}</span>
            <button className="ml-auto text-cyan-500 hover:underline" onClick={() => onOpen(a.output_id)}>context</button>
          </div>
          <div className="mt-1 text-xs font-bold text-white">{a.action.summary}</div>
          {a.action.to && <div className="text-[11px] text-green-500">To: {a.action.to}</div>}
          {a.action.body && <div className="mt-1 rounded bg-black/60 p-2 text-[11px] text-green-200">{a.action.body}</div>}
          <div className="mt-2 flex gap-2">
            <button onClick={() => decideApproval(a.id, "approve")}
              className="flex-1 rounded border border-green-500 bg-green-600/20 py-1 text-xs font-bold text-green-300 hover:bg-green-600/40">
              Approve{a.action.type === "send_message" ? " & send (sim)" : ""}
            </button>
            <button onClick={() => decideApproval(a.id, "decline")}
              className="flex-1 rounded border border-red-500 py-1 text-xs font-bold text-red-300 hover:bg-red-900/40">
              Decline
            </button>
          </div>
        </div>
      ))}
      {decided.length > 0 && (
        <div className="px-3 py-2">
          {decided.map((a) => (
            <div key={a.id} className="text-[11px] text-green-800">
              {fmtT(a.decided_t_sim ?? 0)} {a.status === "approved" ? (a.action.type === "send_message" ? "✓ sent (simulated)" : "✓ approved") : "✗ declined"} — {a.action.summary}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
