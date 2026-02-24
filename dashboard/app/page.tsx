import { X } from "lucide-react";

const todos = [
  "Add coverage config to pyproject.toml",
  "Update ci.yml: add torch-cpu, pytest-cov, coverage report, artifact upload",
  "Commit and push"
];

export default function Home() {
  return (
    <main className="min-h-screen bg-[#0d0d0d] p-4 text-white sm:p-8">
      <section className="mx-auto flex min-h-[calc(100vh-2rem)] w-full max-w-4xl flex-col rounded-[52px] border border-white/10 bg-gradient-to-b from-[#282828] to-[#212121] px-6 py-8 shadow-[0_28px_80px_rgba(0,0,0,0.55)] sm:px-10 sm:py-10">
        <div className="mb-8 flex items-center justify-between sm:mb-10">
          <button
            type="button"
            aria-label="Close update todos"
            className="inline-flex h-20 w-20 items-center justify-center rounded-full border border-white/15 bg-[#2a2a2a]/85 text-white/90"
          >
            <X className="h-10 w-10" strokeWidth={2.2} />
          </button>

          <h1 className="pr-4 text-center text-4xl font-semibold tracking-tight sm:text-6xl">Update Todos</h1>

          <div className="h-20 w-20" aria-hidden="true" />
        </div>

        <div className="rounded-3xl border border-white/10 bg-[#232323]/65 px-4 py-5 sm:px-8 sm:py-7">
          <ul className="space-y-4 sm:space-y-6">
            {todos.map((todo) => (
              <li key={todo} className="flex items-start gap-4 sm:gap-5">
                <span
                  className="mt-1 inline-block h-9 w-9 shrink-0 rounded-md border border-white/35"
                  aria-hidden="true"
                />
                <span className="text-2xl leading-tight text-white/95 sm:text-[3rem] sm:leading-[1.2]">{todo}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </main>
  );
}
