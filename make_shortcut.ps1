# Creates the PIPKA shortcut on the Desktop.
# If dist\PIPKA\PIPKA.exe exists (after build_exe.bat), the shortcut starts the real app.
# Otherwise it starts main.py with pythonw.exe from the .venv folder (no console window).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $root 'dist\PIPKA\PIPKA.exe'
$icon = Join-Path $root 'assets\pipka.ico'
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'PIPKA.lnk'

$pyw = $null
foreach ($name in @('.venv', 'venv')) {
    $candidate = Join-Path $root ($name + '\Scripts\pythonw.exe')
    if (Test-Path $candidate) { $pyw = $candidate; break }
}

if (-not (Test-Path $exe) -and $null -eq $pyw) {
    Write-Host 'Neither dist\PIPKA\PIPKA.exe nor .venv\Scripts\pythonw.exe was found.'
    Write-Host 'Run build_exe.bat first, or create the virtual environment.'
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($lnk)

if (Test-Path $exe) {
    $s.TargetPath = $exe
    $s.Arguments = ''
    $s.WorkingDirectory = Split-Path -Parent $exe
} else {
    $s.TargetPath = $pyw
    $s.Arguments = '"' + (Join-Path $root 'main.py') + '"'
    $s.WorkingDirectory = $root
}

$s.IconLocation = $icon
$s.Description = 'PIPKA assistant'
$s.Save()
Write-Host ('Shortcut created: ' + $lnk)
