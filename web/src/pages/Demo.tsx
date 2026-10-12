import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Markdown from '../components/Markdown'
import { getDoc, type Collect } from '../lib/api'
import { pct, num, SET_NAMES } from '../lib/fmt'
import { streamSSE, type DifyEvent } from '../lib/sse'

// 데모: 요청 → Dify 실행(실시간) → 승인 카드 → 승인/거부 → 보고.
// 화면의 숫자는 모두 Dify 이벤트(노드 출력)와 도구 결과에서 온다

type Phase = 'idle' | 'running' | 'pending' | 'resuming' | 'done' | 'rejected' | 'error'

type NodeRow = { id: string; type: string; title: string; done: boolean; elapsed?: number }
type Call = { id: string; name: string; at: Date; elapsed?: number }
type Evidence = {
  file: string
  title: string
  source_url: string | null
  doc_type: string | null
  retrieved: string | null
  score: number | null
  section: string
  chunk: string
}
type Review = {
  run_id: string
  dataset: string
  budget: number
  verdict: string
  issues: string[]
  warnings: string[]
  sets: Record<string, { n_demos: number; total_frames: number }>
  train_set: { n_demos: number; total_frames: number }
  training_plan: { n_sets: number; algo: string; num_epochs: number; est_minutes: number }
}
type Form = { token: string; runId: string; content: string }

const PRESETS = [
  { label: 'Can 150개', q: 'can 데이터로 학습할 시범 150개 골라줘' },
  { label: 'Can 135개 (50%)', q: 'can 데이터로 학습할 시범 135개 골라줘' },
  { label: 'Square 150개', q: 'square 데이터로 학습할 시범 150개 골라줘' },
  { label: '조건별 분포만 보기', q: 'can 데이터를 위치 조건별로 분석만 해줘' },
  { label: '필터 키는 어떻게 써?', q: 'robomimic 필터 키는 어떻게 써?' },
]

// 화면에 단계로 보여줄 노드. 나머지(분기, 정리용 코드 노드)는 숨긴다
const STEP: Record<string, string> = {
  translate: '질문 해석',
  retrieval: '근거 검색',
  agent: '에이전트 판단',
  review: '검수',
  approval: '승인',
  log_ok: '승인 기록',
  prep: '학습 계획',
  coll: '결과 불러오기',
  report: '보고 작성',
}
const MAIN = Object.keys(STEP)
const VISIBLE = new Set(['llm', 'knowledge-retrieval', 'agent', 'tool', 'human-input'])
const TOOL_OF: Record<string, string> = { llm: 'LLM', 'knowledge-retrieval': '지식베이스', 'human-input': '사람' }

// 도구 노드 제목의 괄호 안이 도구 이름이다. 승인 기록 노드만 제목에 이름이 없다
const toolName = (title: string, id?: string) => (id === 'log_ok' ? 'log_event' : /\(([^)]+)\)/.exec(title)?.[1].replace(' ', '.') ?? title)
const clock = (d: Date) => d.toTimeString().slice(0, 8)
const sec = (x?: number) => (x == null ? '' : `${x.toFixed(1)}초`)

const DOT = {
  ok: 'size-2.5 flex-none rounded-full bg-ok shadow-[0_0_0_3px_#fff]',
  wait: 'size-2.5 flex-none rounded-full border-2 border-accent bg-white shadow-[0_0_0_3px_#e8effd]',
  off: 'size-2.5 flex-none rounded-full border border-[#b5bdc7] bg-white shadow-[0_0_0_3px_#fff]',
  stop: 'size-2.5 flex-none rounded-[2px] bg-muted shadow-[0_0_0_3px_#fff]',
}

const card = 'rounded-[10px] border border-line bg-white'
const btnLine = 'h-10 cursor-pointer rounded-md border border-field bg-white px-4 text-sm text-ink'

