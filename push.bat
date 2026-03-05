@echo off
setlocal enabledelayedexpansion

set REGISTRY=registry.cn-hangzhou.aliyuncs.com
set NAMESPACE=eddycheng
set USERNAME=EddyCheng

set /p VERSION=<VERSION
if "%VERSION%"=="" set VERSION=dev

set IMAGE_NAME=%REGISTRY%/%NAMESPACE%/ihomeguard
set IMAGE_TAG=%IMAGE_NAME%:%VERSION%

echo.
echo ========================================
echo  iHomeGuard Docker Build and Push
echo ========================================
echo  Version: %VERSION%
echo  Image: %IMAGE_TAG%
echo.

echo [1/3] Login to registry...
docker login --username=%USERNAME% %REGISTRY%
if errorlevel 1 (
    echo Login failed!
    pause
    exit /b 1
)

echo.
echo [2/3] Building image...
docker build --build-arg VERSION=%VERSION% -t %IMAGE_TAG% .
if errorlevel 1 (
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo [3/3] Pushing to registry...
docker push %IMAGE_TAG%
if errorlevel 1 (
    echo Push failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Success!
echo ========================================
echo  Image: %IMAGE_TAG%
echo.

pause