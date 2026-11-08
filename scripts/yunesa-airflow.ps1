param(
    [Parameter(Position = 0)]
    [ValidateSet("on", "off", "status", "logs", "tunnel")]
    [string]$Action = "status",

    [Parameter(Position = 1)]
    [ValidateRange(1,1000)]
    [int]$Lines = 50,

    [string]$SshKey = "$env:USERPROFILE\.ssh\yunesa-prod-key.pem",
    [string]$Server = "ubuntu@23.20.126.187",
    [ValidateRange(1,65535)]
    [int]$SshPort = 22,
    [string]$KnownHostsFile = '',
    [ValidateRange(1,65535)]
    [int]$LocalPort = 8080,
    [ValidatePattern('^[A-Za-z0-9.-]+$')]
    [string]$TunnelHost = '127.0.0.1'
)

$ErrorActionPreference = "Stop"
$SshOptions = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no')
$SshOptions += @('-p', "$SshPort")
if ($KnownHostsFile) { $SshOptions += @('-o', "UserKnownHostsFile=$KnownHostsFile") }

if ($Action -eq "tunnel") {
    Write-Host "Opening Airflow at http://localhost:$LocalPort (Ctrl+C to close)..."
    & ssh @SshOptions -i $SshKey -o ExitOnForwardFailure=yes -N -L "${LocalPort}:${TunnelHost}:8080" $Server
    exit $LASTEXITCODE
}

if ($Action -eq "logs") {
    & ssh @SshOptions -i $SshKey $Server "sudo -n /opt/yunesa-app/bin/airflow logs --lines $Lines"
    exit $LASTEXITCODE
}

& ssh @SshOptions -i $SshKey $Server "sudo -n /opt/yunesa-app/bin/airflow $Action"
exit $LASTEXITCODE
