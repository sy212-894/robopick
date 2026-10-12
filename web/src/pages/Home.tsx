import { useState } from 'react'
import { Link } from 'react-router-dom'
import { getOverview, getResults, type Judge, type Overview, type Results } from '../lib/api'
import { num, pct, pp, SIGNAL_NAMES, useApi } from '../lib/fmt'

// 캔버스 산점도와 같은 좌표 변환 (0~100 → 테두리 3% 여백)
const px = (x: number) => 3 + x * 0.94
const py = (y: number) => 3 + (100 - y) * 0.94

function Scatter({ ov }: { ov: Overview }) {
  const [view, setView] = useState<'all' | 'sel' | 'out'>('all')
  const pts = ov.points.filter((p) => view === 'all' || (view === 'sel' ? p[2] === 1 : p[2] === 0))
  const nSel = ov.points.filter((p) => p[2] === 1).length
  const views: [typeof view, string][] = [['all', `전체 ${ov.points.length}`], ['sel', `선별 ${nSel}`], ['out', `제외 ${ov.points.length - nSel}`]]
  const xl = ov.x_edges.slice(1, -1).map(px)
  const yl = ov.y_edges.slice(1, -1).map(py)
  // 칸 이름: 왼쪽 위 모서리 (x0이 왼쪽, y2가 위)
  const colLeft = [1.5, xl[0] + 1, xl[1] + 1]
  const rowTop = [yl[0] + 1.6, yl[1] + 1.6, 1.8]
  return (
    <figure className="m-0 min-w-0 flex-[1_1_440px] rounded-[10px] border border-[#1f2731] bg-[#121820] p-6">
      <div className="mb-[18px] text-sm font-medium text-[#e9edf2]">
        캔 초기 위치 {ov.points.length}개 중 선별 {nSel}개
      </div>
      <div role="img" aria-label="캔 초기 위치 산점도. 3x3 조건 칸마다 선별된 시범이 고르게 퍼져 있다"
        className="relative w-full overflow-hidden rounded border border-[#2a333e]" style={{ aspectRatio: '1 / 0.82' }}>
        {xl.map((l) => <div key={`x${l}`} className="absolute inset-y-0 w-px bg-[#2a333e]" style={{ left: `${l}%` }} />)}
        {yl.map((t) => <div key={`y${t}`} className="absolute inset-x-0 h-px bg-[#2a333e]" style={{ top: `${t}%` }} />)}
        {[0, 1, 2].flatMap((xi) => [0, 1, 2].map((yi) => (
          <span key={`c${xi}${yi}`} className="absolute font-mono text-[10px] text-[#4a5562]"
            style={{ left: `${colLeft[xi]}%`, top: `${rowTop[yi]}%` }}>x{xi}y{yi}</span>
        )))}
        {pts.map((p, i) => (
          <span key={i} className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full ${p[2] ? 'size-2 bg-[#4c86ff]' : 'size-[7px] border border-muted'}`}
            style={{ left: `${px(p[0])}%`, top: `${py(p[1])}%` }} />
        ))}
      </div>
      <div className="mt-3.5 flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="점 표시" className="inline-flex overflow-hidden rounded-md border border-[#2a333e]">
          {views.map(([k, label]) => (
            <button key={k} type="button" aria-pressed={view === k} onClick={() => setView(k)}
              className={`h-9 cursor-pointer px-3.5 text-xs ${view === k ? 'bg-[#1f2a38] text-white' : 'bg-transparent text-[#9aa4b1]'}`}>
              {label}
            </button>
          ))}
        </div>
        <span className="text-xs text-[#9aa4b1]">선: 위치 3×3 조건 칸 (분위수)</span>
      </div>
      <figcaption className="mt-3.5 text-[13px] leading-relaxed text-[#8b96a5]">
        칸마다 시범 수에 비례해 개수를 나누고, 칸 안에서는 길이·이동 경로·멈춤·그리퍼 전환으로 매긴 품질 점수 순으로 골랐습니다.
      </figcaption>
    </figure>
  )
}

function Hero({ ov }: { ov: Overview | null }) {
  return (
    <section className="dot-grid-dark relative overflow-hidden text-[#e9edf2]">
      <div className="relative mx-auto flex max-w-[1200px] flex-wrap items-center gap-16 px-8 pb-[104px] pt-24">
        <div className="min-w-0 flex-[1_1_460px]">
          <div className="mb-7 inline-flex items-center gap-2.5 rounded-full border border-[#2a3a55] bg-[#0f1724] px-3 py-1 font-mono text-xs text-[#9fb4d8]">
            <span className="inline-block size-1.5 rounded-full bg-[#4c86ff]" />
            로봇 모방학습 · 시범 데이터 큐레이션
          </div>
          <h1 className="m-0 text-[54px] font-semibold leading-[1.2] tracking-[-0.03em] text-white">
            <span className="px-0.5" style={{ backgroundImage: 'linear-gradient(#1f5bd6, #1f5bd6)', backgroundRepeat: 'no-repeat', backgroundSize: '100% 0.32em', backgroundPosition: '0 88%' }}>
              좋은 시범
            </span>
            만 골라도
            <br />
            로봇은 더 빨리 배웁니다
          </h1>
          <p className="mt-7 max-w-[520px] text-lg leading-relaxed text-[#b4bdc9]">
            사람이 보여준 시범 300개를 작업 조건과 품질로 나눠 학습에 쓸 150개를 고릅니다. 고른 근거와 학습 계획을 보여주고, 사람이 승인한 계획만 학습합니다.
          </p>
          <div className="mt-10 flex flex-wrap gap-3">
            <Link to="/demo" className="inline-flex h-12 items-center rounded-md bg-white px-[22px] text-[15px] font-semibold text-night hover:no-underline">데모 실행</Link>
            <Link to="/results" className="inline-flex h-12 items-center rounded-md border border-[#36404c] px-[22px] text-[15px] font-medium text-[#e9edf2] hover:no-underline">실험 결과 보기</Link>
          </div>
          <div className="mt-12 flex flex-wrap gap-5 font-mono text-xs text-[#6f7a88]">
            <span>robomimic Can · Square</span><span>Multi-Human 300개</span><span>BC-RNN</span><span>Dify + MCP</span>
          </div>
        </div>
        {ov ? <Scatter ov={ov} /> : <div className="min-h-[420px] flex-[1_1_440px] rounded-[10px] border border-[#1f2731] bg-[#121820]" />}
      </div>
    </section>
  )
}

function Bar2({ label, parts }: { label: string; parts: [number, string][] }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="w-[52px] text-xs text-body">{label}</span>
      <div className="flex h-3 flex-1 overflow-hidden rounded-sm">
        {parts.map(([w, c], i) => <div key={i} style={{ width: `${w}%`, background: c }} />)}
      </div>
    </div>
  )
}

function Ratio({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="w-[52px] text-xs text-body">{label}</span>
      <div className="h-3 flex-1 rounded-sm bg-line-soft"><div className="h-3 rounded-sm bg-ink" style={{ width: `${value * 100}%` }} /></div>
      <span className="w-[34px] text-right font-mono text-xs">{pct(value)}</span>
    </div>
  )
}

function Slope({ c0, c1, r0, r1, e0, e1 }: { c0: number; c1: number; r0: number; r1: number; e0: number; e1: number }) {
  const y = (v: number) => 80 - v * 72
  return (
    <svg role="img" aria-label={`학습 epoch에 따른 성공률: 선별 ${pct(c0)}에서 ${pct(c1)}, 무작위 ${pct(r0)}에서 ${pct(r1)}`} viewBox="0 0 330 92" className="mt-3.5 block h-auto w-full">
      <line x1="40" y1="8" x2="40" y2="80" stroke="#e3e6ea" />
      <line x1="250" y1="8" x2="250" y2="80" stroke="#e3e6ea" />
      <line x1="40" y1={y(c0)} x2="250" y2={y(c1)} stroke="#1f5bd6" strokeWidth="2.5" />
      <line x1="40" y1={y(r0)} x2="250" y2={y(r1)} stroke="#9aa3ae" strokeWidth="2.5" />
      {[[40, c0, '#1f5bd6'], [250, c1, '#1f5bd6'], [40, r0, '#9aa3ae'], [250, r1, '#9aa3ae']].map(([x, v, c], i) => (
        <circle key={i} cx={x as number} cy={y(v as number)} r="4" fill={c as string} />
      ))}
      <text x="32" y={y(c0) + 4} textAnchor="end" fontSize="11" fill="#1f5bd6" fontFamily="IBM Plex Mono">{Math.round(c0 * 100)}</text>
      <text x="32" y={y(r0) + 4} textAnchor="end" fontSize="11" fill="#5a6472" fontFamily="IBM Plex Mono">{Math.round(r0 * 100)}</text>
      <text x="258" y={Math.min(y(c1), y(r1)) + 0} fontSize="11" fill="#1f5bd6" fontFamily="IBM Plex Mono">{Math.round(c1 * 100)} 선별</text>
      <text x="258" y={Math.min(y(c1), y(r1)) + 16} fontSize="11" fill="#5a6472" fontFamily="IBM Plex Mono">{Math.round(r1 * 100)} 무작위</text>
      <text x="40" y="91" textAnchor="middle" fontSize="11" fill="#5a6472" fontFamily="IBM Plex Mono">{e0} epoch</text>
      <text x="250" y="91" textAnchor="middle" fontSize="11" fill="#5a6472" fontFamily="IBM Plex Mono">{e1} epoch</text>
    </svg>
  )
}

function Stats({ ov, res }: { ov: Overview; res: Results }) {
  const p = res.can.paired
  const rate = (k: string) => (p?.rates[k] ? p.rates[k].success / p.rates[k].rollouts : undefined)
  const gain = p?.gain_vs_random
  const early = res.can.judgement?.early_gain_vs_random as Judge | undefined
  const row = (k: string) => res.can.table?.find((r) => r.set === k)
  const cur = row('curated_150')
  const rnd = row('random_150')
  const comp = (k: string) => {
    const c = ov.composition[k]
    const n = c.better + c.okay + c.worse
    return [[(c.better / n) * 100, '#1f5bd6'], [(c.okay / n) * 100, '#9fb8ec'], [(c.worse / n) * 100, '#d5dae0']] as [number, string][]
  }
  const nTest = p ? Math.round(p.rates.curated_150.rollouts / p.rates.curated_150.seeds) : null
  const epochs = res.can.config
  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-[1200px] px-8 pb-12 pt-14">
        <div className="grid gap-0" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
          <div className="border-r border-line py-2 pr-8">
            <div className="text-[44px] font-semibold tracking-tight text-accent">{pp(gain?.diff)}</div>
            <div className="mt-2 text-base font-medium">같은 150개 무작위 대비 평균 차이</div>
            <div className="mt-1.5 text-[13px] text-sub">선별 {pct(rate('curated_150'))} vs 무작위 {pct(rate('random_150'))} · 시드 {gain?.n_seeds ?? '-'}개를 짝지은 비교 · 판정 {gain?.verdict ?? '-'}</div>
            <div role="img" aria-label="숙련도 구성" className="mt-[22px] flex flex-col gap-2">
              <Bar2 label="선별" parts={comp('curated_150')} />
              <Bar2 label="무작위" parts={comp('random_150')} />
              <div className="ml-[62px] flex flex-wrap gap-3 text-[11px] text-sub">
                <span>■ 숙련</span><span className="text-[#6f8fd0]">■ 보통</span><span className="text-[#9aa3ae]">■ 미숙</span><span>사후 확인용 라벨</span>
              </div>
            </div>
          </div>
          <div className="border-r border-line px-8 py-2">
            <div className="text-[44px] font-semibold tracking-tight">{pct(ov.selected.n_demos / ov.train.n_demos)}</div>
            <div className="mt-2 text-base font-medium">전체 데이터 대비 성능 하락 없음</div>
            <div className="mt-1.5 text-[13px] text-sub">{ov.selected.n_demos} / {ov.train.n_demos}개 · 선별 {pct(rate('curated_150'))} vs 전체 {pct(rate('train'))}</div>
            <div role="img" aria-label="시범 수와 프레임 수 비율" className="mt-[22px] flex flex-col gap-2">
              <Ratio label="시범" value={ov.selected.n_demos / ov.train.n_demos} />
              <Ratio label="프레임" value={ov.selected.total_frames / ov.train.total_frames} />
              <div className="ml-[62px] text-[11px] text-sub">짧고 군더더기 없는 시범을 골라 프레임을 더 적게 사용 ({num(ov.selected.total_frames)} / {num(ov.train.total_frames)})</div>
            </div>
          </div>
          <div className="py-2 pl-8">
            <div className="text-[44px] font-semibold tracking-tight">{pp(early?.diff)}</div>
            <div className="mt-2 text-base font-medium">학습 초반({epochs?.early_eval_epoch} epoch) 성공률 차이</div>
            <div className="mt-1.5 text-[13px] text-sub">선별 {pct(cur?.early?.success_rate)} vs 무작위 {pct(rnd?.early?.success_rate)} · 학습 속도</div>
            {cur?.early && rnd?.early && cur.success_rate != null && rnd.success_rate != null && (
              <Slope c0={cur.early.success_rate} c1={cur.success_rate} r0={rnd.early.success_rate} r1={rnd.success_rate}
                e0={epochs?.early_eval_epoch ?? 0} e1={epochs?.num_epochs ?? 0} />
            )}
          </div>
        </div>
        <p className="mt-8 text-[13px] leading-normal text-sub">robomimic Can, BC-RNN {epochs?.num_epochs} epoch, 시험 {nTest ?? '-'}개 기준</p>
      </div>
    </section>
  )
}

function Signals({ ov }: { ov: Overview }) {
  const Q: [keyof Overview['lengths'], string, string][] = [['better', '숙련', '#1f5bd6'], ['okay', '보통', '#9fb8ec'], ['worse', '미숙', '#c4cad2']]
  const scale = Math.max(...Object.values(ov.lengths).map((l) => l.max)) * 1.05
  const ratio = ov.lengths.worse.max / ov.lengths.better.max
  return (
    <section className="border-b border-line bg-paper">
      <div className="mx-auto max-w-[1200px] px-8 py-24">
        <h2 className="m-0 text-[34px] font-semibold leading-snug tracking-tight">무엇을 좋은 시범으로 볼까요?</h2>
        <p className="mt-3.5 max-w-[720px] text-base leading-relaxed text-body">
          누가 잘했는지 알려주는 라벨이 없어도, 로봇이 움직인 기록만 보면 꽤 많은 것을 알 수 있습니다. 능숙한 사람일수록 작업을 짧게 끝내고, 덜 머뭇거리고, 덜 돌아가기 때문입니다. 그래서 시범마다 계산할 수 있는 신호 다섯 가지를 실제 숙련도와 비교해 보고, 잘 맞는 네 가지만 골라 사용합니다.
        </p>
        <div className="mt-12 flex flex-wrap gap-8">
          <div className="min-w-0 flex-[1_1_480px] rounded-[10px] border border-line bg-white p-7">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h3 className="m-0 text-base font-semibold">신호와 숙련도의 순위 상관</h3>
              <span className="font-mono text-[11px] text-sub">Spearman · Can 300개</span>
            </div>
            <div className="mt-6 flex flex-col gap-3.5">
              {ov.signals.map((g) => (
                <div key={g.name} className="flex items-center gap-3">
                  <span className={`w-[116px] text-sm ${g.used ? 'text-ink' : 'text-muted'}`}>{SIGNAL_NAMES[g.name] ?? g.name}</span>
                  <div className="relative h-[18px] flex-1 rounded-sm bg-paper">
                    <div className={`absolute inset-y-0 left-0 rounded-sm ${g.used ? 'bg-accent' : 'bg-[#c4cad2]'}`} style={{ width: `${(Math.abs(g.spearman) / 0.8) * 100}%` }} />
                  </div>
                  <span className={`w-[52px] text-right font-mono text-[13px] ${g.used ? 'text-ink' : 'text-muted'}`}>{g.spearman.toFixed(2).replace('-', '−')}</span>
                  <span className="w-9 text-xs text-sub">{g.used ? '사용' : '제외'}</span>
                </div>
              ))}
            </div>
            <p className="mt-5 text-xs text-sub">막대가 길수록 숙련도와 잘 맞는 신호입니다. 고른 네 가지 신호를 똑같은 비중으로 섞어 시범마다 품질 점수를 매겼습니다.</p>
          </div>
          <div className="min-w-0 flex-[1_1_400px] rounded-[10px] border border-line bg-white p-7">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h3 className="m-0 text-base font-semibold">숙련도별 시범 길이</h3>
              <span className="font-mono text-[11px] text-sub">프레임 · 최소–최대, 점은 평균</span>
            </div>
            <div role="img" aria-label="숙련도별 시범 길이 범위" className="mt-7 flex flex-col gap-[26px]">
              {Q.map(([k, name, c]) => {
                const l = ov.lengths[k]
                return (
                  <div key={k}>
                    <div className="flex justify-between text-[13px]"><span className="font-medium">{name}</span><span className="font-mono text-body">평균 {l.mean}</span></div>
                    <div className="relative mt-2 h-4">
                      <div className="absolute inset-x-0 top-[7px] h-0.5 bg-line-soft" />
                      <div className="absolute top-[5px] h-1.5 rounded-sm" style={{ background: c, left: `${(l.min / scale) * 100}%`, width: `${((l.max - l.min) / scale) * 100}%` }} />
                      <div className="absolute top-0.5 size-3 -translate-x-1/2 rounded-full border-2 border-ink bg-white" style={{ left: `${(l.mean / scale) * 100}%` }} />
                    </div>
                    <div className="mt-1 flex justify-between font-mono text-[11px] text-sub"><span>{l.min}</span><span>{num(l.max)}</span></div>
                  </div>
                )
              })}
            </div>
            <p className="mt-5 text-xs text-sub">학습 후보 {ov.train.n_demos}개를 기준으로, 미숙한 사람의 시범은 같은 일을 끝내는 데 가장 오래 걸린 경우 숙련자보다 {Math.floor(ratio)}배 넘게 걸렸습니다.</p>
          </div>
        </div>
      </div>
    </section>
  )
}

const STEPS = [
  ['01', '분석', '시범마다 길이, 이동 경로, 멈춤 비율, 그리퍼 전환과 물체 초기 위치를 계산해 조건 칸별 분포를 만듭니다.', 'analyze_data'],
  ['02', '선별', '칸마다 비례로 개수를 나누고 칸 안에서 품질 점수 순으로 선택합니다. 비교용 무작위 묶음 3종도 함께 생성합니다.', 'select_demos'],
  ['03', '검수와 승인', '예산, 중복, 평가용 데이터를 규칙으로 검사한 뒤, 사람이 학습 계획을 보고 승인합니다.', 'review_selection · 사람 승인'],
  ['04', '학습과 비교', '같은 설정으로 묶음마다 학습하고, 같은 시험 위치끼리 짝지어 성공률 차이를 신뢰구간과 함께 판정합니다.', 'train_evaluate'],
]

const PRINCIPLES = [
  ['M4 18h16M7 14v4M12 9v9M17 5v13', '숫자는 도구가 계산합니다', 'LLM은 요청을 해석하고 문장을 씁니다. 성공률, 신뢰구간, 판정은 도구가 계산한 값을 그대로 사용합니다.'],
  ['M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6zM9 12l2 2 4-4', '사람이 승인해야 학습합니다', '효율적인 학습을 위해, 사용자에게 계획과 예상 시간을 보여주고 승인을 받은 뒤에만 진행합니다.'],
  ['M6 3h12a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V5a2 2 0 012-2zM8 8h8M8 12h8M8 16h5', '모든 호출이 기록됩니다', '도구 호출과 승인은 실행 ID로 남습니다. 보고에 나온 숫자가 기록과 맞는지 직접 검사할 수 있습니다.'],
]

const ARCH = [
  ['웹', '요청, 진행 표시, 승인, 결과'],
  ['Dify 채팅플로우', '에이전트 Gemma-4-26B, 문서 검색, 승인'],
  ['MCP 도구 서버', '분석, 선별, 검수, 학습 계획, 기록'],
  ['학습', '승인된 계획만, 결과는 파일로 회수'],
]

export default function Home() {
  const ov = useApi(getOverview)
  const res = useApi(getResults)
  return (
    <>
      <Hero ov={ov.data} />
      {ov.data && res.data ? <Stats ov={ov.data} res={res.data} /> : <Loading error={ov.error ?? res.error} />}
      {ov.data && <Signals ov={ov.data} />}

      <section>
        <div className="mx-auto max-w-[1200px] px-8 pb-6 pt-24">
          <h2 className="m-0 text-[34px] font-semibold leading-snug tracking-tight">요청 한 줄에서 학습 계획까지</h2>
          <div className="mt-12 grid gap-8" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
            {STEPS.map(([n, t, d, tool]) => (
              <div key={n} className="border-t-2 border-ink pt-[22px]">
                <span className="-mt-[29px] block size-3.5 rounded-full border-2 border-ink bg-white" />
                <div className="mt-[18px] font-mono text-[46px] font-medium leading-none tracking-tight text-transparent" style={{ WebkitTextStroke: '1px #101418' }}>{n}</div>
                <h3 className="mt-2.5 text-[19px] font-semibold">{t}</h3>
                <p className="mt-2.5 text-[15px] leading-relaxed text-body">{d}</p>
                <div className="mt-4 font-mono text-xs text-accent">{tool}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-[1200px] px-8 pb-6 pt-[72px]">
          <div className="grid gap-10 rounded-[10px] bg-paper p-10" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
            {PRINCIPLES.map(([d, t, s]) => (
              <div key={t}>
                <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="#101418" strokeWidth="1.6"><path d={d} /></svg>
                <h3 className="mt-4 text-[17px] font-semibold">{t}</h3>
                <p className="mt-2 text-sm leading-relaxed text-body">{s}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-[1200px] px-8 pb-6 pt-[72px]">
          <h2 className="m-0 text-[34px] font-semibold leading-snug tracking-tight">모든 계산은 사용자의 노트북 안에서</h2>
          <p className="mt-3.5 max-w-[680px] text-base leading-relaxed text-body">시범 원본은 외부로 나가지 않으며, 외부 LLM에는 문서 검색어와 도구가 만든 요약만 전송합니다.</p>
          <div className="mt-10 flex flex-wrap items-stretch gap-3">
            {ARCH.map(([t, d], i) => (
              <div key={t} className="contents">
                {i > 0 && <div aria-hidden="true" className="flex items-center text-lg text-muted">→</div>}
                <div className="flex-[1_1_180px] rounded-lg border border-[#d5dae0] px-5 py-[18px]">
                  <div className="text-[15px] font-semibold">{t}</div>
                  <div className="mt-1.5 text-[13px] leading-relaxed text-sub">{d}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-[1200px] px-8 py-24">
          <div className="dot-grid-dark flex flex-wrap items-center justify-between gap-6 rounded-xl px-12 py-14">
            <div>
              <h2 className="m-0 text-[30px] font-semibold tracking-tight text-white">직접 요청해 보세요</h2>
              <p className="mt-2.5 text-[15px] text-[#b4bdc9]">"can 데이터로 학습할 시범 150개 골라줘" 한 줄이면 분석부터 승인 요청까지 30초 안에 끝납니다.</p>
            </div>
            <Link to="/demo" className="inline-flex h-12 items-center rounded-md bg-white px-[22px] text-[15px] font-semibold text-night hover:no-underline">데모 실행</Link>
          </div>
        </div>
      </section>
    </>
  )
}

function Loading({ error }: { error: string | null }) {
  return (
    <div className="mx-auto max-w-[1200px] px-8 py-14 text-sm text-sub">
      {error ? `데이터를 불러오지 못했습니다: ${error}` : '실험 데이터를 불러오는 중…'}
    </div>
  )
}
