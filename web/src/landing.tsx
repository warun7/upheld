import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Footer, Nav } from "./components/Chrome";
import { Benchmarks, EditedClaims } from "./sections/Benchmarks";
import { FinalCta, Install, Limits } from "./sections/Closing";
import { Demo } from "./sections/Demo";
import { Hero } from "./sections/Hero";
import { HowItWorks, Problem, Verdicts } from "./sections/Story";
import "./styles.css";

function Landing() {
  return (
    <>
      <Nav page="landing" />
      <main>
        <Hero />
        <Problem />
        <Demo />
        <HowItWorks />
        <Verdicts />
        <Benchmarks />
        <EditedClaims />
        <Limits />
        <Install />
        <FinalCta />
      </main>
      <Footer />
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Landing />
  </StrictMode>,
);
