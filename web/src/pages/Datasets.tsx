import { useState } from 'react'
import { Link } from 'react-router-dom'

// 데이터셋 목록: robomimic 12종. 상세 페이지가 있는 데이터(DETAIL)만 누를 수 있다

export const DETAIL = new Set(['can_mh', 'square_mh', 'lift_mh'])

type Item = { id: string; name: string; text: string; demos: string; kind: string; arms: string }
type Group = { task: string; desc: string; items: Item[] }

const one = '한 팔', two = '두 팔'
const mh = '여러 사람', ph = '숙련자', mg = '강화학습', pr = '좋은·나쁜 쌍'
const row = (id: string, name: string, text: string, demos: string, kind: string, arms: string): Item => ({ id, name, text, demos, kind, arms })

const GROUPS: Group[] = [
  { task: 'Can', desc: '캔을 집어 맞는 칸으로 옮기기', items: [
    row('can_mh', 'Can · 여러 사람', '숙련도가 다른 6명이 모은 시범', '300', mh, one),
    row('can_ph', 'Can · 숙련자', '숙련된 한 사람이 모은 깨끗한 시범', '200', ph, one),
    row('can_mg', 'Can · 강화학습 생성', '강화학습 정책 13개 시점이 만든 시범', '3,900', mg, one),
    row('can_paired', 'Can · 좋은/나쁜 쌍', '같은 시작 상태의 좋은 시범과 나쁜 시범 한 쌍', '200', pr, one),
  ] },
  { task: 'Square', desc: '사각 너트를 집어 기둥에 끼우기', items: [
    row('square_mh', 'Square · 여러 사람', '숙련도가 다른 6명이 모은 시범', '300', mh, one),
    row('square_ph', 'Square · 숙련자', '숙련된 한 사람이 모은 깨끗한 시범', '200', ph, one),
  ] },
  { task: 'Lift', desc: '탁자 위 큐브를 집어 들어 올리기', items: [
    row('lift_mh', 'Lift · 여러 사람', '숙련도가 다른 6명이 모은 시범', '300', mh, one),
    row('lift_ph', 'Lift · 숙련자', '숙련된 한 사람이 모은 깨끗한 시범', '200', ph, one),
    row('lift_mg', 'Lift · 강화학습 생성', '강화학습 정책 5개 시점이 만든 시범', '1,500', mg, one),
  ] },
  { task: 'Transport', desc: '한 팔에서 다른 팔로 물건을 건네기', items: [
    row('transport_mh', 'Transport · 여러 사람', '여러 사람이 두 팔을 함께 조작한 시범', '300', mh, two),
    row('transport_ph', 'Transport · 숙련자', '숙련된 조작자가 모은 시범', '200', ph, two),
  ] },
  { task: 'Tool Hang', desc: '도구를 조립해 걸이에 걸기', items: [
    row('tool_hang_ph', 'Tool Hang · 숙련자', '정밀한 조립이 필요한 긴 작업', '200', ph, one),
  ] },
]

const CHIPS = ['전체', ...GROUPS.map((g) => g.task)]

function CardBody({ d, link }: { d: Item; link: boolean }) {
  return (
    <>
      <div className="mb-3 flex items-center justify-between">
        <span className="font-mono text-[13px] text-sub">{d.id}</span>
        {link && <span className="text-[13px] text-accent">자세히</span>}
      </div>
      <div className="mb-1.5 text-[19px] font-semibold">{d.name}</div>
      <div className="mb-4 min-h-[45px] text-sm leading-relaxed text-body">{d.text}</div>
      <div className="grid grid-cols-3 gap-2 border-t border-line-soft pt-3.5">
        {[
          ['시범', d.demos],
          ['수집 방식', d.kind],
          ['로봇 팔', d.arms],
        ].map(([k, v]) => (
          <div key={k}>
            <div className="text-xs text-sub">{k}</div>
            <div className="text-[17px] font-semibold">{v}</div>
          </div>
        ))}
      </div>
    </>
  )
}

export default function Datasets() {
  const [chip, setChip] = useState('전체')
  const shown = chip === '전체' ? GROUPS : GROUPS.filter((g) => g.task === chip)
  return (
    <main>
      <section className="dot-grid border-b border-line">
        <div className="mx-auto max-w-[1200px] px-8 pt-14 pb-10">
          <h1 className="m-0 mb-3 text-4xl font-bold">데이터셋</h1>
          <p className="m-0 max-w-[720px] text-base leading-[1.7] text-body">
            에이전트가 다룰 수 있는 robomimic 데이터입니다.
            <br />
            데이터를 누르면 분석, 선별 방법의 근거, 학습 실험 결과를 볼 수 있습니다.
          </p>
          <div className="mt-7 flex flex-wrap gap-2" role="group" aria-label="작업으로 거르기">
            {CHIPS.map((c) => {
              const on = c === chip
              return (
                <button
                  key={c}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setChip(c)}
                  className={`h-9 cursor-pointer rounded-full border px-3.5 text-sm ${on ? 'border-ink bg-ink text-white' : 'border-field bg-white text-body hover:border-ink'}`}
                >
                  {c}
                </button>
              )
            })}
          </div>
        </div>
      </section>
      <section className="mx-auto flex max-w-[1200px] flex-col gap-12 px-8 pt-10 pb-24">
        {shown.map((g) => (
          <div key={g.task}>
            <div className="mb-4 flex flex-wrap items-baseline gap-3">
              <h2 className="m-0 text-[22px] font-bold">{g.task}</h2>
              <span className="text-sm text-sub">{g.desc}</span>
            </div>
            <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
              {g.items.map((d) =>
                DETAIL.has(d.id) ? (
                  <Link
                    key={d.id}
                    to={`/datasets/${d.id}`}
                    className="block rounded-[10px] border border-line p-[22px] text-ink transition-colors hover:border-ink hover:no-underline"
                  >
                    <CardBody d={d} link />
                  </Link>
                ) : (
                  <div key={d.id} className="rounded-[10px] border border-line p-[22px]">
                    <CardBody d={d} link={false} />
                  </div>
                ),
              )}
            </div>
          </div>
        ))}
        <div className="flex flex-wrap items-center justify-between gap-6 rounded-[10px] border border-dashed border-field p-7">
          <div>
            <div className="mb-1.5 text-xl font-semibold">내 데이터</div>
            <div className="text-[15px] leading-relaxed text-body">robomimic 형식(hdf5) 파일을 올리면 같은 진단과 선별이 가능합니다. 2GB 이하</div>
          </div>
          <Link
            to="/select#upload"
            className="inline-flex h-11 items-center justify-center rounded-md border border-ink px-5 text-[15px] font-medium text-ink hover:no-underline"
          >
            내 데이터 올리기
          </Link>
        </div>
      </section>
    </main>
  )
}
