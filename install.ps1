# Установка автовыкладки на Авито (Windows 10/11). Запуск из папки репозитория, ПРАВА АДМИНИСТРАТОРА НЕ НУЖНЫ:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -TelegramToken "123:ABC" -TelegramChatId "123456789"
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -DryRun     (только показать, что будет сделано)
# Что делает: создаёт .venv и ставит зависимости; создаёт settings.json; при заданных -TelegramToken/-TelegramChatId пишет
# secrets\telegram.json; настраивает автозапуск наблюдателя (AvitoWatch), сторожа (AvitoGuard, каждые 5 минут) и сайта.
param([string]$TelegramToken = '', [string]$TelegramChatId = '', [switch]$NoAutostart, [switch]$DryRun)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
function Step($t) { Write-Host "==> $t" -ForegroundColor Cyan }
function Run($desc, [scriptblock]$sb) { if ($DryRun) { Write-Host "    [dry-run] $desc" } else { & $sb } }

Step 'Ищу Python 3.10+'
$py = $null
foreach ($c in @('py -3', 'python')) {
  try { $v = & cmd /c "$c --version 2>&1"; if ($v -match 'Python 3\.(\d+)' -and [int]$Matches[1] -ge 10) { $py = $c; break } } catch {}
}
if (-not $py) { throw 'Нужен Python 3.10 или новее (python.org, при установке отметьте Add to PATH).' }
Write-Host "    найден: $py"

Step 'Создаю виртуальное окружение .venv и ставлю зависимости'
Run 'python -m venv .venv; pip install -r requirements.txt' {
  & cmd /c "$py -m venv `"$root\.venv`""
  & "$root\.venv\Scripts\python.exe" -m pip install --upgrade pip | Out-Null
  & "$root\.venv\Scripts\python.exe" -m pip install -r "$root\requirements.txt"
}

Step 'Файлы настроек'
Run 'settings.json и config.json из примеров' {
  if (-not (Test-Path "$root\settings.json")) { Copy-Item "$root\settings.example.json" "$root\settings.json" }
  if (-not (Test-Path "$root\автовыкладка\config.json")) { Copy-Item "$root\автовыкладка\config.example.json" "$root\автовыкладка\config.json" }
  if (-not (Test-Path "$root\data")) { New-Item -ItemType Directory "$root\data" | Out-Null }
}
if ($TelegramToken -and $TelegramChatId) {
  Run 'secrets\telegram.json' {
    New-Item -ItemType Directory -Force "$root\secrets" | Out-Null
    $json = '{"token": "' + $TelegramToken + '", "chat_id": "' + $TelegramChatId + '"}'
    [IO.File]::WriteAllText("$root\secrets\telegram.json", $json, (New-Object Text.UTF8Encoding($false)))
  }
} else { Write-Host '    Telegram не задан: уведомления о сообщениях работать не будут (см. README, раздел Telegram).' -ForegroundColor Yellow }

if ($NoAutostart) { Write-Host 'Автозапуск пропущен (-NoAutostart).'; exit 0 }

$pyw = "$root\.venv\Scripts\pythonw.exe"
$startup = [Environment]::GetFolderPath('Startup')
function Add-Shortcut($name, $target, $arguments, $workdir) {
  $s = (New-Object -ComObject WScript.Shell).CreateShortcut("$startup\$name.lnk")
  $s.TargetPath = $target; $s.Arguments = $arguments; $s.WorkingDirectory = $workdir; $s.WindowStyle = 7; $s.Save()
}

Step 'Автозапуск наблюдателя за сообщениями (AvitoWatch)'
Run 'schtasks ONLOGON или ярлык в автозагрузке' {
  $tr = "`"$pyw`" `"$root\avito_watch.py`""
  & schtasks /Create /TN AvitoWatch /SC ONLOGON /TR $tr /F *> $null
  if ($LASTEXITCODE -ne 0) {
    Write-Host '    Планировщик отказал (нужны права администратора): использую ярлык в автозагрузке.' -ForegroundColor Yellow
    Add-Shortcut 'AvitoWatch' $pyw "`"$root\avito_watch.py`"" $root
  }
}

Step 'Сторож наблюдателя (AvitoGuard, каждые 5 минут)'
Run 'schtasks MINUTE /MO 5' {
  $tr = "`"$pyw`" `"$root\avito_guard.py`""
  & schtasks /Create /TN AvitoGuard /SC MINUTE /MO 5 /TR $tr /F *> $null
  if ($LASTEXITCODE -ne 0) { Write-Host '    Не удалось создать задачу AvitoGuard: сторож не будет работать (необязательно).' -ForegroundColor Yellow }
}

Step 'Автозапуск сайта автовыкладки (ярлык в автозагрузке)'
Run 'ярлык АвитоАвтовыкладка' { Add-Shortcut 'АвитоАвтовыкладка' $pyw 'app.py' "$root\автовыкладка" }

Write-Host ''
Write-Host 'Готово. Дальше: README.md, раздел «Первый запуск» (вход в Авито, при необходимости обход VPN, Telegram).' -ForegroundColor Green
Write-Host 'Сразу запустить без перезагрузки: автовыкладка\запуск_сайта.bat и  .venv\Scripts\pythonw.exe avito_watch.py'
