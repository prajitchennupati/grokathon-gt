import { useEffect, useRef } from "react";
import { fmtT, type LogEntry } from "../api";

const KIND_COLOR: Record<string, string> = {
  alert: "text-red-400",
  advisory: "text-cyan-400",
  approval: "text-green-300",
  instruction: "text-green-300",
  event: "text-amber-300",
  bot: "text-violet-300",
  coordination: "text-violet-300",
  relief: "text-violet-300",
  sim: "text-green-800",
};

export default function ShiftLog({ log }: { log: LogEntry[] }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [log.length]);

  return (
    <div className="h-full overflow-y-auto px-3 py-2 text-[11px] leading-relaxed">
      {log.map((e) => (
        <div key={e.id} className="flex gap-2">
          <span className="shrink-0 text-green-800">{fmtT(e.t_sim)}</span>
          <span className={`shrink-0 w-20 uppercase ${KIND_COLOR[e.kind] ?? "text-green-500"}`}>{e.kind}</span>
          <span className="shrink-0 w-20 text-green-700">{e.actor}</span>
          <span className="text-green-200">{e.message}</span>
        </div>
      ))}
      <div ref={end} />
    </div>
  );
}
