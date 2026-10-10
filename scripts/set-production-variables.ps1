#requires -Version 5.1
<#
.SYNOPSIS
Collect production credentials locally and save them as GitLab CI/CD variables.
.DESCRIPTION
Requires an authenticated glab installation. Secret input uses SecureString and
is sent to glab through stdin. Existing production passwords are preserved.
New variables are protected, masked, hidden, and raw, with scope production.
GitLab cannot change an existing variable from visible to hidden.
.EXAMPLE
powershell.exe -NoProfile -File .\scripts\set-production-variables.ps1 -ValidateOnly
.EXAMPLE
powershell.exe -NoProfile -File .\scripts\set-production-variables.ps1
.EXAMPLE
powershell.exe -NoProfile -File .\scripts\set-production-variables.ps1 -GlabPath C:\path\glab.exe
#>
[CmdletBinding()]
param(
    [uri] $Repository = 'https://gitlab.tugasakhir.space/rizkyyanuark/yunesa',
    [string] $GlabPath,
    [switch] $ValidateOnly,
    [switch] $AdminPasswordOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$scope = 'production'
$planned = [System.Collections.Generic.List[object]]::new()
$savedKeys = [System.Collections.Generic.List[string]]::new()

function ConvertTo-WindowsArgument {
    param([AllowEmptyString()] [string] $Argument)
    $quoted = [System.Text.StringBuilder]::new()
    [void] $quoted.Append('"')
    $backslashes = 0
    foreach ($character in $Argument.ToCharArray()) {
        if ($character -eq '\') { $backslashes++; continue }
        if ($character -eq '"') {
            [void] $quoted.Append([char] '\', $backslashes * 2 + 1)
        }
        else { [void] $quoted.Append([char] '\', $backslashes) }
        [void] $quoted.Append($character)
        $backslashes = 0
    }
    [void] $quoted.Append([char] '\', $backslashes * 2)
    [void] $quoted.Append('"')
    return $quoted.ToString()
}

function Invoke-Glab {
    param(
        [string[]] $Arguments,
        [string] $Operation,
        [System.Security.SecureString] $InputSecret,
        [switch] $CaptureOutput
    )
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $script:GlabPath
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.EnvironmentVariables['GITLAB_HOST'] = $Repository.Host
    $startInfo.EnvironmentVariables['GLAB_CHECK_UPDATE'] = 'false'
    $startInfo.EnvironmentVariables['NO_COLOR'] = '1'
    [void] $startInfo.EnvironmentVariables.Remove('DEBUG')
    [void] $startInfo.EnvironmentVariables.Remove('GLAB_DEBUG_HTTP')
    $startInfo.Arguments = ($Arguments | ForEach-Object { ConvertTo-WindowsArgument $_ }) -join ' '

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $buffer = [IntPtr]::Zero
    $started = $false
    $inputWriter = $null
    try {
        [void] $process.Start()
        $started = $true
        $outputTask = $process.StandardOutput.ReadToEndAsync()
        $errorTask = $process.StandardError.ReadToEndAsync()
        $inputWriter = [System.IO.StreamWriter]::new($process.StandardInput.BaseStream, [System.Text.UTF8Encoding]::new($false), 1024, $true)
        if ($null -ne $InputSecret) {
            $buffer = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($InputSecret)
            for ($index = 0; $index -lt $InputSecret.Length; $index++) {
                $inputWriter.Write([char] [System.Runtime.InteropServices.Marshal]::ReadInt16($buffer, $index * 2))
            }
        }
        $inputWriter.Dispose()
        $inputWriter = $null
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(60000)) {
            $process.Kill()
            throw [System.TimeoutException]::new("$Operation timed out. Raw CLI output was suppressed.")
        }
        $output = $outputTask.GetAwaiter().GetResult()
        [void] $errorTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            throw [System.InvalidOperationException]::new("$Operation failed (exit $($process.ExitCode)). Raw CLI output was suppressed.")
        }
        if ($CaptureOutput) { return $output }
    }
    catch [System.ComponentModel.Win32Exception] {
        throw [System.InvalidOperationException]::new('Could not start glab. Check -GlabPath and the installation.')
    }
    catch [System.IO.IOException] {
        throw [System.InvalidOperationException]::new("$Operation failed while communicating with glab. Raw CLI output was suppressed.")
    }
    finally {
        if ($buffer -ne [IntPtr]::Zero) { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($buffer) }
        if ($started -and -not $process.HasExited) { $process.Kill() }
        if ($null -ne $inputWriter) { $inputWriter.Dispose() }
        $process.Dispose()
    }
}

function Get-VariableMetadata {
    $records = [System.Collections.Generic.List[object]]::new()
    $filter = 'map({key,variable_type,environment_scope,protected,masked,hidden,raw})'
    for ($page = 1; $page -le 81; $page++) {
        $json = Invoke-Glab -Arguments @('variable', 'list', '--repo', $Repository.AbsoluteUri.TrimEnd('/'), '--output', 'json', '--jq', $filter, '--per-page', '100', '--page', "$page") -Operation 'Variable metadata check' -CaptureOutput
        try {
            $decoded = ConvertFrom-Json -InputObject $json -ErrorAction Stop
            $items = @()
            if ($null -ne $decoded) { $items = @($decoded) }
        }
        catch [System.ArgumentException] { throw 'glab returned invalid variable metadata JSON.' }
        foreach ($item in $items) { $records.Add($item) }
        if ($items.Count -lt 100) { return $records.ToArray() }
    }
    throw 'Variable metadata pagination exceeded the GitLab project limit.'
}

function Find-ProductionVariable {
    param([object[]] $Metadata, [string] $Key)
    return $Metadata | Where-Object { $_.key -ceq $Key -and $_.environment_scope -ceq $scope } | Select-Object -First 1
}

function Read-MaskedValue {
    param([string] $Key, [string[]] $VariableNames, [switch] $HttpsUrl, [switch] $AdminPassword)
    while ($true) {
        $secret = Read-Host "$Key (input disembunyikan; q untuk batal)" -AsSecureString
        $buffer = [IntPtr]::Zero
        $accepted = $false
        try {
            $buffer = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
            if ($secret.Length -eq 1 -and [char] [System.Runtime.InteropServices.Marshal]::ReadInt16($buffer) -in @('q', 'Q')) {
                throw [System.OperationCanceledException]::new('Input cancelled.')
            }
            $valid = $secret.Length -ge 8 -and $secret.Length -le 10000
            for ($index = 0; $valid -and $index -lt $secret.Length; $index++) {
                $character = [char] [System.Runtime.InteropServices.Marshal]::ReadInt16($buffer, $index * 2)
                if ([char]::IsWhiteSpace($character) -or [char]::IsControl($character)) { $valid = $false }
            }
            foreach ($name in $VariableNames) {
                if ($name.Length -ne $secret.Length) { continue }
                $matchesName = $true
                for ($index = 0; $matchesName -and $index -lt $name.Length; $index++) {
                    $matchesName = $name[$index] -ceq [char] [System.Runtime.InteropServices.Marshal]::ReadInt16($buffer, $index * 2)
                }
                if ($matchesName) { $valid = $false; break }
            }
            if ($valid -and $HttpsUrl) {
                $url = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($buffer)
                $parsedUrl = $null
                $valid = [uri]::TryCreate($url, [System.UriKind]::Absolute, [ref] $parsedUrl) -and $parsedUrl.Scheme -eq 'https' -and -not [string]::IsNullOrEmpty($parsedUrl.Host) -and [string]::IsNullOrEmpty($parsedUrl.UserInfo)
                $url = $null
            }
            if ($valid -and $AdminPassword) {
                $hasLower = $false; $hasUpper = $false; $hasDigit = $false; $hasSymbol = $false
                for ($index = 0; $index -lt $secret.Length; $index++) {
                    $character = [char] [System.Runtime.InteropServices.Marshal]::ReadInt16($buffer, $index * 2)
                    if ([char]::IsLower($character)) { $hasLower = $true }
                    if ([char]::IsUpper($character)) { $hasUpper = $true }
                    if ([char]::IsDigit($character)) { $hasDigit = $true }
                    if (-not [char]::IsLetterOrDigit($character)) { $hasSymbol = $true }
                }
                $valid = $secret.Length -ge 12 -and $secret.Length -le 128 -and $hasLower -and $hasUpper -and $hasDigit -and $hasSymbol
            }
            if ($valid) { $accepted = $true; return $secret }
            if ($AdminPassword) { Write-Host 'ADMIN_PASSWORD harus 12-128 karakter, memuat huruf besar, huruf kecil, angka, dan simbol; tanpa spasi untuk masking GitLab.' }
            else { Write-Host "$Key harus 8-10000 karakter, satu baris tanpa spasi, dan berbeda dari nama variabel. URL Supabase harus HTTPS." }
        }
        finally {
            if ($buffer -ne [IntPtr]::Zero) { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($buffer) }
            if (-not $accepted) { $secret.Dispose() }
        }
    }
}

function New-GeneratedSecret {
    $bytes = [byte[]]::new(48)
    $secret = [System.Security.SecureString]::new()
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
        $encoded = [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_')
        foreach ($character in $encoded.ToCharArray()) { $secret.AppendChar($character) }
        $secret.MakeReadOnly()
        return $secret
    }
    finally {
        $generator.Dispose()
        [Array]::Clear($bytes, 0, $bytes.Length)
        $encoded = $null
    }
}

try {
    if (-not $Repository.IsAbsoluteUri -or $Repository.Scheme -ne 'https' -or $Repository.AbsolutePath.Trim('/').Split('/').Count -lt 2 -or -not [string]::IsNullOrEmpty($Repository.UserInfo)) {
        throw 'Repository must be an HTTPS project URL without embedded credentials.'
    }
    if ([string]::IsNullOrWhiteSpace($GlabPath)) {
        $command = Get-Command glab -CommandType Application -ErrorAction SilentlyContinue
        $installedPath = Join-Path $env:LOCALAPPDATA 'Programs\glab\glab.exe'
        if ($null -ne $command) { $GlabPath = $command.Source }
        elseif (Test-Path -LiteralPath $installedPath -PathType Leaf) { $GlabPath = $installedPath }
        else { throw 'glab was not found. Install it or supply -GlabPath.' }
    }
    if (-not (Test-Path -LiteralPath $GlabPath -PathType Leaf)) { throw 'The glab executable path does not exist.' }
    $setHelp = Invoke-Glab -Arguments @('variable', 'set', '--help') -Operation 'CLI capability check' -CaptureOutput
    $listHelp = Invoke-Glab -Arguments @('variable', 'list', '--help') -Operation 'CLI capability check' -CaptureOutput
    if ($setHelp -notmatch '--hidden' -or $listHelp -notmatch '--jq') { throw 'This script requires glab with --hidden and --jq support.' }
    $metadata = @(Get-VariableMetadata)
    if ($ValidateOnly) {
        ConvertTo-Json -InputObject $metadata -Depth 4
        return
    }

    Write-Host 'Masukkan credential hanya di terminal lokal ini. Belum ada perubahan hingga Anda mengetik SIMPAN.'
    $keys = @('GEMINI_API_KEY', 'SILICONFLOW_API_KEY', 'GLOBAL_PASSWORD', 'JWT_SECRET_KEY', 'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'ADMIN_PASSWORD')
    $variableNames = @($metadata | ForEach-Object { $_.key }) + $keys
    if ($AdminPasswordOnly) {
        $planned.Add([pscustomobject]@{ Key = 'ADMIN_PASSWORD'; Value = (Read-MaskedValue -Key 'ADMIN_PASSWORD' -VariableNames $variableNames -AdminPassword); Generated = $false })
    }
    else {
    foreach ($key in @('GEMINI_API_KEY', 'SILICONFLOW_API_KEY')) {
        $planned.Add([pscustomobject]@{ Key = $key; Value = (Read-MaskedValue -Key $key -VariableNames $variableNames); Generated = $false })
    }
    foreach ($key in @('GLOBAL_PASSWORD', 'JWT_SECRET_KEY')) {
        if ($null -eq (Find-ProductionVariable -Metadata $metadata -Key $key)) {
            $planned.Add([pscustomobject]@{ Key = $key; Value = (New-GeneratedSecret); Generated = $true })
        }
    }
    $useSupabase = Read-Host 'Konfigurasi Supabase? ketik y untuk isi, n untuk lewati, atau q untuk batal'
    while ($useSupabase -notin @('y', 'n', 'q')) { $useSupabase = Read-Host 'Ketik y, n, atau q' }
    if ($useSupabase -eq 'q') { throw [System.OperationCanceledException]::new('Input cancelled.') }
    if ($useSupabase -eq 'y') {
        $planned.Add([pscustomobject]@{ Key = 'SUPABASE_URL'; Value = (Read-MaskedValue -Key 'SUPABASE_URL' -VariableNames $variableNames -HttpsUrl); Generated = $false })
        $planned.Add([pscustomobject]@{ Key = 'SUPABASE_SERVICE_ROLE_KEY'; Value = (Read-MaskedValue -Key 'SUPABASE_SERVICE_ROLE_KEY' -VariableNames $variableNames); Generated = $false })
    }
    }
    Write-Host "Tujuan: $($Repository.AbsoluteUri.TrimEnd('/')); scope: $scope; variabel: $($planned.Key -join ', ')."
    if ((Read-Host 'Ketik SIMPAN untuk menyimpan; input lain membatalkan') -cne 'SIMPAN') { throw [System.OperationCanceledException]::new('Input cancelled.') }

    $metadata = @(Get-VariableMetadata)
    foreach ($item in $planned) {
        $existing = Find-ProductionVariable -Metadata $metadata -Key $item.Key
        if ($item.Generated -and $null -ne $existing) { continue }
        $action = if ($null -eq $existing) { 'set' } else { 'update' }
        $arguments = @('variable', $action, $item.Key, '--repo', $Repository.AbsoluteUri.TrimEnd('/'), '--scope', $scope, '--type', 'env_var', '--protected', '--masked', '--raw')
        if ($action -eq 'set') { $arguments += '--hidden' }
        Invoke-Glab -Arguments $arguments -InputSecret $item.Value -Operation "Saving $($item.Key)"
        $savedKeys.Add($item.Key)
        Write-Host "$($item.Key): tersimpan ($action, scope $scope)."
    }
    $metadata = @(Get-VariableMetadata)
    foreach ($key in $savedKeys) {
        $record = Find-ProductionVariable -Metadata $metadata -Key $key
        if ($null -eq $record -or $record.variable_type -ne 'env_var' -or -not $record.protected -or -not $record.masked -or -not $record.raw) {
            throw "Metadata verification failed for $key. Check GitLab variable settings; values were not retrieved."
        }
        if (-not $record.hidden) { Write-Warning "$key sudah ada dan belum hidden; GitLab hanya mengizinkan hidden saat pembuatan." }
    }
    foreach ($key in @('GLOBAL_PASSWORD', 'JWT_SECRET_KEY')) {
        if ($key -notin $savedKeys) { Write-Host "${key}: nilai production yang sudah ada dipertahankan." }
    }
    ConvertTo-Json -InputObject $metadata -Depth 4
}
catch [System.OperationCanceledException] {
    Write-Host 'Dibatalkan. Tidak ada variabel yang diubah.'
}
catch {
    if ($savedKeys.Count -gt 0) { Write-Warning "Perubahan selesai sebagian: $($savedKeys -join ', '). Jalankan kembali untuk melanjutkan." }
    throw
}
finally {
    foreach ($item in $planned) { $item.Value.Dispose() }
}
