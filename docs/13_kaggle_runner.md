# MVP 12: 승인 뒤 Kaggle 학습 자동 실행

전에는 사람이 학습 계획을 승인하면 계획 파일까지만 만들었고, 학습은 내가 Kaggle 노트북을 손으로 올려 돌린 뒤 결과 파일을 브라우저로 내려받아 등록했다. 이번 단계에서 이 과정을 에이전트와 웹이 하도록 바꿨다.

- 승인 → 에이전트가 Kaggle GPU 노트북을 만들어 올린다 (launch)
- 진행 확인: 채팅에서 "학습 진행 상황 알려줘" 또는 웹 실행 기록 페이지의 Kaggle 패널 (끝난 실행 수, 경과/예상 시간, 남은 GPU)
- 멈추기·이어서 학습: 웹 패널의 버튼 (사람이 직접 누른다)
- 끝나면 결과 파일을 API로 받아 등록한다. 브라우저 다운로드가 필요 없다

## 구조
```
Dify 흐름 ── 승인 → prepare → collect → launch ─┐
          └─ "학습 진행" 질문 → status ─────────┤
웹 Kaggle 패널 ── /api/kaggle/{대화ID} (status, stop, resume) ─┤
                                                               ▼
        curation_tools/kaggle_runner.py  (노트북 생성, 상태 기록 run_dir/kaggle/state.json, 안전장치)
                       │ 하위 프로세스, JSON 한 줄
                       ▼
        curation_tools/kaggle_helper.py  (kaggle-cli 환경: 파이썬 3.12, kaggle 2.2.4)
                       │
                       ▼
                 Kaggle API (push, status, logs, cancel, quota, output)
```
- 도우미를 따로 두는 이유: 도구 서버 환경(`curation`, 파이썬 3.10)에는 새 Kaggle 토큰을 지원하는 kaggle 1.8+가 설치되지 않는다. 그래서 kaggle 2.x가 있는 `kaggle-cli` 환경의 파이썬을 하위 프로세스로 부른다
- 토큰은 kaggle 패키지가 `~/.kaggle/access_token`(또는 `KAGGLE_API_TOKEN`)에서 직접 읽는다. 우리 코드는 토큰 값을 읽거나 출력하지 않는다

## 노트북이 진행 상황을 알리는 방법
`build_notebook`이 학습 계획(plan.json)으로 노트북을 만든다. 학습 코드는 그동안 쓴 노트북(03_square.ipynb)의 셀을 그대로 쓰고, 세 가지를 더했다.
- 시작할 때 `SESSION <번호>`를 출력한다. 번호는 컨테이너 이름(`KAGGLE_CONTAINER_NAME`)에서 읽는다. 중단(cancel)에 이 번호가 필요하다
- 실행(묶음×시드) 하나가 끝날 때마다 `RUNJSON {...}`로 그 결과를 출력한다
- 이어서 학습할 때는 끝난 실행 결과를 노트북에 넣어 다시 올리고, 노트북은 그 실행을 건너뛴다

status는 Kaggle 실행 로그를 몇 초 읽어 이 두 줄을 찾는다. 그래서 학습 중에도 끝난 실행 수를 알 수 있고, 멈춘 뒤에도 끝난 실행 결과가 남는다.

## 안전장치
| 상황 | 동작 |
|---|---|
| 같은 계획의 결과가 이미 있음 | 다시 학습하지 않음 (`already_trained`, 결과 표를 그대로 보여줌) |
| 같은 계획이 이미 Kaggle에서 실행 중 | 거부 (`already_running`) |
| 다른 계획이 실행 중 | 거부 (`busy`). GPU 동시 실행을 1개로 제한 |
| 남은 GPU < 예상 시간 | 거부 (`no_gpu`). 남은 GPU는 Kaggle API에서 읽음 |
| 자동 학습이 꺼져 있음 (기본) | 계획까지만 만들고 안내 (`disabled`) |
| 멈추기 대상 | 이 도구가 올린 `curation-run-*` 노트북만. 실험 노트북(curation-seeds45 등)은 멈추지 않음 |
| Kaggle 접속·API 오류 | 도구 실패 대신 `kaggle_error` 상태로 알림 |

자동 학습은 기본으로 꺼져 있다. 시연이나 개발 중에 승인 버튼 한 번으로 GPU 1~2시간을 쓰지 않게 하기 위해서다. 켤 때만 `start.ps1 -Kaggle`로 띄운다.

