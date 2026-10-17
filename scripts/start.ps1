# 데모를 한 번에 띄운다: Dify(Docker) → MCP 도구 서버 → 화면 빌드(필요할 때) → 중계 서버 → 브라우저
# 사용: curation-agent 폴더에서  powershell -ExecutionPolicy Bypass -File scripts\start.ps1  [-Build]
#   -Build  화면 코드를 고쳤을 때 다시 빌드한다 (빌드 결과가 없으면 자동으로 빌드)
# 이미 켜져 있는 것은 건너뛴다. 끄기는 scripts\stop.ps1
param([switch]$Build)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path $PSScriptRoot -Parent
$DifyDir = 'C:\dify\docker'
$WebDist = 'C:\curation-data\web-dist'

function Test-Port([int]$Port) {
    $c = New-Object Net.Sockets.TcpClient
    try { $c.Connect('127.0.0.1', $Port); return $true } catch { return $false } finally { $c.Close() }
}
function Test-Url([string]$Url) {
    try { $null = Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 3; return $true } catch { return $false }
}
function Wait-Until([scriptblock]$Ok, [int]$Seconds, [string]$What) {
    for ($i = 0; $i -lt $Seconds; $i += 2) { if (& $Ok) { return } ; Start-Sleep 2 }
    throw "$What 이(가) ${Seconds}초 안에 켜지지 않았습니다"
}
# 새 창에서 conda 환경 curation으로 파이썬 모듈을 띄운다. 창을 닫지 않아서 오류가 나면 그 창에서 볼 수 있다
function Start-Module([string]$Module, [string]$Title) {
    $cmd = "`$Host.UI.RawUI.WindowTitle='$Title'; Set-Location '$Repo'; `$env:PYTHONIOENCODING='utf-8'; conda run --no-capture-output -n curation python -m $Module"
    Start-Process powershell -ArgumentList '-NoExit', '-Command', $cmd -WindowStyle Minimized
}

Write-Host '[1/5] Dify' -ForegroundColor Cyan
if (Test-Url 'http://localhost/') {
    Write-Host '      이미 켜져 있음'
} else {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host '      Docker Desktop 시작'
        Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
        Wait-Until { docker info *> $null; $LASTEXITCODE -eq 0 } 180 'Docker'
    }
    Write-Host '      docker compose up -d'
    Push-Location $DifyDir; try { docker compose up -d } finally { Pop-Location }
    Wait-Until { Test-Url 'http://localhost/' } 180 'Dify'
}

Write-Host '[2/5] MCP 도구 서버 (127.0.0.1:8800)' -ForegroundColor Cyan
if (Test-Port 8800) { Write-Host '      이미 켜져 있음' } else {
    Start-Module 'curation_tools.server' '도구 서버 8800'
    Wait-Until { Test-Port 8800 } 60 '도구 서버'
}

Write-Host '[3/5] 화면 빌드' -ForegroundColor Cyan
if ($Build -or -not (Test-Path "$WebDist\index.html")) {
    Push-Location "$Repo\web"; try { npm run build; if ($LASTEXITCODE -ne 0) { throw '화면 빌드 실패' } } finally { Pop-Location }
} else { Write-Host '      기존 빌드 사용 (코드를 고쳤으면 -Build)' }

Write-Host '[4/5] 중계 서버 (127.0.0.1:8900)' -ForegroundColor Cyan
if (Test-Port 8900) {
    Write-Host '      이미 켜져 있음'
    if ($Build) { Write-Host '      새 빌드는 브라우저 새로고침으로 반영됩니다 (index.html을 매번 새로 읽음)' }
} else {
    Start-Module 'webapi' '중계 서버 8900'
    Wait-Until { Test-Port 8900 } 60 '중계 서버'
}

Write-Host '[5/5] 연결 확인' -ForegroundColor Cyan
# PowerShell 5.1은 charset 없는 JSON을 UTF-8로 읽지 않아서 한글이 깨진다. 바이트를 직접 UTF-8로 푼다
$r = Invoke-WebRequest 'http://127.0.0.1:8900/api/health' -UseBasicParsing
$h = [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json
Write-Host ("      Dify: {0} ({1})" -f $(if ($h.dify.ok) { '정상' } else { '문제' }), $h.dify.detail)
Write-Host ("      도구 서버: {0} ({1})" -f $(if ($h.tools.ok) { '정상' } else { '문제' }), $h.tools.detail)
Start-Process 'http://127.0.0.1:8900'
Write-Host '준비 완료: http://127.0.0.1:8900' -ForegroundColor Green