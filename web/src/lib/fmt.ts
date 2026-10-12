// 숫자 표시. 모든 값은 API에서 받은 것을 반올림만 한다
import { useEffect, useState } from 'react'

export const pct = (x: number | undefined | null, digits = 0) => (x == null ? '-' : `${(x * 100).toFixed(digits)}%`)

export const pp = (x: number | undefined | null, digits = 0) => {
  if (x == null) return '-'
  const v = x * 100
  const s = Math.abs(v).toFixed(digits)
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${s}%p`
}

export const signed = (x: number, digits = 0) => {
  const v = x * 100
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(digits)}`
}

export const num = (x: number | undefined | null) => (x == null ? '-' : x.toLocaleString('ko-KR'))

export const SIGNAL_NAMES: Record<string, string> = {
  length: '시범 길이',
  idle_ratio: '멈춤 비율',
  path_length: '이동 경로 길이',
  gripper_switches: '그리퍼 전환 수',
  action_roughness: '동작 거칠기',
}

export const SET_NAMES: Record<string, { name: string; sub: string }> = {
  curated_150: { name: '선별 150', sub: '품질 점수 + 칸별 배분' },
  curated_135: { name: '선별 135', sub: '품질 점수 + 칸별 배분' },
  train: { name: '전체 270', sub: '학습 후보 전부' },
  random_150: { name: '무작위 150', sub: '같은 개수' },
  random_135: { name: '무작위 135', sub: '같은 개수' },
  random_frames: { name: '프레임 맞춘 무작위', sub: '같은 프레임 수' },
  stratified_random_150: { name: '조건별 균등 무작위 150', sub: '칸별 개수만 같게' },
  stratified_random_135: { name: '조건별 균등 무작위 135', sub: '칸별 개수만 같게' },
}

// API를 한 번 불러 상태로 들고 있는다
export function useApi<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    load()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String(e.message ?? e)))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return { data, error }
}
