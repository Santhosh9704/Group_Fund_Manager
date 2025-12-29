from waitress import serve
from app import app
import socket

# Get local IP
hostname = socket.gethostname()
local_ip = socket.gethostbyname(hostname)

print(f"✅ Starting Production Server...")
print(f"🌍 Access locally: http://localhost:8080")
print(f"📡 Access on network: http://{local_ip}:8080")

serve(app, host='0.0.0.0', port=8080)
