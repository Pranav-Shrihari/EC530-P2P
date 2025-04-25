import socket
import threading
import time
import requests
import sqlite3
import os
import random

# ---- Setup ----
DISCOVERY_SERVER = 'http://127.0.0.1:5000'
USERNAME = input("Enter your username: ")
DB_FILE = f"{USERNAME}_messages.db"
LISTEN_PORT = random.randint(50000, 60000)

blocked_users = set()
muted_users = {}
users_cache = {}
users_lock = threading.Lock()
active_chat_peer = None  # Track currently active chat session

# pending_messages in memory: { peer: [ (msg_id, message), ... ] }
pending_messages = {}

# ---- DB Setup ----
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # store history
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peer TEXT,
            direction TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            message TEXT
        )
    """)
    # store queued messages
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peer TEXT,
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_local_message(peer, direction, message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (peer, direction, message) VALUES (?, ?, ?)",
        (peer, direction, message)
    )
    conn.commit()
    conn.close()

def save_pending_to_db(peer, message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO pending_messages (peer, message) VALUES (?, ?)",
        (peer, message)
    )
    msg_id = c.lastrowid
    conn.commit()
    conn.close()
    return msg_id

def delete_pending_from_db(msg_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM pending_messages WHERE id = ?", (msg_id,))
    conn.commit()
    conn.close()

def load_pending_from_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, peer, message FROM pending_messages")
    rows = c.fetchall()
    conn.close()
    pm = {}
    for msg_id, peer, message in rows:
        pm.setdefault(peer, []).append((msg_id, message))
    return pm

# ---- Discovery Server API ----
def register():
    try:
        requests.post(
            f"{DISCOVERY_SERVER}/register",
            json={"username": USERNAME, "port": LISTEN_PORT}
        )
    except Exception as e:
        print(f"[!] Error registering: {e}")
        exit(1)

def keep_alive_loop():
    while True:
        try:
            requests.post(
                f"{DISCOVERY_SERVER}/keep_alive",
                json={"username": USERNAME}
            )
        except Exception as e:
            print(f"\n[!] Keep alive failed: {e}")
        time.sleep(10)

def get_available_users():
    resp = requests.get(f"{DISCOVERY_SERVER}/users")
    return resp.json()

def block_user(username):
    blocked_users.add(username)
    requests.post(
        f"{DISCOVERY_SERVER}/block",
        json={"blocker": USERNAME, "blockee": username}
    )

def mute_user(username, duration_sec):
    muted_users[username] = time.time() + duration_sec

def is_muted(username):
    return time.time() < muted_users.get(username, 0)

# ---- Communication ----
def send_message(peer, peer_info, message):
    """Attempt to send; on failure, queue persistently."""
    if peer in blocked_users:
        print(f"You have blocked {peer}.")
        return False

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((peer_info['ip'], peer_info['port']))
            s.sendall(f"{USERNAME}:{message}".encode())
            save_local_message(peer, "out", message)
        return True

    except Exception as e:
        print(f"Failed to send message to {peer}: {e}")
        msg_id = save_pending_to_db(peer, message)
        pending_messages.setdefault(peer, []).append((msg_id, message))
        return False

def listener():
    """Accept incoming connections, print them, save history,
       and re-display the main prompt."""
    global active_chat_peer

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
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

                # Print incoming
                print(f"\n🔔 {sender}: {msg}")
                save_local_message(sender, "in", msg)

                # If not actively chatting, re-display prompt
                if active_chat_peer is None:
                    print("Start chat with (type 'block' or 'mute' to manage users, 'exit' to quit): ", end='', flush=True)
                else:
                    print(f"{USERNAME} > ", end='', flush=True)

# ---- User Update Loop ----
def update_users_loop():
    global users_cache
    global active_chat_peer

    previous_users = {}
    sleep_time = 5

    while True:
        try:
            updated_users = get_available_users()
            with users_lock:
                # announce newcomers without auto-sending
                new_users = {
                    u: info for u, info in updated_users.items()
                    if u not in previous_users and u != USERNAME
                }
                for user in new_users:
                    print(f"\n🚀 New user joined: {user}")

                # announce departures
                left_users = {u for u in previous_users if u not in updated_users and u != USERNAME}
                for user in left_users:
                    print(f"\n❌ User left: {user}")
                    if user == active_chat_peer:
                        print(f"⚠️ The person you were chatting with ({user}) left. You should exit chat.")
                        active_chat_peer = None
                    print("Start chat with (type 'block' or 'mute' to manage users, 'exit' to quit): ", end='', flush=True)

                users_cache = updated_users
                previous_users = updated_users
                sleep_time = 5 if (new_users or left_users) else min(sleep_time + 5, 30)

        except Exception as e:
            print(f"\n[!] Error updating users list: {e}")
            sleep_time = 5

        time.sleep(sleep_time)

# ---- Deferred Delivery Helper ----
def deliver_pending_for_peer(peer, peer_info):
    """Send any queued messages for `peer` now that you're actively in a chat."""
    if peer not in pending_messages:
        return
    queue = pending_messages[peer][:]
    for msg_id, msg in queue:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((peer_info['ip'], peer_info['port']))
                s.sendall(f"{USERNAME}:{msg}".encode())
                save_local_message(peer, "out", msg)
            delete_pending_from_db(msg_id)
            pending_messages[peer].remove((msg_id, msg))
        except Exception:
            break
    if not pending_messages.get(peer):
        pending_messages.pop(peer, None)

# ---- Startup ----
init_db()
pending_messages = load_pending_from_db()
register()
threading.Thread(target=update_users_loop, daemon=True).start()
threading.Thread(target=keep_alive_loop, daemon=True).start()
threading.Thread(target=listener, daemon=True).start()

# ---- Chat Loop ----
while True:
    # Wait until at least one other user is known
    while True:
        with users_lock:
            available_users = {u: info for u, info in users_cache.items() if u != USERNAME}
        if available_users:
            break
        print("\n[!] No users online. Waiting...")
        time.sleep(5)

    # Show available users
    print("\nAvailable Users:")
    for user, info in available_users.items():
        print(f"{user} @ {info['ip']}:{info['port']}")

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

    # ---- Deliver queued messages when you actively start chatting ----
    peer_info = available_users[to_user]
    deliver_pending_for_peer(to_user, peer_info)

    # ---- Chatting Session ----
    print(f"\n--- Chat session with {to_user} ---")
    print("Type your message (or type '/exit' to leave chat):")
    active_chat_peer = to_user

    while True:
        # If they go offline mid-chat
        with users_lock:
            if to_user not in users_cache:
                print(f"\n⚠️ {to_user} appears to have gone offline.")
                active_chat_peer = None
                break

        try:
            msg = input(f"{USERNAME} > ")
        except KeyboardInterrupt:
            print("\n[!] Interrupted. Leaving chat.")
            active_chat_peer = None
            break

        if msg.strip() == "/exit":
            print(f"Left chat with {to_user}")
            active_chat_peer = None
            break

        success = send_message(to_user, peer_info, msg)
        if not success:
            print(f"\n⚠️ Could not reach {to_user}. Ending chat session.")
            active_chat_peer = None
            break
