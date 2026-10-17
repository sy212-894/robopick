// 중계 서버(webapi) 호출과 응답 모양. 개발 중에는 vite가 /api를 127.0.0.1:8900으로 넘긴다

export type Health = {
  dify: { ok: boolean; detail: string }
  tools: { ok: boolean; detail: string }
}

export type Overview = {
  dataset: string
  points: [number, number, 0 | 1][]
  x_edges: number[]
  y_edges: number[]
  selected: { n_demos: number; total_frames: number }
  train: { n_demos: number; total_frames: number }
  composition: Record<string, { worse: number; okay: number; better: number }>
  signals: { name: string; spearman: number; used: boolean }[]
  lengths: Record<'better' | 'okay' | 'worse', { min: number; max: number; mean: number }>
}

export type Judge = {
  diff: number
  ci95: [number, number]
  verdict: string
  n_seeds?: number
  n_pairs?: number
  per_seed_diff?: Record<string, number>
  note?: string
  question?: string
  meaning?: string
  confirmed?: boolean // 하락 기준: 신뢰구간 위쪽 끝이 기준 이내
}

export type TableRow = {
  set: string
  n_demos: number
  n_seeds?: number
  success?: number
  rollouts?: number
  success_rate?: number
  ci95?: [number, number]
  early?: { epoch: number; success: number; rollouts: number; success_rate: number }
  status?: string
}

export type Collect = {
  run_id: string
  fingerprint?: string
  status: string
  label?: string
  config?: { num_epochs: number; early_eval_epoch?: number; rollout_n?: number }
  table?: TableRow[]
  judgement?: Record<string, Judge | string>
  detail?: string
  sets?: Record<string, { n_demos: number; total_frames: number }>
  plan_config?: { num_epochs: number; early_eval_epoch?: number; early_eval_n?: number; rollout_n?: number }
  // 같은 위치끼리 짝지은 재평가가 있으면 (주 판정). judgement 맨 앞의 paired_* 키와 함께 온다
  paired?: { label: string; rates: Record<string, { success: number; rollouts: number; seeds: number }> }
}

export type Paired = {
  label: string
  success: Record<string, string>
  rates: Record<string, { success: number; rollouts: number; seeds: number }>
  gain_vs_random?: Judge
  drop_vs_full?: Judge
  effect_quality?: Judge
  effect_allocation?: Judge
  same_frames?: Judge
}

export type Results = {
  can: Collect & { paired: Paired | null }
  can_budget: Collect
  square: Collect
}

export type RunRow = {
  session_id: string
  start: string
  end: string
  dataset: string | null
  budget: number | null
  review: string | null
  approval: 'approved' | 'rejected' | 'waiting' | null
  selection_run: string | null
  plan: string | null
  n_events: number
}

export type RunEvent = {
  ts: string
  t: number
  tool: string | null
  event: string | null
  duration_sec: number | null
  run_id: string | null
  detail: string | null
}

export type Doc = {
  file: string
  title: string
  source_url: string | null
  doc_type: string | null
  retrieved: string | null
  content?: string
}

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${path} ${r.status}`)
  return (await r.json()) as T
}

export async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const j = await r.json()
  if (!r.ok) throw new Error(j?.detail ?? `${path} ${r.status}`)
  return j as T
}

export const getHealth = () => getJSON<Health>('/api/health')
export const getOverview = () => getJSON<Overview>('/api/overview')
export const getResults = () => getJSON<Results>('/api/results')
export const getRuns = () => getJSON<{ runs: RunRow[] }>('/api/runs')
export const getRun = (sid: string) => getJSON<{ session_id: string; events: RunEvent[] }>(`/api/runs/${sid}`)
export type CheckResult = { verdict: 'pass' | 'check' | 'no_runs'; numbers?: number; unmatched?: string[]; run_ids?: string[]; detail?: string }
export const postCheck = (sid: string) => postJSON<CheckResult>(`/api/check/${sid}`, {})
export const getDoc =(file: string) => getJSON<Doc>(`/api/docs/${encodeURIComponent(file)}`)