## 설정 (환경 변수)
| 이름 | 기본값 | 뜻 |
|---|---|---|
| `KAGGLE_LAUNCH` | `0` | `1`이면 launch·resume이 실제로 GPU 학습을 올린다 (`start.ps1 -Kaggle`이 켬) |
| `KAGGLE_PYTHON` | `C:/miniconda3/envs/kaggle-cli/python.exe` | 도우미를 실행할 파이썬 |
| `KAGGLE_OWNER` | `qkdsy482` | 노트북 주인 (Kaggle 사용자 이름) |
| `KAGGLE_WEEKLY_GPU_HOURS` | `30` | API가 허용량을 주지 않을 때만 쓰는 주간 GPU 시간 |

경로와 토큰을 모두 설정으로 읽으므로, 나중에 서버(Docker)로 배포할 때는 이미지 안에 두 환경을 설치하고 이 값만 바꾸면 된다. 배포하면 모든 사용자가 한 Kaggle 계정의 GPU(주 30시간, 동시 1개)를 나눠 쓴다는 점은 남는 제약이다.

## 실행
```
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Kaggle
```
`-Kaggle` 없이 띄우면 승인해도 학습 계획까지만 만든다. 이미 켜져 있으면 건너뛰므로, 바꾸려면 `stop.ps1`로 끄고 다시 띄운다.

## 확인한 것
- 테스트: `tests/test_kaggle_runner.py` (가짜 Kaggle로 노트북 내용, launch·status·stop·resume, 완료 후 결과 등록, 안전장치, 꺼짐, 올리기 전 상태), `tests/test_webapi.py::test_kaggle_panel` (패널 API, 실행 기록). 전체 54개 통과
- 실제 Kaggle (GPU 없이 CPU 시험 노트북 `curation-run-smoke`): 올리기 → 바로 RUNNING, 로그에서 세션 번호와 끝난 실행 4개를 읽음, 중단 → CANCEL_ACKNOWLEDGED, 짧은 버전을 끝까지 돌려 결과 파일을 API로 받음, 남은 GPU 27.2/30시간
- Dify (게시 후 웹 데모): 승인 → prepare → collect → launch(0.23초) → 이미 결과가 있는 계획이라 다시 학습하지 않고 결과 표 표시. "학습 진행 상황 알려줘" → 진행 질문 분기 → "미리 실행한 결과가 있어 다시 학습하지 않았다" 안내
- 웹 실행 기록 페이지: Kaggle 패널에 상태, 남은 GPU(10/17 09:00 초기화), 꺼짐 안내, 버튼 표시

실제 GPU 학습을 처음부터 끝까지 자동으로 돌리는 시험은 이번 주 GPU가 2.8시간만 남아 하지 않았다. 10/17 초기화 뒤 남는 GPU로 한 번 확인한다.

## 겪은 문제
- 로그 흐름(SSE) 읽기가 끝나지 않음: Kaggle은 실행 중 로그를 처음부터 계속 보내 준다. 정해진 초만 읽고 끊도록 만들었다. 또 서버가 로그 주소를 최대 20초 기다린 뒤 응답해서 읽기 시간 제한을 30초로 늘리고, 시간이 넘어도 그때까지 받은 줄은 쓴다
- 남은 GPU가 3.2시간으로 나옴: kaggle 라이브러리의 `to_dict()`가 시간 값을 글자로 바꿀 때 "일" 단위를 빠뜨린다 (1일 3.2시간 → 3.2시간). 원래 시간 값(timedelta)을 직접 읽어 27.2시간으로 고쳤다
- 중단에 필요한 세션 번호를 API로 얻을 방법이 없음: 노트북이 시작할 때 컨테이너 이름에서 번호를 읽어 출력하게 했다
- 중계 서버가 UTF-8이 아닌 요청 본문에 500 오류를 냄: 400으로 돌려주게 고쳤다
- Dify 게시 이름은 20자까지다

## 이어서 고친 것 (10/13)
- 데모 화면: 맨 위 안내·승인 카드 문구·승인 버튼 이름이 자동 학습 켜짐 여부(`/api/health`의 `kaggle.launch_enabled`)를 따른다. 진행 단계에 "Kaggle 학습 시작"을 넣고, 승인 뒤 데모 화면에도 Kaggle 패널을 보여 준다
- 선별 예산: 에이전트(Gemma)가 "100개 골라줘"에도 150을 도구에 넘기는 일이 있었다. 이제 근거 정리 코드 노드가 요청 문장에서 개수("100개", "budget=100")를 읽고, select_demos의 budget을 그 값으로 고정한다 (없으면 150). 100, 120으로 실제 확인
- 승인 뒤 보고가 "승인 시 학습 진행"처럼 승인을 앞으로 할 일로 쓰던 문구를 막았다
- Can 150 결과에 학습 시드 5개 추가 분석을 붙였다 (`docs/11_seeds45.md`). 주 판정(시드 3개)은 바꾸지 않는다
