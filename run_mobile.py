"""
AI Search Studio - Mobile & Local Network Launcher
Runs the web app on your local network so any laptop, mobile phone, or tablet
on the same Wi-Fi can connect directly and install it as an app.
"""

import socket
import threading
import webbrowser
import uvicorn

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def open_browser(port: int):
    try:
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        pass

if __name__ == "__main__":
    local_ip = get_local_ip()
    port = 8000

    print("\n" + "=" * 65)
    print("🚀  AI SEARCH STUDIO - MOBILE & LAPTOP APP SERVER")
    print("=" * 65)
    print(f"\n💻 On THIS LAPTOP, open:")
    print(f"   👉 http://localhost:{port}  (Opening automatically in your browser...)")
    print(f"\n📱 On your MOBILE PHONE (connected to the same Wi-Fi), open:")
    print(f"   👉 http://{local_ip}:{port}")
    print("\n⚠️  NOTE: Do NOT open 'http://0.0.0.0:8000' in your browser.")
    print("   '0.0.0.0' is only an internal server listener and causes ERR_ADDRESS_INVALID.")
    print("   Always use 'http://localhost:8000' on your laptop!")
    print("\n📲 To install as an app on your phone:")
    print("   • Android (Chrome): Tap 'Install' banner or menu ⋮ -> 'Add to Home screen'")
    print("   • iPhone (Safari): Tap Share ⎋ -> 'Add to Home Screen ➕'")
    print("=" * 65 + "\n")

    # Automatically launch laptop browser after 1.5 seconds
    threading.Timer(1.5, open_browser, args=(port,)).start()

    uvicorn.run("web_app:app", host="0.0.0.0", port=port, reload=False)
