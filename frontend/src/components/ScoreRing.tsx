interface ScoreRingProps {
  score: number | null | undefined;
  size?: number;
  strokeWidth?: number;
  label?: string;
}

export function ScoreRing({ score, size = 52, strokeWidth = 4.5, label = "FIT" }: ScoreRingProps) {
  const value = typeof score === "number" ? Math.max(0, Math.min(100, score)) : 0;
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (value / 100) * circumference;
  const color =
    value >= 80 ? "#16a34a" : value >= 60 ? "#5b5bd6" : value >= 40 ? "#ea580c" : "#dc2626";
  const trackColor =
    value >= 80
      ? "rgba(22,163,74,0.12)"
      : value >= 60
        ? "rgba(91,91,214,0.12)"
        : "rgba(234,88,12,0.12)";

  return (
    <div className="relative flex shrink-0 items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={trackColor}
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-mono font-semibold leading-none" style={{ fontSize: size * 0.22, color }}>
          {typeof score === "number" ? score : "--"}
        </span>
        {label && (
          <span className="mt-0.5 font-mono text-[9px] uppercase tracking-wide text-[#71717a]">
            {label}
          </span>
        )}
      </div>
    </div>
  );
}
