import { Link } from 'react-router-dom'

// 소개. 산점도·핵심 숫자·품질 신호 섹션은 3단계에서 /api 데이터로 채운다
export default function Home() {
  return (
    <section className="dot-grid-dark text-[#e9edf2]">
      <div className="mx-auto max-w-[1200px] px-8 pb-[104px] pt-24">
        <div className="mb-7 inline-flex items-center gap-2.5 rounded-full border border-[#2a3a55] bg-[#0f1724] px-3 py-1 font-mono text-xs text-[#9fb4d8]">
          <span className="inline-block size-1.5 rounded-full bg-[#4c86ff]" />
          로봇 모방학습 · 시범 데이터 큐레이션
        </div>
        <h1 className="m-0 text-[54px] font-semibold leading-[1.2] tracking-[-0.03em] text-white">
          좋은 시범만 골라도
          <br />
          로봇은 더 빨리 배웁니다
        </h1>
        <p className="mt-7 max-w-[520px] text-lg leading-relaxed text-[#b4bdc9]">
          사람이 보여준 시범 300개를 작업 조건과 품질로 나눠 학습에 쓸 150개를 고릅니다. 고른 근거와 학습 계획을
          보여주고, 사람이 승인한 계획만 학습합니다.
        </p>
        <div className="mt-10 flex flex-wrap gap-3">
          <Link to="/demo" className="inline-flex h-12 items-center rounded-md bg-white px-5 text-[15px] font-semibold text-night hover:no-underline">
            데모 실행
          </Link>
          <Link to="/results" className="inline-flex h-12 items-center rounded-md border border-[#36404c] px-5 text-[15px] font-medium text-[#e9edf2] hover:no-underline">
            실험 결과 보기
          </Link>
        </div>
      </div>
    </section>
  )
}
