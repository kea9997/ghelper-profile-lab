[CmdletBinding()]
param(
    [string]$PythonExecutable = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw 'Build this Windows executable on Windows.'
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$desktopPath = Join-Path $repositoryRoot 'desktop'
$buildPath = Join-Path $repositoryRoot 'build'
$distPath = Join-Path $repositoryRoot 'dist'
$venvPath = Join-Path $buildPath '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
$pyInstallerVersion = '6.22.3'

function Invoke-PythonChecked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw ('Python command failed with exit code {0}.' -f $LASTEXITCODE)
    }
}

$requiredFiles = @(
    (Join-Path $desktopPath 'app.py'),
    (Join-Path $desktopPath 'requirements.txt'),
    (Join-Path $desktopPath 'catalog.json'),
    (Join-Path $desktopPath 'app.ico'),
    (Join-Path $desktopPath 'web\index.html'),
    (Join-Path $desktopPath 'THIRD-PARTY-LICENSES.txt'),
    (Join-Path $desktopPath 'STEAM-UI-LICENSES.txt'),
    (Join-Path $desktopPath 'PYTHON-LICENSE.txt'),
    (Join-Path $repositoryRoot 'README.md')
)
foreach ($file in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw ('Required source file is missing: {0}' -f $file)
    }
}

# Pass arguments as an array; do not compose a command string or use Invoke-Expression.
$versionCheck = 'import sys; assert sys.version_info >= (3, 14), "Python 3.14 or newer is required"; assert sys.maxsize > 2**32, "64-bit Python is required"'
Invoke-PythonChecked -Executable $PythonExecutable -Arguments @('-c', $versionCheck)
[System.IO.Directory]::CreateDirectory($buildPath) | Out-Null
[System.IO.Directory]::CreateDirectory($distPath) | Out-Null
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Invoke-PythonChecked -Executable $PythonExecutable -Arguments @('-m', 'venv', $venvPath)
}
Invoke-PythonChecked -Executable $venvPython -Arguments @('-c', $versionCheck)
Invoke-PythonChecked -Executable $venvPython -Arguments @(
    '-m', 'pip', 'install', '--disable-pip-version-check',
    '-r', (Join-Path $desktopPath 'requirements.txt'),
    ('pyinstaller=={0}' -f $pyInstallerVersion)
)
$uiautomationDll = Join-Path $venvPath 'Lib\site-packages\uiautomation\bin\UIAutomationClient_VC140_X64.dll'
if (-not (Test-Path -LiteralPath $uiautomationDll -PathType Leaf)) {
    throw 'The uiautomation x64 DLL is missing from the build environment.'
}

# A new build directory avoids cleanup/deletion and stale intermediate artifacts.
$buildId = [System.Guid]::NewGuid().ToString('N')
$currentBuild = Join-Path $buildPath $buildId
[System.IO.Directory]::CreateDirectory($currentBuild) | Out-Null
$bundleArguments = @(
    '-m', 'PyInstaller',
    '--onefile', '--noconsole', '--noconfirm', '--noupx',
    '--name', 'GHelperProfileLab',
    '--icon', (Join-Path $desktopPath 'app.ico'),
    '--paths', $desktopPath,
    '--distpath', $distPath,
    '--workpath', (Join-Path $currentBuild 'work'),
    '--specpath', $currentBuild,
    '--add-data', ('{0};web' -f (Join-Path $desktopPath 'web')),
    '--add-data', ('{0};.' -f (Join-Path $desktopPath 'catalog.json')),
    '--add-data', ('{0};.' -f (Join-Path $desktopPath 'app.ico')),
    '--add-binary', ('{0};uiautomation/bin' -f $uiautomationDll),
    '--hidden-import', 'webview.platforms.winforms',
    '--hidden-import', 'webview.platforms.edgechromium',
    '--hidden-import', 'pystray._win32',
    (Join-Path $desktopPath 'app.py')
)
Invoke-PythonChecked -Executable $venvPython -Arguments $bundleArguments

$executablePath = Join-Path $distPath 'GHelperProfileLab.exe'
if (-not (Test-Path -LiteralPath $executablePath -PathType Leaf)) {
    throw 'PyInstaller did not produce the expected executable.'
}
$hashPath = Join-Path $distPath 'SHA256SUMS.txt'
$executableHash = (Get-FileHash -LiteralPath $executablePath -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText($hashPath, ($executableHash + '  GHelperProfileLab.exe' + [Environment]::NewLine), [System.Text.UTF8Encoding]::new($false))

# Explicit file allowlist: no source settings, logs, credentials or user data enter the ZIP.
$packageFiles = @(
    [pscustomobject]@{ Source = $executablePath; Entry = 'GHelperProfileLab.exe' },
    [pscustomobject]@{ Source = $hashPath; Entry = 'SHA256SUMS.txt' },
    [pscustomobject]@{ Source = (Join-Path $repositoryRoot 'README.md'); Entry = 'README.md' },
    [pscustomobject]@{ Source = (Join-Path $desktopPath 'THIRD-PARTY-LICENSES.txt'); Entry = 'licenses/THIRD-PARTY-LICENSES.txt' },
    [pscustomobject]@{ Source = (Join-Path $desktopPath 'STEAM-UI-LICENSES.txt'); Entry = 'licenses/STEAM-UI-LICENSES.txt' },
    [pscustomobject]@{ Source = (Join-Path $desktopPath 'PYTHON-LICENSE.txt'); Entry = 'licenses/PYTHON-LICENSE.txt' }
)
foreach ($document in Get-ChildItem -LiteralPath $desktopPath -Filter '*.md' -File) {
    $packageFiles += [pscustomobject]@{ Source = $document.FullName; Entry = ('docs/' + $document.Name) }
}
$buildingGuide = Join-Path $repositoryRoot 'BUILDING.md'
if (Test-Path -LiteralPath $buildingGuide -PathType Leaf) {
    $packageFiles += [pscustomobject]@{ Source = $buildingGuide; Entry = 'BUILDING.md' }
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zipPath = Join-Path $distPath 'GHelperProfileLab-windows-x64.zip'
$zipStream = [System.IO.File]::Open($zipPath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
$archive = $null
try {
    $archive = [System.IO.Compression.ZipArchive]::new($zipStream, [System.IO.Compression.ZipArchiveMode]::Create, $false)
    foreach ($item in $packageFiles) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive, $item.Source, $item.Entry, [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
} finally {
    if ($null -ne $archive) { $archive.Dispose() }
    $zipStream.Dispose()
}

Write-Host ('Executable: {0}' -f $executablePath)
Write-Host ('ZIP: {0}' -f $zipPath)
Write-Host ('SHA-256: {0}' -f $executableHash)
