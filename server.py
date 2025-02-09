from pymongo import MongoClient
from flask import Flask, render_template
from flask_socketio import SocketIO, send, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET'] = "secret123!"
socketio = SocketIO(app, cors_allowed_origins="*")

mongoclient = MongoClient("mongodb://localhost:27017/")
chatlog_collection = ""
db = mongoclient["mongoChat"]
chatlog_collection = db.chatlog

def init_mongodb():
    pass
    #chatlog_collection.insert_one({"username": "Server", "message": "Welcome to the chatroom!", "time": datetime.now().strftime("%H:%M")})

def send_chatlog():
    pass

@socketio.on('connect')
def handle_connect(connectMsg):
    try:
        mongoclient.admin.command('ping')
    except:
        print("MongoDB connection failed, could not load chatlog")
        return

    messages = chatlog_collection.find(limit=20, sort=[('time')])
    for msg in messages:
        #print(msg)
        msgDict = {
            'username': msg['username'],
            'message': msg['message'],
            'time': msg['time']
        }
        emit("message", msgDict, broadcast=False)

@socketio.on('message')
def handle_message(message):
    if message == "User connected!":
        # Send user the recent chatlog on server
        send_chatlog()
        return

    time = "[" + datetime.now().strftime("%H:%M") + "] "
    username = message['username']
    message = message['message']
    print("Message received: " + time + " " + username + ": " + message)

    # Save message to MongoDB
    try:
        chatlog_collection.insert_one({"username": username, "message": message, "time": time})
    except:
        print("Error saving message to MongoDB")

    msgDict = {
        'username': username,
        'message': message,
        'time': time}
    emit("message", msgDict, broadcast=True)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    init_mongodb()
    socketio.run(app, host="localhost")