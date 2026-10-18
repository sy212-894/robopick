import { Link } from 'react-router-dom'

// 소개: 무엇을 하는지, 어떻게 쓰는지, 무엇을 주는지. 오른쪽 카드는 Can MH로 선별을 요청했을 때 실제로 나오는 분석 결과다

const PAINS = [
  {
    t: '다 쓰자니 오래 걸리고, 고르자니 기준이 없다',
    d: '시범이 수백 개쯤 되면 하나하나 보고 고를 수 없습니다. 숙련도가 섞여 있으면 성공한 시범이라고 다 좋은 시범도 아닙니다.',
  },
  {
    t: '몇 개면 충분한지 모른다',
    d: '학습 결과 성능을 기다리자니, 시간이 너무 낭비됩니다. 여러 개수로 학습해 보며 찾는 건 GPU 비용이 커서 어렵습니다.',
  },
  {
    t: '데이터가 균형적인지 알 수 없다',
    d: '물체 위치가 가운데에만 몰렸거나 거의 같은 시범이 여러 개 있어도, 학습해 보기 전에는 잘 드러나지 않습니다.',
  },
]

const STEPS = [
  { n: '01', t: '데이터 정하기', d: 'Can·Square 같은 공개 데이터를 고르거나 사용자의 파일을 올립니다. 데이터가 없으면 학습 목적만 말해도 맞는 데이터를 찾아 드립니다.' },
  { n: '02', t: '진단 보기', d: '물체 위치가 몰린 곳, 중복된 시범, 선별 규칙이 이 데이터에 맞는지 등을 파악합니다.' },
  { n: '03', t: '개수 정하기', d: '실험으로 확인된 추천 개수와 그 이유를 보여주고, 사용자의 확인을 받습니다.' },
  { n: '04', t: '학습 키트 받기', d: '선별한 결과로 데이터 파일, 학습 설정, 노트북을 받습니다.' },
  { n: '05', t: '학습 결과 올리기', d: '사용자의 환경에서 학습한 뒤 결과 파일을 올리면 학습이 잘되었는지 판정합니다.' },
]

const OFFERS = [
  { when: '학습 전', t: '진단과 추천 개수', items: ['부족한 위치 칸과 더 모을 개수', '거의 같은 시범 쌍', '선별 규칙이 이 데이터에서도 맞는지', '실험으로 확인된 추천 개수와 이유'] },
  { when: '개수를 정한 후', t: '학습 키트', items: ['선별된 데이터 파일', 'robomimic 학습 설정', '노트북 2종: 선별만 하기 / 선별·무작위·전체 비교하기', 'Colab, Kaggle, 리눅스 서버에서 실행'] },
  { when: '학습 후', t: '결과 판정 카드', items: ['성공률과 신뢰구간', '무작위 학습과의 성능 비교', '공개 데이터의 경우, 이미 학습된 결과와 성능 비교'] },
]

const EXAMPLE: [string, string, string?][] = [
  ['부족한 위치', '4칸'],
  ['거의 같은 시범', '0쌍'],
  ['규칙 점검', '통과', 'text-ok-ink'],
  ['추천 개수', '135개', 'font-semibold'],
]

const startBtn = 'inline-flex h-12 items-center rounded-md bg-white px-[22px] text-base font-semibold text-ink hover:no-underline'

