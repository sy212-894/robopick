import { useCallback, useEffect, useState } from 'react'
import { getKaggle, postKaggle, type KaggleState } from '../lib/api'

// 실행 기록에서 고른 대화의 Kaggle 학습 패널. 진행(끝난 실행 수, 경과/예상 시간), 남은 GPU, 중단·이어서 버튼
// 학습 중이면 1분마다 다시 확인한다 (한 번 확인에 Kaggle 로그를 몇 초 읽는다)

const LABEL: Record<string, { text: string; cls: string }> = {
  queued: { text: '시작 대기', cls: 'bg-accent-soft text-accent-ink' },
  running: { text: '학습 중', cls: 'bg-accent-soft text-accent-ink' },
  stopping: { text: '중단 요청됨', cls: 'bg-warn-soft text-warn-ink' },
  stopped: { text: '중단됨', cls: 'bg-warn-soft text-warn-ink' },
  complete: { text: '완료 · 결과 등록됨', cls: 'bg-ok-soft text-ok-ink' },
  error: { text: '오류로 멈춤', cls: 'bg-warn-soft text-warn-ink' },
  not_launched: { text: 'Kaggle에 올리지 않음', cls: 'bg-line-soft text-body' },
  already_trained: { text: '학습 결과 있음', cls: 'bg-ok-soft text-ok-ink' },
}
const LIVE = ['queued', 'running', 'stopping']

const kst = (iso?: string) => {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function KagglePanel({ sid }: { sid: string }) {
  const [st, setSt] = useState<KaggleState | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState<'load' | 'stop' | 'resume' | null>('load')
  const [note, setNote] = useState<string | null>(null)

  const load = useCallback(async () => {
    setBusy('load')
    setErr(null)
    try {
      setSt(await getKaggle(sid))
    } catch (e) {
      setErr(String((e as Error).message ?? e))
    } finally {
      setBusy(null)
    }
  }, [sid])

  useEffect(() => {
    setSt(null)
    setNote(null)
    load()
  }, [load])

  useEffect(() => {
    if (!st || !LIVE.includes(st.status)) return
    const id = window.setInterval(load, 60_000)
    return () => window.clearInterval(id)
  }, [st, load])

  const act = async (a: 'stop' | 'resume') => {
    if (a === 'stop' && !window.confirm('Kaggle 학습을 멈출까요? 끝난 실행 결과는 남고, 진행 중이던 실행은 이어서 학습할 때 처음부터 다시 합니다.')) return
    setBusy(a)
    setNote(null)
    try {
      const r = await postKaggle(sid, a)
      const ok = (a === 'stop' && r.status === 'stopping') || (a === 'resume' && r.status === 'resumed')
      setNote(ok ? (a === 'stop' ? '중단을 요청했습니다. 잠시 뒤 상태가 "중단됨"으로 바뀝니다.' : `남은 실행 ${r.left_runs}개를 다시 올렸습니다 (예상 약 ${r.est_minutes}분).`) : (r.detail ?? r.status))
      await load()
    } catch (e) {
      setNote(String((e as Error).message ?? e))
      setBusy(null)
    }
  }

  if (st?.status === 'no_plan') return null // 학습 계획까지 가지 않은 대화

  const lab = st ? (LABEL[st.status] ?? { text: st.status, cls: 'bg-line-soft text-body' }) : null
  const total = st?.total_runs ?? 0
  const done = st?.done_runs ?? 0
  const g = st?.gpu
  const btn = 'h-10 cursor-pointer rounded-md border border-field bg-white px-4 text-sm text-ink disabled:cursor-not-allowed disabled:text-muted'

  return (
    <section aria-label="Kaggle 학습" className="mt-6 rounded-lg border border-line-soft bg-[#fafbfc] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="m-0 text-[15px] font-semibold">Kaggle 학습</h3>
        {lab && <span className={`rounded px-2 py-0.5 text-xs ${lab.cls}`}>{lab.text}</span>}
      </div>

      {err && <p className="mt-3 text-sm text-danger">상태를 불러오지 못했습니다: {err}</p>}
      {!st && !err && <p className="mt-3 text-sm text-sub">Kaggle 상태 확인 중 (몇 초 걸립니다)</p>}

      {st && st.status === 'kaggle_error' && <p className="mt-3 text-sm text-danger">Kaggle에 연결하지 못했습니다: {st.detail}</p>}

      {st && total > 0 && (
        <>
          <div className="mt-4 flex items-center gap-3">
            <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-line-soft" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
              <div className="h-full rounded-full bg-accent" style={{ width: `${(done / total) * 100}%` }} />
            </div>
            <span className="font-mono text-xs text-body tabular-nums">
              {done}/{total} 실행
            </span>
          </div>
          <p className="mt-2 text-[13px] text-sub tabular-nums">
            경과 {st.elapsed_minutes}분 / 예상 약 {st.est_minutes}분
            {st.url && (
              <>
                {' · '}
                <a href={st.url} target="_blank" rel="noreferrer">
                  Kaggle에서 보기
                </a>
              </>
            )}
          </p>
          {st.failure && <p className="mt-2 text-[13px] text-danger">오류 내용: {st.failure}</p>}
        </>
      )}

      {st?.status === 'not_launched' && (
        <p className="mt-3 text-[13px] text-sub">
          학습 계획은 준비됐지만 Kaggle에 올리지 않았습니다.
          {st.launch_enabled === false && ' 도구 서버의 Kaggle 자동 학습(KAGGLE_LAUNCH)이 꺼져 있습니다.'}
        </p>
      )}

      {st?.status === 'already_trained' && (
        <p className="mt-3 text-[13px] text-sub">같은 선별 결과와 설정으로 미리 실행한 학습 결과가 있어 다시 학습하지 않습니다.</p>
      )}

      {g && (
        <p className="mt-2 text-[13px] text-sub tabular-nums">
          {g.ok ? `남은 GPU ${g.left}시간 (이번 주 ${g.used}/${g.allowed}시간 사용, ${kst(g.refresh)} 초기화)` : `남은 GPU를 확인하지 못했습니다: ${g.detail}`}
        </p>
      )}

      {st && (
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="button" className={btn} onClick={() => act('stop')} disabled={!st.can_stop || busy !== null}>
            {busy === 'stop' ? '중단 요청 중' : '학습 멈추기'}
          </button>
          <button type="button" className={btn} onClick={() => act('resume')} disabled={!st.can_resume || busy !== null}>
            {busy === 'resume' ? '다시 올리는 중' : '이어서 학습'}
          </button>
          <button type="button" className={btn} onClick={load} disabled={busy !== null}>
            {busy === 'load' ? '확인 중' : '새로 확인'}
          </button>
        </div>
      )}
      {note && (
        <div role="status" className="mt-3 rounded-md bg-paper px-3.5 py-3 text-[13px] text-body">
          {note}
        </div>
      )}
      <p className="mt-3 text-xs text-sub">학습 시작은 에이전트가 사람의 승인 뒤에 합니다. 멈추기·이어서는 여기서 직접 누릅니다.</p>
    </section>
  )
}
