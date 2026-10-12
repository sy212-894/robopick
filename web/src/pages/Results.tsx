import { useState } from 'react'
import { getOverview, getResults, type Collect, type Judge, type Results as R, type TableRow } from '../lib/api'
import { num, pct, pp, SET_NAMES, signed, useApi } from '../lib/fmt'

const isJudge = (x: unknown): x is Judge => typeof x === 'object' && x !== null && 'diff' in x

// 판정 문구 → 표시 배지. "더 나쁨"은 (전체 − 선별)처럼 앞쪽이 낮다는 뜻이라 문맥별 이름을 받는다
function Badge({ j, negLabel }: { j: Judge; negLabel?: string }) {
  const yes = j.verdict.startsWith('차이 있음') || (j.verdict === '더 나쁨' && !!negLabel)
  const label = j.verdict.startsWith('차이 있음') ? '차이 있음' : j.verdict === '더 나쁨' ? negLabel ?? '더 나쁨' : j.verdict
  return (
    <span title={j.note} className={`whitespace-nowrap rounded px-2.5 py-0.5 text-xs ${yes ? 'bg-ok-soft text-ok-ink' : 'bg-line-soft text-body'}`}>
      {label}
    </span>
  )
}

function SeedSigns({ j }: { j: Judge }) {
  const per = Object.values(j.per_seed_diff ?? {})
  if (!per.length) return <span className="text-[13px] text-sub">-</span>
  return (
    <div className="flex items-center gap-2.5">
      <span className="inline-flex gap-[3px]">
        {per.map((v, i) => <span key={i} className={`inline-block size-2.5 rounded-sm ${v > 0 ? 'bg-accent' : v < 0 ? 'bg-[#c4cad2]' : 'bg-line'}`} />)}
      </span>
      <span className="text-[13px]">{per.map((v) => signed(v)).join(', ')}</span>
    </div>
  )
}

function Kpi({ label, value, sub, accent }: { label: string; value: string; sub: string; accent?: boolean }) {
  return (
    <div className="rounded-lg bg-paper px-5 py-[18px]">
      <div className="text-[13px] text-sub">{label}</div>
      <div className={`mt-1.5 text-[30px] font-semibold ${accent ? 'text-accent' : ''}`}>{value}</div>
      <div className="mt-1 text-[13px] text-body">{sub}</div>
    </div>
  )
}

const ciText = (j: Judge, digits = 0) => `${signed(j.ci95[0], digits)} ~ ${signed(j.ci95[1], digits)}`

