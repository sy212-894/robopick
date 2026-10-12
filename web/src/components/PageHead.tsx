import type { ReactNode } from 'react'

// 페이지 제목 줄 (데모·결과·기록 공통). children은 오른쪽에 붙는다 (필터 등)
export default function PageHead({ title, desc, children }: { title: string; desc: string; children?: ReactNode }) {
  return (
    <div className="mx-auto flex max-w-[1200px] flex-wrap items-end justify-between gap-4 px-8 pt-12">
      <div>
        <h1 className="m-0 text-[34px] font-semibold tracking-tight">{title}</h1>
        <p className="mt-2.5 text-[15px] text-body">{desc}</p>
      </div>
      {children}
    </div>
  )
}
