#!/usr/bin/env python
import sys
import uvicorn
from app.main import app

if __name__ == "__main__":
    print("Starting FastAPI server on http://127.0.0.1:8003")
    print("Python executable:", sys.executable)
    try:
        uvicorn.run(app, host="127.0.0.1", port=8003)
    except Exception as e:
        print(f"Error starting server: {e}")
        import traceback
        traceback.print_exc()
