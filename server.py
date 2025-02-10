from pymongo import MongoClient
from flask import Flask, render_template, session

from flask_socketio import SocketIO, send, emit

from datetime import datetime
import hashlib

app = Flask(__name__)
app.config['SECRET'] = "secret123!"
socketio = SocketIO(app, cors_allowed_origins="*")

mongoclient = MongoClient("mongodb://localhost:27017/")
db = mongoclient["mongoChat"]
chatlog_collection = db.chatlog
users_collection = db.users
message_of_the_day = "Welcome to the chatroom!"

@socketio.on('connect')
def handle_connect(connectMsg):
    try:
        mongoclient.admin.command('ping')
    except:
        print("MongoDB connection failed, could not load chatlog")
        return

    # Load last 20 messages from chatlog database
    messages = chatlog_collection.find(limit=20, sort=[('$natural', -1)])
    msgArray = []
    for msg in messages:
        #print(msg)
        msgDict = {
            'username': msg['username'],
            'message': msg['message'],
            'time': msg['time']
        }
        msgArray.append(msgDict)
    msgArray.append({'username': 'Server', 'message': message_of_the_day, 'time': datetime.now().strftime("[%H:%M]")})
    # Reverse the array to send the messages in the correct order
    for msg in msgArray[::-1]:
        emit("message", msg, broadcast=False)
    # Send a message to the user to scroll down the chatlog
    send("scroll down", broadcast=False)
    session['logged_in'] = False

@socketio.on('register')
def user_register(user):
    username = user['username']
    password = user['password']
    password = hashlib.sha256(password.encode()).hexdigest()

    print("User register attempt: " + username)

    if users_collection.find_one({"username": username}) != None:
        print("User already exists: " + username)
        emit("register", {'success' : False}, broadcast=False)
        return

    users_collection.insert_one({"username": username, "password": password})
    emit("register", {'success' : True}, broadcast=False)
    print("User registered: " + username)
    session['logged_in'] = True
    session['username'] = username
    password = ""

@socketio.on('login')
def user_login(user):
    username = user['username']
    password = user['password']
    password = hashlib.sha256(password.encode()).hexdigest()
    print("User login attempt: " + username)

    if users_collection.find_one({"username": username, "password": password}) != None:
        emit("login", {'logged_in' : True}, broadcast=False)
        print("User logged in: " + username)
        session['logged_in'] = True
        session['username'] = username
    else:
        emit("login", {'logged_in' : False}, broadcast=False)
        print("User failed to login: " + username)
        session['logged_in'] = False
    password = ""

@socketio.on('message')
def handle_message(message):
    if message == "User connected!":
        return
    
    if session['logged_in'] == False:
        print("User not logged in, message not sent")
        emit("error", {'logged_in' : False}, broadcast=False)
        return

    time = "[" + datetime.now().strftime("%d.%m.%Y %H:%M") + "] "
    username = session['username']#message['username']
    message = message['message']
    print("Message received: " + time + " " + username + ": " + message)

    if username == "" or message == "":
        return

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
    socketio.run(app, host="localhost")