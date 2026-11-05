import { CaretDownIcon } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Footer, Nav } from "./components/Chrome";
import { Section } from "./components/ui";
import { DOCS } from "./docs/content";
import { DocSection } from "./docs/prose";
import { mount } from "./mount";
import "./styles.css";

const PAGES = DOCS.flatMap((g) => g.pages);

/** The last section whose top has scrolled past a line near the top of the window, for the sidebar marker. */
function useActivePage() {
  const [active, setActive] = useState(PAGES[0].id);
  useEffect(() => {
    let raf = 0;
    const update = () => {
      raf = 0;
      const line = window.innerHeight * 0.3;
      let current = PAGES[0].id;
      for (const p of PAGES) {
        const top = document.getElementById(p.id)?.getBoundingClientRect().top;
        if (top !== undefined && top <= line) current = p.id;
      }
      setActive(current);
    };
    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      cancelAnimationFrame(raf);
    };
  }, []);
  return active;
}

function Toc({ active, onPick }: { active: string; onPick?: () => void }) {
  return (
    <nav aria-label="Docs" className="space-y-7">
      {DOCS.map((g) => (
        <div key={g.group}>
          <p className="label">{g.group}</p>
          <ul className="mt-3 space-y-0.5 text-sm">
            {g.pages.map((p) => (
              <li key={p.id}>
                <a
                  href={`#${p.id}`}
                  onClick={onPick}
                  aria-current={active === p.id ? "location" : undefined}
                  className={`relative block py-1.5 pl-4 transition-colors hover:text-ink ${active === p.id ? "text-ink" : "text-ink-2"}`}
                >
                  {active === p.id && <span className="absolute top-1/2 left-0 size-1.5 -translate-y-1/2 bg-accent" aria-hidden />}
                  {p.title}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function Docs() {
  const active = useActivePage();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Nav page="docs" />
      <main>
        <Section className="!border-t-0">
          <div className="px-5 pt-14 pb-10 sm:px-8 md:pt-20 lg:px-12">
            <p className="label">Documentation</p>
            <h1 className="display mt-5 text-[2.6rem] leading-[1.0] sm:text-6xl">Run upheld on your own answers</h1>
            <p className="mt-6 max-w-[58ch] text-lg leading-relaxed text-ink-2">
              Install it, audit an answer from the command line, check a RAG pipeline from Python or over HTTP, and read what comes back.
            </p>
          </div>
        </Section>
        <Section>
          <div className="grid grid-cols-1 lg:grid-cols-[15.5rem_minmax(0,1fr)]">
            <aside className="border-b border-line lg:border-r lg:border-b-0">
              <div className="lg:hidden">
                <button
                  type="button"
                  onClick={() => setOpen((o) => !o)}
                  aria-expanded={open}
                  className="flex h-12 w-full items-center px-5 text-sm text-ink sm:px-8"
                >
                  {PAGES.find((p) => p.id === active)?.title}
                  <CaretDownIcon size={14} weight="bold" className={`ml-auto transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
                </button>
                {open && (
                  <div className="border-t border-line px-5 py-6 sm:px-8">
                    <Toc active={active} onPick={() => setOpen(false)} />
                  </div>
                )}
              </div>
              <div className="sticky top-14 hidden max-h-[calc(100vh-3.5rem)] overflow-y-auto px-6 py-10 lg:block">
                <Toc active={active} />
              </div>
            </aside>
            <div className="min-w-0">
              {PAGES.map((p) => (
                <DocSection key={p.id} id={p.id} title={p.title}>
                  {p.body}
                </DocSection>
              ))}
            </div>
          </div>
        </Section>
      </main>
      <Footer />
    </>
  );
}

mount(<Docs />);
