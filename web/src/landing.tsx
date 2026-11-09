import { Footer, Nav } from "./components/Chrome";
import { Benchmarks, EditedClaims, FreshBenchmark, Quality } from "./sections/Benchmarks";
import { FinalCta, Install, Limits } from "./sections/Closing";
import { Hero } from "./sections/Hero";
import { HowItWorks, Problem, Verdicts } from "./sections/Story";
import { Report } from "./sections/Report";
import { mount } from "./mount";
import "./fonts.css";
import "./styles.css";

export function Landing() {
  return (
    <>
      <Nav page="landing" />
      <main>
        <Hero />
        <Problem />
        <Report />
        <HowItWorks />
        <Verdicts />
        <Quality />
        <Benchmarks />
        <EditedClaims />
        <FreshBenchmark />
        <Limits />
        <Install />
        <FinalCta />
      </main>
      <Footer />
    </>
  );
}

mount(<Landing />);
