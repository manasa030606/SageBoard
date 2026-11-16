import Link from "next/link";

import { HomeLink } from "@/components/brand/home-link";
import { Logo } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";

const PIPELINE = [
  {
    n: "01",
    title: "Understand",
    body: "Restates your question, names the metric, grain and time window, and lists its assumptions.",
  },
  {
    n: "02",
    title: "Read the schema",
    body: "Looks up the real tables, columns and joins before planning, so nothing is invented.",
  },
  {
    n: "03",
    title: "Plan",
    body: "Breaks the question into a short, explicit sequence of analytical steps.",
  },
  {
    n: "04",
    title: "Write & validate SQL",
    body: "Every query is parsed and checked: read-only, allow-listed tables, bounded cost.",
  },
  {
    n: "05",
    title: "Analyse",
    body: "Computes totals, shares and changes with deterministic code, not by guessing.",
  },
  {
    n: "06",
    title: "Verify & explain",
    body: "Insights are checked against the results. Anything unsupported is removed.",
  },
];

const PRINCIPLES = [
  {
    title: "Read-only by design",
    body: "Queries run in a read-only transaction under a database role that can only see your dataset. Writing data is not possible.",
  },
  {
    title: "Validated before it runs",
    body: "Generated SQL is checked independently of the model. A rejected query is repaired and checked again, never executed as written.",
  },
  {
    title: "Every number has a source",
    body: "Each insight points to the rows or computed fact behind it. When the data cannot answer a question, Sageboard says so.",
  },
];

// Real questions from the evaluation set (apps/api/evals/cases.py), asked of the sample dataset.
const EXAMPLE_QUESTIONS = [
  "What is the total revenue?",
  "What is the revenue by product category?",
  "Which 5 products generated the most revenue?",
  "How did revenue change from September 2026 to October 2026?",
  "Why did revenue change between September and October 2026? Break it down by region.",
];

const AUDIENCE = [
  {
    who: "Business analysts",
    what: "Answer one-off questions and keep the SQL for review.",
  },
  {
    who: "Data teams",
    what: "Let colleagues ask their own questions while every query stays auditable.",
  },
  { who: "Students", what: "See how a question becomes a plan, a query and a conclusion." },
  {
    who: "Small businesses",
    what: "Get answers from your sales exports without writing SQL.",
  },
];

