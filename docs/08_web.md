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
한 번에 띄우기 (curation-agent 폴더에서, PowerShell)
```
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```
Dify(Docker, 꺼져 있으면 Docker Desktop부터) → MCP 도구 서버(8800) → 화면 빌드(결과가 없을 때만) → 중계 서버(8900) → 연결 확인 → 브라우저로 http://127.0.0.1:8900 을 연다. 이미 켜진 것은 건너뛴다. 도구 서버와 중계 서버는 최소화된 PowerShell 창에서 돌고, 오류가 나면 그 창에 남는다.
- 화면 코드를 고쳤으면 `-Build`를 붙인다. 중계 서버가 켜져 있어도 브라우저 새로고침으로 새 빌드가 보인다
- 끄기: `powershell -ExecutionPolicy Bypass -File scripts\stop.ps1` (8800·8900만 끄고 Dify는 둔다)

개발용 (코드를 고치면 화면이 바로 바뀜): 중계 서버를 띄운 상태에서 `web` 폴더에서 `npm run dev` → http://localhost:5173 (`/api`는 8900으로 넘어감)
## 겪은 문제
- **OneDrive 안에서 빌드가 죽음**: `web/dist`에 빌드 결과를 쓰면 Node가 0xC0000409로 비정상 종료됐다. OneDrive 밖(`C:\curation-data\web-dist`)에 쓰면 정상이라, 동기화 중인 파일과 부딪힌 것으로 본다. 빌드 결과 위치를 `WEB_DIST`(기본 `C:/curation-data/web-dist`)로 바꿨고 중계 서버도 같은 곳을 읽는다
- **버튼 글자색이 덮임**: 기본 링크 색(`a { color }`)을 CSS 층 밖에 두면 Tailwind 유틸리티(`text-white`)보다 우선한다. `@layer base`로 옮겼다
- **Square 승인 카드에서 화면이 하얗게 멈춤**: 검수 알림(issues·warnings)이 문자열이 아니라 `{check, detail}` 객체로 온다. React는 객체를 글자로 그릴 수 없어 페이지 전체가 멈췄다. Can 시나리오에는 알림이 없어서 못 봤고 Square 시나리오에서 드러났다. "항목: 설명"으로 바꿔 그린다
- **경과 시간이 1791812847초로 나옴**: 실행 구간을 더하는 상태 갱신 함수가 나중에 실행되는데, 그 안에서 시작 시각(ref)을 읽으니 이미 null이었다(`Date.now() - null`). 값을 먼저 꺼내 두고 갱신한다
- **PowerShell 5.1에서 /api/health 한글이 깨짐**: 응답 형식에 charset이 없으면 UTF-8로 읽지 않는다. 시작 스크립트는 바이트를 직접 UTF-8로 푼다. 스크립트 파일도 한글이 있어서 BOM 붙은 UTF-8로 저장했다

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
- [x] 3단계 페이지 옮기기: 소개(산점도·품질 신호), 실험 결과(Can·135·Square 탭), 실행 기록(필터·시간 막대·수치 검사·JSON 내려받기), 데모
- [x] 4단계 데모 연결: Dify 이벤트를 실시간으로 받아 진행 단계·도구 호출·근거 문서를 그리고, 승인 카드는 검수 도구 출력(묶음 구성·학습 계획·알림)으로 만든다. 보고는 최종 답변 + 결과 조회 도구의 성공률 막대
- [x] 5단계 한 번에 띄우기 (`scripts\start.ps1`, `scripts\stop.ps1`)

데모 시나리오 확인 (2026-10-12, 화면에서 직접)
| 시나리오 | 결과 |
|---|---|
| Can 150개 → 승인 | 승인 대기까지 약 22초, 승인 → 보고까지 단계 4개(승인 기록·학습 계획·결과 조회·보고 작성), 비용 $0.0014. 미리 실행한 결과(계획 c15466d53a01cedb)를 불러옴 |
| Square 150개 → 거부 | 위치 쏠림 알림 1건이 승인 카드에 표시, 거부 후 "학습하지 않음"과 거부 답변, 22.1초, $0.0013 |
| 필터 키 질문 (도구 없음) | 12.2초, 근거 문서 4건(관련도 0.99~0.62), 문서 패널에서 검색 문단·전체 문서·원문 링크 확인 |
| 실행 기록 → 수치 검사 | 웹에서 만든 대화의 보고 숫자 98개 모두 기록과 일치 |

남은 것
- (해결, 10/13) 데모 보고의 판정이 결과 페이지와 달랐다. 결과 조회 도구(collect)가 시드별 시험을 합친 독립 비교만 냈고, 주 판정인 짝지은 비교는 원래 실행 폴더에만 있어서 데모가 새로 만든 실행 폴더에서는 보이지 않았다. 짝지은 결과를 지문 저장소에도 등록하고(`train_eval --save-paired`), collect가 그것을 `paired_*` 주 판정으로 맨 앞에 내게 했다. Dify 보고 정리 노드(train_md, res_md)도 짝지은 비교를 "주 판정"으로 맨 위에, 합산 비교를 "보조 · 시험 합산"으로 표시한다. 웹 데모 보고 칸은 짝지은 성공률(시험 100개)과 주 판정 2줄을 보여준다
- 캔버스 시안의 "학습 진행·학습 중단" 화면은 넣지 않았다. 지금 흐름은 승인 뒤 미리 실행한 결과를 불러오고 실제 학습은 Kaggle 노트북에서 따로 돌린다. 웹에서 중단하려면 Kaggle API 연동이 필요하다