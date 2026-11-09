[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Destination,
    [Parameter(Mandatory)][string]$Source
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $Destination) { throw "Destination already exists: $Destination" }
if (!(Test-Path -LiteralPath $Source -PathType Container)) { throw "Source is not a directory: $Source" }
New-Item -ItemType Junction -Path $Destination -Target $Source -ErrorAction Stop | Out-Null
