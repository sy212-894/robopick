// 페이지 제목 줄 (데모·결과·기록 공통)
export default function PageHead({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="mx-auto max-w-[1200px] px-8 pt-12">
      <h1 className="m-0 text-[34px] font-semibold tracking-tight">{title}</h1>
      <p className="mt-2.5 text-[15px] text-body">{desc}</p>
    </div>
  )
}
