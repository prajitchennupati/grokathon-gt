/** First-run explainer for people who've never seen an air traffic control screen. */
export default function Intro({ onDemo, onLive, onClose }: { onDemo: () => void; onLive: () => void; onClose: () => void }) {
  const cards = [
    { icon: "✈", title: "Watch the planes", text: "Each plane icon is a flight near Atlanta. Click one to see the airline, aircraft, height and speed." },
    { icon: "⚠", title: "Get warned early", text: "If two planes are going to get too close, a red card appears with a fix that has been safety-checked. A person always decides." },
    { icon: "✎", title: "Helpers do the paperwork", text: "Four AI helpers write briefings, messages and reports. Nothing is sent without approval." },
  ];
  return (
    <div className="absolute inset-0 z-[2000] flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-3xl rounded-2xl border border-gray-700 bg-[#0f141a] p-8 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="text-xs font-bold uppercase tracking-[0.3em] text-green-400">Clearance</div>
        <h1 className="mt-2 text-3xl font-bold text-white">An AI co-pilot for air traffic controllers</h1>
        <p className="mt-2 text-gray-400">It watches the sky, warns about planes getting too close, and handles the paperwork, so controllers can focus on the planes.</p>
        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          {cards.map((c) => (
            <div key={c.title} className="rounded-xl border border-gray-800 bg-black/40 p-4">
              <div className="text-2xl">{c.icon}</div>
              <div className="mt-2 font-bold text-gray-100">{c.title}</div>
              <div className="mt-1 text-sm leading-relaxed text-gray-400">{c.text}</div>
            </div>
          ))}
        </div>
        <div className="mt-7 flex flex-wrap items-center gap-3">
          <button onClick={onDemo} className="rounded-xl bg-amber-400 px-6 py-3 text-base font-bold text-black hover:bg-amber-300">▶ Start the guided demo</button>
          <button onClick={onLive} className="rounded-xl border-2 border-gray-600 px-6 py-3 text-base font-bold text-gray-200 hover:border-gray-400">See live Atlanta traffic</button>
        </div>
      </div>
    </div>
  );
}
