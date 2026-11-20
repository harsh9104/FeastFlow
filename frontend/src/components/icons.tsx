// Small inline icons (no icon library needed). They inherit the text colour.
const base = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

export const IconSearch = () => (
  <svg {...base}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
);
export const IconPin = () => (
  <svg {...base}><path d="M12 21s-7-6.2-7-11a7 7 0 1 1 14 0c0 4.8-7 11-7 11Z" /><circle cx="12" cy="10" r="2.5" /></svg>
);
export const IconClock = () => (
  <svg {...base} width={15} height={15}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
);
export const IconBag = () => (
  <svg {...base}><path d="M6 7h12l1 13H5L6 7Z" /><path d="M9 7a3 3 0 0 1 6 0" /></svg>
);
export const IconReceipt = () => (
  <svg {...base}><path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Z" /><path d="M9 8h6M9 12h6" /></svg>
);
export const IconUser = () => (
  <svg {...base}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>
);
export const IconStar = ({ size = 12 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
    <path d="m12 2.8 2.8 5.9 6.4.8-4.7 4.4 1.2 6.4L12 17.2l-5.7 3.1 1.2-6.4L2.8 9.5l6.4-.8L12 2.8Z" />
  </svg>
);
export const IconCrown = () => (
  <svg {...base}><path d="m3 8 4.5 4L12 5l4.5 7L21 8l-2 11H5L3 8Z" /></svg>
);
export const IconPlus = () => (
  <svg {...base} width={16} height={16}><path d="M12 5v14M5 12h14" /></svg>
);
export const IconEdit = () => (
  <svg {...base} width={15} height={15}><path d="M4 20h4L19 9l-4-4L4 16v4Z" /></svg>
);
export const IconClose = () => (
  <svg {...base}><path d="M6 6l12 12M18 6 6 18" /></svg>
);
export const IconGrid = () => (
  <svg {...base}><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /></svg>
);
export const IconBike = () => (
  <svg {...base}><circle cx="6" cy="17" r="3" /><circle cx="18" cy="17" r="3" /><path d="M6 17h6l3-7h3M12 17 9 10H7" /></svg>
);
export const IconParty = () => (
  <svg {...base}><path d="m4 20 5-14 9 9-14 5Z" /><path d="M14 4v2M19 5l-1.5 1.5M20 10h-2" /></svg>
);
export const IconMenu = () => (
  <svg {...base}><path d="M5 4v16M5 4c3 0 4 2 4 5s-1 4-4 4M15 4v16M19 4v6a4 4 0 0 1-4 4" /></svg>
);
export const IconUsers = () => (
  <svg {...base}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a5 5 0 0 1 3.5 6" /></svg>
);
export const IconLogout = () => (
  <svg {...base}><path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10" /></svg>
);
