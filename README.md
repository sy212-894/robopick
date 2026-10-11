# curation-agent

로봇 모방학습 Demonstration 자동 선별 에이전트 (실전 AI 에이전트 시스템 설계·구축, 8주차 MVP)

- 데이터: robomimic v0.1 Can Multi-Human low_dim (`C:\curation-data`, 저장소에 포함하지 않음)
- 구조: Dify 채팅플로우 + 자체 MCP 도구 서버(`curation_tools/`) + Google Colab 학습·평가
- 계획: `../8주차/MVP_구현계획.md`

## 폴더
- `curation_tools/` MCP 도구 서버 (analyze_data, select_demos, train_evaluate, log_event)
- `colab/` 코랩 노트북
- `docs/` 단계별 기록

## 환경
- conda 환경 `curation` (Python 3.10): h5py, numpy, mcp 1.x (`mcp[cli]<2`, 2.x는 API 변경)

## 실행
도구 서버 켜기 (PowerShell, 이 폴더에서). Dify 시연 중에는 켜져 있어야 한다.
```powershell
conda run --no-capture-output -n curation python -m curation_tools.server
```
- 주소: `http://127.0.0.1:8800/mcp`, Dify 컨테이너에서는 `http://host.docker.internal:8800/mcp`
- 실행 기록: `C:\curation-data\logs\events.jsonl`
- 결과: `C:\curation-data\runs\<run_id>\`

테스트
```powershell
conda run -n curation python -m pytest tests -q
```
