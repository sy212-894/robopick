import { useEffect, useMemo, useState } from 'react'
import PageHead from '../components/PageHead'
import { getRun, getRuns, postCheck, type RunEvent, type RunRow } from '../lib/api'
import { useApi } from '../lib/fmt'

// 실행 기록. events.jsonl을 대화(session_id)별로 묶은 표와, 고른 대화의 도구 호출 시간 막대·이벤트 목록

const BADGE = {
  ok: 'rounded bg-ok-soft px-2 py-0.5 text-xs text-ok-ink',
  no: 'rounded bg-line-soft px-2 py-0.5 text-xs text-body',
  wait: 'rounded bg-accent-soft px-2 py-0.5 text-xs text-accent-ink',
  none: 'text-xs text-muted',
}

const AP: Record<string, { label: string; cls: string }> = {
  approved: { label: '승인', cls: BADGE.ok },
  rejected: { label: '거부', cls: BADGE.no },
  waiting: { label: '대기', cls: BADGE.wait },
  none: { label: '없음', cls: BADGE.none },
}

const short = (sid: string) => sid.slice(0, 8)
const when = (ts: string) => `${ts.slice(5, 10)} ${ts.slice(11, 19)}`

// 이벤트 한 줄을 사람이 읽는 말로. 시작 이벤트는 끝 이벤트(걸린 시간 포함)와 겹쳐서 목록에서 뺀다
function describe(e: RunEvent): string | null {
  switch (e.event) {
    case 'tool_start':
      return null
    case 'tool_end':
      return e.detail ? `끝 · ${e.detail}` : '끝'
    case 'review':
      return `검수 ${e.detail}`
    case 'prepared':
      return `학습 계획 ${e.detail}`
    case 'agent_log':
      return e.detail ?? '에이전트 기록'
    default:
      return [e.event, e.detail].filter(Boolean).join(' · ')
  }
}

const isHuman = (e: RunEvent) => e.tool === 'log_event'
const barColor = (tool: string) => (tool === 'log_event' ? 'bg-ok' : tool.startsWith('train_evaluate') ? 'bg-[#39424e]' : 'bg-accent')

