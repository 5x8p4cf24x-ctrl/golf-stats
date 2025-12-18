$ErrorActionPreference = "Stop"

$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm"
$backupDir  = "C:\Users\sergi\Documents\golf-stats\backups"

$pidTag = $PID
$backupPath = Join-Path $backupDir "golf_stats_${timestamp}_$pidTag.dump"
$logPath    = Join-Path $backupDir "backup_${timestamp}_$pidTag.log"

New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

"START $(Get-Date -Format s)" | Out-File -FilePath $logPath -Encoding utf8

$env:PGCONNECT_TIMEOUT = "15"
$env:PGPASSWORD = "h6PWbwtv4U5XVtmyRoxe0qJRwDb2sEM6"

$pgDump = "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"

& $pgDump `
  -h dpg-d516htchg0os73bmiqo0-a.virginia-postgres.render.com `
  -p 5432 `
  -U golfstatsdb1_user `
  -d golfstatsdb1 `
  -w `
  -F c `
  -f $backupPath `
  *>> $logPath

$exitCode = $LASTEXITCODE
"EXITCODE $exitCode" | Out-File -FilePath $logPath -Append -Encoding utf8

if ($exitCode -ne 0) {
  throw "pg_dump failed with exit code $exitCode. Check log: $logPath"
}

# Rotación: borrar backups y logs de >30 días
Get-ChildItem $backupDir -Filter "golf_stats_*.dump" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem $backupDir -Filter "backup_*.log"      | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force -ErrorAction SilentlyContinue


"OK - Backup created: $backupPath" | Out-File -FilePath $logPath -Append -Encoding utf8
exit 0
