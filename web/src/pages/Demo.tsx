import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Markdown from '../components/Markdown'
import { getDoc, postResult, type Judgement } from '../lib/api'
import { pct, pp, signed } from '../lib/fmt'
import { streamSSE, type DifyEvent } from '../lib/sse'

// 데모: 요청 → Dify 실행(실시간) → 개수 확인 카드(사람) → 선별·검수·학습 키트 → 보고 → 결과 파일 올리기 → 판정.
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
  issues: Note[]
  warnings: Note[]
  sets: Record<string, { n_demos: number; total_frames: number }>
  train_set: { n_demos: number; total_frames: number }
}
// 진단 정리 노드의 출력: 개수 확인 카드에 보여 줄 진단·추천과 기본 개수
type Diag = { status: string; run_id: string; dataset: string; default_budget: string; diag_md: string }
type Form = { token: string; runId: string; content: string }
// 검수 알림은 {check, detail} 객체로 온다 (예전 형식은 문자열)
type Note = string | { check?: string; detail?: string }

const PRESETS = [
  { label: 'Can 골라줘 (추천 개수)', q: 'can 데이터로 학습할 시범 골라줘' },
  { label: 'Can 100개', q: 'can 데이터로 학습할 시범 100개 골라줘' },
  { label: 'Square 골라줘', q: 'square 데이터로 학습할 시범 골라줘' },
  { label: '데이터 추천받기', q: '캔을 집어서 통에 옮기는 걸 로봇에게 학습시키고 싶어. 어떤 데이터가 좋아?' },
  { label: '필터 키는 어떻게 써?', q: 'robomimic 필터 키는 어떻게 써?' },
]

// 화면에 단계로 보여줄 노드. 나머지(분기, 정리용 코드 노드)는 숨긴다
const STEP: Record<string, string> = {
  translate: '질문 해석',
  retrieval: '근거 검색',
  agent: '에이전트 판단',
  pend: '진단과 추천',
  confirm: '개수 확인',
  log_ok: '확정 기록',
  sel: '선별',
  review: '검수',
  kit: '학습 키트',
  report: '보고 작성',
}
const MAIN = Object.keys(STEP)
const VISIBLE = new Set(['llm', 'knowledge-retrieval', 'agent', 'tool', 'human-input'])
const TOOL_OF: Record<string, string> = { llm: 'LLM', 'knowledge-retrieval': '지식베이스', 'human-input': '사람' }

