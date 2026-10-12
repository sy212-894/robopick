import PageHead from '../components/PageHead'

// 데모. 요청 → 진행 → 승인 → 결과는 4단계에서 Dify와 연결한다
export default function Demo() {
  return (
    <main className="pb-24">
      <PageHead title="데모" desc="요청을 보내면 에이전트가 분석하고 선별한 뒤, 학습 계획을 승인받습니다." />
    </main>
  )
}
