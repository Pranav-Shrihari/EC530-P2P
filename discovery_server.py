from flask import Flask, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)
users = {}  # {username: {'ip': ..., 'last_seen': ..., 'blocked_by': set()}}

KEEP_ALIVE_TIMEOUT = timedelta(seconds=30)

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data['username']
    ip = request.remote_addr
    users[username] = {'ip': ip, 'last_seen': datetime.utcnow(), 'blocked_by': set()}
    return jsonify(success=True)

@app.route('/keep_alive', methods=['POST'])
def keep_alive():
    data = request.json
    username = data['username']
    if username in users:
        users[username]['last_seen'] = datetime.utcnow()
        return jsonify(success=True)
    return jsonify(success=False)

@app.route('/users', methods=['GET'])
def get_users():
    now = datetime.utcnow()
    available_users = {
        user: info['ip'] for user, info in users.items()
        if now - info['last_seen'] < KEEP_ALIVE_TIMEOUT
    }
    return jsonify(available_users)

@app.route('/block', methods=['POST'])
def block_user():
    data = request.json
    blocker = data['blocker']
    blockee = data['blockee']
    if blockee in users:
        users[blockee]['blocked_by'].add(blocker)
    return jsonify(success=True)

if __name__ == '__main__':
    app.run(port=5000)
