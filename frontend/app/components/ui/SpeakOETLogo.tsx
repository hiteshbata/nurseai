import Image from "next/image";

type SpeakOETLogoProps = {
  variant?: "full" | "mark";
  theme?: "dark" | "light";
  height?: number;
  // Only pass this for a logo that's actually visible immediately on load
  // (e.g. the main nav, an auth page's side panel). It forces Next.js to
  // <link rel="preload"> the image -- setting it on a below-the-fold usage
  // (e.g. the footer) wastes a render-blocking preload on an image the
  // browser won't paint for seconds, if ever, which is what triggered the
  // "preloaded but not used" console warning.
  priority?: boolean;
};

const FULL_ASPECT_RATIO = 1268 / 278;
const MARK_ASPECT_RATIO = 242 / 214;

export default function SpeakOETLogo({
  variant = "full",
  theme = "dark",
  height = 36,
  priority = false,
}: SpeakOETLogoProps) {
  if (variant === "mark") {
    return (
      <Image
        src="/logo-mark.png"
        alt="SpeakOET logo"
        width={Math.round(height * MARK_ASPECT_RATIO)}
        height={height}
        priority={priority}
      />
    );
  }

  const src = theme === "light" ? "/logo-full-light.png" : "/logo-full.png";

  return (
    <Image
      src={src}
      alt="SpeakOET logo"
      width={Math.round(height * FULL_ASPECT_RATIO)}
      height={height}
      priority={priority}
    />
  );
}
