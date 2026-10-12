import PageHead from '../components/PageHead'

// 실험 결과. Can 150 / Can 135 / Square 탭은 3단계에서 결과 파일로 채운다
export default function Results() {
  return (
    <main className="pb-24">
      <PageHead
        title="실험 결과"
        desc="같은 정책과 같은 설정으로 묶음마다 학습하고, 시뮬레이터에서 같은 시험 위치로 성공률을 쟀습니다."
      />
    </main>
  )
}
