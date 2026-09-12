import { Navbar } from "@/components/landing/Navbar";
import { Hero } from "@/components/landing/Hero";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { ExtractionAnatomy } from "@/components/landing/ExtractionAnatomy";
import { SignatureInteraction } from "@/components/landing/SignatureInteraction";
import { PrivacyAndCta } from "@/components/landing/PrivacyAndCta";
import { Footer } from "@/components/landing/Footer";

/**
 * Landing page — UX-UI-SPEC section 1.
 *
 * Section order follows the spec, with one substitution: "sample looks" became
 * ExtractionAnatomy, because the project ships no garment photography and a fabricated
 * closet would contradict the product's own grounding rule. Recorded in docs/DECISIONS.md.
 */
export default function Home() {
  return (
    <>
      <Navbar />
      <Hero />
      <SignatureInteraction />
      <HowItWorks />
      <ExtractionAnatomy />
      <PrivacyAndCta />
      <Footer />
    </>
  );
}
