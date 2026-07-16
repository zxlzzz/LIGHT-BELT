[CmdletBinding()]
param(
    [string]$VisualStudioPath
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pioDir = Join-Path $projectDir ".pio"
$buildDir = Join-Path $pioDir "native-msvc"
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

$env:PLATFORMIO_CORE_DIR = Join-Path $pioDir "core"
$env:PLATFORMIO_PLATFORMS_DIR = Join-Path $pioDir "platforms"
$env:PLATFORMIO_PACKAGES_DIR = Join-Path $pioDir "packages"
$env:PLATFORMIO_CACHE_DIR = Join-Path $pioDir "cache"
$env:TEMP = $buildDir
$env:TMP = $buildDir
$env:TMPDIR = $buildDir
$env:PLATFORMIO_SETTING_ENABLE_TELEMETRY = "No"

function Find-UnitySource {
    $candidates = @(
        (Join-Path $pioDir "libdeps\native\Unity\src"),
        (Join-Path $pioDir "packages\framework-arduinoespressif32\tools\sdk\esp32s3\include\unity\unity\src")
    )
    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath (Join-Path $candidate "unity.h")) -and
            (Test-Path -LiteralPath (Join-Path $candidate "unity.c"))) {
            return (Resolve-Path $candidate).Path
        }
    }
    return $null
}

$unityDir = Find-UnitySource
if (-not $unityDir) {
    $pio = Get-Command pio -ErrorAction Stop
    & $pio.Source pkg install -d $projectDir -e native
    if ($LASTEXITCODE -ne 0) {
        throw "PlatformIO failed to install the native Unity dependency."
    }
    $unityDir = Find-UnitySource
}
if (-not $unityDir) {
    throw "Unity source was not found under the project-local .pio directory."
}

if (-not $VisualStudioPath) {
    $vswhereCandidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"),
        (Join-Path $env:ProgramFiles "Microsoft Visual Studio\Installer\vswhere.exe")
    )
    $vswhere = $vswhereCandidates |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
    if ($vswhere) {
        $installations = @(& $vswhere -latest -products * `
            -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
            -property installationPath)
        $VisualStudioPath = $installations |
            Where-Object { $_ } |
            Select-Object -First 1
    }
}
if (-not $VisualStudioPath) {
    throw "Visual Studio with the C++ x64 tools was not found."
}

$vcvars = Join-Path $VisualStudioPath "VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path -LiteralPath $vcvars)) {
    throw "Missing Visual Studio environment script: $vcvars"
}

$relativeSources = @(
    "test\test_protocol.cpp",
    "src\protocol.cpp",
    "src\presentation_clock.cpp",
    "src\frame_state.cpp",
    "src\owned_frame.cpp",
    "src\ws2811_spi_encoder.cpp",
    "src\ws2811_spi3_encoder.cpp",
    "src\ws2811_spi6_encoder.cpp",
    "src\ws2811_parallel_spi_encoder.cpp",
    "src\ws2811_rmt_encoder.cpp"
)
$sources = foreach ($relativeSource in $relativeSources) {
    $source = Join-Path $projectDir $relativeSource
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing native test source: $source"
    }
    (Resolve-Path $source).Path
}

$executable = Join-Path $buildDir "esp32-native-tests.exe"
$compilerArgs = @(
    "/nologo",
    "/std:c++17",
    "/EHsc",
    "/W4",
    "/WX",
    "/wd4310",
    "/I`"$unityDir`""
)
$compilerArgs += $sources | ForEach-Object { "`"$_`"" }
$compilerArgs += "`"$(Join-Path $unityDir 'unity.c')`""
$compilerArgs += "/Fe:`"$executable`""

$compileCommand = "call `"$vcvars`" >nul && cd /d `"$buildDir`" && cl " +
    ($compilerArgs -join " ")
& $env:COMSPEC /d /c $compileCommand
if ($LASTEXITCODE -ne 0) {
    throw "MSVC native firmware test build failed with exit code $LASTEXITCODE."
}

& $executable
if ($LASTEXITCODE -ne 0) {
    throw "Native firmware tests failed with exit code $LASTEXITCODE."
}

Write-Output "MSVC_NATIVE_TESTS_OK"
