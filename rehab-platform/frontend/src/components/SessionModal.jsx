export default function SessionModal({ isOpen, summary, onClose }) {
  if (!isOpen) {
    return null;
  }

  async function handleCopy() {
    await navigator.clipboard.writeText(summary ?? "");
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 p-4 opacity-100 transition-opacity duration-200"
      onClick={onClose}
      role="presentation"
    >
      <section
        className="w-full max-w-xl scale-100 rounded-lg border border-slate-700 bg-slate-900 p-6 shadow-2xl shadow-slate-950 transition duration-200 ease-out"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="text-3xl" aria-hidden="true">
              ✅
            </span>
            <h2 className="text-xl font-bold text-slate-50">Session Complete</h2>
          </div>
        </div>

        <pre className="max-h-[50vh] overflow-auto whitespace-pre-wrap rounded-md bg-slate-950 p-4 text-sm leading-6 text-slate-200">
          {summary ?? ""}
        </pre>

        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button
            type="button"
            onClick={handleCopy}
            className="rounded-md border border-slate-600 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:bg-slate-800"
          >
            Copy Summary
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-cyan-400 px-4 py-2 text-sm font-bold text-slate-950 transition hover:bg-cyan-300"
          >
            Close
          </button>
        </div>
      </section>
    </div>
  );
}
