[CmdletBinding()]
param(
    [switch]$SkipKicad,
    [switch]$SkipSpice,
    [switch]$SkipPdf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path Variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$GeneratedRoot = Join-Path $ProjectRoot 'spice\generated'
$OutputRoot = Join-Path $GeneratedRoot 'preflight'
$ValidationOutput = Join-Path $GeneratedRoot 'validation'
$Failures = [System.Collections.Generic.List[string]]::new()
$Warnings = [System.Collections.Generic.List[string]]::new()

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
New-Item -ItemType Directory -Force -Path $ValidationOutput | Out-Null

function Write-Section {
    param([Parameter(Mandatory)][string]$Text)
    Write-Host "`n== $Text ==" -ForegroundColor Cyan
}

function Add-Failure {
    param([Parameter(Mandatory)][string]$Text)
    $Failures.Add($Text)
    Write-Host "FAIL: $Text" -ForegroundColor Red
}

function Add-Warning {
    param([Parameter(Mandatory)][string]$Text)
    $Warnings.Add($Text)
    Write-Host "WARN: $Text" -ForegroundColor Yellow
}

function Resolve-Executable {
    param(
        [Parameter(Mandatory)][string]$Name,
        [string[]]$Candidates = @()
    )

    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $Candidate).Path
        }
    }

    $Command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Command) {
        return $Command.Source
    }
    return $null
}

function Find-WinGetExecutable {
    param(
        [Parameter(Mandatory)][string]$PackagePattern,
        [Parameter(Mandatory)][string]$Executable
    )

    if (-not $env:LOCALAPPDATA) {
        return $null
    }
    $PackagesRoot = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    if (-not (Test-Path -LiteralPath $PackagesRoot -PathType Container)) {
        return $null
    }
    $PackageDirectories = Get-ChildItem -LiteralPath $PackagesRoot -Directory `
        -Filter $PackagePattern -ErrorAction SilentlyContinue
    foreach ($Directory in $PackageDirectories) {
        $Match = Get-ChildItem -LiteralPath $Directory.FullName -File -Recurse `
            -Filter $Executable -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($Match) {
            return $Match.FullName
        }
    }
    return $null
}

