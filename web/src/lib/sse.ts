// 중계 서버의 실시간 흐름(SSE)을 POST로 받아 이벤트마다 onEvent를 부른다.
// EventSource는 GET만 되므로 fetch 스트림을 직접 읽는다

export type DifyEvent = { event: string; [k: string]: unknown }

export async function streamSSE(path: string, body: unknown, onEvent: (e: DifyEvent) => void, signal?: AbortSignal) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!r.ok || !r.body) {
    let detail = `${path} ${r.status}`
    try {
      detail = (await r.json()).detail ?? detail
    } catch {
      /* 본문이 JSON이 아니면 상태 코드만 */
    }
    throw new Error(detail)
  }
  const reader = r.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, i)
      buf = buf.slice(i + 2)
      for (const line of block.split('\n')) {
        if (!line.startsWith('data:')) continue
        try {
          onEvent(JSON.parse(line.slice(5)))
        } catch {
          /* 깨진 줄은 건너뛴다 */
        }
      }
    }
  }
}
