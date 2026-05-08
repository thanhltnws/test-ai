import logoUrl from '../assets/logo-nws.png'

export default function Logo({ size = 32 }: { size?: number }) {
  return (
    <img src={logoUrl} width={size} height={size} alt="AI Insight Hub" style={{ objectFit: 'contain' }} />
  )
}
