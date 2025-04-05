import os
import google.generativeai as genai
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, CallbackContext
)
from PIL import Image
import io
from duckduckgo_search import DDGS

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGODB_URI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# MongoDB Setup
client = MongoClient(MONGO_URI)
db = client['telegram_bot']
users = db['users']
chats = db['chat_history']

# Configure Gemini AI
genai.configure(api_key=GEMINI_API_KEY)

#  User Registration
async def register(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    user = users.find_one({"chat_id": chat_id})

    if user:
        await update.message.reply_text("✅ You are already registered!")
    else:
        users.insert_one({"chat_id": chat_id, "username": update.message.from_user.username})
        await update.message.reply_text("✅ Registration successful! You can now use the bot.")

#  Check if User is Registered
def is_registered(chat_id):
    return users.find_one({"chat_id": chat_id}) is not None

#  Start Command
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Welcome to AI Chatbot! 🤖\n"
        "Please register first using /register.\n"
        "Type /help to see available commands."
    )

#  Help Command
async def help_command(update: Update, context: CallbackContext):
    help_text = (
        "Here are the available commands:\n\n"
        "/register - Register yourself to use the bot.\n"
        "/start - Start the bot and get an introduction.\n"
        "/help - Display available commands.\n"
        "/chat <message> - Chat with AI.\n"
        "/websearch <query> - Search the web for information.\n"
        "/analyze - Send an image for analysis.\n\n"
        "Just send a message or image, and the bot will assist you!"
    )
    await update.message.reply_text(help_text)

#  AI Chat Function
async def chat_with_ai(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id

    if not is_registered(chat_id):
        await update.message.reply_text("⚠️ You need to register first using /register.")
        return

    user_message = update.message.text

    if user_message.startswith("/chat "):
        user_message = user_message[6:]  # Remove "/chat "

    try:
        model = genai.GenerativeModel("gemini-pro")  # Create Gemini model instance
        response = model.generate_content(user_message)  # Generate AI response

        reply = response.text if hasattr(response, 'text') else "⚠️ Sorry, I couldn't generate a response."

        # Store conversation history
        chats.insert_one({
            "chat_id": chat_id,
            "user_message": user_message,
            "bot_reply": reply
        })

        await update.message.reply_text(reply)

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

#  Image Analysis
async def analyze_image(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id

    if not is_registered(chat_id):
        await update.message.reply_text("⚠️ You need to register first using /register.")
        return

    if not update.message.photo:
        await update.message.reply_text("❌ Please send an image for analysis!")
        return

    try:
        # Get image file from Telegram
        file = await update.message.photo[-1].get_file()
        file_path = file.file_path

        # Download image and convert it to a format compatible with Gemini API
        image_response = requests.get(file_path)
        image_bytes = io.BytesIO(image_response.content)
        image = Image.open(image_bytes)  # Convert to PIL Image

        # Use Gemini model for analysis
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(["Describe this image.", image])

        description = response.text if hasattr(response, 'text') else "⚠️ Could not generate a description."

        # Store file details
        users.update_one(
            {"chat_id": chat_id},
            {"$push": {"files": {"file_path": file_path, "description": description}}}
        )

        await update.message.reply_text(f"📷 Image Analysis:\n{description}")

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error processing image: {str(e)}")

#  Web Search Function (Using DuckDuckGo)
async def web_search(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id

    if not is_registered(chat_id):
        await update.message.reply_text("⚠️ You need to register first using /register.")
        return

    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("❌ Please provide a search query! Example: /websearch AI news")
        return

    try:
        results = list(DDGS().text(query, max_results=3))  # Get top 3 results

        if results:
            response_text = "🌍 **Top Search Results:**\n\n"
            for result in results:
                response_text += f"🔹 {result['title']}\n🔗 {result['href']}\n\n"
            await update.message.reply_text(response_text)
        else:
            await update.message.reply_text("❌ No results found. Try a different query.")

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error fetching search results: {str(e)}")

#  Create Bot Application
app = Application.builder().token(TOKEN).build()

#  Add Handlers
app.add_handler(CommandHandler("register", register))  # User Registration
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))  
app.add_handler(CommandHandler("websearch", web_search))  # Updated Web Search
app.add_handler(CommandHandler("chat", chat_with_ai))  
app.add_handler(MessageHandler(filters.PHOTO, analyze_image))  
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_with_ai))  

# ✅ Run the Bot
print("🤖 Bot is running...")
app.run_polling()
