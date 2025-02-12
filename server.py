from pymongo import MongoClient
from flask import Flask, render_template, session, request

from flask_socketio import SocketIO, send, emit

from datetime import datetime, timezone, timedelta
import hashlib
import random, uuid

app = Flask(__name__)
app.config['SECRET'] = "secret123!"
socketio = SocketIO(app, cors_allowed_origins="*")

mongoclient = MongoClient("mongodb://localhost:27017/")
db = mongoclient["mongoChat"]
chatlog_collection = db.chatlog
users_collection = db.users
message_of_the_day = "Welcome to the chatroom!"
users_last_seen = {}

def update_last_seen(username, logout=False):
    if logout:
        users_last_seen.pop(username)
        return
    users_last_seen[username] = get_utc_date()
def generate_session_id(username):
    # Generate session ID from username and random integer
    session_id = str(uuid.uuid4())

    users_collection.update_one({"username": username}, {"$set": {"session_id": session_id}})
    print("Session ID generated for user: " + username)
    return session_id
def get_utc_date():
    # MongoDB stores datetime values in coordinated universal time (UTC)
    return datetime.now(tz=timezone.utc)#.isoformat(timespec='minutes')
def get_iso_date():
    return get_utc_date().isoformat(timespec='minutes')
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
            'time': msg['time'].isoformat(timespec='minutes')
        }
        msgArray.append(msgDict)
    msgArray.append({'username': 'Server', 'message': message_of_the_day, 'time': get_iso_date()})
    # Reverse the array to send the messages in the correct order
    for msg in msgArray[::-1]:
        emit("message", msg, broadcast=False)
    # Send a message to the user to scroll down the chatlog
    send("scroll down", broadcast=False)
    session['logged_in'] = False

@socketio.on('online_users')
def online_users():
    print("Online users list requested")
    #users = users_collection.find({"session_id": {"$ne": ""}})
    online_users = []
    for username in users_last_seen:
        last_seen_time = users_last_seen[username]
        two_minutes = timedelta(minutes=2)
        print("Checking user: " + username + " last seen time difference: " + str(get_utc_date() - last_seen_time))
        if get_utc_date() - last_seen_time < two_minutes:
            online_users.append(username)
    emit("online_users", online_users, broadcast=False)

@socketio.on('ping')
def user_ping():
    if 'username' not in session or session['username'] == "" and 'logged_in' not in session:
        return
    if session['logged_in'] == False:
        return
    username = session['username']
    update_last_seen(username)
    print("Received ping from user: " + username)

@socketio.on('register')
def user_register(user):
    username = user['username']
    username_lower = username.lower()
    password = user['password']
    password = hashlib.sha256(password.encode()).hexdigest()

    print("User register attempt: " + username)

    if users_collection.find_one({"username_lower": username_lower}) != None:
        print("User already exists: " + username)
        emit("register", {'success' : False}, broadcast=False)
        return

    users_collection.insert_one({"username": username, "username_lower": username_lower, "password": password})
    session_id = generate_session_id(username)
    emit("register", {'success' : True, 'session_id': session_id}, broadcast=False)
    print("User registered: " + username)
    session['logged_in'] = True
    session['username'] = username
    update_last_seen(username)
    password = ""
@socketio.on('logout')
def user_logout():
    if session['logged_in'] == False:
        print("User not logged in, logout not possible")
        return
    username = session['username']
    users_collection.update_one({"username": username}, {"$set": {"session_id": ""}})
    session['logged_in'] = False
    update_last_seen(username, logout=True)
    session['username'] = ""
    print("User logged out: " + username)

@socketio.on('login')
def user_login(user):
    login_with_session_id = False
    if 'session_id' in user and user['session_id'] != "":
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
        session_id = ""
        if not login_with_session_id:
            session_id = generate_session_id(username)
        emit("login", {'logged_in' : True, 'session_id': session_id, 'update_session_id': not login_with_session_id}, broadcast=False)
        print("User logged in: " + username)
        session['logged_in'] = True
        session['username'] = username
        # TODO: Finish users online list based on when they were last seen online
        update_last_seen(username)
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

    #time = "[" + datetime.now().strftime("%d.%m.%Y %H:%M") + "] "
    time = get_iso_date()
    username = session['username']#message['username']
    message = message['message']
    print("Message received: " + time + " " + username + ": " + message)

    if username == "" or message == "":
        return

    # Save message to MongoDB
    try:
        chatlog_collection.insert_one({"username": username, "message": message, "time": get_utc_date()})
    except:
        print("Error saving message to MongoDB")

    msgDict = {
        'username': username,
        'message': message,
        'time': time}
    emit("message", msgDict, broadcast=True)
    update_last_seen(username)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)