# Демо пересборки для защиты: меняем одно число в учебном слое и пересобираем курс одной командой.
# Запуск из папки g2k:   powershell -ExecutionPolicy Bypass -File demo\rebuild_demo.ps1
# Вернуть как было:      powershell -ExecutionPolicy Bypass -File demo\rebuild_demo.ps1 -Undo
param([switch]$Undo)
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$patch = "patches\latyshova.json"
if ($Undo) {
    if (Test-Path $patch) { Remove-Item $patch }
    Write-Host "Правка убрана, пересобираю курс..."
} else {
    New-Item -ItemType Directory -Force patches | Out-Null
    $json = @'
[{"target": "latyshova.mud_properties", "field": "course.numbers.0.text",
  "value": "Оптимальная водоотдача глинистого раствора: 5—8 см³/ч. Условия изучения наиболее благоприятны.",
  "minutes": 1, "reason": "демо пересборки на защите: 4 → 5"}]
'@
    [System.IO.File]::WriteAllText((Join-Path (Get-Location) $patch), $json, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "Правка: шаг «Как буровой раствор искажает измерения», «Цифры и условия»: 4—8 → 5—8 см³/ч"
}
python run.py build latyshova --stage course
Start-Process "out\latyshova\course\index.html"
Write-Host "Откройте шаг 2 «Как буровой раствор искажает измерения» → раздел «Цифры и условия»."
