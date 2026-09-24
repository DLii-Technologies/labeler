# Run on a disposable Windows runner after building the MSI.
$ErrorActionPreference = 'Stop'
$msi = (Resolve-Path "$PSScriptRoot/../dist/dlii-labeler-windows.msi").Path
$installDir = Join-Path $env:LOCALAPPDATA 'Labeler installer test'
$originalPath = [Environment]::GetEnvironmentVariable('Path', 'User')

function Invoke-Msi([string] $Arguments, [string] $LogName) {
    $log = Join-Path $env:TEMP $LogName
    $process = Start-Process msiexec.exe -ArgumentList "$Arguments /qn /norestart /l*v `"$log`"" -Wait -PassThru
    if ($process.ExitCode -notin @(0, 3010)) {
        Get-Content $log
        throw "Windows Installer failed with exit code $($process.ExitCode)"
    }
}

foreach ($withPath in @($false, $true)) {
    $features = if ($withPath) { 'ADDLOCAL=App,AddToPath' } else { '' }
    try {
        Invoke-Msi "/i `"$msi`" INSTALLFOLDER=`"$installDir`" $features" "labeler-install-$withPath.log"
        if (-not (Test-Path "$installDir/dlii_labeler.exe")) {
            throw 'Application was not installed in the selected directory'
        }
        $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        if ($withPath) {
            $entries = @($userPath -split ';' | ForEach-Object { $_.TrimEnd('\') })
            if ($installDir -notin $entries) { throw 'Installer did not add the selected directory to PATH' }
            # Refresh this process as a newly opened terminal would, then check command discovery.
            $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + $userPath
            if ((Get-Command dlii_labeler.exe).Source -ne "$installDir\dlii_labeler.exe") {
                throw 'CLI command did not resolve to the installed executable'
            }
        } elseif ($userPath -cne $originalPath) {
            throw 'Default installation changed PATH without opting in'
        }
    } finally {
        Invoke-Msi "/x `"$msi`"" "labeler-uninstall-$withPath.log"
    }
    if (Test-Path "$installDir/dlii_labeler.exe") { throw 'Uninstall left the executable behind' }
    $restoredPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    # Windows Installer can remove the trailing PATH separator when removing its entry.
    if (([string]$restoredPath).TrimEnd(';') -cne ([string]$originalPath).TrimEnd(';')) {
        throw "Uninstall did not restore the original user PATH (AddToPath=$withPath).`nExpected: [$originalPath]`nActual:   [$restoredPath]"
    }
}
Write-Host 'Installer passed: default install, optional PATH, CLI discovery, and uninstall.'
