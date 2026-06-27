import React from "react";

type SpeakOETLogoProps = {
  variant?: "full" | "mark";
  theme?: "dark" | "light";
  height?: number;
};

export default function SpeakOETLogo({
  variant = "full",
  theme = "dark",
  height = 36,
}: SpeakOETLogoProps) {
  const navy = "#0F2356";
  const emerald = "#10B981";
  const white = "#FFFFFF";

  const primary = theme === "light" ? white : navy;
  const leftWave = theme === "light" ? "rgba(255,255,255,0.65)" : "rgba(15,35,86,0.6)";
  const speakColor = theme === "light" ? white : navy;

  const markWidth = 72;
  const fullWidth = 180;

  return (
    <svg
      width={variant === "mark" ? (height * markWidth) / 36 : (height * fullWidth) / 36}
      height={height}
      viewBox={variant === "mark" ? "0 0 72 36" : "0 0 180 36"}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="SpeakOET logo"
    >
      {/* LOGO MARK */}
      <g transform="translate(0,0)">
        {/* Left waveform */}
        <rect x="2" y="14" width="3" height="8" rx="1.5" fill={leftWave} />
        <rect x="8" y="10" width="3" height="16" rx="1.5" fill={leftWave} />
        <rect x="14" y="6" width="3" height="24" rx="1.5" fill={leftWave} />
        <rect x="20" y="10" width="3" height="16" rx="1.5" fill={leftWave} />

        {/* Right waveform */}
        <rect x="49" y="10" width="3" height="16" rx="1.5" fill={emerald} />
        <rect x="55" y="6" width="3" height="24" rx="1.5" fill={emerald} />
        <rect x="61" y="10" width="3" height="16" rx="1.5" fill={emerald} />
        <rect x="67" y="14" width="3" height="8" rx="1.5" fill={emerald} />

        {/* Stethoscope head */}
        <circle
          cx="36"
          cy="10"
          r="6"
          stroke={primary}
          strokeWidth="2.5"
        />
        <circle cx="36" cy="10" r="3.5" fill={primary} />

        {/* Stem */}
        <path
          d="M36 16V27"
          stroke={primary}
          strokeWidth="2.5"
          strokeLinecap="round"
        />

        {/* Tubes */}
        <path
          d="M36 27
             C36 32, 32 34, 29 34
             C26 34, 24 32, 24 29
             V24"
          stroke={primary}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        <path
          d="M36 27
             C36 32, 40 34, 43 34
             C46 34, 48 32, 48 29
             V24"
          stroke={primary}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>

      {/* WORDMARK */}
      {variant === "full" && (
        <g transform="translate(74,0)">
          <text
            x="0"
            y="25"
            fill={speakColor}
            fontSize="20"
            fontWeight="700"
            fontFamily="Inter, system-ui, sans-serif"
          >
            Speak
          </text>

          <text
            x="58"
            y="25"
            fill={emerald}
            fontSize="20"
            fontWeight="700"
            fontFamily="Inter, system-ui, sans-serif"
          >
            OET
          </text>
        </g>
      )}
    </svg>
  );
}
