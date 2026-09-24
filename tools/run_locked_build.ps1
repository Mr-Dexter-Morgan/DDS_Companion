param(
    [Parameter(Mandatory = $true)]
    [string]$BatchPath
)

$mutexName = "Local\DDS_Companion_Windows_Build_v1"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$acquired = $false

try {
    try {
        $acquired = $mutex.WaitOne(0, $false)
    }
    catch [System.Threading.AbandonedMutexException] {
        $acquired = $true
    }

    if (-not $acquired) {
        Write-Error "[DDS] Another Windows build is already active."
        exit 16
    }

    $env:DDS_BUILD_LOCK_HELD = "1"
    $quotedBatch = '"' + $BatchPath + '"'
    $process = Start-Process -FilePath $env:ComSpec -ArgumentList @("/d", "/c", $quotedBatch) -NoNewWindow -Wait -PassThru
    exit $process.ExitCode
}
finally {
    if ($acquired) {
        try { $mutex.ReleaseMutex() } catch {}
    }
    $mutex.Dispose()
}
