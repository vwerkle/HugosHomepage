from waitress import serve
from app import app

if __name__ == "__main__":
    print("Waitress is now serving Hugo's Site on port 5000...")
    # 'threads=4' allows 4 people to click around simultaneously
    serve(app, host='0.0.0.0', port=5000, threads=4)