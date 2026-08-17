@echo off
echo Installing dependencies...
python -m pip install --prefer-binary -r backend\requirements.txt

echo.
echo Starting Live Trading Dashboard...
echo.
echo   Local:    http://localhost:8000
echo   Network:  http://10.0.0.119:8000
echo.
echo Open either URL in any browser on your WiFi network.
echo.
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