function Bars({ rows, title, sub }: { rows: TableRow[]; title: string; sub: string }) {
  const color = (k: string) => (k.startsWith('curated') ? '#1f5bd6' : k === 'train' ? '#39424e' : k.startsWith('random_1') ? '#9aa3ae' : '#b9c0c9')
  const sorted = [...rows].filter((r) => r.success_rate != null).sort((a, b) => (b.success_rate ?? 0) - (a.success_rate ?? 0))
  return (
    <>
      <h2 className="mt-12 text-xl font-semibold">{title}</h2>
      <p className="mt-1.5 text-sm text-sub">{sub}</p>
      <div className="mt-5 flex flex-col gap-3.5">
        {sorted.map((r) => (
          <div key={r.set} className="flex flex-wrap items-center gap-4">
            <div className="w-[220px] flex-none">
              <div className="text-sm font-medium">{SET_NAMES[r.set]?.name ?? r.set}{r.set === 'random_frames' ? ` ${r.n_demos}` : ''}</div>
              <div className="text-xs text-sub">{SET_NAMES[r.set]?.sub}</div>
            </div>
            <div className="relative h-[26px] flex-[1_1_360px] rounded-[3px] bg-[#f0f2f5]">
              <div className="absolute inset-y-0 left-0 rounded-[3px]" style={{ width: `${(r.success_rate ?? 0) * 100}%`, background: color(r.set) }} />
              {r.ci95 && <div className="absolute top-1/2 -mt-px h-0.5 bg-ink/55" style={{ left: `${r.ci95[0] * 100}%`, width: `${(r.ci95[1] - r.ci95[0]) * 100}%` }} />}
            </div>
            <div className="w-[130px] text-right text-sm tabular-nums">
              <span className="font-semibold">{pct(r.success_rate)}</span>{' '}
              {r.ci95 && <span className="text-xs text-sub">{Math.round(r.ci95[0] * 100)}–{pct(r.ci95[1])}</span>}
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

type Row = { name: string; kind: string; j: Judge; negLabel?: string }

function JudgeTable({ rows, digits = 0 }: { rows: Row[]; digits?: number }) {
  return (
    <>
      <h2 className="mt-12 text-xl font-semibold">판정</h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm tabular-nums">
          <thead>
            <tr className="text-left text-xs text-sub">
              <th className="border-b border-[#d5dae0] py-2.5 pr-3 font-medium">비교</th>
              <th className="border-b border-[#d5dae0] px-3 py-2.5 text-right font-medium">차이</th>
              <th className="border-b border-[#d5dae0] px-3 py-2.5 font-medium">95% 신뢰구간</th>
              <th className="border-b border-[#d5dae0] px-3 py-2.5 font-medium">시드별</th>
              <th className="border-b border-[#d5dae0] py-2.5 pl-3 font-medium">결과</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name + r.kind}>
                <td className="border-b border-line-soft py-3 pr-3">{r.name}<div className="mt-0.5 text-xs text-sub">{r.kind}</div></td>
                <td className="border-b border-line-soft px-3 py-3 text-right font-medium">{pp(r.j.diff, digits)}</td>
                <td className="border-b border-line-soft px-3 py-3 text-body">{ciText(r.j, digits)}</td>
                <td className="border-b border-line-soft px-3 py-3 text-body"><SeedSigns j={r.j} /></td>
                <td className="border-b border-line-soft py-3 pl-3"><Badge j={r.j} negLabel={r.negLabel} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function CanTab({ can }: { can: R['can'] }) {
  const p = can.paired
  const J = (k: string) => (isJudge(can.judgement?.[k]) ? (can.judgement![k] as Judge) : undefined)
  const gain = p?.gain_vs_random ?? J('gain_vs_random')
  const drop = p?.drop_vs_full ?? J('drop_vs_full')
  const early = J('early_gain_vs_random')
  const cur = can.table?.find((r) => r.set === 'curated_150')
  const rnd = can.table?.find((r) => r.set === 'random_150')
  const nTest = p ? Math.round(p.rates.curated_150.rollouts / p.rates.curated_150.seeds) : can.config?.rollout_n
  const pick = (k: 'effect_quality' | 'same_frames' | 'effect_allocation') => p?.[k] ?? J(k)
  const rows: Row[] = [
    gain && { name: '선별 − 무작위', kind: `주 판정 · ${p ? '짝지은 비교' : '비교'} · 1주차 목표 +5%p`, j: gain },
    drop && { name: '전체 − 선별', kind: `주 판정 · ${p ? '짝지은 비교' : '비교'} · 1주차 목표 하락 5%p 이내${drop.confirmed ? ' (충족)' : ''}`, j: drop, negLabel: '선별이 높음' },
    early && { name: `${can.config?.early_eval_epoch} epoch 선별 − 무작위`, kind: '학습 속도', j: early },
    pick('effect_quality') && { name: '선별 − 조건별 균등', kind: '품질 점수 효과', j: pick('effect_quality')! },
    pick('same_frames') && { name: '선별 − 프레임 맞춘 무작위', kind: '같은 프레임 수', j: pick('same_frames')! },
    pick('effect_allocation') && { name: '조건별 균등 − 무작위', kind: '칸별 배분 효과', j: pick('effect_allocation')! },
  ].filter(Boolean) as Row[]
  return (
    <section className="pt-8">
      <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
        {gain && <Kpi accent label="주 판정 · 선별 − 무작위" value={pp(gain.diff)} sub={`신뢰구간 ${ciText(gain)} · ${gain.verdict.startsWith('차이 있음') ? '차이 있음' : gain.verdict}`} />}
        {drop && <Kpi label="주 판정 · 전체 − 선별" value={pp(drop.diff)} sub={drop.confirmed ? `1주차 기준 충족 · 하락 5%p 이내 (신뢰구간 끝 ${signed(drop.ci95[1], 1)}%p)` : drop.diff < 0 ? '선별이 더 높음 · 하락 없음' : drop.verdict} />}
        {early && <Kpi label={`학습 속도 · ${can.config?.early_eval_epoch} epoch`} value={pp(early.diff)} sub={`선별 ${pct(cur?.early?.success_rate)} vs 무작위 ${pct(rnd?.early?.success_rate)}`} />}
      </div>
      <div className="mt-4 rounded-md bg-warn-soft px-3.5 py-2.5 text-[13px] text-warn-ink">시험 {nTest}개 기준</div>
      {p ? (
        <Bars
          rows={Object.entries(p.rates).map(([set, v]) => ({ set, n_demos: can.table?.find((r) => r.set === set)?.n_demos ?? 0, success: v.success, rollouts: v.rollouts, success_rate: v.success / v.rollouts, ci95: wilson(v.success, v.rollouts) }))}
          title="묶음별 최종 성공률"
          sub={`짝지은 재평가 · 시험 ${nTest}개 x 시드 ${p.rates.curated_150.seeds}개 · ${can.config?.num_epochs} epoch · 가는 선은 95% 신뢰구간`}
        />
      ) : (
        can.table && <Bars rows={can.table} title="묶음별 최종 성공률" sub={`학습 직후 평가 · ${can.config?.num_epochs} epoch · 시드 합계 · 가는 선은 95% 신뢰구간`} />
      )}
      <JudgeTable rows={rows} />
    </section>
  )
}

function BudgetTab({ b }: { b: Collect }) {
  const ov = useApi(getOverview)
  const trainFrames = ov.data?.train.total_frames
  const cur = b.sets?.curated_135
  const rnd = b.sets?.random_135
  const trained = b.status === 'complete' || b.status === 'partial'
  const J = (k: string) => (isJudge(b.judgement?.[k]) ? (b.judgement![k] as Judge) : undefined)
  const gain = J('paired_gain_vs_random')
  const drop = J('paired_drop_vs_full')
  const early = J('paired_early_gain_vs_random')
  // 짝지은 비교의 성공률(전체 270 포함)로 막대를 그린다. 없으면 결과 조회 도구의 표
  const pr = b.paired?.rates
  const barRows: TableRow[] = pr
    ? Object.entries(pr).map(([set, v]) => ({ set, n_demos: b.sets?.[set]?.n_demos ?? 270, success: v.success, rollouts: v.rollouts, success_rate: v.success / v.rollouts, ci95: wilson(v.success, v.rollouts) }))
    : (b.table ?? [])
  const rows: Row[] = [
    gain && { name: '선별 135 − 무작위 135', kind: '주 판정 · 짝지은 비교 · 1주차 목표 +5%p 이상', j: gain },
    drop && { name: '전체 270 − 선별 135', kind: `주 판정 · 짝지은 비교 · 1주차 목표 하락 5%p 이내${drop.confirmed ? ' (충족)' : ''}`, j: drop, negLabel: '선별이 높음' },
    early && { name: '200 epoch 선별 − 무작위', kind: '보조 · 학습 속도', j: early },
  ].filter(Boolean) as Row[]
  return (
    <section className="pt-8">
      <div className="rounded-[10px] border border-dashed border-[#b5bdc7] p-8">
        <div className="flex flex-wrap items-center gap-2.5">
          <h2 className="m-0 text-xl font-semibold">예산 135개 (학습 후보의 50%)</h2>
          <span className="rounded-full bg-line-soft px-2.5 py-0.5 text-xs text-body">{trained ? '결과 있음' : '실험 진행 중'}</span>
        </div>
        <p className="mt-2.5 max-w-[760px] text-[15px] leading-relaxed text-body">
          학습 후보의 50% 이하 시범으로 전체 대비 하락 5%p 이내를 확인하는 실험입니다. 본 실험과 같은 분석·설정으로, 예산만 135개로 설정합니다.
        </p>
        <div className="mt-6 grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
          <div className="rounded-lg bg-paper px-[18px] py-4"><div className="text-[13px] text-sub">선별 135</div><div className="mt-1 text-xl font-semibold">{num(cur?.total_frames)} 프레임</div><div className="mt-0.5 text-[13px] text-body">전체 프레임의 {cur && trainFrames ? pct(cur.total_frames / trainFrames) : '-'}</div></div>
          <div className="rounded-lg bg-paper px-[18px] py-4"><div className="text-[13px] text-sub">무작위 135</div><div className="mt-1 text-xl font-semibold">{num(rnd?.total_frames)} 프레임</div><div className="mt-0.5 text-[13px] text-body">같은 개수 기준선</div></div>
          <div className="rounded-lg bg-paper px-[18px] py-4"><div className="text-[13px] text-sub">평가</div><div className="mt-1 text-xl font-semibold">시드 3 × 시험 {b.plan_config?.rollout_n}</div><div className="mt-0.5 font-mono text-[13px] text-body">계획 {b.fingerprint}</div></div>
        </div>
        <p className="mt-5 text-[13px] text-sub">판정 기준(결과 전에 정함): 같은 시험 위치끼리 짝지은 비교, 세 시드 모두 같은 방향일 때만 "차이 있음". {trained ? '' : '결과: 실험이 끝나면 표시'}</p>
      </div>
      {trained && (
        <>
          <div className="mt-8 grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            {gain && <Kpi accent label="주 판정 · 선별 − 무작위" value={pp(gain.diff, 1)} sub={`신뢰구간 ${ciText(gain, 1)} · ${gain.verdict.startsWith('차이 있음') ? '차이 있음' : gain.verdict}`} />}
            {drop && <Kpi label="주 판정 · 전체 − 선별" value={pp(drop.diff, 1)} sub={drop.confirmed ? `1주차 기준 충족 · 하락 5%p 이내 (신뢰구간 끝 ${signed(drop.ci95[1], 1)}%p)` : `${drop.verdict} · 기준 확정 못 함`} />}
            {early && <Kpi label="학습 속도 · 200 epoch 선별 − 무작위" value={pp(early.diff, 1)} sub={early.verdict.startsWith('차이 있음') ? '차이 있음' : early.verdict} />}
          </div>
          <Bars rows={barRows} title="묶음별 최종 성공률" sub="시드 합계 · 가는 선은 95% 신뢰구간 · 전체 270은 Can 최종 평가의 같은 모델을 같은 시험 위치로 짝지어 비교" />
          <JudgeTable rows={rows} digits={1} />
          <p className="mt-5 max-w-[760px] text-[13px] leading-relaxed text-sub">
            135개 실험의 성공률이 150개 실험보다 전반적으로 높지만, 서로 다른 실험끼리의 비교라 학습 흔들림과 묶음 뽑기 운이 섞여 있습니다. 판정은 같은 실험 안에서 같은 시드·같은 시험 위치끼리만 비교합니다.
          </p>
        </>
      )}
    </section>
  )
}

// 성공률 95% 신뢰구간 (윌슨 방법, 결과 조회 도구와 같은 식)
function wilson(k: number, n: number): [number, number] {
  if (!n) return [0, 0]
  const z = 1.96
  const p = k / n
  const d = 1 + (z * z) / n
  const c = (p + (z * z) / (2 * n)) / d
  const h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d
  return [Math.max(0, c - h), Math.min(1, c + h)]
}

function SquareTab({ sq }: { sq: Collect }) {
  const J = (k: string) => (isJudge(sq.judgement?.[k]) ? (sq.judgement![k] as Judge) : undefined)
  const gain = J('paired_gain_vs_random') ?? J('gain_vs_random')
  const drop = J('paired_drop_vs_full') ?? J('drop_vs_full')
  const train = sq.table?.find((r) => r.set === 'train')
  const validity = typeof sq.judgement?.validity === 'string' ? (sq.judgement.validity as string) : null
  const rows: Row[] = [
    gain && { name: '선별 − 무작위', kind: `주 판정 · 짝지은 비교 · ${sq.config?.num_epochs} epoch`, j: gain },
    drop && { name: '전체 − 선별', kind: '주 판정 · 짝지은 비교', j: drop, negLabel: '선별이 높음' },
    J('paired_early_gain_vs_random') && { name: `${sq.config?.early_eval_epoch} epoch 선별 − 무작위`, kind: '보조 · 학습 속도', j: J('paired_early_gain_vs_random')! },
    J('paired_both_gain_vs_random') && { name: '선별 − 무작위 (두 시점 합침)', kind: '보조 · 결과를 본 뒤 추가', j: J('paired_both_gain_vs_random')! },
  ].filter(Boolean) as Row[]
  return (
    <section className="pt-8">
      <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
        {gain && <Kpi accent label="주 판정 · 선별 − 무작위" value={pp(gain.diff, 1)} sub={`신뢰구간 ${signed(gain.ci95[0], 1)} ~ ${signed(gain.ci95[1], 1)} · ${gain.verdict.startsWith('차이 있음') ? '차이 있음' : gain.verdict}`} />}
        {drop && <Kpi label="주 판정 · 전체 − 선별" value={pp(drop.diff, 1)} sub={`${drop.verdict} · ${drop.diff < 0 ? '하락 없음' : ''}`} />}
        {train && <Kpi label="전체 데이터 기준선" value={pct(train.success_rate, 1)} sub={validity ?? (Math.abs((train.success_rate ?? 0) - 0.2) < 0.02 ? '무효 기준(20% 미만) 경계' : '무효 기준(20% 미만) 통과')} />}
      </div>
      <p className="mt-5 max-w-[760px] text-[15px] leading-relaxed text-body">
        너트를 기둥에 끼우는 Square는 Can보다 훨씬 어렵습니다. {sq.config?.num_epochs} epoch에서도 성공률이 20%대이고 학습 시점마다 크게 오르내립니다. 선별 쪽이 일관되게 높았지만 확정의 정도는 약해 보조 근거로 씁니다.
      </p>
      {sq.table && <Bars rows={sq.table} title="묶음별 최종 성공률" sub={`${sq.config?.num_epochs} epoch · 시드 합계 · 가는 선은 95% 신뢰구간`} />}
      <JudgeTable rows={rows} digits={1} />
    </section>
  )
}

const TABS = [['can', 'Can · 150개'], ['budget', 'Can · 135개'], ['square', 'Square · 150개']] as const

export default function Results() {
  const { data, error } = useApi(getResults)
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('can')
  const canGain = data?.can.paired?.gain_vs_random?.diff
  const sqGain = (data?.square.judgement?.paired_gain_vs_random as Judge | undefined)?.diff
  return (
    <>
      <section className="dot-grid-dark text-[#e9edf2]">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-end justify-between gap-10 px-8 pb-14 pt-16">
          <div className="min-w-0 flex-[1_1_520px]">
            <div className="font-mono text-xs text-[#8b96a5]">BC-RNN · 시드 3개 · 짝지은 비교</div>
            <h1 className="mt-3.5 text-[40px] font-semibold tracking-tight text-white">실험 결과</h1>
            <p className="mt-3.5 max-w-[640px] text-base leading-relaxed text-[#b4bdc9]">
              같은 정책과 같은 설정으로 묶음마다 학습하고, 시뮬레이터에서 같은 시험 위치로 성공률을 측정합니다. 미리 정한 규칙으로 판정을 진행합니다.
            </p>
          </div>
          <div className="flex flex-wrap overflow-hidden rounded-lg border border-[#26303b]">
            <div className="border-r border-[#26303b] px-[22px] py-4"><div className="font-mono text-[11px] text-[#8b96a5]">Can 선별−무작위</div><div className="mt-1.5 text-[26px] font-semibold text-[#7aa5ff]">{pp(canGain)}</div></div>
            <div className="border-r border-[#26303b] px-[22px] py-4"><div className="font-mono text-[11px] text-[#8b96a5]">Square 선별−무작위</div><div className="mt-1.5 text-[26px] font-semibold text-[#7aa5ff]">{pp(sqGain, 1)}</div></div>
            <div className="px-[22px] py-4"><div className="font-mono text-[11px] text-[#8b96a5]">과제</div><div className="mt-1.5 text-[26px] font-semibold text-white">Can · Square</div></div>
          </div>
        </div>
      </section>
      <main className="mx-auto max-w-[1200px] px-8 pb-24 pt-2">
        <div role="tablist" aria-label="실험" className="mt-8 flex flex-wrap gap-1 border-b border-line">
          {TABS.map(([k, label]) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
              className={`-mb-px h-11 cursor-pointer border-b-2 px-[18px] text-[15px] ${tab === k ? 'border-ink font-semibold text-ink' : 'border-transparent text-sub'}`}>
              {label}
            </button>
          ))}
        </div>
        {!data && <p className="mt-8 text-sm text-sub">{error ? `불러오지 못했습니다: ${error}` : '불러오는 중…'}</p>}
        {data && tab === 'can' && <CanTab can={data.can} />}
        {data && tab === 'budget' && <BudgetTab b={data.can_budget} />}
        {data && tab === 'square' && <SquareTab sq={data.square} />}
      </main>
    </>
  )
}
