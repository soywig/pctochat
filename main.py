from datetime import datetime
from flask import Flask, request, send_from_directory
from waitress import serve
import queue
import argparse
import sys
import socket

# default port if none provided via CLI
PORT = 2004

custom_address = None
verbose = False

def get_local_ip():
    """Get the local IP address of the machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # doesn't actually send data
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "localhost"

app = Flask(__name__, static_folder="public", static_url_path="")

# each client connection has its own queue
clients = []

@app.route("/")
@app.route("/<path:filename>")
def static_files(filename="index.html"):
    if 'u' in request.args:
        username = request.args.get('u')
        log(f"{request.remote_addr} connected with username: {username}")
        send_new_user_message(username)
        return send_from_directory("public", filename)
    else:
        log(f"{request.remote_addr} connected with no username; redirecting to login page")
        return send_from_directory("public", filename if filename != "index.html" else "login.html")

# POST: receives a message from one client and forwards it to all other connections
@app.route("/api/messages", methods=["POST"])
def post_message():
    payload = request.get_data(as_text=True)
    log(f"Message received by {request.remote_addr}: {payload}")
    for q in clients[:]:
        try:
            q.put(payload) 
            log(f"Message from {request.remote_addr} forwarded to {q.qsize()} listener(s)")
        except:
            clients.remove(q)
    return '', 204

# GET: all clients listen here, with long-polling
@app.route("/api/messages", methods=["GET"])
def get_messages():
    q = queue.Queue()
    clients.append(q)
    try:
        # wait up to 30 seconds for a message
        msg = q.get(timeout=30)
        return msg, 200
    except queue.Empty:
        return '', 204  # no message, client retries
    finally:
        clients.remove(q) # clean up client queue on disconnect

@app.route("/api/room/details", methods=["GET"])
def get_room_details():
    log(f"Room details requested by {request.remote_addr}")
    return {
        "serverIP": custom_address or get_local_ip(),
        "port": PORT,
    }, 200

def send_new_user_message(username):
    welcome_message = f'{{"type": "system", "content": "Now entering room: {username}"}}'
    for q in clients[:]:
        try:
            q.put(welcome_message)
        except:
            clients.remove(q)

def log(msg):
    if verbose:
        timestamp = "[{:%Y-%m-%d %H:%M:%S}]".format(datetime.now())
        print(f"{timestamp}: {msg}")

if __name__ == "__main__":
    import socket

    parser = argparse.ArgumentParser(description="run pctochat web server")
    parser.add_argument("--port", "-p", type=int, help="port to listen on (default: %(default)s)", default=PORT)
    parser.add_argument("--server", "-s", action="store_true", help="run server in headless mode without opening a browser")
    parser.add_argument("--threads", "-t", type=int, help="number of threads to use (default: %(default)s)", default=8)
    parser.add_argument("--address", "-a", type=str, help="address displayed to users in browser", default="0.0.0.0")
    parser.add_argument("--verbose", "-v", action="store_true", help="enable verbose logging")
    args = parser.parse_args()

    port = args.port or PORT
    open_browser = not args.server
    threads = args.threads
    custom_address = args.address
    verbose = args.verbose

    local_ip = get_local_ip()

    print(f"\nServer running!")
    print(f" → Local:   http://127.0.0.1:{port}")
    print(f" → Network: http://{local_ip}:{port}\n")

    if not (1 <= port <= 65535):
        log(f"Error: port {port} is out of range (1-65535)")
        sys.exit(2)

    if open_browser:
        import webbrowser
        webbrowser.open(f"http://{local_ip}:{port}")

    serve(app, host="0.0.0.0", port=port, threads=threads)