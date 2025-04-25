from flask import Flask, request, jsonify
import time

app = Flask(__name__)
users = {}

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data['username']
    port = data['port']
    users[username] = {
        "ip": request.remote_addr,
        "port": port,
        "last_seen": time.time()
    }
    return '', 200

@app.route('/keep_alive', methods=['POST'])
def keep_alive():
    data = request.get_json()
    username = data['username']
    if username in users:
        users[username]['last_seen'] = time.time()
    return '', 200

@app.route('/users', methods=['GET'])
def get_users():
    # Clean up old users
    now = time.time()
    to_remove = [user for user, info in users.items() if now - info['last_seen'] > 30]
    for user in to_remove:
        del users[user]
    
    # Only return {username: {ip, port}}
    return jsonify({
        user: {"ip": info["ip"], "port": info["port"]}
        for user, info in users.items()
    })

@app.route('/block', methods=['POST'])
def block_user():
    # You can implement block logic here if needed
    return '', 200

if __name__ == '__main__':
    app.run(port=5000)
