# 7단계: 웹 (데모 프런트)

디자인 시안(캔버스 4페이지: 소개, 데모, 실험 결과, 실행 기록)을 실제로 동작하는 웹으로 옮긴다.

## 구조
```
브라우저 ── web/ (React + Tailwind, Vite) ── /api ──> webapi/ (중계 서버, Starlette, 127.0.0.1:8900)
                                                        ├─ Dify 앱 API (채팅, 승인)      http://localhost/v1
                                                        ├─ MCP 도구 서버 상태             127.0.0.1:8800
                                                        └─ 실행 기록·결과 파일            C:\curation-data
```
- 중계 서버를 두는 이유: Dify API 키를 브라우저에 노출하지 않고, 서로 다른 주소 사이 호출 제한(CORS)을 피하기 위해
- FastAPI 대신 Starlette를 쓴 이유: MCP 서버 때문에 Starlette·uvicorn·httpx가 이미 `curation` 환경에 있다. FastAPI를 설치하면 Starlette 버전이 바뀌어 MCP 도구 서버가 깨질 수 있다

## 처음 한 번
1. `webapi\.env.example`이 `webapi\.env`로 복사돼 있다 (git 제외). Dify 앱 API 키를 넣는다:
   Dify 스튜디오(http://localhost/apps) → "시범데이터 선별 에이전트" → 왼쪽 "API 접근" → 오른쪽 위 "API 키" → "새 시크릿 키 생성" → `DIFY_API_KEY=` 뒤에 붙여 넣기
2. 화면 패키지: `web` 폴더에서 `npm install` (이미 한 번 함)

## 실행
시연용 (화면을 빌드해 중계 서버가 함께 띄움)
```
cd web
npm run build
cd ..
conda run --no-capture-output -n curation python -m webapi
```
→ http://127.0.0.1:8900

개발용 (코드를 고치면 화면이 바로 바뀜): 중계 서버를 띄운 상태에서 `web` 폴더에서 `npm run dev` → http://localhost:5173 (`/api`는 8900으로 넘어감)

MCP 도구 서버(`python -m curation_tools.server`)와 Dify(Docker)도 켜져 있어야 데모가 동작한다. 상단 오른쪽 표시가 초록이면 둘 다 연결된 상태다.

## 겪은 문제
- **OneDrive 안에서 빌드가 죽음**: `web/dist`에 빌드 결과를 쓰면 Node가 0xC0000409로 비정상 종료됐다. OneDrive 밖(`C:\curation-data\web-dist`)에 쓰면 정상이라, 동기화 중인 파일과 부딪힌 것으로 본다. 빌드 결과 위치를 `WEB_DIST`(기본 `C:/curation-data/web-dist`)로 바꿨고 중계 서버도 같은 곳을 읽는다
- **버튼 글자색이 덮임**: 기본 링크 색(`a { color }`)을 CSS 층 밖에 두면 Tailwind 유틸리티(`text-white`)보다 우선한다. `@layer base`로 옮겼다

## 중계 서버 API (2단계)
| API | 하는 일 |
|---|---|
| `GET /api/health` | Dify(키 확인 포함)·도구 서버 연결 상태 |
| `POST /api/chat` | `{query, conversation_id?}` → Dify 이벤트를 실시간으로 넘김(SSE). 근거 검색 노드가 끝나면 `evidence` 이벤트 추가 |
| `POST /api/approve` | `{form_token, action, workflow_run_id, conversation_id}` → 승인·거부 제출 후 이어지는 이벤트 + `final_message` |
| `GET /api/message/{대화ID}` | 마지막 메시지 |
| `GET /api/runs`, `/api/runs/{대화ID}` | 실행 기록 목록, 대화별 이벤트 (`?download=1`이면 원본 JSON 파일) |
| `POST /api/check/{대화ID}` | 보고 수치 검사. 답변을 안 보내면 Dify에서 가져옴 (웹에서 만든 대화만) |
| `GET /api/results` | Can 150(짝지은 비교 포함) / Can 135 / Square 결과와 판정 |
| `GET /api/overview` | 소개 페이지: 캔 위치 산점도, 품질 신호, 숙련도 구성, 길이 분포 |
| `GET /api/docs`, `/api/docs/{파일}` | 지식베이스 원본 문서 목록, 제목·출처 주소·전체 내용 |

Dify 앱 API로 승인을 받는 흐름 (Dify 1.17 서버 코드로 확인)
1. `/chat-messages`(streaming) → 승인 노드에서 `human_input_required`(form_token)와 `workflow_paused`(workflow_run_id) 후 닫힘
2. `/form/human_input/{form_token}`에 `{inputs, action, user}` 제출 → 실행 재개. 승인 노드가 "웹앱 전달"이어야 한다
3. `/workflow/{workflow_run_id}/events?include_state_snapshot=true` → 이어지는 이벤트. 제출과 구독 사이에 지나간 이벤트를 놓치지 않게 지난 상태부터 다시 받는다
4. 모든 호출의 user는 `web-demo`로 고정 (Dify는 실행을 만든 user만 이어서 볼 수 있다)

알게 된 것
- 비용·토큰은 `/messages`에는 없고 보고 끝 이벤트(`message_end`)의 `metadata.usage`에 있다. 화면은 그 값을 쓴다
- 우리 흐름은 검색 결과를 코드 노드로 에이전트 지시문에 넣어서 Dify 기본 인용(`retriever_resources`)이 비어 있다. 그래서 근거 검색 노드 출력에서 문서 이름·점수·문단을 꺼내 지식베이스 원본의 제목·출처 주소를 붙인다
- 실제 확인 (2026-10-12): S1 요청→승인 대기 13~20초, 승인→보고 3.6~5.8초, 보고 숫자 98개 수치 검사 통과, 근거 질문에 문서 4건(점수 1.0~0.59)과 출처 주소

## 진행
- [x] 1단계 뼈대: 페이지 4개 경로, 공통 머리글(로고·메뉴·연결 상태), 중계 서버 상태 확인 `/api/health`
- [x] 2단계 중계 서버 API (위 표), 테스트 14개 (가짜 Dify 응답 + 임시 파일 + 실제 결과 파일)
- [ ] 3단계 페이지 옮기기 (캔버스 디자인 그대로, 숫자는 API에서)
- [ ] 4단계 데모 연결과 시나리오 4개 재확인
- [ ] 5단계 한 번에 띄우는 방법 정리
