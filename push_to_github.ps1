# Set error action to stop so we see if any step fails
$ErrorActionPreference = "Stop"

Write-Host "1. Checking git status..." -ForegroundColor Cyan
git status

Write-Host "`n2. Adding files to repository..." -ForegroundColor Cyan
git add .

Write-Host "`n3. Committing changes..." -ForegroundColor Cyan
git commit -m "first commit"

Write-Host "`n4. Configuring remote..." -ForegroundColor Cyan
# Remove existing origin remote if it exists to avoid conflicts
try {
    git remote remove origin
} catch {
    # Ignore error if origin didn't exist
}
git remote add origin https://github.com/anamolpaudel02/SabdhaAi-plus.git

Write-Host "`n5. Renaming branch to main..." -ForegroundColor Cyan
git branch -M main

Write-Host "`n6. Pushing to GitHub (origin/main)..." -ForegroundColor Cyan
git push -u origin main

Write-Host "`nSuccess! Project has been pushed." -ForegroundColor Green