function Detail({ row }: { row: RunRow }) {
  const [events, setEvents] = useState<RunEvent[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'warn' | 'info'; text: string } | null>(null)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    let alive = true
    setEvents(null)
    setErr(null)
    setMsg(null)
    getRun(row.session_id)
      .then((d) => alive && setEvents(d.events))
      .catch((e) => alive && setErr(String(e.message ?? e)))
    return () => {
      alive = false
    }
  }, [row.session_id])

  const runCheck = async () => {
    setChecking(true)
    setMsg(null)
    try {
      const r = await postCheck(row.session_id)
      if (r.verdict === 'pass') setMsg({ kind: 'ok', text: `검사 통과 · 보고에 나온 숫자 ${r.numbers}개가 모두 실행 기록·결과 파일의 값과 일치합니다.` })
      else if (r.verdict === 'check')
        setMsg({ kind: 'warn', text: `확인 필요 · 숫자 ${r.numbers}개 중 기록에서 찾지 못한 값: ${r.unmatched?.join(', ')}` })
      else setMsg({ kind: 'info', text: r.detail ?? '검사할 실행 기록이 없습니다.' })
    } catch (e) {
      setMsg({ kind: 'info', text: String((e as Error).message ?? e) })
    } finally {
      setChecking(false)
    }
  }

  const ev = events ?? []
  const last = ev.length ? ev[ev.length - 1].t : 0
  const span = Math.max(Math.ceil(last) + 1, 4)
  const tools = ev.filter((e) => e.event === 'tool_end').length
  const human = ev.filter(isHuman).length
  const gantt = ev.filter((e) => e.event === 'tool_end' || isHuman(e))
  const listed = ev.map((e) => ({ e, what: describe(e) })).filter((x) => x.what !== null)
  const msgCls = msg?.kind === 'ok' ? 'bg-ok-soft text-ok-ink' : msg?.kind === 'warn' ? 'bg-warn-soft text-warn-ink' : 'bg-paper text-body'

  return (
    <section className="mt-8 rounded-[10px] border border-line p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="m-0 text-lg font-semibold">
          대화 <span className="font-mono text-[15px]">{short(row.session_id)}</span>의 기록
        </h2>
        <span className="text-[13px] text-sub">
          {row.dataset ?? '데이터 없음'} · {last.toFixed(1)}초 · 도구 호출 {tools}회 · 사람 판단 {human}회
        </span>
      </div>

      {err && <p className="mt-4 text-sm text-danger">기록을 불러오지 못했습니다: {err}</p>}
      {!events && !err && <p className="mt-4 text-sm text-sub">불러오는 중</p>}

      {events && (
        <>
          <div role="img" aria-label="도구 호출 시간 막대" className="mt-6 rounded-lg border border-line-soft bg-[#fafbfc] px-5 pt-5 pb-3">
            {gantt.map((e, i) => {
              const dur = e.duration_sec ?? 0
              const left = ((e.t - dur) / span) * 100
              const w = Math.max((dur / span) * 100, 0.8)
              return (
                <div key={i} className="flex h-7 items-center gap-3">
                  <span className="w-[168px] flex-none truncate font-mono text-xs text-body">
                    {isHuman(e) ? `사람 ${(e.detail ?? '').replace('학습 계획 ', '')}` : e.tool}
                  </span>
                  <div className="relative h-7 flex-1 bg-[linear-gradient(90deg,#eef0f3_1px,transparent_1px)] bg-size-[25%_100%]">
                    <div className={`absolute top-[7px] h-3.5 rounded-sm ${barColor(e.tool ?? '')}`} style={{ left: `${left}%`, width: `${w}%` }} />
                    {!isHuman(e) && (
                      <span className="absolute top-1.5 font-mono text-[11px] whitespace-nowrap text-sub" style={{ left: `calc(${left + w}% + 8px)` }}>
                        {dur.toFixed(2)}s
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
            <div className="mt-1.5 flex gap-3">
              <span className="w-[168px] flex-none" />
              <div className="flex flex-1 justify-between font-mono text-[11px] text-muted">
                {[0, 1, 2, 3, 4].map((i) => (
                  <span key={i}>{Math.round((span * i) / 4)}s</span>
                ))}
              </div>
            </div>
            <p className="mt-2.5 text-xs text-sub">도구 사이의 빈 구간은 에이전트(LLM)가 판단하는 시간입니다.</p>
          </div>

          <ol className="mt-5 flex list-none flex-col p-0">
            {listed.map(({ e, what }, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-4 border-t border-line-soft py-[9px]">
                <span className="w-16 font-mono text-xs text-muted">{e.ts.slice(11, 19)}</span>
                <span className="w-[220px] font-mono text-[13px]">{e.tool}</span>
                <span className="flex-1 text-[13px] text-body">{what}</span>
                <span className="font-mono text-xs text-sub">{e.duration_sec ? `${e.duration_sec.toFixed(2)}s` : ''}</span>
              </li>
            ))}
          </ol>
        </>
      )}

      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={runCheck}
          disabled={checking}
          className="h-10 cursor-pointer rounded-md border border-field bg-white px-4 text-sm text-ink disabled:cursor-wait disabled:text-muted"
        >
          {checking ? '검사 중' : '보고 수치 검사 실행'}
        </button>
        <a
          href={`/api/runs/${row.session_id}?download=1`}
          className="inline-flex h-10 items-center rounded-md border border-field bg-white px-4 text-sm text-ink hover:no-underline"
        >
          원본 JSON 내려받기
        </a>
      </div>
      {msg && (
        <div role="status" className={`mt-3.5 rounded-md px-3.5 py-3 text-[13px] ${msgCls}`}>
          {msg.text}
        </div>
      )}
    </section>
  )
}

export default function Runs() {
  const { data, error } = useApi(getRuns)
  const [ds, setDs] = useState('all')
  const [ap, setAp] = useState('all')
  const [sel, setSel] = useState<string | null>(null)

  const all = data?.runs ?? []
  const datasets = useMemo(() => [...new Set(all.map((r) => r.dataset).filter((d): d is string => !!d))].sort(), [all])
  const rows = all.filter((r) => (ds === 'all' || r.dataset === ds) && (ap === 'all' || (r.approval ?? 'none') === ap))
  // 처음에는 선별까지 간 가장 최근 대화를 보여준다
  const cur = all.find((r) => r.session_id === sel) ?? all.find((r) => r.selection_run) ?? all[0]

  const selectCls = 'h-10 rounded-md border border-field bg-white px-3 text-sm'
  return (
    <main className="pb-24">
      <PageHead title="실행 기록" desc="도구 호출과 사용자의 승인은 대화마다 실행 ID로 기록됩니다.">
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="f-data" className="text-[13px] text-sub">
            데이터
          </label>
          <select id="f-data" value={ds} onChange={(e) => setDs(e.target.value)} className={selectCls}>
            <option value="all">모두</option>
            {datasets.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <label htmlFor="f-ap" className="ml-2 text-[13px] text-sub">
            승인
          </label>
          <select id="f-ap" value={ap} onChange={(e) => setAp(e.target.value)} className={selectCls}>
            <option value="all">모두</option>
            {Object.entries(AP).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </select>
        </div>
      </PageHead>

      <div className="mx-auto max-w-[1200px] px-8">
        {error && <p className="mt-7 text-sm text-danger">실행 기록을 불러오지 못했습니다: {error}</p>}
        <div className="mt-7 overflow-x-auto rounded-[10px] border border-line">
          <table className="w-full min-w-[900px] border-collapse text-sm">
            <thead>
              <tr className="bg-[#f8f9fa] text-left text-xs text-sub">
                {['시작', '대화', '데이터', '예산', '검수', '승인', '선별 실행 ID', '기록'].map((h, i) => (
                  <th key={h} className={`px-4 py-3 font-medium ${i === 3 || i === 7 ? 'text-right' : ''}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {rows.map((r) => {
                const on = r.session_id === cur?.session_id
                const a = AP[r.approval ?? 'none']
                return (
                  <tr
                    key={r.session_id}
                    onClick={() => setSel(r.session_id)}
                    className={`cursor-pointer border-t border-line-soft ${on ? 'bg-[#f3f6fd]' : 'hover:bg-[#fafbfc]'}`}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-body">{when(r.start)}</td>
                    <td className="px-4 py-2">
                      <button
                        type="button"
                        onClick={() => setSel(r.session_id)}
                        aria-label={`대화 ${short(r.session_id)} 기록 보기`}
                        className={`h-8 cursor-pointer rounded-md border bg-white px-2.5 font-mono text-xs ${on ? 'border-accent text-accent' : 'border-[#d5dae0] text-ink'}`}
                      >
                        {short(r.session_id)}
                      </button>
                    </td>
                    <td className="px-4 py-3">{r.dataset ?? '-'}</td>
                    <td className="px-4 py-3 text-right">{r.budget ?? '-'}</td>
                    <td className="px-4 py-3">
                      <span className={r.review === 'pass' ? BADGE.ok : r.review ? BADGE.wait : BADGE.none}>{r.review ?? '-'}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={a.cls}>{a.label}</span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-body">{r.selection_run ?? '-'}</td>
                    <td className="px-4 py-3 text-right text-sub">{r.n_events}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {data && rows.length === 0 && <div className="p-7 text-center text-sm text-sub">조건에 맞는 대화가 없습니다.</div>}
          {!data && !error && <div className="p-7 text-center text-sm text-sub">불러오는 중</div>}
        </div>
        <p className="mt-2.5 text-xs text-sub">대화 ID를 누르면 아래에 그 대화의 기록이 나옵니다. 최근 50개 대화만 보여줍니다.</p>

        {cur && <Detail row={cur} />}
      </div>
    </main>
  )
}