export default function LandingPage() {
  return (
    <div className="flex flex-1 flex-col">
      <header className="sticky top-0 z-30 border-b border-line/80 bg-warm/95 backdrop-blur-sm">
        <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-5 sm:px-8">
          <HomeLink>
            <Logo />
          </HomeLink>
          <nav
            aria-label="Primary"
            className="hidden items-center gap-7 text-sm text-ink-2 md:flex"
          >
            <a href="#how" className="hover:text-ink">
              How it works
            </a>
            <a href="#trust" className="hover:text-ink">
              Safety
            </a>
            <a href="#who" className="hover:text-ink">
              Who it’s for
            </a>
          </nav>
          <div className="flex items-center gap-2">
            <ButtonLink href="/login" variant="ghost" className="max-sm:hidden">
              Sign in
            </ButtonLink>
            <ButtonLink href="/register" variant="primary">
              Create account
            </ButtonLink>
          </div>
        </div>
      </header>

      <main>
        {/* Hero ---------------------------------------------------------- */}
        <section className="mx-auto grid max-w-[1200px] gap-14 px-5 pt-16 pb-20 sm:px-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] lg:items-center lg:pt-24 lg:pb-28">
          <div>
            <p className="eyebrow">Natural-language data analysis</p>
            <h1 className="mt-5 text-display text-[40px] text-navy sm:text-[56px]">
              Ask questions about your data in plain language.
            </h1>
            <p className="mt-6 max-w-xl text-[17px] leading-7 text-ink-2">
              Sageboard reads your schema, plans the analysis, writes and validates read-only SQL,
              and explains the result with evidence you can check. Load the sample retail dataset or
              upload your own CSV file.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <ButtonLink href="/register" variant="primary" size="lg">
                Create account
              </ButtonLink>
              <ButtonLink href="/login" variant="secondary" size="lg">
                Sign in
              </ButtonLink>
            </div>
          </div>
          <div className="rounded-md border border-line bg-paper p-6">
            <p className="eyebrow">Example questions</p>
            <p className="mt-2 text-[14px] leading-6 text-ink-2">
              Questions Sageboard is tested with, asked of the sample retail dataset.
            </p>
            <ul className="mt-4 divide-y divide-line border-t border-line">
              {EXAMPLE_QUESTIONS.map((q) => (
                <li key={q} className="py-3 text-[15px] text-ink">
                  {q}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* How it works ---------------------------------------------------- */}
        <section id="how" aria-labelledby="how-heading" className="border-y border-line bg-paper">
          <div className="mx-auto max-w-[1200px] px-5 py-20 sm:px-8">
            <div className="max-w-2xl">
              <p className="eyebrow">How it works</p>
              <h2 id="how-heading" className="mt-4 text-title text-[34px] text-navy">
                Six steps from question to answer.
              </h2>
              <p className="mt-4 text-[16px] leading-7 text-ink-2">
                Each question moves through the same six steps, and you can open every one of them
                to see what ran.
              </p>
            </div>
            <ol className="mt-12 grid border-t border-line sm:grid-cols-2 lg:grid-cols-3">
              {PIPELINE.map((step) => (
                <li
                  key={step.n}
                  className="border-b border-line py-7 sm:pr-8 lg:[&:nth-last-child(-n+3)]:border-b-0"
                >
                  <span className="font-mono text-xs text-amber-ink tabular">{step.n}</span>
                  <h3 className="mt-3 text-[17px] font-semibold text-ink">{step.title}</h3>
                  <p className="mt-2 text-[14px] leading-6 text-ink-2">{step.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Trust ----------------------------------------------------------- */}
        <section
          id="trust"
          aria-labelledby="trust-heading"
          className="mx-auto max-w-[1200px] px-5 py-20 sm:px-8"
        >
          <p className="eyebrow">Safety and trust</p>
          <h2 id="trust-heading" className="mt-4 max-w-2xl text-title text-[34px] text-navy">
            Checks that do not depend on the model behaving well.
          </h2>
          <ul className="mt-10 grid gap-x-10 gap-y-8 md:grid-cols-3">
            {PRINCIPLES.map(({ title, body }) => (
              <li key={title}>
                <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
                <p className="mt-1 text-[14px] leading-6 text-ink-2">{body}</p>
              </li>
            ))}
          </ul>
        </section>

        {/* Audience -------------------------------------------------------- */}
        <section id="who" aria-labelledby="who-heading" className="border-t border-line">
          <div className="mx-auto max-w-[1200px] px-5 py-20 sm:px-8">
            <h2 id="who-heading" className="text-title text-[28px] text-navy">
              Who it is for
            </h2>
            <dl className="mt-8 grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:grid-cols-4">
              {AUDIENCE.map((a) => (
                <div key={a.who}>
                  <dt className="text-[15px] font-semibold text-ink">{a.who}</dt>
                  <dd className="mt-2 text-[14px] leading-6 text-ink-2">{a.what}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        {/* CTA ------------------------------------------------------------- */}
        <section className="bg-navy">
          <div className="mx-auto flex max-w-[1200px] flex-col items-start justify-between gap-8 px-5 py-16 sm:px-8 md:flex-row md:items-center">
            <div>
              <h2 className="text-title text-[30px] text-warm">Try it on the sample dataset.</h2>
              <p className="mt-2 text-[15px] text-sage">
                Create an account, load the retail sample in one click and ask a question.
              </p>
            </div>
            <ButtonLink href="/register" variant="inverse" size="lg">
              Create account
            </ButtonLink>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1200px] flex-col gap-4 px-5 py-8 text-[13px] text-ink-2 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <div className="flex items-center gap-3">
            <HomeLink>
              <Logo />
            </HomeLink>
            <span className="hidden sm:inline">Your data. Your questions. Clear decisions.</span>
          </div>
          <div className="flex gap-6">
            <Link href="/app/dashboard" className="hover:text-ink">
              Product
            </Link>
            <Link href="/status" className="hover:text-ink">
              System status
            </Link>
            <span>© 2026 Sageboard</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
