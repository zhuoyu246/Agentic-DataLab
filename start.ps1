# Agentic-DataLab 启动脚本
Write-Host "🚀 启动 Agentic-DataLab..." -ForegroundColor Cyan

# 启动后端
Write-Host "`n📦 启动后端服务..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\backend'; Write-Host '=== Backend Server ===' -ForegroundColor Green; .\.venv\Scripts\Activate.ps1; uvicorn main:app --reload --port 8000 --host 127.0.0.1"

Start-Sleep -Seconds 3

# 启动前端
Write-Host "🎨 启动前端服务..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\frontend'; Write-Host '=== Frontend Server ===' -ForegroundColor Green; npm run dev"

Start-Sleep -Seconds 2

Write-Host "`n✅ 服务启动中..." -ForegroundColor Green
Write-Host "`n📍 访问地址:" -ForegroundColor Cyan
Write-Host "   前端: http://localhost:5173" -ForegroundColor White
Write-Host "   后端: http://localhost:8000" -ForegroundColor White
Write-Host "   文档: http://localhost:8000/docs" -ForegroundColor White
Write-Host "`n💡 提示: API Key 已配置在顶部状态栏，可随时更换" -ForegroundColor Gray
