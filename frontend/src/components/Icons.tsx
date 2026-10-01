/** Line icons drawn at 24 px on a 24 unit grid; they take the text color. */
type IconProps = { className?: string };

function Icon({
  className = "size-5",
  children,
}: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export const FlameIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 22c4 0 7-2.7 7-7 0-3.5-2.2-6-4-8 .2 2-1 3.5-2.4 3.5C11 10.5 11.5 6 9 3 8.6 7.2 5 9.8 5 15c0 4.3 3 7 7 7Z" />
  </Icon>
);

export const SprayIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 14c0 2.8 2.2 5 5 5s5-2.2 5-5c0-3.2-5-9-5-9s-5 5.8-5 9Z" />
    <path d="M3 9h2M19 9h2M4.5 4.5 6 6M19.5 4.5 18 6" />
  </Icon>
);

export const BoltIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" />
  </Icon>
);

export const HistoryIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
    <path d="M3 3v5h5M12 7v5l3 2" />
  </Icon>
);

export const ForecastIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 20h18" />
    <path d="M6 16l4-5 3 3 5-7" />
    <path d="M15 7h3v3" />
  </Icon>
);

export const LayersIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m12 3 9 5-9 5-9-5 9-5Z" />
    <path d="m3 13 9 5 9-5" />
  </Icon>
);

export const LocateIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
  </Icon>
);

export const PlusIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);

export const CloseIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Icon>
);

export const SatelliteIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m13 7 4 4-6 6-4-4 6-6Z" />
    <path d="m5 11 3 3M16 4l4 4M9 17c-1.5 1.5-3.5 1.5-5 0M11 19c-2.7 2.7-6.3 2.7-9 0" />
  </Icon>
);

export const SearchIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Icon>
);

export const CheckIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m5 12 5 5 9-10" />
  </Icon>
);

export const PencilPlusIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 20l1-4.5L15 5.5l3.5 3.5-10 10L4 20Z" />
    <path d="M18 14v6M15 17h6" />
  </Icon>
);

export const PencilMinusIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 20l1-4.5L15 5.5l3.5 3.5-10 10L4 20Z" />
    <path d="M15 17h6" />
  </Icon>
);
