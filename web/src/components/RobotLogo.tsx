export default function RobotLogo({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="#101418"
      strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 21h9" />
      <path d="M6 21v-3h5v3" />
      <path d="M8.5 18l-2-6.5" />
      <circle cx="6.5" cy="11" r="1.6" />
      <path d="M7.9 10.2l7.3-4" />
      <circle cx="16" cy="5.8" r="1.4" />
      <path d="M16.8 6.9l1.8 3.1" stroke="#1f5bd6" />
      <path d="M17 11.2l1.6-1.2 1.6 1.2" stroke="#1f5bd6" />
    </svg>
  )
}