export default function Demo() {
  const [query, setQuery] = useState(PRESETS[0].q)
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState<string | null>(null)
  const [nodes, setNodes] = useState<NodeRow[]>([])
  const [calls, setCalls] = useState<Call[]>([])
  const [model, setModel] = useState<string | null>(null)
  const [agentText, setAgentText] = useState('')
  const [docs, setDocs] = useState<Evidence[]>([])
  const [review, setReview] = useState<Review | null>(null)
  const [form, setForm] = useState<Form | null>(null)
  const [action, setAction] = useState<'approve' | 'reject' | null>(null)
  const [convId, setConvId] = useState('')
  const [answer, setAnswer] = useState('')
  const [collect, setCollect] = useState<Collect | null>(null)
  const [cost, setCost] = useState<number | null>(null)
  // 경과 시간: 실행 중인 구간만 더한다 (승인을 기다리는 시간은 빼고)
  const [activeMs, setActiveMs] = useState(0)
  const segStart = useRef<number | null>(null)
  const [, tick] = useState(0)
  const abort = useRef<AbortController | null>(null)

  const busy = phase === 'running' || phase === 'resuming'
  useEffect(() => {
    if (!busy) return
    const id = setInterval(() => tick((x) => x + 1), 200)
    return () => clearInterval(id)
  }, [busy])
  useEffect(() => () => abort.current?.abort(), [])

  const elapsed = (activeMs + (segStart.current != null ? Date.now() - segStart.current : 0)) / 1000
  const startSeg = () => (segStart.current = Date.now())
  const endSeg = () => {
    // 값을 먼저 꺼내 둔다. 상태 갱신 함수는 나중에 실행되므로 그 안에서 ref를 읽으면 이미 null이다
    const s = segStart.current
    segStart.current = null
    if (s != null) setActiveMs((m) => m + Date.now() - s)
  }

  function onEvent(e: DifyEvent) {
    const d = (e.data ?? {}) as Record<string, any>
    if (typeof e.conversation_id === 'string' && e.conversation_id) setConvId(e.conversation_id)
    switch (e.event) {
      case 'node_started':
      case 'node_finished': {
        if (!VISIBLE.has(d.node_type)) break
        const done = e.event === 'node_finished'
        setNodes((ns) => {
          const row: NodeRow = { id: d.node_id, type: d.node_type, title: d.title, done, elapsed: done ? d.elapsed_time : undefined }
          const k = ns.findIndex((n) => n.id === d.node_id)
          if (k < 0) return [...ns, row]
          // 승인 뒤 다시 받는 지난 상태(snapshot)에는 시작 이벤트가 또 온다. 끝난 기록은 덮지 않는다
          if (!done && ns[k].done) return ns
          const copy = ns.slice()
          copy[k] = { ...row, elapsed: d.node_type === 'human-input' ? undefined : row.elapsed }
          return copy
        })
        if (done && d.node_type === 'tool') {
          const out = d.outputs?.json?.[0]
          if (d.node_id === 'review' && out?.run_id) setReview(out as Review)
          if (d.node_id === 'coll' && out) setCollect(out as Collect)
          setCalls((cs) => (cs.some((c) => c.id === d.node_id) ? cs : [...cs, { id: d.node_id, name: toolName(d.title, d.node_id), at: new Date(), elapsed: d.elapsed_time }]))
        }
        break
      }
      case 'agent_log': {
        const label: string = d.label ?? ''
        if (label.startsWith('CALL ')) {
          setCalls((cs) => {
            const k = cs.findIndex((c) => c.id === d.id)
            if (k < 0) return [...cs, { id: d.id, name: label.slice(5), at: new Date() }]
            if (d.status === 'start') return cs
            const copy = cs.slice()
            copy[k] = { ...copy[k], elapsed: d.metadata?.elapsed_time }
            return copy
          })
        } else if (label.endsWith(' Thought')) {
          setModel(label.replace(' Thought', '').split('/').pop() ?? null)
          const o = d.data?.output
          if (d.status === 'success' && typeof o === 'string' && o.trim()) setAgentText(o)
        }
        break
      }
      case 'evidence':
        setDocs(e.docs as Evidence[])
        break
      case 'human_input_required':
        setForm({ token: d.form_token, runId: String(e.workflow_run_id ?? ''), content: d.form_content })
        break
      case 'workflow_paused':
        setForm((f) => (f ? { ...f, runId: d.workflow_run_id ?? f.runId } : f))
        break
      case 'message':
        setAnswer((a) => a + String(e.answer ?? ''))
        break
      case 'message_replace':
        setAnswer(String(e.answer ?? ''))
        break
      case 'message_end': {
        const u = (e.metadata as any)?.usage
        if (u?.total_price) setCost(Number(u.total_price))
        break
      }
      case 'final_message':
        if (typeof e.answer === 'string') setAnswer(e.answer)
        break
      case 'error':
        setError(String(e.message ?? '실행 중 오류'))
        break
    }
  }

  function reset() {
    abort.current?.abort()
    setPhase('idle')
    setError(null)
    setNodes([])
    setCalls([])
    setModel(null)
    setAgentText('')
    setDocs([])
    setReview(null)
    setForm(null)
    setAction(null)
    setConvId('')
    setAnswer('')
    setCollect(null)
    setCost(null)
    setActiveMs(0)
    segStart.current = null
  }

  async function send(q = query) {
    if (!q.trim() || busy) return
    reset()
    setQuery(q)
    setPhase('running')
    startSeg()
    const ac = new AbortController()
    abort.current = ac
    let paused = false
    try {
      await streamSSE('/api/chat', { query: q }, (e) => {
        if (e.event === 'workflow_paused') paused = true
        onEvent(e)
      }, ac.signal)
      setPhase(paused ? 'pending' : 'done')
    } catch (err) {
      if (ac.signal.aborted) return
      setError((err as Error).message)
      setPhase('error')
    } finally {
      endSeg()
    }
  }

  async function decide(act: 'approve' | 'reject') {
    if (!form) return
    setAction(act)
    setPhase('resuming')
    startSeg()
    const ac = new AbortController()
    abort.current = ac
    try {
      await streamSSE('/api/approve', { form_token: form.token, action: act, workflow_run_id: form.runId, conversation_id: convId }, onEvent, ac.signal)
      setPhase(act === 'approve' ? 'done' : 'rejected')
    } catch (err) {
      if (ac.signal.aborted) return
      setError((err as Error).message)
      setPhase('error')
    } finally {
      endSeg()
    }
  }

  // 진행 단계: 받은 노드 + 아직 오지 않은 주요 단계(회색)
  const seen = new Set(nodes.map((n) => n.id))
  const lastMain = Math.max(-1, ...nodes.map((n) => MAIN.indexOf(n.id)))
  const upcoming = busy || phase === 'pending' ? MAIN.slice(lastMain + 1).filter((id) => !seen.has(id)) : []
  const agentCalls = calls.filter((c) => !nodes.some((n) => n.id === c.id))

  const status: Record<Phase, [string, string]> = {
    idle: ['요청 전', 'text-sub'],
    running: ['실행 중', 'text-accent'],
    pending: ['승인 대기', 'text-accent'],
    resuming: [action === 'reject' ? '거부 처리 중' : '학습 계획·결과 조회 중', 'text-accent'],
    done: ['완료', 'text-ok'],
    rejected: ['거부됨', 'text-sub'],
    error: ['오류', 'text-danger'],
  }

  return (
    <main className="bg-paper">
      <div className="mx-auto max-w-[1280px] px-8 pt-8 pb-16">
        <div className="dot-grid mb-6 rounded-[10px] border border-line bg-white px-7 pt-7 pb-6">
          <h1 className="m-0 text-[28px] font-semibold tracking-tight">데모</h1>
          <p className="mt-1.5 text-[15px] text-[#475060]">
            요청을 보내면 에이전트가 분석하고 선별한 뒤, 학습 계획을 승인받습니다. 학습은 미리 실행한 결과를 불러옵니다.
          </p>
        </div>

        <div className="flex flex-wrap items-start gap-6">
          <div className="flex min-w-0 flex-[999_1_640px] flex-col gap-4">
            <section className={`${card} p-5`}>
              <label htmlFor="req" className="mb-2 block text-[13px] text-[#475060]">
                요청
              </label>
              <form
                className="flex flex-wrap gap-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  send()
                }}
              >
                <input
                  id="req"
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  disabled={busy}
                  className="h-[46px] min-w-0 flex-[1_1_320px] rounded-md border border-field bg-white px-3.5 text-[15px] text-ink disabled:bg-paper"
                />
                <button
                  type="submit"
                  disabled={busy || !query.trim()}
                  className="h-[46px] cursor-pointer rounded-md bg-ink px-5 text-[15px] font-medium text-white disabled:cursor-wait disabled:opacity-60"
                >
                  {busy ? '실행 중' : '보내기'}
                </button>
              </form>
              <div className="mt-3 flex flex-wrap gap-2">
                {PRESETS.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    disabled={busy}
                    onClick={() => send(p.q)}
                    className="h-8 cursor-pointer rounded-2xl border border-[#d5dae0] bg-white px-3 text-[13px] text-body disabled:cursor-wait disabled:opacity-60"
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </section>

            {error && (
              <section role="alert" className="rounded-[10px] border border-[#e8b4ad] bg-white p-5 text-sm text-danger">
                {error}
                <button type="button" onClick={reset} className={`${btnLine} ml-3`}>
                  처음으로
                </button>
              </section>
            )}

            {phase !== 'idle' && (
              <section className={`${card} p-5`}>
                <div className="mb-3.5 flex items-baseline justify-between">
                  <h2 className="m-0 text-[15px] font-semibold">진행</h2>
                  <span className="font-mono text-xs text-sub">
                    {busy ? `${elapsed.toFixed(1)}초 경과` : `총 ${elapsed.toFixed(1)}초${form ? ' (승인 대기 제외)' : ''}`}
                  </span>
                </div>
                <ol className="relative m-0 flex list-none flex-col p-0">
                  <div className="absolute top-5 bottom-5 left-1 w-0.5 bg-line" />
                  {nodes.map((n) => {
                    const human = n.type === 'human-input'
                    const waiting = human && !n.done
                    const name = human ? (waiting ? '승인 대기' : action === 'reject' ? '승인 거부' : '승인') : STEP[n.id] ?? n.title
                    const dot = waiting || !n.done ? DOT.wait : human && action === 'reject' ? DOT.stop : DOT.ok
                    const tool = TOOL_OF[n.type] ?? (n.type === 'agent' ? `${model ?? 'LLM'} · 도구 ${agentCalls.length}회` : toolName(n.title, n.id))
                    return (
                      <li key={n.id}>
                        <div className="relative flex items-center gap-3.5 py-2.5">
                          <span className={dot} />
                          <span className={`flex-1 text-sm ${!n.done ? 'text-accent' : 'text-ink'}`}>{name}</span>
                          <span className="font-mono text-xs text-sub">{tool}</span>
                          <span className="w-16 text-right font-mono text-xs text-body">{waiting ? '대기 중' : n.done ? sec(n.elapsed) : '진행 중'}</span>
                        </div>
                        {n.type === 'agent' && agentCalls.length > 0 && (
                          <ul className="m-0 mb-1 ml-6 flex list-none flex-col gap-1 p-0">
                            {agentCalls.map((c) => (
                              <li key={c.id} className="flex items-center gap-3 font-mono text-xs text-body">
                                <span className="text-muted">└</span>
                                <span className="flex-1">{c.name}</span>
                                <span className="w-16 text-right">{c.elapsed != null ? sec(c.elapsed) : '진행 중'}</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </li>
                    )
                  })}
                  {upcoming.map((id) => (
                    <li key={id} className="relative flex items-center gap-3.5 py-2.5">
                      <span className={DOT.off} />
                      <span className="flex-1 text-sm text-muted">{STEP[id]}</span>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {agentText && phase !== 'done' && phase !== 'rejected' && (
              <section className={`${card} p-6`}>
                <h2 className="m-0 mb-2 text-[15px] font-semibold">에이전트 답변</h2>
                <Markdown text={agentText} />
              </section>
            )}

            {form && (phase === 'pending' || phase === 'resuming') && (
              <Approval review={review} form={form} busy={phase === 'resuming'} action={action} onDecide={decide} />
            )}

            {phase === 'rejected' && (
              <section className={`${card} p-6`}>
                <h2 className="m-0 text-lg font-semibold">학습하지 않음</h2>
                <p className="mt-2 text-sm text-[#475060]">학습 계획이 거부되어 학습을 진행하지 않습니다. 예산이나 데이터를 바꿔 다시 요청할 수 있습니다.</p>
                {answer && (
                  <div className="mt-4 border-t border-line-soft pt-4">
                    <Markdown text={answer} />
                  </div>
                )}
                <button type="button" onClick={reset} className={`${btnLine} mt-4`}>
                  새 요청
                </button>
              </section>
            )}

            {phase === 'done' && <Report answer={answer} collect={collect} approved={action === 'approve'} onReset={reset} />}
          </div>

          <aside className="flex min-w-0 flex-[1_1_300px] flex-col gap-4">
            <section className={`${card} p-5`}>
              <h2 className="m-0 mb-3.5 text-[15px] font-semibold">실행 정보</h2>
              <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2.5 text-[13px]">
                <dt className="text-sub">상태</dt>
                <dd className={`m-0 font-medium ${status[phase][1]}`}>{status[phase][0]}</dd>
                <dt className="text-sub">실행 ID</dt>
                <dd className="m-0 font-mono text-xs [overflow-wrap:anywhere]">{review?.run_id ?? '-'}</dd>
                <dt className="text-sub">대화 ID</dt>
                <dd className="m-0 font-mono text-xs">{convId ? convId.slice(0, 8) : '-'}</dd>
                <dt className="text-sub">데이터</dt>
                <dd className="m-0">{review ? `${review.dataset} · 학습 후보 ${review.train_set.n_demos}개` : '-'}</dd>
                <dt className="text-sub">모델</dt>
                <dd className="m-0">{model ?? '-'}</dd>
                <dt className="text-sub">응답 시간</dt>
                <dd className="m-0 font-mono text-xs">{phase === 'idle' ? '-' : `${elapsed.toFixed(1)}s`}</dd>
                <dt className="text-sub">비용</dt>
                <dd className="m-0 font-mono text-xs">{cost != null ? `$${cost.toFixed(4)}` : busy || phase === 'pending' ? '집계 중' : '-'}</dd>
              </dl>
            </section>

            <section className={`${card} p-5`}>
              <h2 className="m-0 mb-3 text-[15px] font-semibold">도구 호출 기록</h2>
              {calls.length === 0 ? (
                <p className="m-0 text-xs text-sub">아직 호출이 없습니다.</p>
              ) : (
                <ol className="m-0 flex list-none flex-col gap-2 p-0 font-mono text-xs">
                  {calls.map((c) => (
                    <li key={c.id} className="flex gap-2.5">
                      <span className="text-muted">{clock(c.at)}</span>
                      <span className="flex-1 text-[#22282f]">{c.name}</span>
                      <span className="text-sub">{c.elapsed != null ? `${c.elapsed.toFixed(2)}s` : ''}</span>
                    </li>
                  ))}
                </ol>
              )}
              <Link to={convId ? `/runs?sid=${convId}` : '/runs'} className="mt-3.5 inline-block text-[13px]">
                {convId ? '이 대화의 전체 기록 보기' : '전체 기록 보기'}
              </Link>
            </section>

            <EvidencePanel docs={docs} />
          </aside>
        </div>
      </div>
    </main>
  )
}

// ---------- 승인 카드: 검수 도구가 낸 묶음 구성과 학습 계획 ----------

function Approval({ review, form, busy, action, onDecide }: {
  review: Review | null
  form: Form
  busy: boolean
  action: 'approve' | 'reject' | null
  onDecide: (a: 'approve' | 'reject') => void
}) {
  const tp = review?.training_plan
  const rows = review ? [...Object.entries(review.sets), ['train', review.train_set] as const] : []
  const notes = review ? [...review.issues, ...review.warnings] : []
  return (
    <section aria-label="학습 승인 요청" className="overflow-hidden rounded-[10px] border border-[#9fb8ec] bg-white px-6 pb-6">
      <div className="-mx-6 mb-5 flex items-center gap-2.5 bg-accent px-6 py-3 text-[13px] text-white">
        <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="#fff" strokeWidth="2">
          <path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z" />
        </svg>
        <span>사용자 확인 단계 · 승인 전에는 GPU를 쓰지 않습니다</span>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="m-0 text-lg font-semibold">학습 승인 요청</h2>
        <span className="rounded-xl bg-accent-soft px-2.5 py-1 text-xs text-accent-ink">사용자 확인 필요</span>
      </div>
      {review ? (
        <>
          <p className="mt-2 text-sm text-[#475060]">
            선별 결과 <span className="font-mono text-[13px]">{review.run_id}</span> · 데이터 {review.dataset} · 예산 {review.budget}개
          </p>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[460px] border-collapse text-sm tabular-nums">
              <thead>
                <tr className="text-left text-xs text-sub">
                  <th className="border-b border-line py-2 font-medium">묶음</th>
                  <th className="border-b border-line py-2 font-medium">설명</th>
                  <th className="border-b border-line py-2 text-right font-medium">시범</th>
                  <th className="border-b border-line py-2 text-right font-medium">프레임</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([k, v], i) => (
                  <tr key={k}>
                    <td className={`py-2.5 ${i < rows.length - 1 ? 'border-b border-line-soft' : ''} ${k.startsWith('curated') ? 'font-medium text-accent' : ''}`}>{k}</td>
                    <td className={`py-2.5 text-body ${i < rows.length - 1 ? 'border-b border-line-soft' : ''}`}>{SET_NAMES[k]?.sub ?? (k === 'train' ? '전체' : '')}</td>
                    <td className={`py-2.5 text-right ${i < rows.length - 1 ? 'border-b border-line-soft' : ''}`}>{v.n_demos}</td>
                    <td className={`py-2.5 text-right ${i < rows.length - 1 ? 'border-b border-line-soft' : ''}`}>{num(v.total_frames)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">
            <div className="rounded-md bg-paper px-3.5 py-3">
              <div className="text-xs text-sub">검수</div>
              <div className={`mt-1 text-[15px] font-semibold ${review.verdict === 'pass' ? 'text-ok' : 'text-warn-ink'}`}>
                {review.verdict === 'pass' ? '통과' : review.verdict} · {notes.length ? `알림 ${notes.length}건` : '경고 없음'}
              </div>
            </div>
            {tp && (
              <>
                <div className="rounded-md bg-paper px-3.5 py-3">
                  <div className="text-xs text-sub">학습 계획</div>
                  <div className="mt-1 text-[15px] font-semibold">
                    {tp.algo.toUpperCase().replace('_', '-')} {tp.num_epochs} epoch × {tp.n_sets}묶음
                  </div>
                </div>
                <div className="rounded-md bg-paper px-3.5 py-3">
                  <div className="text-xs text-sub">예상 시간</div>
                  <div className="mt-1 text-[15px] font-semibold">약 {tp.est_minutes}분 (T4 GPU)</div>
                </div>
              </>
            )}
          </div>
          {notes.length > 0 && (
            <ul className="mt-3 mb-0 flex list-disc flex-col gap-1 pl-5 text-[13px] text-warn-ink">
              {notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className="mt-3">
          <Markdown text={form.content} />
        </div>
      )}
      <p className="mt-4 text-[13px] text-sub">
        승인하면 학습 계획이 만들어지고 GPU가 사용됩니다. 같은 계획으로 미리 실행한 결과가 있으면 그 결과를 불러옵니다.
      </p>
      <div className="mt-5 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => onDecide('approve')}
          className="h-11 cursor-pointer rounded-md bg-accent px-[22px] text-[15px] font-semibold text-white disabled:cursor-wait disabled:opacity-60"
        >
          {busy && action === 'approve' ? '처리 중' : '승인하고 학습 계획 만들기'}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onDecide('reject')}
          className="h-11 cursor-pointer rounded-md border border-field bg-white px-[18px] text-[15px] text-ink disabled:cursor-wait disabled:opacity-60"
        >
          {busy && action === 'reject' ? '처리 중' : '거부'}
        </button>
      </div>
    </section>
  )
}

// ---------- 보고: 최종 답변 + 결과 조회 도구의 성공률 막대 (판정은 답변 안의 표에 있다) ----------

function Report({ answer, collect, approved, onReset }: { answer: string; collect: Collect | null; approved: boolean; onReset: () => void }) {
  const table = collect?.table?.filter((r) => r.success_rate != null) ?? []
  const max = Math.max(0.01, ...table.map((r) => r.success_rate ?? 0))
  return (
    <section className={`${card} p-6`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="m-0 text-lg font-semibold">보고</h2>
        {approved && collect?.fingerprint && (
          <span className="rounded-xl bg-ok-soft px-2.5 py-1 text-xs text-ok-ink">승인됨 · 계획 {collect.fingerprint}</span>
        )}
      </div>
      <div className="mt-3">{answer ? <Markdown text={answer} /> : <p className="text-sm text-sub">답변이 비어 있습니다.</p>}</div>

      {collect && collect.status === 'not_trained' && (
        <div className="mt-6 rounded-md bg-warn-soft px-4 py-3 text-[13px] text-warn-ink">
          이 계획(지문 {collect.fingerprint})은 아직 학습 결과가 없습니다. 학습 노트북을 실행하면 같은 지문의 결과를 불러옵니다.
        </div>
      )}

      {table.length > 0 && (
        <>
          <div className="mt-6 text-[13px] text-sub">
            결과 조회 도구가 돌려준 최종 성공률{collect?.status === 'partial' ? ' · 일부 묶음만 끝남' : ''} · 시드별 시험을 합친 값
          </div>
          <div className="mt-3 flex flex-col gap-2.5">
            {table.map((r) => (
              <div key={r.set} className="flex items-center gap-3">
                <span className={`w-36 text-sm ${r.set.startsWith('curated') ? 'font-medium' : ''}`}>{SET_NAMES[r.set]?.name ?? r.set}</span>
                <div className="h-[22px] flex-1 rounded-[3px] bg-line-soft">
                  <div
                    className={`h-[22px] rounded-[3px] ${r.set.startsWith('curated') ? 'bg-accent' : r.set === 'train' ? 'bg-[#39424e]' : 'bg-[#9aa3ae]'}`}
                    style={{ width: `${((r.success_rate ?? 0) / max) * 100}%` }}
                  />
                </div>
                <span className={`w-12 text-right text-sm ${r.set.startsWith('curated') ? 'font-semibold' : ''}`}>{pct(r.success_rate)}</span>
              </div>
            ))}
          </div>
          <p className="mt-5 text-xs text-sub">
            수치와 판정은 도구가 계산했습니다. 같은 시험 위치끼리 짝지은 비교(주 판정)는 <Link to="/results">실험 결과</Link>에 있습니다.
          </p>
        </>
      )}
      <button type="button" onClick={onReset} className={`${btnLine} mt-4`}>
        새 요청
      </button>
    </section>
  )
}

// ---------- 근거 문서: 검색된 문단과 지식베이스 원문 ----------

function EvidencePanel({ docs }: { docs: Evidence[] }) {
  const [open, setOpen] = useState<Evidence | null>(null)
  const [full, setFull] = useState<string | null>(null)
  const [showFull, setShowFull] = useState(false)
  useEffect(() => {
    setOpen(null)
  }, [docs])
  useEffect(() => {
    setFull(null)
    setShowFull(false)
  }, [open])

  const toggleFull = async () => {
    if (!open) return
    if (!showFull && full == null) {
      try {
        setFull((await getDoc(open.file)).content ?? '')
      } catch (e) {
        setFull(`문서를 불러오지 못했습니다: ${(e as Error).message}`)
      }
    }
    setShowFull((s) => !s)
  }

  const host = (u: string | null) => {
    try {
      return u ? new URL(u).host : '출처 없음'
    } catch {
      return u ?? '출처 없음'
    }
  }

  if (open)
    return (
      <section aria-label="근거 문서 보기" className="rounded-[10px] border border-[#9fb8ec] bg-white p-5">
        <div className="flex items-center justify-between gap-2">
          <button type="button" onClick={() => setOpen(null)} className="h-8 cursor-pointer rounded-md border border-[#d5dae0] bg-white px-2.5 text-[13px]">
            ‹ 목록
          </button>
          <span className="font-mono text-[11px] text-sub">{open.file}</span>
        </div>
        <h2 className="mt-3.5 mb-0 text-base leading-snug font-semibold">{open.title}</h2>
        <div className="mt-1.5 text-xs text-sub">
          {[open.doc_type, open.score != null ? `관련도 ${open.score.toFixed(2)}` : null, open.retrieved ? `수집 ${open.retrieved}` : null].filter(Boolean).join(' · ')}
        </div>
        <div className="mt-4 text-xs text-sub">답변에 쓰인 문단{open.section ? ` · ${open.section}` : ''}</div>
        <blockquote className="mt-2 mb-0 rounded-md border border-[#d6e2fa] bg-[#f3f6fd] px-3.5 py-3 text-[13px] leading-[1.7] whitespace-pre-line text-[#22282f]">
          {open.chunk}
        </blockquote>
        {showFull && full != null && (
          <div className="mt-3.5 max-h-[220px] overflow-y-auto rounded-md border border-line-soft px-3.5 py-3 text-[13px] leading-[1.7] whitespace-pre-line text-body">
            {full}
          </div>
        )}
        <div className="mt-4 flex flex-col gap-2">
          {open.source_url && (
            <a
              href={open.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex h-10 items-center justify-center gap-1.5 rounded-md bg-ink text-sm font-medium text-white hover:no-underline"
            >
              원문 페이지 열기 <span aria-hidden="true">↗</span>
            </a>
          )}
          <button type="button" onClick={toggleFull} className="h-10 cursor-pointer rounded-md border border-field bg-white text-sm">
            {showFull ? '문서 전체 접기' : '지식베이스 문서 전체 보기'}
          </button>
        </div>
        {open.source_url && <div className="mt-2.5 font-mono text-[11px] [overflow-wrap:anywhere] text-sub">{open.source_url}</div>}
      </section>
    )

  return (
    <section className={`${card} p-5`}>
      <h2 className="m-0 mb-1 text-[15px] font-semibold">근거 문서</h2>
      {docs.length === 0 ? (
        <p className="m-0 text-xs text-sub">요청을 보내면 검색된 문서가 여기에 나옵니다.</p>
      ) : (
        <>
          <p className="mt-0 mb-3 text-xs text-sub">누르면 답변에 쓰인 문단과 원문을 볼 수 있습니다</p>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {docs.map((d, i) => (
              <li key={`${d.file}-${i}`}>
                <button
                  type="button"
                  onClick={() => setOpen(d)}
                  className="flex w-full cursor-pointer items-start gap-2.5 rounded-lg border border-line bg-white px-3 py-2.5 text-left hover:border-[#c5d3f0]"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="#1f5bd6" strokeWidth="1.6" className="mt-px flex-none">
                    <path d="M7 3h7l5 5v13H7z" />
                    <path d="M14 3v5h5" />
                    <path d="M10 13h6M10 17h6" />
                  </svg>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium text-ink">{d.title}</span>
                    <span className="mt-0.5 block text-xs text-sub">
                      {host(d.source_url)}
                      {d.score != null ? ` · 관련도 ${d.score.toFixed(2)}` : ''}
                    </span>
                  </span>
                  <span aria-hidden="true" className="text-base text-muted">
                    ›
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