export default function Home() {
  return (
    <main>
      <section className="dot-grid-dark text-white">
        <div className="mx-auto grid max-w-[1200px] items-center gap-x-6 gap-y-12 px-8 pt-24 pb-[104px] lg:grid-cols-12">
          <div className="lg:col-span-7">
            <div className="inline-flex items-center gap-2 rounded-full border border-[#263140] px-3.5 py-1.5 text-[13px] text-[#aeb7c2]">
              <span className="size-1.5 rounded-full bg-[#5b8cf0]" />
              RoboPick · 로봇 모방학습 데이터 선별
            </div>
            <h1 className="mt-7 mb-6 text-[40px] leading-[1.2] font-bold tracking-[-0.01em] sm:text-[54px]">
              시범 데이터,
              <br />다 쓰지 말고 골라 쓰세요
            </h1>
            <p className="m-0 mb-9 max-w-[600px] text-lg leading-[1.75] text-[#c4ccd6]">
              데이터를 고르거나 올리면 학습 전에 진단하고, 몇 개를 쓰면 되는지 실험 근거와 함께 알려 드립니다. 개수를 정하면 바로 돌릴 수 있는 학습 키트를 제공하고, 학습 결과를 올리면 제대로 선별됐는지 판정합니다.
            </p>
            <Link to="/select" className={startBtn}>
              선별 시작
            </Link>
          </div>
          <figure className="m-0 lg:col-span-4 lg:col-start-9">
            <div className="rounded-[10px] bg-white px-[22px] py-5 text-ink">
              <div className="mb-1.5 text-[13px] text-sub">개수 확인</div>
              <div className="mb-3.5 text-[17px] font-semibold">can_mh · 선별 후보 270개</div>
              <dl className="m-0 flex flex-col gap-2 text-sm leading-normal">
                {EXAMPLE.map(([k, v, cls]) => (
                  <div key={k} className="flex justify-between">
                    <dt className="text-sub">{k}</dt>
                    <dd className={`m-0 ${cls ?? ''}`}>{v}</dd>
                  </div>
                ))}
              </dl>
              <div className="mt-4 flex gap-2">
                <div className="flex h-10 flex-1 items-center rounded-md border border-field px-3 font-mono text-[15px]">135</div>
                <Link to="/datasets/can_mh" className="inline-flex h-10 items-center rounded-md bg-ink px-3.5 text-sm text-white hover:no-underline">
                  이 개수로 고르기
                </Link>
              </div>
            </div>
            <figcaption className="mt-3 text-[13px] leading-relaxed text-[#aeb7c2]">사용 예시: Can MH 데이터로 선별을 요청하면 나오는 실제 분석 결과</figcaption>
          </figure>
        </div>
      </section>

      <section className="mx-auto max-w-[1200px] px-8 pt-[88px] pb-10">
        <h2 className="m-0 mb-8 text-[30px] font-bold">이런 고민, 한 번쯤 해보시지 않았나요?</h2>
        <div className="grid gap-5 md:grid-cols-3">
          {PAINS.map((p) => (
            <div key={p.t} className="rounded-[10px] border border-line p-6">
              <div className="mb-2.5 text-[17px] font-semibold">{p.t}</div>
              <p className="m-0 text-[15px] leading-[1.7] text-body">{p.d}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-[1200px] px-8 py-14">
        <h2 className="m-0 mb-2 text-[30px] font-bold">어떻게 사용하나요?</h2>
        <p className="m-0 mb-8 text-base text-sub">대화 한 번으로 4단계까지 몇 초면 충분합니다.</p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {STEPS.map((s) => (
            <div key={s.n} className="border-t-2 border-ink pt-4">
              <div className="mb-2 font-mono text-[13px] text-sub">{s.n}</div>
              <div className="mb-2 text-[17px] font-semibold">{s.t}</div>
              <p className="m-0 text-sm leading-[1.7] text-body">{s.d}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-10 bg-paper">
        <div className="mx-auto max-w-[1200px] px-8 py-[72px]">
          <h2 className="m-0 mb-8 text-[30px] font-bold">무엇을 제공하나요?</h2>
          <div className="grid gap-5 md:grid-cols-3">
            {OFFERS.map((o) => (
              <div key={o.t} className="rounded-[10px] border border-line bg-white p-[22px]">
                <div className="mb-1 text-[13px] text-sub">{o.when}</div>
                <div className="mb-3.5 text-lg font-semibold">{o.t}</div>
                <ul className="m-0 pl-[18px] text-sm leading-[1.9] text-body">
                  {o.items.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="dot-grid-dark text-white">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-6 px-8 py-[72px]">
          <div>
            <div className="mb-2 text-[28px] font-bold">직접 골라 보세요</div>
            <div className="text-base text-[#c4ccd6]">"can_mh에서 학습할 시범 골라줘" 한 줄이면 진단과 추천 개수까지 30초 안에 나옵니다.</div>
          </div>
          <Link to="/select?q=can_mh에서 학습할 시범 골라줘" className={startBtn}>
            선별 시작
          </Link>
        </div>
      </section>
    </main>
  )
}
