import Image from "next/image";

type SpeakOETLogoProps = {
  variant?: "full" | "mark";
  theme?: "dark" | "light";
  height?: number;
};

const FULL_ASPECT_RATIO = 1268 / 278;
const MARK_ASPECT_RATIO = 242 / 214;

export default function SpeakOETLogo({
  variant = "full",
  theme = "dark",
  height = 36,
}: SpeakOETLogoProps) {
  if (variant === "mark") {
    return (
      <Image
        src="/logo-mark.png"
        alt="SpeakOET logo"
        width={Math.round(height * MARK_ASPECT_RATIO)}
        height={height}
        priority
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
      priority
    />
  );
}
