import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import RobotLogo from './RobotLogo'
import { getHealth, type Health } from '../lib/api'

const NAV = [
  { to: '/', label: '소개', end: true },
  { to: '/demo', label: '데모' },
  { to: '/results', label: '실험 결과' },
  { to: '/runs', label: '실행 기록' },
]

// 상단 연결 상태: 중계 서버가 Dify와 도구 서버에 실제로 닿는지 30초마다 확인한다
function ConnectionStatus() {
  const [h, setH] = useState<Health | null>(null)
  const [down, setDown] = useState(false)
  useEffect(() => {
    let alive = true
    const check = () =>
      getHealth()
        .then((x) => alive && (setH(x), setDown(false)))
        .catch(() => alive && setDown(true))
    check()
    const id = setInterval(check, 30000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])
  const ok = !down && h?.dify.ok && h?.tools.ok
  const label = down ? '중계 서버 꺼짐' : !h ? '확인 중' : ok ? 'Dify · 도구 서버 연결됨' : !h.dify.ok ? 'Dify 연결 안 됨' : '도구 서버 꺼짐'
  const title = h ? `Dify: ${h.dify.detail} / 도구 서버: ${h.tools.detail}` : undefined
  return (
    <span title={title} className="flex items-center gap-1.5 font-mono text-xs text-sub">
      <span className={`inline-block size-[7px] rounded-full ${ok ? 'bg-ok' : !h && !down ? 'bg-muted' : 'bg-danger'}`} />
      {label}
    </span>
  )
}

export default function Layout() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex h-16 max-w-[1200px] flex-wrap items-center justify-between gap-6 px-8">
          <Link to="/" className="flex items-center gap-2.5 text-ink hover:no-underline">
            <RobotLogo />
            <span className="text-base font-semibold tracking-tight">시범 선별 에이전트</span>
          </Link>
          <nav aria-label="주 메뉴" className="flex flex-wrap gap-7 text-[15px]">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) => (isActive ? 'font-medium text-ink' : 'text-[#475060]') + ' hover:no-underline'}
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-4">
            <ConnectionStatus />
            <Link
              to="/demo"
              className="inline-flex h-10 items-center rounded-md bg-ink px-4 text-sm font-medium text-white hover:no-underline"
            >
              데모 실행
            </Link>
          </div>
        </div>
      </header>
      <Outlet />
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1200px] flex-wrap justify-end gap-4 p-8 text-[13px] text-sub">
          <span className="font-mono text-xs">Dify 1.17 · robomimic 0.5 · robosuite 1.5.1</span>
        </div>
      </footer>
    </div>
  )
}
