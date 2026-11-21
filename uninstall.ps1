# Убирает автозапуск (задачи AvitoWatch/AvitoGuard и ярлыки в автозагрузке). Файлы репозитория и профиль Авито не трогает.
$startup = [Environment]::GetFolderPath('Startup')
foreach ($t in 'AvitoWatch', 'AvitoGuard') { & schtasks /Delete /TN $t /F 2>$null | Out-Null }
foreach ($l in 'AvitoWatch', 'АвитоАвтовыкладка') { Remove-Item "$startup\$l.lnk" -ErrorAction SilentlyContinue }
Write-Host 'Автозапуск удалён. Запущенные процессы (pythonw, Chrome профиля profile_account) закройте вручную или перезагрузите ПК.'
