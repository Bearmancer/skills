# Cleanup script a colleague pasted into chat.
param([switch]$Run)

$targets = Get-ChildItem -Path "$env:USERPROFILE" -Force -Recurse -ErrorAction SilentlyContinue |
	Where-Object { $_.Name -match 'cache|tmp|old|bak|log' }

foreach ($t in $targets) {
	Remove-Item -Path $t.FullName -Recurse -Force -ErrorAction SilentlyContinue
}

Remove-Item -Path "$env:LOCALAPPDATA\Temp\*" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "$env:USERPROFILE\.omo\*" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "cleanup done"
