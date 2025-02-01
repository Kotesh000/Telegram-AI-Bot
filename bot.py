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
from serpapi import GoogleSearch # type: ignore

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGODB_URI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")  # For Web Search

# MongoDB Setup
client = MongoClient(MONGO_URI)
db = client['telegram_bot']
users = db['users']
chats = db['chat_history']

# Configure Gemini AI
genai.configure(api_key=GEMINI_API_KEY)

# Start Command
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Welcome to AI Chatbot! 🤖\n"
        "Type /help to see available commands."
    )

# Help Command
async def help_command(update: Update, context: CallbackContext):
    help_text = (
        "Here are the available commands:\n\n"
        "/start - Start the bot and get an introduction.\n"
        "/help - Display available commands.\n"
        "/chat <message> - Chat with AI.\n"
        "/websearch <query> - Search the web for information.\n"
        "/analyze - Send an image for analysis (the bot will describe the image).\n\n"
        "Just send a message or image, and the bot will assist you!"
    )
    await update.message.reply_text(help_text)

# ✅ FIXED: AI Chat Function (used for any question as well)
async def chat_with_ai(update: Update, context: CallbackContext):
    user_message = update.message.text

    if user_message.startswith("/chat "):
        # The message is a request for a detailed answer
        user_message = user_message[6:]  # Remove the "/chat " part

        try:
            model = genai.GenerativeModel("gemini-pro")  # Create Gemini model instance
            response = model.generate_content(user_message)  # Generate AI response

            if hasattr(response, 'text'):
                reply = response.text  # Detailed response
            else:
                reply = "⚠️ Sorry, I couldn't generate a detailed response."

            # Store conversation history in MongoDB
            chats.insert_one({
                "chat_id": update.message.chat_id,
                "user_message": user_message,
                "bot_reply": reply
            })

            await update.message.reply_text(reply)

        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {str(e)}")

    else:
        # The message is a regular question that doesn't use /chat
        try:
            model = genai.GenerativeModel("gemini-pro")  # Create Gemini model instance
            response = model.generate_content(user_message)  # Generate AI response

            if hasattr(response, 'text'):
                reply = response.text  # Short response or definition
            else:
                reply = "⚠️ Sorry, I couldn't generate a response."

            # Store conversation history in MongoDB
            chats.insert_one({
                "chat_id": update.message.chat_id,
                "user_message": user_message,
                "bot_reply": reply
            })

            await update.message.reply_text(reply)

        except Exception as e:
            await update.message.reply_text(f"⚠️ Error: {str(e)}")

# ✅ FIXED: Image/File Analysis
async def analyze_image(update: Update, context: CallbackContext):
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

        # Use the latest Gemini model (gemini-1.5-flash)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        # ✅ Add a text prompt with the image
        response = model.generate_content(
            ["Describe this image.", image]  # Send text prompt + image
        )

        if hasattr(response, 'text'):
            description = response.text  # Extract text response
        else:
            description = "⚠️ Could not generate a description."

        # Store file details in MongoDB
        users.update_one(
            {"chat_id": update.message.chat_id},
            {"$push": {"files": {"file_path": file_path, "description": description}}}
        )

        await update.message.reply_text(f"📷 Image Analysis:\n{description}")

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error processing image: {str(e)}")

# ✅ FIXED: Web Search Function
async def web_search(update: Update, context: CallbackContext):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("❌ Please provide a search query! Example: /websearch AI news")
        return

    params = {
        "q": query,
        "location": "India",
        "hl": "en",
        "gl": "in",
        "api_key": SERPAPI_KEY
    }

    search = GoogleSearch(params)
    results = search.get_dict()

    if "organic_results" in results:
        response_text = "🌍 **Top Search Results:**\n\n"
        for idx, result in enumerate(results["organic_results"][:3]):  # Get top 3 results
            response_text += f"🔹 {result['title']}\n🔗 {result['link']}\n\n"
        await update.message.reply_text(response_text)
    else:
        await update.message.reply_text("❌ No results found. Try a different query.")

# Create Bot Application
app = Application.builder().token(TOKEN).build()

# Add Handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))  # Added /help command
app.add_handler(CommandHandler("websearch", web_search))
app.add_handler(CommandHandler("chat", chat_with_ai))  # Added /chat command
app.add_handler(MessageHandler(filters.PHOTO, analyze_image))  # Handles images sent to bot

# Handle any text message as a question to AI
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_with_ai))  # Handles text questions

# Run the Bot
print("🤖 Bot is running...")
app.run_polling()