// 도구 노드 제목의 괄호 안이 도구 이름이다. 기록 노드만 제목에 이름이 없다
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
  const [diag, setDiag] = useState<Diag | null>(null)
  const [action, setAction] = useState<'select' | 'cancel' | null>(null)
  const [chosen, setChosen] = useState('')
  const [convId, setConvId] = useState('')
  const [answer, setAnswer] = useState('')
  const [cost, setCost] = useState<number | null>(null)
  // 경과 시간: 실행 중인 구간만 더한다 (사람이 개수를 정하는 시간은 빼고)
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
        // 진단 정리(코드 노드)는 단계로 보이지 않지만, 출력은 개수 확인 카드에 쓴다
        if (e.event === 'node_finished' && d.node_id === 'diag' && d.outputs) setDiag(d.outputs as Diag)
        if (!VISIBLE.has(d.node_type)) break
        const done = e.event === 'node_finished'
        setNodes((ns) => {
          const row: NodeRow = { id: d.node_id, type: d.node_type, title: d.title, done, elapsed: done ? d.elapsed_time : undefined }
          const k = ns.findIndex((n) => n.id === d.node_id)
          if (k < 0) return [...ns, row]
          // 확인 뒤 다시 받는 지난 상태(snapshot)에는 시작 이벤트가 또 온다. 끝난 기록은 덮지 않는다
          if (!done && ns[k].done) return ns
          const copy = ns.slice()
          copy[k] = { ...row, elapsed: d.node_type === 'human-input' ? undefined : row.elapsed }
          return copy
        })
        if (done && d.node_type === 'tool') {
          const out = d.outputs?.json?.[0]
          if (d.node_id === 'review' && out?.run_id) setReview(out as Review)
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
    setDiag(null)
    setAction(null)
    setChosen('')
    setConvId('')
    setAnswer('')
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

  async function decide(act: 'select' | 'cancel', budget: string) {
    if (!form) return
    setAction(act)
    setChosen(budget)
    setPhase('resuming')
    startSeg()
    const ac = new AbortController()
    abort.current = ac
    try {
      // 카드의 입력칸 값(고를 개수)을 Dify 양식 입력으로 넘긴다
      await streamSSE('/api/approve', { form_token: form.token, action: act, workflow_run_id: form.runId, conversation_id: convId, inputs: { budget } }, onEvent, ac.signal)
      setPhase(act === 'select' ? 'done' : 'rejected')
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
    pending: ['개수 확인 대기', 'text-accent'],
    resuming: [action === 'cancel' ? '취소 처리 중' : '선별·검수·학습 키트 만드는 중', 'text-accent'],
    done: ['완료', 'text-ok'],
    rejected: ['취소됨', 'text-sub'],
    error: ['오류', 'text-danger'],
  }

  return (
    <main className="bg-paper">
      <div className="mx-auto max-w-[1280px] px-8 pt-8 pb-16">
        <div className="dot-grid mb-6 rounded-[10px] border border-line bg-white px-7 pt-7 pb-6">
          <h1 className="m-0 text-[28px] font-semibold tracking-tight">데모</h1>
          <p className="mt-1.5 text-[15px] text-[#475060]">
            데이터를 분석해 위치 편중·중복을 진단하고, 실험으로 확인된 개수를 추천합니다. 사람이 개수를 확정하면 학습 전에 좋은 시범을 골라 바로 돌릴 수 있는 학습 키트를 줍니다. 학습은 자기 환경에서 하고, 결과 파일을 올리면 판정합니다.
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
                    {busy ? `${elapsed.toFixed(1)}초 경과` : `총 ${elapsed.toFixed(1)}초${form ? ' (개수 확인 대기 제외)' : ''}`}
                  </span>
                </div>
                <ol className="relative m-0 flex list-none flex-col p-0">
                  <div className="absolute top-5 bottom-5 left-1 w-0.5 bg-line" />
                  {nodes.map((n) => {
                    const human = n.type === 'human-input'
                    const waiting = human && !n.done
                    const name = human ? (waiting ? '개수 확인 대기' : action === 'cancel' ? '개수 확인 취소' : `개수 확정 ${chosen}개`) : STEP[n.id] ?? n.title
                    const dot = waiting || !n.done ? DOT.wait : human && action === 'cancel' ? DOT.stop : DOT.ok
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
              <Confirm diag={diag} form={form} busy={phase === 'resuming'} action={action} onDecide={decide} />
            )}

            {phase === 'rejected' && (
              <section className={`${card} p-6`}>
                <h2 className="m-0 text-lg font-semibold">고르지 않음</h2>
                <p className="mt-2 text-sm text-[#475060]">개수 확인을 취소해 시범을 고르지 않았습니다. 개수나 데이터를 바꿔 다시 요청할 수 있습니다.</p>
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

            {phase === 'done' && <Report answer={answer} chosen={action === 'select' ? chosen : null} sid={convId} onReset={reset} />}
          </div>

          <aside className="flex min-w-0 flex-[1_1_300px] flex-col gap-4">
            <section className={`${card} p-5`}>
              <h2 className="m-0 mb-3.5 text-[15px] font-semibold">실행 정보</h2>
              <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2.5 text-[13px]">
                <dt className="text-sub">상태</dt>
                <dd className={`m-0 font-medium ${status[phase][1]}`}>{status[phase][0]}</dd>
                <dt className="text-sub">실행 ID</dt>
                <dd className="m-0 font-mono text-xs [overflow-wrap:anywhere]">{review?.run_id ?? diag?.run_id ?? '-'}</dd>
                <dt className="text-sub">대화 ID</dt>
                <dd className="m-0 font-mono text-xs">{convId ? convId.slice(0, 8) : '-'}</dd>
                <dt className="text-sub">데이터</dt>
                <dd className="m-0">{review ? `${review.dataset} · 선별 후보 ${review.train_set.n_demos}개` : diag?.dataset || '-'}</dd>
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

// ---------- 개수 확인 카드 (사람 확인): 진단·추천·근거를 보고 고를 개수를 확정한다 ----------

function Confirm({ diag, form, busy, action, onDecide }: {
  diag: Diag | null
  form: Form
  busy: boolean
  action: 'select' | 'cancel' | null
  onDecide: (a: 'select' | 'cancel', budget: string) => void
}) {
  const [value, setValue] = useState(diag?.default_budget ?? '')
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => setValue(diag?.default_budget ?? ''), [diag?.default_budget])
  // 진단이 없으면(이벤트를 놓친 경우) Dify 양식 본문을 그대로 보여 준다. 입력칸 자리 표시는 지운다
  const body = diag?.diag_md || form.content.replace(/\{\{#\$output\.\w+#\}\}/g, '').replace(/^## .*\n/, '')
  const submit = () => {
    const n = Number(value)
    if (!Number.isInteger(n) || n < 10) {
      setErr('10 이상의 정수를 넣어 주세요')
      return
    }
    setErr(null)
    onDecide('select', String(n))
  }
  return (
    <section aria-label="고를 개수 확인" className="overflow-hidden rounded-[10px] border border-[#9fb8ec] bg-white px-6 pb-6">
      <div className="-mx-6 mb-5 flex items-center gap-2.5 bg-accent px-6 py-3 text-[13px] text-white">
        <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="#fff" strokeWidth="2">
          <path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z" />
        </svg>
        <span>사용자 확인 단계 · 진단을 보고 고를 개수를 정합니다</span>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="m-0 text-lg font-semibold">고를 개수 확인</h2>
        <span className="rounded-xl bg-accent-soft px-2.5 py-1 text-xs text-accent-ink">사용자 확인 필요</span>
      </div>
      <div className="mt-3">
        <Markdown text={body} />
      </div>
      <form
        className="mt-5 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <label className="flex flex-col gap-1.5 text-[13px] text-[#475060]">
          고를 개수
          <input
            type="number"
            inputMode="numeric"
            min={10}
            value={value}
            disabled={busy}
            onChange={(e) => {
              setValue(e.target.value)
              setErr(null)
            }}
            aria-invalid={!!err}
            className="h-11 w-32 rounded-md border border-field bg-white px-3 text-[15px] text-ink tabular-nums disabled:bg-paper"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="h-11 cursor-pointer rounded-md bg-accent px-[22px] text-[15px] font-semibold text-white disabled:cursor-wait disabled:opacity-60"
        >
          {busy && action === 'select' ? '처리 중' : '이 개수로 고르기'}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onDecide('cancel', value)}
          className="h-11 cursor-pointer rounded-md border border-field bg-white px-[18px] text-[15px] text-ink disabled:cursor-wait disabled:opacity-60"
        >
          {busy && action === 'cancel' ? '처리 중' : '취소'}
        </button>
      </form>
      {err && <p role="alert" className="mt-2 mb-0 text-[13px] text-danger">{err}</p>}
      <p className="mt-4 mb-0 text-[13px] text-sub">
        고르면 바로 선별·검수하고 학습 키트를 만듭니다. 학습은 하지 않으며 GPU를 쓰지 않습니다. 개수는 10부터 선별 후보 수까지입니다.
      </p>
    </section>
  )
}

// ---------- 보고: 최종 답변(학습 키트·근거·수집 계획) + 학습 결과 올리기 → 판정 ----------

function Report({ answer, chosen, sid, onReset }: { answer: string; chosen: string | null; sid: string; onReset: () => void }) {
  return (
    <>
      <section className={`${card} p-6`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="m-0 text-lg font-semibold">보고</h2>
          {chosen && <span className="rounded-xl bg-ok-soft px-2.5 py-1 text-xs text-ok-ink">개수 확정 · {chosen}개</span>}
        </div>
        <div className="mt-3">{answer ? <Markdown text={answer} /> : <p className="text-sm text-sub">답변이 비어 있습니다.</p>}</div>
        <button type="button" onClick={onReset} className={`${btnLine} mt-4`}>
          새 요청
        </button>
      </section>
      {chosen && sid && <ResultUpload sid={sid} />}
    </>
  )
}

// 사용자가 학습 키트로 학습한 뒤 결과 파일을 올리면 판정한다 (선별·무작위·전체면 선별 효과 판정, 선별만이면 결과 확인)
function ResultUpload({ sid }: { sid: string }) {
  const [res, setRes] = useState<Judgement | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const onFile = async (f: File | undefined) => {
    if (!f) return
    setErr(null)
    setRes(null)
    if (!f.name.endsWith('.json')) {
      setErr('노트북이 만든 결과 파일(results_main_<지문>.json)을 골라 주세요')
      return
    }
    setBusy(true)
    try {
      setRes(await postResult(sid, await f.text()))
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const names: Record<string, string> = { curated: '선별', random: '무작위', train: '전체' }
  const g = res?.gain_vs_random
  const d = res?.drop_vs_full
  return (
    <section aria-label="학습 결과 올리기" className={`${card} p-6`}>
      <h2 className="m-0 text-lg font-semibold">학습 결과 올리기</h2>
      <p className="mt-1.5 mb-0 text-sm text-[#475060]">
        노트북이 끝나면 결과 폴더(curation_results)의 결과 파일을 올립니다. 비교 학습이면 선별 효과를 판정하고, 선별만 학습했으면 성공률과 우리 실험의 비슷한 결과를 보여 줍니다.
      </p>
      <label className="mt-4 inline-flex h-10 cursor-pointer items-center rounded-md border border-field bg-white px-4 text-sm text-ink">
        {busy ? '판정 중' : '결과 파일 고르기'}
        <input type="file" accept=".json,application/json" className="sr-only" disabled={busy} onChange={(e) => onFile(e.target.files?.[0])} />
      </label>
      {err && <p role="alert" className="mt-3 mb-0 text-[13px] text-danger">{err}</p>}
      {res && (
        <div className="mt-5 border-t border-line-soft pt-4">
          <div className="flex flex-wrap items-center gap-2.5">
            <h3 className="m-0 text-[15px] font-semibold">{res.title}</h3>
            <span className="text-[13px] text-sub">
              {res.dataset} · 선별 {res.budget}개 · {res.epoch} epoch{res.platform ? ` · ${res.platform}` : ''}
            </span>
          </div>
          <table className="mt-3 w-full max-w-[520px] border-collapse text-sm tabular-nums">
            <tbody>
              {Object.entries(res.rates).map(([k, x]) => (
                <tr key={k}>
                  <td className="border-b border-line-soft py-2">{names[k] ?? k}</td>
                  <td className="border-b border-line-soft py-2 text-right font-medium">{pct(x!.rate)}</td>
                  <td className="border-b border-line-soft py-2 pl-3 text-right text-sub">
                    {x!.success}/{x!.rollouts} · {pct(x!.ci95[0])}~{pct(x!.ci95[1])}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {res.kind === 'effect' && (
            <ul className="mt-4 mb-0 flex list-none flex-col gap-2 p-0 text-sm">
              {g && (
                <li className="flex flex-wrap items-baseline gap-2.5">
                  <span className={`rounded px-2 py-0.5 text-xs ${g.verdict.startsWith('차이 있음') ? 'bg-ok-soft text-ok-ink' : 'bg-line-soft text-body'}`}>{g.verdict}</span>
                  <span>선별 − 무작위 {pp(g.diff, 1)}</span>
                  <span className="text-sub">(95% 신뢰구간 {signed(g.ci95[0], 1)} ~ {signed(g.ci95[1], 1)}%p)</span>
                </li>
              )}
              {d && (
                <li className="flex flex-wrap items-baseline gap-2.5">
                  <span className={`rounded px-2 py-0.5 text-xs ${d.confirmed ? 'bg-ok-soft text-ok-ink' : 'bg-line-soft text-body'}`}>
                    {d.confirmed ? '하락 기준 충족' : '하락 기준 확인 안 됨'}
                  </span>
                  <span>전체 − 선별 {pp(d.diff, 1)}</span>
                  <span className="text-sub">(신뢰구간 위쪽 끝 {signed(d.ci95[1], 1)}%p, 기준 +5%p 이하)</span>
                </li>
              )}
              {(res.missing ?? []).map((m) => (
                <li key={m} className="text-[13px] text-sub">{names[m] ?? m} 묶음 결과가 없어 그 비교는 하지 않았습니다</li>
              ))}
            </ul>
          )}
          {res.evidence && res.evidence.rows.length > 0 && (
            <div className="mt-4 text-[13px] text-body">
              <div className="text-sub">우리 실험의 비슷한 결과{res.evidence.same_plan ? ' (같은 학습 계획)' : ''}</div>
              <ul className="mt-1.5 mb-0 flex list-disc flex-col gap-1 pl-5">
                {res.evidence.rows.map((r) => (
                  <li key={`${r.dataset}-${r.budget}`}>
                    {r.dataset} · {r.budget}개:{' '}
                    {Object.entries(r.rates)
                      .map(([k, x]) => `${names[k] ?? k} ${pct(x!.rate)}`)
                      .join(', ')}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {res.note && <p className="mt-3 mb-0 text-[13px] text-warn-ink">{res.note}</p>}
          <p className="mt-3 mb-0 text-xs text-sub">판정은 코드가 같은 시험 위치끼리 짝지어 계산했습니다. 결과는 이 대화의 기록에 남고, 우리 실험 결과는 바꾸지 않습니다.</p>
        </div>
      )}
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
