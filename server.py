from pymongo import MongoClient
from flask import Flask, render_template, session, request

from flask_socketio import SocketIO, send, emit

from datetime import datetime
import hashlib
import random

app = Flask(__name__)
app.config['SECRET'] = "secret123!"
socketio = SocketIO(app, cors_allowed_origins="*")

mongoclient = MongoClient("mongodb://localhost:27017/")
db = mongoclient["mongoChat"]
chatlog_collection = db.chatlog
users_collection = db.users
message_of_the_day = "Welcome to the chatroom!"

def generate_session_id(username):
    # Generate session ID from username and random integer
    session_id = username + str(random.randint(0, 1000))
    session_id = hashlib.sha256(session_id.encode()).hexdigest()

    # If session ID already exists keep generating new ones until a unique one is found
    while users_collection.find_one({"session_id": session_id}) != None:
        session_id = username + str(random.randint(0, 1000))
        session_id = hashlib.sha256(session_id.encode()).hexdigest()
    users_collection.update_one({"username": username}, {"$set": {"session_id": session_id}})
    print("Session ID generated for user: " + username)
    return session_id

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
    session_id = generate_session_id(username)
    emit("register", {'success' : True, 'session_id': session_id}, broadcast=False)
    print("User registered: " + username)
    session['logged_in'] = True
    session['username'] = username
    password = ""
    # TODO: Generate session ID, save it to users table and send it to client so they don't have to keep logging in.


@socketio.on('login')
def user_login(user):
    login_with_session_id = False
    if 'session_id' in user:
        _user = users_collection.find_one({"session_id": user['session_id']})
        if _user != None:
            username = _user['username']
            password = ""
            login_with_session_id = True
            print("User logged in with sessionID: " + username)
        else:
            print("User failed to login with sessionID: ")


    if not login_with_session_id:
        if 'username' not in user or 'password' not in user:
            print("User login attempt failed, missing username or password")
            return
        username = user['username']
        password = user['password']
        password = hashlib.sha256(password.encode()).hexdigest()
    print("User login attempt: " + username)

    if users_collection.find_one({"username": username, "password": password}) != None or login_with_session_id:
        # TODO: Generate session ID, save it to users table and send it to client so they don't have to keep logging in.
        session_id = ""
        if not login_with_session_id:
            session_id = generate_session_id(username)
        emit("login", {'logged_in' : True, 'session_id': session_id, 'update_session_id': not login_with_session_id}, broadcast=False)
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
    socketio.run(app, host="0.0.0.0", port=5000)