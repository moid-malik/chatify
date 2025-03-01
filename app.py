import os
import streamlit as st
from pymongo import MongoClient
import hashlib
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from dotenv import load_dotenv
load_dotenv()

# MongoDB Connection
client = MongoClient(os.getenv(("DB_URI")))
db = client["chatify"]
users_collection = db["users"]
messages_collection = db["messages"]

# Emoji Choices
EMOJIS = ["😀", "😎", "😍", "😂", "🥳", "🤩", "😇", "👻", "💀", "🤖"]

# Hash password
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Authenticate user
def authenticate(username, password):
    user = users_collection.find_one({"username": username})
    return user if user and user["password"] == hash_password(password) else None

# Register new user
def register_user(username, password, emoji):
    if users_collection.find_one({"username": username}):
        return False
    users_collection.insert_one({
        "username": username,
        "password": hash_password(password),
        "emoji": emoji
    })
    return True

# Fetch messages between two users, sorted oldest first
def fetch_messages(sender, receiver):
    return list(messages_collection.find({
        "$or": [
            {"sender": sender, "receiver": receiver},
            {"sender": receiver, "receiver": sender}
        ]
    }).sort("timestamp", 1))

# Store new message with initial status "sent"
def store_message(sender, receiver, message):
    messages_collection.insert_one({
        "sender": sender,
        "receiver": receiver,
        "message": message,
        "timestamp": datetime.utcnow(),
        "status": "sent"
    })

# Update message status to "seen" for messages received by current user
def update_message_status(current_user, chat_partner):
    messages_collection.update_many(
        {
            "sender": chat_partner,
            "receiver": current_user,
            "status": {"$ne": "seen"}
        },
        {"$set": {"status": "seen"}}
    )

# Initialize session state variables
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "selected_user" not in st.session_state:
    st.session_state.selected_user = None
if "search_query" not in st.session_state:
    st.session_state.search_query = ""

st.title("💬 WhatsApp Clone")

# Authentication: Login / Register
if not st.session_state.logged_in:
    tab1, tab2 = st.tabs(["Login", "Register"])
    with tab1:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            user = authenticate(username, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.emoji = user["emoji"]
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")
    with tab2:
        new_username = st.text_input("New Username")
        new_password = st.text_input("New Password", type="password")
        selected_emoji = st.selectbox("Choose your emoji PFP", EMOJIS)
        if st.button("Register"):
            if register_user(new_username, new_password, selected_emoji):
                st.success("Registered successfully! You can now log in.")
            else:
                st.error("Username already exists!")
else:
    # Auto-refresh chat every 2 seconds for real-time updates
    st_autorefresh(interval=2000, key="chat_autorefresh")

    # Sidebar: Search and User List with Unread Count Indicator
    st.sidebar.title("Users")
    search_query = st.sidebar.text_input("Search Users:", key="search_query")
    
    all_users = list(users_collection.find({}, {"_id": 0, "username": 1, "emoji": 1}))
    user_dict = {u["username"]: u["emoji"] for u in all_users}
    # Exclude the logged-in user
    all_usernames = [u["username"] for u in all_users if u["username"] != st.session_state.username]
    
    # Filter based on search query
    if search_query:
        all_usernames = [uname for uname in all_usernames if search_query.lower() in uname.lower()]
    
    # Function to display unread count next to each user.
    def format_username(u):
        count = messages_collection.count_documents({
            "sender": u,
            "receiver": st.session_state.username,
            "status": "sent"
        })
        return f"{u} ({count} unread)" if count > 0 else u

    if all_usernames:
        # Add a default option to avoid auto-switching
        options = all_usernames
        # Determine default index based on previously selected user (if still available)
        default_index = 0
        if st.session_state.selected_user in all_usernames:
            default_index = options.index(st.session_state.selected_user)
        selected = st.sidebar.radio(
            "Chat with:", 
            options, 
            index=default_index, 
            key="user_selection",
            format_func=lambda x: x if x=="Select a user" else format_username(x)
        )
        # Only update selected_user if a valid username is chosen
        if selected != "Select a user":
            st.session_state.selected_user = selected
        else:
            st.session_state.selected_user = None

        # Conversation Screen
        if st.session_state.selected_user:
            st.subheader(f"Chat with {user_dict.get(st.session_state.selected_user, '❓')} {st.session_state.selected_user}")
            
            messages = fetch_messages(st.session_state.username, st.session_state.selected_user)
            update_message_status(st.session_state.username, st.session_state.selected_user)
            
            st.write("### Messages")
            for msg in messages:
                sender_emoji = user_dict.get(msg["sender"], "❓")
                if msg["sender"] == st.session_state.username:
                    status = msg.get("status", "sent").capitalize()
                    st.markdown(f"**{sender_emoji} {msg['sender']}**: {msg['message']}  _({status})_")
                else:
                    st.markdown(f"**{sender_emoji} {msg['sender']}**: {msg['message']}")
            
            # Message Input Field
            message = st.chat_input("Type a message...", key="chat_input")
            if message:
                store_message(st.session_state.username, st.session_state.selected_user, message)
                st.experimental_rerun()
        else:
            st.sidebar.write("Please select a user to chat with.")
    else:
        st.sidebar.write("No users found matching the search criteria.")
