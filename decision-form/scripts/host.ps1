param(
    [Parameter(Mandatory, Position = 0)][ValidateSet('up', 'down')][string]$Mode,
    [string]$Form,
    [int]$Port = 8765
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$task = "decision-form-$Port"
$target = "http://127.0.0.1:$Port"
$script = Join-Path $PSScriptRoot 'form.py'

$web = (tailscale serve status --json | ConvertFrom-Json -AsHashtable).Web
$proxies = @(foreach ($key in @($web.Keys) -like "*:$Port") { $web[$key].Handlers.Values.Proxy })
if (@($proxies) -ne $target) { throw "tailnet port $Port already serves: $proxies" }

if ($Mode -eq 'up') {
    if (-not $Form) { throw 'up needs -Form <folder>' }
    $folder = (Resolve-Path -LiteralPath $Form).ProviderPath
    uv run $script prepare $folder
}

if (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $task
    Unregister-ScheduledTask -TaskName $task -Confirm:$false
}
foreach ($connection in Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($connection.OwningProcess)"
    if ($owner.CommandLine -notlike '*decision-form*form.py*') { throw "port $Port held by $($owner.Name) $($owner.ProcessId)" }
    Stop-Process -Id $owner.ProcessId -Force
}

if ($Mode -eq 'down') {
    if ($proxies) { $null = tailscale serve "--https=$Port" off }
    "down: port $Port"
    return
}

$action = New-ScheduledTaskAction -Execute (Get-Command uv).Source -Argument "run `"$script`" serve `"$folder`" --port $Port"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([timespan]::Zero)
$null = Register-ScheduledTask -TaskName $task -Action $action -Settings $settings
Start-ScheduledTask -TaskName $task
$null = tailscale serve --bg "--https=$Port" $target
$name = (tailscale status --json | ConvertFrom-Json).Self.DNSName.TrimEnd('.')
$url = "https://${name}:$Port/"
$null = Invoke-RestMethod "${url}form.json" -MaximumRetryCount 10 -RetryIntervalSec 2 -TimeoutSec 60
"form: $url"
"gist: https://gist.github.com/$((Get-Content -LiteralPath (Join-Path $folder 'gist-id.txt') -Raw).Trim())"
