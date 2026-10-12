import type { ReactNode } from 'react'

// 에이전트 보고에 나오는 정도의 마크다운만 그린다: 제목, 문단, 목록, 표, 구분선, 굵게, 코드.
// HTML로 넣지 않고 React 요소로 만들어서 답변에 태그가 섞여도 그대로 글자로 보인다

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**') && p.length > 4) return <strong key={i}>{p.slice(2, -2)}</strong>
    if (p.startsWith('`') && p.endsWith('`') && p.length > 2)
      return (
        <code key={i} className="rounded bg-paper px-1 font-mono text-[0.9em]">
          {p.slice(1, -1)}
        </code>
      )
    return p
  })
}

const cells = (line: string) =>
  line
    .trim()
    .replace(/^\||\|$/g, '')
    .split('|')
    .map((c) => c.trim())

export default function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r/g, '').split('\n')
  const out: ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const ln = lines[i]
    const t = ln.trim()
    if (!t) {
      i++
      continue
    }
    if (/^-{3,}$/.test(t)) {
      out.push(<hr key={i} className="my-5 border-0 border-t border-line" />)
      i++
      continue
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(t)
    if (h) {
      out.push(
        <h3 key={i} className="mt-5 mb-2 text-[15px] font-semibold first:mt-0">
          {inline(h[2])}
        </h3>,
      )
      i++
      continue
    }
    if (t.startsWith('|')) {
      const rows: string[][] = []
      const start = i
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        if (!/^\|?[\s:|-]+\|?$/.test(lines[i].trim())) rows.push(cells(lines[i]))
        i++
      }
      const [head, ...body] = rows
      out.push(
        <div key={start} className="my-3 overflow-x-auto">
          <table className="w-full border-collapse text-[13px] tabular-nums">
            <thead>
              <tr className="text-left text-xs text-sub">
                {head.map((c, j) => (
                  <th key={j} className="border-b border-line py-1.5 pr-3 font-medium">
                    {inline(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((r, k) => (
                <tr key={k}>
                  {r.map((c, j) => (
                    <td key={j} className="border-b border-line-soft py-1.5 pr-3">
                      {inline(c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }
    const isItem = (s: string) => /^([-*]|\d+\.)\s+/.test(s.trim())
    if (isItem(t)) {
      const ordered = /^\d+\./.test(t)
      const items: string[] = []
      const start = i
      while (i < lines.length && isItem(lines[i])) {
        items.push(lines[i].trim().replace(/^([-*]|\d+\.)\s+/, ''))
        i++
      }
      const Tag = ordered ? 'ol' : 'ul'
      out.push(
        <Tag key={start} className={`my-2 flex flex-col gap-1 pl-5 ${ordered ? 'list-decimal' : 'list-disc'}`}>
          {items.map((it, j) => (
            <li key={j}>{inline(it)}</li>
          ))}
        </Tag>,
      )
      continue
    }
    const para: string[] = []
    const start = i
    while (i < lines.length && lines[i].trim() && !isItem(lines[i]) && !lines[i].trim().startsWith('|') && !/^(-{3,}|#{1,4}\s)/.test(lines[i].trim())) {
      para.push(lines[i].trim())
      i++
    }
    out.push(
      <p key={start} className="my-2">
        {para.map((p, j) => (
          <span key={j}>
            {j > 0 && <br />}
            {inline(p)}
          </span>
        ))}
      </p>,
    )
  }
  return <div className="text-[15px] leading-[1.75] text-[#22282f]">{out}</div>
}
