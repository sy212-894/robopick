# 도구 서버(8800)와 중계 서버(8900)를 끈다. Dify(Docker)는 그대로 둔다 (끄려면 C:\dify\docker에서 docker compose stop)
# 사용: powershell -ExecutionPolicy Bypass -File scripts\stop.ps1
foreach ($port in 8800, 8900) {
    $pids = netstat -ano | Select-String "127\.0\.0\.1:$port\s+\S+\s+LISTENING\s+(\d+)" | ForEach-Object { $_.Matches[0].Groups[1].Value } | Sort-Object -Unique
    if (-not $pids) { Write-Host "$port 꺼져 있음"; continue }
    foreach ($p in $pids) { Stop-Process -Id $p -Force; Write-Host "$port 끔 (PID $p)" }
}