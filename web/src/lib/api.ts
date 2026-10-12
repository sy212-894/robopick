// 중계 서버(webapi) 호출. 개발 중에는 vite가 /api를 127.0.0.1:8900으로 넘긴다

export type Health = {
  dify: { ok: boolean; detail: string }
  tools: { ok: boolean; detail: string }
}

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${path} ${r.status}`)
  return (await r.json()) as T
}

export const getHealth = () => getJSON<Health>('/api/health')