function Invoke-LoggedCommand {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][string]$Executable,
        [string[]]$ArgumentList = @(),
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter(Mandatory)][string]$LogPath
    )

    Write-Host $Label
    Push-Location $WorkingDirectory
    try {
        & $Executable @ArgumentList *> $LogPath
        $ExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($ExitCode -ne 0) {
        Add-Failure "$Label exited with code $ExitCode; see $LogPath"
        return $false
    }
    $WarningMatches = @(Select-String -LiteralPath $LogPath `
        -Pattern '\bwarning\b' -CaseSensitive:$false -ErrorAction SilentlyContinue)
    if ($WarningMatches) {
        Add-Warning "$Label emitted $($WarningMatches.Count) warning line(s); see $LogPath"
    }
    Write-Host "PASS: $Label" -ForegroundColor Green
    return $true
}

$KiCadCli = Resolve-Executable 'kicad-cli' @(
    'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe'
)
$Ngspice = Resolve-Executable 'ngspice_con' @(
    (Join-Path $ProjectRoot 'spice\runtime\ngspice-46\bin\ngspice_con.exe'),
    'C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe'
)
$Python = Resolve-Executable 'python'
$Git = Resolve-Executable 'git'
$Tesseract = Resolve-Executable 'tesseract' @(
    'C:\Program Files\Tesseract-OCR\tesseract.exe'
)
$PdfInfo = Resolve-Executable 'pdfinfo' @(
    (Find-WinGetExecutable 'oschwartz10612.Poppler*' 'pdfinfo.exe')
)
$PdfToText = Resolve-Executable 'pdftotext' @(
    (Find-WinGetExecutable 'oschwartz10612.Poppler*' 'pdftotext.exe')
)
$PdfToPpm = Resolve-Executable 'pdftoppm' @(
    (Find-WinGetExecutable 'oschwartz10612.Poppler*' 'pdftoppm.exe')
)

Write-Section 'Project state'
$LockFiles = Get-ChildItem -LiteralPath $ProjectRoot -Recurse -File `
    -Filter '~*.lck' -ErrorAction SilentlyContinue
if ($LockFiles) {
    Write-Host 'KiCad lock files are present. This preflight is read-only, but do not rewrite these documents:'
    $LockFiles | ForEach-Object { Write-Host "  $($_.FullName)" -ForegroundColor Yellow }
}
else {
    Write-Host 'No KiCad lock files found.' -ForegroundColor Green
}

if (-not $Git) {
    Add-Failure 'Git was not found.'
}
else {
    $StatusLog = Join-Path $OutputRoot 'git-status.txt'
    Invoke-LoggedCommand 'Git status' $Git @('status', '--short') $ProjectRoot $StatusLog | Out-Null
    $StatusText = Get-Content -LiteralPath $StatusLog -Raw -ErrorAction SilentlyContinue
    if ($StatusText) {
        Write-Host "Working tree has changes; details: $StatusLog" -ForegroundColor Yellow
    }
    else {
        Write-Host 'Working tree is clean.' -ForegroundColor Green
    }
    Invoke-LoggedCommand 'Git working-tree whitespace check' $Git `
        @('diff', '--check') $ProjectRoot `
        (Join-Path $OutputRoot 'git-diff-check.txt') | Out-Null
    Invoke-LoggedCommand 'Git staged whitespace check' $Git `
        @('diff', '--cached', '--check') $ProjectRoot `
        (Join-Path $OutputRoot 'git-diff-cached-check.txt') | Out-Null
}

if (-not $SkipKicad) {
    Write-Section 'KiCad schematic exports'
    if (-not $KiCadCli) {
        Add-Failure 'kicad-cli was not found.'
    }
    else {
        foreach ($SchematicName in @('80166_rf_amp.kicad_sch', 'triton_540.kicad_sch')) {
            $SchematicPath = Join-Path $ProjectRoot $SchematicName
            $OutputName = [IO.Path]::GetFileNameWithoutExtension($SchematicName) + '-bom.csv'
            $BomPath = Join-Path $OutputRoot $OutputName
            Invoke-LoggedCommand "KiCad BOM export: $SchematicName" $KiCadCli `
                @('sch', 'export', 'bom', '-o', $BomPath, $SchematicPath) `
                $ProjectRoot `
                (Join-Path $OutputRoot "$SchematicName.log") | Out-Null
        }
    }
}

if (-not $SkipSpice) {
    Write-Section 'ngspice model regressions'
    if (-not $Ngspice) {
        Add-Failure 'ngspice_con was not found.'
    }
    else {
        $ValidationRoot = Join-Path $ProjectRoot 'spice\validation'
        foreach ($Circuit in @(
            'MC1496P_validation.cir',
            '40823_validation.cir',
            '80166_rf_magnetics_validation.cir',
            'SW_Rotary_1x5_validation.cir',
            'SW_Rotary_4x5_validation.cir',
            'SW_Rotary_1x4_validation.cir',
            'Potentiometer_Position_validation.cir',
            'MV2201_validation.cir',
            '2N5486_validation.cir',
            'MPS6514_validation.cir',
            'MPS6512_validation.cir',
            '1N4154_validation.cir',
            '80289_vfo_magnetics_validation.cir'
        )) {
            Invoke-LoggedCommand "ngspice validation: $Circuit" $Ngspice `
                @('-b', '-D', 'ngbehavior=ltpsa', $Circuit) `
                $ValidationRoot `
                (Join-Path $OutputRoot "$Circuit.log") | Out-Null
        }
    }
}

if (-not $SkipPdf) {
    Write-Section 'Manual PDF and OCR smoke test'
    $ManualPath = Join-Path $ProjectRoot 'literature\540 Triton Owner Manual.pdf'
    if (-not (Test-Path -LiteralPath $ManualPath -PathType Leaf)) {
        Add-Failure "Primary manual is missing: $ManualPath"
    }
    elseif (-not $PdfInfo -or -not $PdfToText -or -not $PdfToPpm) {
        Add-Failure 'Poppler tools pdfinfo, pdftotext, and pdftoppm were not all found.'
    }
    else {
        Invoke-LoggedCommand 'PDF metadata read' $PdfInfo @($ManualPath) `
            $ProjectRoot (Join-Path $OutputRoot 'manual-pdfinfo.txt') | Out-Null
        Invoke-LoggedCommand 'PDF text extraction, pages 24-25' $PdfToText `
            @('-f', '24', '-l', '25', '-layout', $ManualPath,
                (Join-Path $OutputRoot 'manual-pages-24-25.txt')) `
            $ProjectRoot (Join-Path $OutputRoot 'manual-pdftotext.log') | Out-Null
        $RenderedBase = Join-Path $OutputRoot 'manual-page-24'
        $RenderedPath = "$RenderedBase.png"
        Invoke-LoggedCommand 'PDF render, page 24' $PdfToPpm `
            @('-f', '24', '-l', '24', '-r', '150', '-png', '-singlefile',
                $ManualPath, $RenderedBase) `
            $ProjectRoot (Join-Path $OutputRoot 'manual-pdftoppm.log') | Out-Null

        if (-not $Tesseract) {
            Add-Failure 'Tesseract was not found.'
        }
        elseif (Test-Path -LiteralPath $RenderedPath -PathType Leaf) {
            Invoke-LoggedCommand 'Tesseract OCR, rendered page 24' $Tesseract `
                @($RenderedPath, (Join-Path $OutputRoot 'manual-page-24-ocr'), '-l', 'eng') `
                $ProjectRoot (Join-Path $OutputRoot 'manual-tesseract.log') | Out-Null
        }
    }

    if (-not $Python) {
        Add-Failure 'Python was not found.'
    }
    else {
        Invoke-LoggedCommand 'Python PDF/image imports' $Python `
            @('-c', 'import fitz, pypdf, PIL; print(f"PyMuPDF {fitz.VersionBind}; pypdf {pypdf.__version__}; Pillow {PIL.__version__}")') `
            $ProjectRoot (Join-Path $OutputRoot 'python-pdf-libraries.txt') | Out-Null
    }
}

Write-Section 'Summary'
if ($Warnings.Count) {
    Write-Host "$($Warnings.Count) command(s) emitted warnings:" -ForegroundColor Yellow
    $Warnings | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
}
if ($Failures.Count) {
    Write-Host "$($Failures.Count) preflight check(s) failed:" -ForegroundColor Red
    $Failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host "Generated logs: $OutputRoot"
    exit 1
}

Write-Host 'All requested preflight checks passed.' -ForegroundColor Green
Write-Host "Generated logs: $OutputRoot"
exit 0
