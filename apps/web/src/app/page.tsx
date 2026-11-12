import { ArrowRight, FileCheck2, Lock, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";
import { ProductPreview } from "@/features/landing/product-preview";

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
    icon: Lock,
    title: "Read-only by design",
    body: "Queries run in a read-only transaction under a role that can only see your dataset. Writing data isn’t possible.",
  },
  {
    icon: ShieldCheck,
    title: "Validated before it runs",
    body: "Generated SQL is checked independently of the model. Rejected queries are repaired, never executed.",
  },
  {
    icon: FileCheck2,
    title: "Every number has a source",
    body: "Each insight links to the rows or computed fact behind it. If the data can’t answer, Sageboard says so.",
  },
];

const AUDIENCE = [
  {
    who: "Business analysts",
    what: "Answer ad-hoc questions in minutes and keep the SQL for review.",
  },
  { who: "Data teams", what: "Let stakeholders self-serve while every query stays auditable." },
  { who: "Students", what: "See how a question becomes a plan, a query and a conclusion." },
  {
    who: "Small businesses",
    what: "Get plain-language answers from your sales exports, no SQL needed.",
  },
];

export default function LandingPage() {
  return (
    <div className="flex flex-1 flex-col">
      <header className="sticky top-0 z-30 border-b border-line/80 bg-warm/95 backdrop-blur-sm">
        <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-5 sm:px-8">
          <Link href="/" aria-label="Sageboard home">
            <Logo />
          </Link>
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
            <ButtonLink href="/app/dashboard" variant="ghost" className="hidden sm:inline-flex">
              Sign in
            </ButtonLink>
            <ButtonLink href="/app/analyst" variant="primary">
              Open the demo
            </ButtonLink>
          </div>
        </div>
      </header>

      <main>
        {/* Hero ---------------------------------------------------------- */}
        <section className="mx-auto grid max-w-[1200px] gap-14 px-5 pt-16 pb-20 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:items-center lg:pt-24 lg:pb-28">
          <div>
            <p className="eyebrow">An autonomous data analyst</p>
            <h1 className="mt-5 text-display text-[44px] text-navy sm:text-[60px]">
              Your data. Your questions.{" "}
              <em className="text-forest not-italic sm:italic">Clear decisions.</em>
            </h1>
            <p className="mt-6 max-w-xl text-[17px] leading-7 text-ink-2">
              Ask a business question in plain language. Sageboard reads your schema, plans the
              analysis, writes and validates read-only SQL, and explains the result with evidence
              you can check.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <ButtonLink
                href="/app/analyst"
                variant="primary"
                size="lg"
                trailingIcon={<ArrowRight className="size-4" aria-hidden />}
              >
                Try the analyst
              </ButtonLink>
              <ButtonLink href="/app/dashboard" variant="secondary" size="lg">
                View the dashboard
              </ButtonLink>
            </div>
            <p className="mt-5 text-xs text-ink-2">
              Runs on a bundled retail sample dataset. No sign-up needed for the demo.
            </p>
          </div>
          <ProductPreview />
        </section>

        {/* How it works ---------------------------------------------------- */}
        <section id="how" aria-labelledby="how-heading" className="border-y border-line bg-paper">
          <div className="mx-auto max-w-[1200px] px-5 py-20 sm:px-8">
            <div className="max-w-2xl">
              <p className="eyebrow">How it works</p>
              <h2 id="how-heading" className="mt-4 text-title text-[34px] text-navy">
                An analyst’s method, made explicit.
              </h2>
              <p className="mt-4 text-[16px] leading-7 text-ink-2">
                Sageboard isn’t a chatbot guessing at answers. Each question moves through six
                inspectable steps, and you can open every one of them.
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
          <div className="grid gap-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <div>
              <p className="eyebrow">Safety & trust</p>
              <h2 id="trust-heading" className="mt-4 text-title text-[34px] text-navy">
                Confident answers start with a careful process.
              </h2>
              <ul className="mt-10 grid gap-8">
                {PRINCIPLES.map(({ icon: Icon, title, body }) => (
                  <li key={title} className="grid grid-cols-[auto_1fr] gap-4">
                    <span className="grid size-9 place-items-center rounded-sm bg-sage-50 text-forest">
                      <Icon className="size-[18px]" aria-hidden strokeWidth={1.75} />
                    </span>
                    <div>
                      <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
                      <p className="mt-1 text-[14px] leading-6 text-ink-2">{body}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            <figure className="self-center overflow-hidden rounded-md border border-line bg-navy text-[12.5px]">
              <figcaption className="flex items-center justify-between border-b border-white/10 px-4 py-2.5 text-2xs tracking-[0.08em] text-sage uppercase">
                <span>Query validation</span>
                <span className="font-mono tracking-normal text-warm/60 normal-case">
                  attempt 1 of 3
                </span>
              </figcaption>
              <pre className="overflow-x-auto px-4 py-4 leading-6 text-warm/90">
                <code>
                  <span className="text-sage">SELECT</span> date_trunc(
                  <span className="text-amber">&apos;month&apos;</span>, order_date),{"\n"}
                  {"       "}
                  <span className="text-sage">SUM</span>(
                  <span className="underline decoration-amber decoration-wavy underline-offset-4">
                    revenue
                  </span>
                  ){"\n"}
                  <span className="text-sage">FROM</span> orders{"\n"}
                  <span className="text-sage">GROUP BY</span> 1;
                </code>
              </pre>
              <div className="border-t border-white/10 px-4 py-3 font-mono text-[12px] leading-5">
                <p className="text-amber">✕ UNKNOWN_COLUMN orders.revenue</p>
                <p className="text-warm/70"> → repaired using order_items.quantity × unit_price</p>
                <p className="mt-1 text-sage">✓ read-only · allow-listed tables · LIMIT applied</p>
              </div>
            </figure>
          </div>
        </section>

        {/* Audience -------------------------------------------------------- */}
        <section id="who" aria-labelledby="who-heading" className="border-t border-line">
          <div className="mx-auto max-w-[1200px] px-5 py-20 sm:px-8">
            <h2 id="who-heading" className="text-title text-[28px] text-navy">
              Built for people who need answers, not dashboards to maintain.
            </h2>
            <dl className="mt-10 grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:grid-cols-4">
              {AUDIENCE.map((a) => (
                <div key={a.who} className="border-t-2 border-forest pt-4">
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
              <h2 className="text-title text-[30px] text-warm">Ask your first question.</h2>
              <p className="mt-2 text-[15px] text-sage">
                Explore the analyst with the retail sample dataset.
              </p>
            </div>
            <ButtonLink
              href="/app/analyst"
              variant="inverse"
              size="lg"
              trailingIcon={<ArrowRight className="size-4" aria-hidden />}
            >
              Open the analyst
            </ButtonLink>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1200px] flex-col gap-4 px-5 py-8 text-[13px] text-ink-2 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <div className="flex items-center gap-3">
            <Logo />
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
