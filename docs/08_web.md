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

## 진행
- [x] 1단계 뼈대: 페이지 4개 경로, 공통 머리글(로고·메뉴·연결 상태), 중계 서버 상태 확인 `/api/health`, 테스트 4개
- [ ] 2단계 중계 서버 API: 채팅(실시간 흐름), 승인, 실행 기록, 결과, 소개 데이터, 수치 검사, 근거 문서
- [ ] 3단계 페이지 옮기기 (캔버스 디자인 그대로, 숫자는 API에서)
- [ ] 4단계 데모 연결과 시나리오 4개 재확인
- [ ] 5단계 한 번에 띄우는 방법 정리
