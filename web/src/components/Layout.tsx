import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import RobotLogo from './RobotLogo'
import { getHealth, type Health } from '../lib/api'

const NAV = [
  { to: '/', label: '소개', end: true },
  { to: '/select', label: '선별하기' },
  { to: '/datasets', label: '데이터셋' },
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
    <span title={title} className="hidden items-center md:flex gap-1.5 font-mono text-[13px] text-sub">
      <span className={`inline-block size-[7px] rounded-full ${ok ? 'bg-ok' : !h && !down ? 'bg-muted' : 'bg-danger'}`} />
      {label}
    </span>
  )
}

// 페이지를 옮기면 맨 위에서 시작한다 (같은 페이지 안의 #이동은 그대로 둔다)
function ScrollTop() {
  const { pathname } = useLocation()
  // 중괄호로 감싼다. scrollTo가 값을 돌려주는 환경에서는 React가 그 값을 정리 함수로 불러 화면이 깨진다
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])
  return null
}

export default function Layout() {
  return (
    <div className="min-h-screen">
      <ScrollTop />
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex min-h-20 max-w-[1200px] flex-wrap items-center justify-between gap-x-6 gap-y-3 px-8 py-3">
          <Link to="/" className="flex items-center gap-3 text-ink hover:no-underline">
            <RobotLogo size={30} />
            <span className="text-2xl font-bold tracking-tight">RoboPick</span>
            <span className="hidden text-sm text-sub sm:inline">시범 선별 에이전트</span>
          </Link>
          <nav aria-label="주 메뉴" className="order-last flex w-full gap-5 overflow-x-auto text-[15px] whitespace-nowrap lg:order-none lg:w-auto lg:gap-9 lg:text-[17px]">
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
              to="/select"
              className="inline-flex h-11 items-center rounded-md bg-ink px-5 text-[15px] whitespace-nowrap font-medium text-white hover:no-underline"
            >
              선별 시작
            </Link>
          </div>
        </div>
      </header>
      <Outlet />
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1200px] flex-wrap justify-between gap-4 p-8 text-[13px] text-sub">
          <span>RoboPick · 로봇 시범 선별 에이전트</span>
          <span className="font-mono text-xs">Dify 1.17 · robomimic 0.5 · robosuite 1.5.1</span>
        </div>
      </footer>
    </div>
  )
}
