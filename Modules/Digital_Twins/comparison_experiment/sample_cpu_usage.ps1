param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [Parameter(Mandatory = $true)]
    [string]$StopPath,
    [double]$IntervalSeconds = 1.0
)

$ErrorActionPreference = 'SilentlyContinue'
$culture = [System.Globalization.CultureInfo]::InvariantCulture

function Get-ProcessCpuSum([string[]]$Names) {
    $sum = 0.0
    foreach ($name in $Names) {
        $items = Get-Process -Name $name -ErrorAction SilentlyContinue
        foreach ($item in $items) {
            if ($null -ne $item.CPU) {
                $sum += [double]$item.CPU
            }
        }
    }
    return $sum
}

$parent = Split-Path -Parent $OutputPath
if ($parent -and -not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

'timestamp_utc,total_cpu_pct,matlab_cpu_s,python_cpu_s,lm_studio_cpu_s' |
    Set-Content -LiteralPath $OutputPath -Encoding utf8

while (-not (Test-Path -LiteralPath $StopPath)) {
    $totalCpu = [double]::NaN
    $sample = Get-Counter '\Processor(_Total)\% Processor Time' -ErrorAction SilentlyContinue
    if ($null -ne $sample) {
        $totalCpu = [double]$sample.CounterSamples[0].CookedValue
    }

    $timestamp = [DateTimeOffset]::UtcNow.ToString('o', $culture)
    $matlabCpu = Get-ProcessCpuSum @('MATLAB', 'matlab')
    $pythonCpu = Get-ProcessCpuSum @('python', 'pythonw')
    $lmCpu = Get-ProcessCpuSum @('LM Studio', 'lms', 'llama-server')
    $line = '{0},{1},{2},{3},{4}' -f `
        $timestamp, `
        $totalCpu.ToString('F6', $culture), `
        $matlabCpu.ToString('F6', $culture), `
        $pythonCpu.ToString('F6', $culture), `
        $lmCpu.ToString('F6', $culture)
    Add-Content -LiteralPath $OutputPath -Value $line -Encoding utf8
    Start-Sleep -Milliseconds ([math]::Max(100, [int]($IntervalSeconds * 1000)))
}
