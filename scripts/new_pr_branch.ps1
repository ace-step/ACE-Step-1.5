param(
    [Parameter(Mandatory = $true)]
    [string]$BranchName,
    [string]$BaseRef = "upstream/main"
)

$ErrorActionPreference = "Stop"

git fetch upstream
git checkout -b $BranchName $BaseRef

Write-Host "Created '$BranchName' from '$BaseRef'."
