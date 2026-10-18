import { useState, type ReactNode } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'

// 데이터셋 상세 (can_mh, square_mh, lift_mh). 숫자는 docs/와 results/의 실험 기록에서 옮겼다

type Stat = { label: string; value: string; note: string }
type Signal = [name: string, r: number, used: boolean]
type Detail = {
  id: string
  title: string
  intro: string
  stats: Stat[]
  object: string // 진단 그림 설명에 쓰는 물체 이름
  cells: Record<string, number>
  diagText: string
  diagNote: string
  howText: string
  signals: Signal[]
  signalCaption: string
  lengths: [number, number, number] // 숙련 / 보통 / 미숙 평균 프레임
  lengthNote: string
  tabs: { id: string; label: string }[]
  body: ReactNode
}

const ORDER = ['x0y2', 'x1y2', 'x2y2', 'x0y1', 'x1y1', 'x2y1', 'x0y0', 'x1y0', 'x2y0']
const minus = (r: number) => (r < 0 ? '−' : '+') + Math.abs(r).toFixed(2)

// ---------- 공통 조각 ----------

function Hero({ d }: { d: Detail }) {
  return (
    <section className="dot-grid-dark text-white">
      <div className="mx-auto max-w-[1200px] px-8 pt-12 pb-14">
        <div className="mb-4 text-sm text-muted">
          <Link to="/datasets" className="text-[#aeb7c2]">
            데이터셋
          </Link>{' '}
          / {d.id}
        </div>
        <h1 className="m-0 mb-2.5 text-[40px] font-bold">{d.title}</h1>
        <p className="m-0 max-w-[680px] text-base leading-[1.7] text-[#c4ccd6]">{d.intro}</p>
        <div className="mt-9 grid grid-cols-2 gap-4 lg:grid-cols-4">
          {d.stats.map((s) => (
            <div key={s.label} className="border-t border-[#263140] pt-3.5">
              <div className="text-[13px] text-muted">{s.label}</div>
              <div className="mt-1 text-[32px] font-bold">{s.value}</div>
              <div className="text-[13px] text-[#aeb7c2]">{s.note}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function SubNav({ tabs }: { tabs: Detail['tabs'] }) {
  const [on, setOn] = useState(tabs[0].id)
  return (
    <nav aria-label="이 페이지" className="sticky top-0 z-10 border-b border-line bg-white">
      <div className="mx-auto flex max-w-[1200px] gap-7 px-8 text-[15px]">
        {tabs.map((t) => (
          <a
            key={t.id}
            href={`#${t.id}`}
            onClick={(e) => {
              e.preventDefault()
              setOn(t.id)
              document.getElementById(t.id)?.scrollIntoView({ behavior: 'smooth' })
            }}
            className={`border-b-2 py-4 hover:no-underline ${on === t.id ? 'border-ink font-medium text-ink' : 'border-transparent text-[#475060]'}`}
          >
            {t.label}
          </a>
        ))}
      </div>
    </nav>
  )
}

function Diagnosis({ d }: { d: Detail }) {
  const values = Object.values(d.cells)
  const mean = values.reduce((a, b) => a + b, 0) / values.length
  return (
    <section id="diag" className="mx-auto grid max-w-[1200px] scroll-mt-14 gap-x-6 gap-y-8 px-8 pt-16 pb-6 lg:grid-cols-12">
      <div className="lg:col-span-5">
        <h2 className="m-0 mb-3.5 text-[26px] font-bold">진단</h2>
        <p className="m-0 mb-5 text-[15px] leading-[1.75] text-body">{d.diagText}</p>
        <div className="rounded-lg bg-accent-soft px-4 py-3.5 text-sm leading-[1.7] text-accent-ink">{d.diagNote}</div>
      </div>
      <figure className="m-0 lg:col-span-6 lg:col-start-7">
        <div className="grid grid-cols-3 gap-1.5">
          {ORDER.map((c) => {
            const n = d.cells[c]
            const low = n < mean / 2
            const dense = n > mean * 2
            const cls = low ? 'bg-accent-soft text-accent-ink' : dense ? 'bg-ink text-white' : 'bg-line-soft text-ink'
            return (
              <div key={c} className={`flex h-24 flex-col justify-between rounded-md px-3 py-2.5 ${cls}`}>
                <span className="font-mono text-xs">{c}</span>
                <span className="text-[26px] font-bold">{n}</span>
              </div>
            )
          })}
        </div>
        <figcaption className="mt-2.5 text-[13px] text-sub">
          {d.object} 처음 위치별 시범 수 (학습 후보 270개).{' '}
          {values.some((n) => n < mean / 2) ? '파란 칸은 평균의 절반 미만' : `평균 ${Math.round(mean)}개, 가장 적은 칸 ${Math.min(...values)}개`}
        </figcaption>
      </figure>
    </section>
  )
}

function How({ d }: { d: Detail }) {
  const max = Math.max(...d.lengths)
  const colors = ['bg-ok', 'bg-muted', 'bg-danger']
  return (
    <section id="how" className="mx-auto max-w-[1200px] scroll-mt-14 px-8 pt-[72px] pb-6">
      <h2 className="m-0 mb-3.5 text-[26px] font-bold">고르는 방법</h2>
      <p className="m-0 mb-7 max-w-[760px] text-[15px] leading-[1.75] text-body">{d.howText}</p>
      <div className="grid gap-8 lg:grid-cols-2">
        <figure className={`${box} m-0`}>
          <div className="mb-4 text-[15px] font-semibold">신호와 숙련도의 순위 상관</div>
          <div className="flex flex-col gap-3">
            {d.signals.map(([name, r, used]) => (
              <div key={name} className="grid grid-cols-[120px_minmax(0,1fr)_56px_40px] items-center gap-3 text-sm">
                <span>{name}</span>
                <div className="h-3 bg-line-soft">
                  <div className={`h-3 ${used ? 'bg-accent' : 'bg-field'}`} style={{ width: `${(Math.abs(r) / 0.8) * 100}%` }} />
                </div>
                <span className="text-right font-mono">{minus(r)}</span>
                <span className={`text-xs ${used ? 'text-accent-ink' : 'text-muted'}`}>{used ? '사용' : '제외'}</span>
              </div>
            ))}
          </div>
          <figcaption className="mt-3.5 text-[13px] text-sub">{d.signalCaption}</figcaption>
        </figure>
        <figure className={`${box} m-0`}>
          <div className="mb-4 text-[15px] font-semibold">숙련도별 시범 길이 (평균 프레임)</div>
          <div className="flex flex-col gap-3.5">
            {['숙련', '보통', '미숙'].map((k, i) => (
              <div key={k} className="grid grid-cols-[60px_minmax(0,1fr)_48px] items-center gap-3 text-sm">
                <span>{k}</span>
                <div className="h-[18px] bg-line-soft">
                  <div className={`h-[18px] ${colors[i]}`} style={{ width: `${(d.lengths[i] / max) * 100}%` }} />
                </div>
                <span className="text-right font-mono">{d.lengths[i]}</span>
              </div>
            ))}
          </div>
          <p className="m-0 mt-[18px] text-sm leading-[1.7] text-body">{d.lengthNote}</p>
        </figure>
      </div>
    </section>
  )
}

const box = 'rounded-[10px] border border-line p-[22px]'
const sectionCls = 'mx-auto max-w-[1200px] scroll-mt-14 px-8 pt-[72px] pb-24'
const h2 = 'm-0 mb-3.5 text-[26px] font-bold'
const lead = 'm-0 mb-6 max-w-[760px] text-[15px] leading-[1.75] text-body'

// ---------- Can: 개수별 표 + 예산 60 기준선 막대 ----------

const CAN_EXPS = [
  { n: '150 (56%)', cur: '77.3%', rnd: '63.7%', full: '74.7%', gain: '+13.7%p 높음 · 시드 3개 중 2개 높음, 1개 같음', drop: '전체보다 2.7%p 높음', up: true },
  { n: '150, 시드 5개', cur: '78.8%', rnd: '58.8%', full: '66.6%', gain: '+20.0%p 높음 · 시드 5개 중 4개 높음, 1개 같음', drop: '전체보다 12.2%p 높음', up: true },
  { n: '135 (50%)', cur: '87.7%', rnd: '82.3%', full: '74.7%', gain: '+5.3%p 높음 · 시드 3개 중 2개 높음', drop: '전체보다 13.0%p 높음', up: true },
  { n: '60 (22%)', cur: '72.3%', rnd: '51.3%', full: '74.7%', gain: '+21.0%p 높음 · 시드 3개 모두 높음', drop: '전체의 97% 수준', up: false },
]
const MOSTLY = '대체로 높음 · 3개 중 2개'
const ALL3 = '높음 · 3개 모두'
const CAN_BARS: [string, number, string][] = [
  ['우리 방법', 72.3, ''],
  ['멈춤 비율만', 63.3, MOSTLY],
  ['길이 뺀 3신호', 60.7, MOSTLY],
  ['그리퍼만', 54.7, MOSTLY],
  ['무작위', 51.3, ALL3],
  ['길이만', 45.3, ALL3],
  ['이동 경로만', 44.7, ALL3],
  ['칸별 균등 무작위', 43.7, ALL3],
  ['위치 다양성', 41.3, ALL3],
  ['가장 긴 시범', 28.0, ALL3],
]
const EXP_COLS = 'grid grid-cols-[170px_120px_120px_120px_minmax(0,1fr)_minmax(0,1fr)] gap-3'

function CanExp() {
  return (
    <section id="exp" className={sectionCls}>
      <h2 className={h2}>학습 실험</h2>
      <p className={lead}>
        robomimic BC-RNN, 400 epoch. 시험 100회는 시작 위치와 행동 난수를 고정해 모든 모델이 같은 시험을 치르고, 같은 위치끼리 짝지어 비교합니다.
      </p>
      <div className="mb-8 overflow-x-auto rounded-[10px] border border-line">
        <div className="min-w-[900px]">
          <div className="px-5 pt-[18px] pb-3.5 text-[15px] font-semibold">개수별 성공률 비교 (시험 100회, 시드 평균)</div>
          <div className={`${EXP_COLS} bg-paper px-5 py-3 text-[13px] text-sub`}>
            <span>개수 (후보 대비)</span>
            <span>선별</span>
            <span>무작위</span>
            <span>전체 270</span>
            <span>무작위 대비</span>
            <span>전체 대비</span>
          </div>
          {CAN_EXPS.map((e) => (
            <div key={e.n} className={`${EXP_COLS} items-center border-t border-line-soft px-5 py-3.5 text-sm`}>
              <span className="font-semibold">{e.n}</span>
              <span className="font-mono">{e.cur}</span>
              <span className="font-mono text-sub">{e.rnd}</span>
              <span className="font-mono text-sub">{e.full}</span>
              <span>{e.gain}</span>
              <span className={e.up ? 'text-ok-ink' : 'text-ink'}>{e.drop}</span>
            </div>
          ))}
        </div>
      </div>
      <figure className={`${box} m-0`}>
        <div className="mb-4 text-[15px] font-semibold">예산 60개 성공률: 다른 선별 방법과 비교</div>
        <div className="flex flex-col gap-2.5">
          {CAN_BARS.map(([name, v, verdict], i) => (
            <div key={name} className="grid grid-cols-[120px_minmax(0,1fr)_48px] items-center gap-3 text-sm sm:grid-cols-[160px_minmax(0,1fr)_56px_190px]">
              <span className={i === 0 ? 'font-semibold' : ''}>{name}</span>
              <div className="h-3.5 bg-line-soft">
                <div className={`h-3.5 ${i === 0 ? 'bg-accent' : verdict === MOSTLY ? 'bg-muted' : 'bg-field'}`} style={{ width: `${(v / 80) * 100}%` }} />
              </div>
              <span className="text-right font-mono">{v.toFixed(1)}</span>
              <span className="hidden text-xs text-sub sm:block">{verdict}</span>
            </div>
          ))}
        </div>
      </figure>
    </section>
  )
}

// ---------- Square: 묶음별 성공률 + 비교 표 ----------

const SQ_SETS: [string, number, string, boolean][] = [
  ['선별 150', 28.7, '11 / 15 / 17', true],
  ['전체 270', 20.0, '7 / 8 / 15', false],
  ['무작위 150', 18.0, '5 / 13 / 9', false],
]
const SQ_ROWS: [string, string, string, boolean][] = [
  ['무작위 대비', '+10.7%p', '높음 · 시드 3개 모두', true],
  ['전체 대비', '+8.7%p', '전체보다 높음', true],
  ['400 epoch에서 무작위 대비', '+1.1%p', '높음 · 시드 3개 중 2개', false],
]

function SquareExp() {
  return (
    <section id="exp" className={sectionCls}>
      <h2 className={h2}>학습 실험</h2>
      <p className={lead}>
        robomimic BC-RNN. Square는 어려운 동작이기에 400 epoch에서 성공률이 낮아 600 epoch까지 더 많이 학습했고, 시험 50회로 평가했습니다. 같은 시험 위치끼리 짝지어 비교합니다.
      </p>
      <div className="grid gap-8 lg:grid-cols-2">
        <figure className={`${box} m-0`}>
          <div className="mb-4 text-[15px] font-semibold">묶음별 성공률 (600 epoch, 시드 3 × 시험 50)</div>
          <div className="flex flex-col gap-3.5">
            {SQ_SETS.map(([name, v, seeds, ours]) => (
              <div key={name} className="grid grid-cols-[90px_minmax(0,1fr)_64px_110px] items-center gap-3 text-sm">
                <span className={ours ? 'font-semibold' : ''}>{name}</span>
                <div className="h-[18px] bg-line-soft">
                  <div className={`h-[18px] ${ours ? 'bg-accent' : 'bg-field'}`} style={{ width: `${(v / 40) * 100}%` }} />
                </div>
                <span className="text-right font-mono">{v.toFixed(1)}%</span>
                <span className="font-mono text-xs text-sub">{seeds}</span>
              </div>
            ))}
          </div>
          <figcaption className="mt-3.5 text-[13px] text-sub">오른쪽 숫자는 시드 1 / 2 / 3의 성공 횟수 (각 50회)</figcaption>
        </figure>
        <div className="overflow-hidden rounded-[10px] border border-line">
          <div className="grid grid-cols-[minmax(0,1fr)_90px_150px] gap-3 bg-paper px-5 py-3 text-[13px] text-sub">
            <span>비교</span>
            <span>차이</span>
            <span>결과</span>
          </div>
          {SQ_ROWS.map(([k, v, r, strong]) => (
            <div key={k} className="grid grid-cols-[minmax(0,1fr)_90px_150px] gap-3 border-t border-line-soft px-5 py-3.5 text-sm">
              <span>{k}</span>
              <span className="font-mono">{v}</span>
              <span className={strong ? 'text-ok-ink' : 'text-body'}>{r}</span>
            </div>
          ))}
          <p className="m-0 border-t border-line-soft px-5 py-3.5 text-[13px] leading-[1.7] text-sub">
            선별은 세 시드 모두 무작위보다 높았습니다 (+12, +4, +16%p). 데이터를 56%만 쓰고도 전체보다 낮지 않았습니다.
          </p>
        </div>
      </div>
    </section>
  )
}

// ---------- Lift: 학습 실험 대신 직접 확인하는 방법 ----------

const LIFT_STEPS = [
  ['01', '선별하기에서 키트 받기', '기본 150개로 고르면 데이터 파일과 노트북 두 종류가 함께 나옵니다.'],
  ['02', '비교 노트북 실행', '선별·무작위·전체를 같은 설정과 같은 시험 위치로 학습하고 평가합니다.'],
  ['03', '결과 올리기', '무작위보다 나은지, 전체 대비 하락이 5%p 이내인지 판정 카드로 받습니다.'],
]

function LiftCheck() {
  return (
    <section id="check" className={sectionCls}>
      <h2 className={h2}>학습으로 확인하기</h2>
      <p className={`${lead} mb-7`}>
        Lift는 성공률이 쉽게 높아지는 작업이라, 몇 개를 쓸지는 직접 비교해 보고 정하는 편이 정확합니다. 학습 키트의 비교 노트북이 선별, 무작위, 전체를 같은 조건으로 학습하고, 결과 파일을 올리면 같은 기준으로 판정합니다.
      </p>
      <div className="grid gap-5 md:grid-cols-3">
        {LIFT_STEPS.map(([n, t, d]) => (
          <div key={n} className={box}>
            <div className="mb-2 font-mono text-[13px] text-sub">{n}</div>
            <div className="mb-2 text-base font-semibold">{t}</div>
            <p className="m-0 text-sm leading-[1.7] text-body">{d}</p>
          </div>
        ))}
      </div>
      <div className="mt-7">
        <Link
          to="/select?q=lift 데이터로 학습할 시범 골라줘"
          className="inline-flex h-12 items-center rounded-md bg-ink px-[22px] text-base font-medium text-white hover:no-underline"
        >
          Lift로 선별 시작
        </Link>
      </div>
    </section>
  )
}

// ---------- 데이터별 내용 ----------

const CAN_SIG: Signal[] = [['시범 길이', -0.72, true], ['멈춤 비율', -0.44, true], ['이동 경로 길이', -0.42, true], ['그리퍼 여닫기', -0.3, true], ['동작 거칠기', -0.08, false]]
const EXP_TABS = [
  { id: 'diag', label: '진단' },
  { id: 'how', label: '고르는 방법' },
  { id: 'exp', label: '학습 실험' },
]

const DETAILS: Record<string, Detail> = {
  can_mh: {
    id: 'can_mh',
    title: 'Can · 여러 사람',
    intro: '캔을 집어 맞는 칸으로 옮기는 robomimic 작업. 숙련도가 다른 6명이 모은 성공 시범 300개(학습 후보 270, 검증 30)를 사용합니다.',
    stats: [
      { label: '추천 개수', value: '135', note: '후보의 50%, 하락 기준 충족' },
      { label: '선별 135 vs 전체 270', value: '87.7 / 74.7%', note: '시드 3 × 시험 100' },
      { label: '품질 점수 효과', value: '+22.7%p', note: '같은 칸 배분의 무작위 대비' },
      { label: '키트 재현', value: '100 / 100', note: '시험별 결과 일치 (T4)' },
    ],
    object: '캔',
    cells: { x0y0: 10, x1y0: 39, x2y0: 7, x0y1: 28, x1y1: 92, x2y1: 38, x0y2: 5, x1y2: 38, x2y2: 13 },
    diagText: '캔의 처음 위치를 같은 넓이 칸 9개로 나눴습니다. 가운데 칸에 92개가 몰렸고, 네 모서리는 평균(30개)의 절반에 못 미칩니다. 거의 같은 시범(손끝 경로 평균 거리 2cm 미만)은 없었습니다. 가장 가까운 쌍도 2.6cm 떨어져 있습니다.',
    diagNote: '수집 계획: 모서리 4칸에 각각 17~25개를 더 모으면 평균 수준이 됩니다.',
    howText: '누가 잘했는지 라벨이 없어도, 로봇이 움직인 기록으로 품질을 알 수 있습니다. 능숙한 사람일수록 짧게 끝내고 덜 머뭇거리고 덜 돌아갑니다. 신호 다섯 가지를 실제 숙련도와 비교해 맞는 네 가지만 씁니다. 위치 칸마다 시범 수에 비례해 개수를 나누고, 칸 안에서 품질 점수 순으로 고릅니다.',
    signals: CAN_SIG,
    signalCaption: '스피어만 순위 상관, 학습 후보 270개. Square, Lift에서도 같은 네 신호가 같은 방향',
    lengths: [143, 181, 301],
    lengthNote: '숙련도 라벨은 각 90개씩입니다. 라벨은 선별에 쓰지 않고, 고른 결과를 확인하는 데만 씁니다 (규칙 점검: 점수 상위 절반의 숙련자 비율 56%, 하위 10%).',
    tabs: EXP_TABS,
    body: <CanExp />,
  },
  square_mh: {
    id: 'square_mh',
    title: 'Square · 여러 사람',
    intro: '사각 너트를 집어 기둥에 끼우는 robomimic 작업. Can보다 정밀한 작업이라 시범도 깁니다. 숙련도가 다른 6명이 모은 성공 시범 300개(학습 후보 270, 검증 30)를 사용합니다.',
    stats: [
      { label: '추천 개수', value: '150', note: '후보의 56%, 하락 기준 충족' },
      { label: '선별 vs 무작위 150', value: '29 / 18%', note: '+10.7%p 높음' },
      { label: '전체 270', value: '20%', note: '선별보다 낮음' },
      { label: '규칙 점검', value: '−0.71', note: '품질 점수와 숙련도 상관' },
    ],
    object: '너트',
    cells: { x0y0: 6, x1y0: 33, x2y0: 9, x0y1: 28, x1y1: 115, x2y1: 49, x0y2: 9, x1y2: 14, x2y2: 7 },
    diagText: '너트의 처음 위치를 같은 넓이 칸 9개로 나눴습니다. 가운데 칸에 115개가 몰려 Can보다 더 치우쳤고, 다섯 칸이 평균(30개)의 절반에 못 미칩니다. 거의 같은 시범(손끝 경로 평균 거리 2cm 미만)은 없었고, 가장 가까운 쌍은 2.1cm 떨어져 있습니다.',
    diagNote: '수집 계획: 부족한 5칸에 각각 16~24개를 더 모으면 평균 수준이 됩니다.',
    howText: '길이, 멈춤 비율, 이동 경로 길이, 그리퍼 여닫기 네 신호를 사용합니다. 모두 같은 방향으로 숙련도와 일치합니다.',
    signals: [['시범 길이', -0.69, true], ['이동 경로 길이', -0.65, true], ['멈춤 비율', -0.45, true], ['그리퍼 여닫기', -0.25, true], ['동작 거칠기', 0.12, false]],
    signalCaption: '스피어만 순위 상관, 학습 후보 270개. 동작 거칠기는 방향이 반대(+0.12)',
    lengths: [187, 267, 353],
    lengthNote: '숙련도 라벨은 각 90개씩이며 선별에는 쓰지 않습니다. 규칙 점검: 점수 상위 절반의 숙련자 비율 61%, 하위 6%.',
    tabs: EXP_TABS,
    body: <SquareExp />,
  },
  lift_mh: {
    id: 'lift_mh',
    title: 'Lift · 여러 사람',
    intro: '탁자 위 큐브를 집어 들어 올리는 robomimic 작업. 가장 짧고 쉬운 작업이라 시범끼리 서로 많이 유사합니다. 숙련도가 다른 6명이 모은 성공 시범 300개(학습 후보 270, 검증 30)를 사용합니다.',
    stats: [
      { label: '기본 개수', value: '150', note: '비교 학습으로 조정' },
      { label: '거의 같은 시범', value: '632쌍', note: '가장 가까운 쌍 0.8cm' },
      { label: '위치 편중', value: '없음', note: '9칸 모두 20개 이상' },
      { label: '규칙 점검', value: '−0.71', note: '품질 점수와 숙련도 상관' },
    ],
    object: '큐브',
    cells: { x0y0: 28, x1y0: 27, x2y0: 37, x0y1: 20, x1y1: 29, x2y1: 41, x0y2: 27, x1y2: 27, x2y2: 34 },
    diagText: 'Can, Square와 반대입니다. 큐브 처음 위치는 9칸에 고르게 퍼져 있어 부족한 칸이 없습니다. 대신 손끝 경로가 2cm 안으로 겹치는 시범 쌍이 632개 있습니다. 쉬운 작업이라 누가 하든 비슷하게 움직이기 때문입니다.',
    diagNote: '거의 같은 시범 쌍은 진단 카드에서 목록으로 확인할 수 있습니다. 선별은 다른 데이터와 같이 위치 배분과 품질 점수로 합니다.',
    howText: '길이, 멈춤 비율, 이동 경로 길이, 그리퍼 여닫기 네 신호를 사용합니다. 네 신호 모두 숙련도와 같은 방향이었고, 이 신호로 매긴 품질 점수는 숙련자 시범을 앞에 두었습니다 (상관 −0.71, 점수 상위 절반의 숙련자 비율 59%, 하위 8%).',
    signals: [['시범 길이', -0.7, true], ['이동 경로 길이', -0.65, true], ['멈춤 비율', -0.3, true], ['그리퍼 여닫기', -0.18, true], ['동작 거칠기', -0.31, false]],
    signalCaption: '스피어만 순위 상관, 학습 후보 270개. 신호 목록은 Can에서 정한 그대로',
    lengths: [72, 94, 147],
    lengthNote: 'Can(143 / 181 / 301 프레임)의 절반 정도 길이입니다. 숙련도 라벨은 각 90개씩이며 선별에는 쓰지 않습니다.',
    tabs: [
      { id: 'diag', label: '진단' },
      { id: 'how', label: '고르는 방법' },
      { id: 'check', label: '학습으로 확인하기' },
    ],
    body: <LiftCheck />,
  },
}

export default function Dataset() {
  const { id = '' } = useParams()
  const d = DETAILS[id]
  if (!d) return <Navigate to="/datasets" replace />
  return (
    <main>
      <Hero d={d} />
      <SubNav key={d.id} tabs={d.tabs} />
      <Diagnosis d={d} />
      <How d={d} />
      {d.body}
    </main>
  )
}
