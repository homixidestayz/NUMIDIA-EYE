/* The legend's flame, drawn from the same path geometry as the map icon so
   the key and the marks cannot drift apart over time. */
export function FlameIcon({ color, size = 15 }: { color: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <path
        d="M32 62C16 50 10 38 13 29C15 20 22 15 25 10C27 7 30 5 32 2C34 9 41 13 45 21C51 32 52 42 47 50C43 56 37 60 32 62Z"
        fill={color}
      />
      <path d="M32 58C25 50 24 44 30 36C32 40 37 42 32 58Z" fill="#ffe0a3" opacity="0.75" />
    </svg>
  );
}