import HeroSection from "./HeroSection"
import StatsBar from "./StatsBar"
import FailureSection from "./FailureSection"
import HowItWorks from "./HowItWorks"
import FeaturesGrid from "./FeaturesGrid"
import InstituteSection from "./InstituteSection"
import TestimonialsSection from "./TestimonialsSection"
import FAQSection from "./FAQSection"
import CTASection from "./CTASection"

export default function LandingPage() {
  return (
    <main>
      <HeroSection />
      <StatsBar />
      <FailureSection />
      <HowItWorks />
      <FeaturesGrid />
      <InstituteSection />
      <TestimonialsSection />
      <FAQSection />
      <CTASection />
    </main>
  )
}
