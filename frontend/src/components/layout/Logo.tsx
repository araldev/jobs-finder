"use client";

interface LogoProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const sizes = {
  sm: { container: 24, icon: 16 },
  md: { container: 32, icon: 20 },
  lg: { container: 40, icon: 28 },
};

export function Logo({ size = "md", className = "" }: LogoProps) {
  const { container, icon } = sizes[size];

  return (
    <svg
      width={container}
      height={container}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <rect width="32" height="32" rx="6" fill="#0F172A" />
      <circle cx="16" cy="16" r="13" stroke="#0D9488" strokeWidth="1.5" />
      <path d="M16 5L18 13H14L16 5Z" fill="#0D9488" />
      <path d="M16 27L14 19H18L16 27Z" fill="#F97316" />
      <path d="M27 16L19 18V14L27 16Z" fill="#0D9488" />
      <path d="M5 16L13 14V18L5 16Z" fill="#F97316" />
      <rect
        x="13.5"
        y="13.5"
        width="5"
        height="5"
        rx="1"
        transform="rotate(45 16 16)"
        fill="#14B8A6"
      />
    </svg>
  );
}
