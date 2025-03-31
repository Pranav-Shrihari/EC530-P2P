import socket
import threading
import sqlite3
from datetime import datetime

# Database Code
def init_db():
    conn = sqlite3.connect("chat_log.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            sender TEXT,
            message TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_message(sender, message):
    conn = sqlite3.connect("chat_log.db")
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO messages (timestamp, sender, message) VALUES (?, ?, ?)",
                   (timestamp, sender, message))
    conn.commit()
    conn.close()

# Server Code
def start_server(host='127.0.0.1', port=65432):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen()
    print(f"Server listening on {host}:{port}")
    
    conn, addr = server_socket.accept()
    print(f"Connected by {addr}")
    
    def receive_messages():
        while True:
            data = conn.recv(1024)
            if not data:
                break
            print(f"Client: {data.decode()}")
            log_message("Client", data.decode())

            response = input("Server: ")
            conn.sendall(response.encode())
            log_message("Server", response)
    
    receive_messages()
    conn.close()
    server_socket.close()

# Client Code
def start_client(host='127.0.0.1', port=65432):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((host, port))
    
    def send_messages():
        while True:
            message = input("Client: ")
            client_socket.sendall(message.encode())

            data = client_socket.recv(1024)
            print(f"Server: {data.decode()}")
    
    send_messages()
    client_socket.close()

if __name__ == "__main__":
    choice = input("Start as (server/client): ").strip().lower()
    if choice == "server":
        start_server()
    elif choice == "client":
        start_client()
    else:
        print("Invalid choice. Exiting.")