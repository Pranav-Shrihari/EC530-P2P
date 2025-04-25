# P2P Chat Client
A lightweight peer-to-peer chat client written in Python, featuring:
- User Discovery via a central discovery server
- Persistent Message History stored in SQLite
- Blocking & Muting: easily manage unwanted contacts
- Keep-Alive Heartbeats to maintain presence
- Configurable Listening Port (randomly assigned on startup)

## How to use
First, you will need to **download the repository** and then go to the downloaded directory. After that, follow the following steps in order.

## Running the discovery server
First, you will need to install the required dependencies. Therefore, run the following command in the right directory:
<pre lang="markdown"> pip install flask </pre>
After that, you can run the following command to initialize the discovery server:
<pre lang="markdown"> python3 discovery_server.py </pre>
This will initialize the discovery server. 

## Running the client side
After running the discovery server, you can run the following command in a seperate terminal:
<pre lang="markdown"> python3 client.py </pre>
This will initialize a client session. After this, you should:
- Enter a unique username when prompted.
- A `<username>`_messages.db file is created.

## Usage
- Wait until another peer is online; the client polls automatically.
- Available commands:
    - `block` — block a user.
    - `mute` — mute a user.
    - `exit` — quit the client.
- To start a chat, type a username. In chat, type messages or /exit to leave.
- Incoming messages display immediately, prompting you to reply.
