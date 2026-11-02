/** Compass logo. `light` is for dark backgrounds. */
export function BrandMark({
  light = false,
  size = 28,
}: {
  light?: boolean;
  size?: number;
}) {
  const ring = light ? '#FFFFFF' : 'var(--ink)';
  const needle = light ? '#F08A4B' : '#E0661F';
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="16" cy="16" r="14" stroke={ring} strokeWidth="2" />
      <path d="M16 6l4 10-4 10-4-10z" fill={needle} />
    </svg>
  );
}
