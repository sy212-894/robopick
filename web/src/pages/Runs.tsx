import PageHead from '../components/PageHead'

// 실행 기록. 표·필터·시간 막대는 3단계에서 events.jsonl로 채운다
export default function Runs() {
  return (
    <main className="pb-24">
      <PageHead title="실행 기록" desc="도구 호출과 사용자의 승인은 대화마다 실행 ID로 기록됩니다." />
    </main>
  )
}
