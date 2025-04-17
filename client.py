import socket
import threading
import time
import requests
import sqlite3
import os

# ---- Setup ----
DISCOVERY_SERVER = 'http://127.0.0.1:5000'
USERNAME = input("Enter your username: ")
DB_FILE = f"{USERNAME}_messages.db"

blocked_users = set()
muted_users = {}
users_cache = {}
pending_messages = {}
users_lock = threading.Lock()
active_chat_peer = None  # Track currently active chat session

def update_users_loop():
    global users_cache
    previous_users = {}

    while True:
        try:
            updated_users = get_available_users()

            with users_lock:
                # Detect joined users
                new_users = {u: ip for u, ip in updated_users.items() if u not in previous_users and u != USERNAME}
                for user in new_users:
                    print(f"\n🚀 New user joined: {user}")

                    # Attempt to send any pending messages
                    if user in pending_messages:
                        print(f"📤 Sending {len(pending_messages[user])} queued message(s) to {user}")
                        for msg in pending_messages[user]:
                            send_message(user, updated_users[user], msg)
                        del pending_messages[user]

                # Detect left users
                left_users = {u for u in previous_users if u not in updated_users and u != USERNAME}
                for user in left_users:
                    print(f"\n User left: {user}")
                    print("Start chat with (type 'block' or 'mute' to manage users, 'exit' to quit): ", end='', flush=True)

                users_cache = updated_users
                previous_users = updated_users

        except Exception as e:
            print(f"\n[!] Error updating users list: {e}")

        time.sleep(5)



# ---- DB Setup ----
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peer TEXT,
            direction TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            message TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_local_message(peer, direction, message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO messages (peer, direction, message) VALUES (?, ?, ?)",
              (peer, direction, message))
    conn.commit()
    conn.close()

# ---- Discovery Server API ----
def register():
    requests.post(f"{DISCOVERY_SERVER}/register", json={"username": USERNAME})

def keep_alive_loop():
    while True:
        requests.post(f"{DISCOVERY_SERVER}/keep_alive", json={"username": USERNAME})
        time.sleep(10)

def get_available_users():
    response = requests.get(f"{DISCOVERY_SERVER}/users")
    return response.json()

def block_user(username):
    blocked_users.add(username)
    requests.post(f"{DISCOVERY_SERVER}/block", json={"blocker": USERNAME, "blockee": username})

def mute_user(username, duration_sec):
    muted_users[username] = time.time() + duration_sec

def is_muted(username):
    return time.time() < muted_users.get(username, 0)

# ---- Communication ----
def send_message(peer, peer_ip, message):
    if peer in blocked_users:
        print(f"You have blocked {peer}.")
        return
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((peer_ip, peer_port := 65432 + int(peer[-1])))
            s.sendall(f"{USERNAME}:{message}".encode())
            save_local_message(peer, "out", message)
    except Exception as e:
        print(f"Failed to send message to {peer}: {e}")
        # Queue message for retry
        pending_messages.setdefault(peer, []).append(message)

def listener():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        LISTEN_PORT = 65432 + int(USERNAME[-1])
        s.bind(('', LISTEN_PORT))
        s.listen()
        while True:
            conn, addr = s.accept()
            with conn:
                data = conn.recv(1024)
                if not data:
                    continue
                decoded = data.decode()
                sender, msg = decoded.split(":", 1)
                if sender in blocked_users or is_muted(sender):
                    continue
                print(f"\n{sender}: {msg}")
                save_local_message(sender, "in", msg)

# ---- Startup ----
init_db()
register()
threading.Thread(target=update_users_loop, daemon=True).start()
threading.Thread(target=keep_alive_loop, daemon=True).start()
threading.Thread(target=listener, daemon=True).start()

# ---- Chat Loop ----
while True:
    # Wait until at least one other user is available
    while True:
        with users_lock:
            available_users = {u: ip for u, ip in users_cache.items() if u != USERNAME}
        if available_users:
            break
        print("\n[!] No users online. Waiting for others to join...")
        time.sleep(5)

    # Show the updated list
    print("\nAvailable Users:")
    for user, ip in available_users.items():
        print(f"{user} @ {ip}")

    to_user = input("Start chat with (type 'block' or 'mute' to manage users, 'exit' to quit): ").strip()

    if to_user == "exit":
        break
    elif to_user == "block":
        block = input("Block who? ")
        block_user(block)
        continue
    elif to_user == "mute":
        mute = input("Mute who? ")
        secs = int(input("Duration in seconds: "))
        mute_user(mute, secs)
        continue

    if to_user not in available_users:
        print("User not found.")
        continue

    # ---- Session Chat Loop ----
    peer_ip = available_users[to_user]
    print(f"\n--- Chat session with {to_user} ---")
    print("Type your message (or type '/exit' to leave chat):")

    while True:
        # Check if peer is still online
        with users_lock:
            if to_user not in users_cache:
                print(f"\n⚠️ {to_user} appears to have gone offline.")
                break

        try:
            msg = input(f"{USERNAME} > ")
        except KeyboardInterrupt:
            print("\n[!] Interrupted. Leaving chat.")
            break

        if msg.strip() == "/exit":
            print(f"Left chat with {to_user}")
            break

        send_message(to_user, peer_ip, msg)
