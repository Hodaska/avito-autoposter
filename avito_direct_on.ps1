# Пускает подсети Авито мимо VPN через роутер. Маршруты ПОСТОЯННЫЕ (route -p): переживают перезагрузку. Запуск от администратора.
# Нужен, только если VPN перехватывает весь трафик и Авито просит проверку по IP. Шлюз (IP роутера) определяется сам; можно задать явно:
#   .vito_direct_on.ps1 -Gateway 192.168.1.1
param([string]$Gateway = '')
if (-not $Gateway) {
  $Gateway = (Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | Get-NetIPConfiguration | Where-Object IPv4DefaultGateway | Select-Object -First 1).IPv4DefaultGateway.NextHop
}
if (-not $Gateway) { Write-Error 'Не удалось определить IP роутера, укажите -Gateway'; exit 1 }
Write-Host "Шлюз: $Gateway"
$nets = '176.114.120.0','176.114.122.0','176.114.124.0','151.236.83.0','95.181.182.0','46.42.187.0'
foreach ($n in $nets) { route delete $n 2>$null | Out-Null; route -p add $n mask 255.255.255.0 $Gateway metric 1 }
route print -4 | Select-String '176.114|151.236.83|95.181.182|46.42.187'
