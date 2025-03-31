import socket
import threading
import time
import requests
import sqlite3
import os
from cryptography.fernet import Fernet

# ---- Setup ----
DISCOVERY_SERVER = 'http://127.0.0.1:5000'
USERNAME = input("Enter your username: ")
DB_FILE = f"{USERNAME}_messages.db"

SHARED_SECRET = Fernet.generate_key()
peer_keys = {
    "u1": Fernet(SHARED_SECRET),
    "u2": Fernet(SHARED_SECRET)
}
blocked_users = set()
muted_users = {}

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
            encrypted_message TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS peer_keys (
            peer TEXT PRIMARY KEY,
            fernet_key TEXT
        )
    """)
    conn.commit()
    conn.close()

# ---- Key & Crypto ----
def load_or_generate_key(peer):
    if peer not in peer_keys:
        peer_keys[peer] = Fernet(Fernet.generate_key())
    return peer_keys[peer]

def encrypt_message(peer, message):
    return load_or_generate_key(peer).encrypt(message.encode()).decode()

def decrypt_message(peer, encrypted_msg):
    return load_or_generate_key(peer).decrypt(encrypted_msg.encode()).decode()

# ---- Message Store ----
def save_local_message(peer, direction, encrypted_message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO messages (peer, direction, encrypted_message) VALUES (?, ?, ?)",
              (peer, direction, encrypted_message))
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
    encrypted = encrypt_message(peer, message)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect((peer_ip, peer_port := 65432 + int(peer[-1])))
            s.sendall(f"{USERNAME}:{encrypted}".encode())
            save_local_message(peer, "out", encrypted)
        except Exception as e:
            print(f"Failed to send message to {peer}: {e}")

def listener():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        LISTEN_PORT = 65432 + int(USERNAME[-1])  # e.g., u1 → 65433, u2 → 65434
        s.bind(('', LISTEN_PORT))
        s.listen()
        while True:
            conn, addr = s.accept()
            with conn:
                data = conn.recv(1024)
                if not data:
                    continue
                decoded = data.decode()
                sender, enc_msg = decoded.split(":", 1)
                if sender in blocked_users or is_muted(sender):
                    continue
                try:
                    message = decrypt_message(sender, enc_msg)
                    print(f"{sender}: {message}")
                    save_local_message(sender, "in", enc_msg)
                except Exception as e:
                    print(f"Decryption failed from {sender}: {e}")

# ---- Startup ----
init_db()
register()
threading.Thread(target=keep_alive_loop, daemon=True).start()
threading.Thread(target=listener, daemon=True).start()

# ---- Main Chat Loop ----
while True:
    print("\nAvailable Users:")
    users = get_available_users()
    for user, ip in users.items():
        if user != USERNAME:
            print(f"{user} @ {ip}")
    to_user = input("Send message to: ")
    if to_user == "block":
        block = input("Block who? ")
        block_user(block)
        continue
    if to_user == "mute":
        mute = input("Mute who? ")
        secs = int(input("Duration in seconds: "))
        mute_user(mute, secs)
        continue
    msg = input("Message: ")
    if to_user in users:
        send_message(to_user, users[to_user], msg)
    else:
        print("User not found.")
