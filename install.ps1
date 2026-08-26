$ErrorActionPreference = "Stop"

$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillName = "play-llm-chess"
$skillSource = Join-Path $packageRoot "src\llm_chess\skills\$skillName"
$codexHome = if ($env:CODEX_HOME) {
    $env:CODEX_HOME
} else {
    Join-Path $env:USERPROFILE ".codex"
}
$skillsDirectory = [System.IO.Path]::GetFullPath((Join-Path $codexHome "skills"))
$skillDestination = [System.IO.Path]::GetFullPath((Join-Path $skillsDirectory $skillName))
$skillMarkerPath = Join-Path $skillsDirectory "$skillName.llm-chess-managed"
$skillMarkerOwner = "llm-chess:$skillName"

if (-not (Test-Path -LiteralPath (Join-Path $skillSource "SKILL.md") -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $skillSource "agents\openai.yaml") -PathType Leaf)) {
    throw "Codex 스킬 원본이 완전하지 않습니다: $skillSource"
}

$destinationParent = [System.IO.Directory]::GetParent($skillDestination).FullName
if (-not [System.StringComparer]::OrdinalIgnoreCase.Equals($destinationParent, $skillsDirectory)) {
    throw "Codex 스킬 대상 경로가 skills 폴더 밖을 가리킵니다: $skillDestination"
}

New-Item -ItemType Directory -Force -Path $skillsDirectory | Out-Null
$hasSkillMarker = Test-Path -LiteralPath $skillMarkerPath -PathType Leaf
if ($hasSkillMarker) {
    $existingSkillMarkerOwner = (Get-Content -LiteralPath $skillMarkerPath -Raw).Trim()
    if ($existingSkillMarkerOwner -ne $skillMarkerOwner) {
        throw "기존 Codex 스킬 소유권 표시를 보존했습니다: $skillMarkerPath"
    }
}

if (Test-Path -LiteralPath $skillDestination) {
    if (-not $hasSkillMarker) {
        throw "기존 Codex 스킬을 보존했습니다: $skillDestination"
    }

    $destinationItem = Get-Item -LiteralPath $skillDestination -Force
    if (-not $destinationItem.PSIsContainer -or
        ($destinationItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "관리 대상 Codex 스킬 경로가 일반 폴더가 아닙니다: $skillDestination"
    }
}

& uv tool install --python 3.13 --force --reinstall-package llm-chess $packageRoot
if ($LASTEXITCODE -ne 0) {
    throw "uv tool install failed with exit code $LASTEXITCODE"
}

$binDirectory = Join-Path $env:USERPROFILE "bin"
$chessExecutable = Join-Path $env:USERPROFILE ".local\bin\chess.exe"
$launcherPath = Join-Path $binDirectory "chess.exe"
$markerPath = Join-Path $binDirectory "chess.exe.llm-chess"
$legacyShimPath = Join-Path $binDirectory "chess.cmd"

New-Item -ItemType Directory -Force -Path $binDirectory | Out-Null
if ((Test-Path -LiteralPath $launcherPath) -and -not (Test-Path -LiteralPath $markerPath)) {
    throw "기존 chess.exe를 보존했습니다. 다른 명령 이름을 사용하려면 설치 스크립트를 수정하세요: $launcherPath"
}
Copy-Item -LiteralPath $chessExecutable -Destination $launcherPath -Force
Set-Content -LiteralPath $markerPath -Value "llm-chess launcher" -Encoding ASCII

if (Test-Path -LiteralPath $legacyShimPath) {
    $legacyShim = Get-Content -LiteralPath $legacyShimPath -Raw
    if ($legacyShim -match [regex]::Escape($chessExecutable)) {
        Remove-Item -LiteralPath $legacyShimPath -Force
    }
}

$installId = [System.Guid]::NewGuid().ToString("N")
$stagingPath = Join-Path $skillsDirectory "$skillName.installing-$installId"
$backupPath = Join-Path $skillsDirectory "$skillName.backup-$installId"
$hadSkillDestination = Test-Path -LiteralPath $skillDestination
$previousSkillMoved = $false
$newSkillPlaced = $false
$skillInstalled = $false

try {
    Copy-Item -LiteralPath $skillSource -Destination $stagingPath -Recurse
    if (-not (Test-Path -LiteralPath (Join-Path $stagingPath "SKILL.md") -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $stagingPath "agents\openai.yaml") -PathType Leaf)) {
        throw "Codex 스킬 복사본이 완전하지 않습니다: $stagingPath"
    }

    if (-not $hasSkillMarker) {
        Set-Content -LiteralPath $skillMarkerPath -Value $skillMarkerOwner -Encoding ASCII
    }
    if ($hadSkillDestination) {
        Move-Item -LiteralPath $skillDestination -Destination $backupPath
        $previousSkillMoved = $true
    }
    Move-Item -LiteralPath $stagingPath -Destination $skillDestination
    $newSkillPlaced = $true
    $skillInstalled = $true
} catch {
    if ($newSkillPlaced -and (Test-Path -LiteralPath $skillDestination)) {
        Remove-Item -LiteralPath $skillDestination -Recurse -Force
    }
    if ($previousSkillMoved -and (Test-Path -LiteralPath $backupPath)) {
        Move-Item -LiteralPath $backupPath -Destination $skillDestination
    }
    if (-not $hasSkillMarker -and (Test-Path -LiteralPath $skillMarkerPath -PathType Leaf)) {
        Remove-Item -LiteralPath $skillMarkerPath -Force
    }
    throw
} finally {
    if (Test-Path -LiteralPath $stagingPath) {
        Remove-Item -LiteralPath $stagingPath -Recurse -Force
    }
    if ($skillInstalled -and (Test-Path -LiteralPath $backupPath)) {
        Remove-Item -LiteralPath $backupPath -Recurse -Force
    }
}

Write-Host "설치가 완료되었습니다: $launcherPath"
Write-Host "Codex 스킬이 설치되었습니다: $skillDestination"
