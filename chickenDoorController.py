# chickenDoorController.py

# Imports
import logging
import os
import time
import json
import schedule
from threading import Thread
from datetime import datetime
import RPi.GPIO as GPIO
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext, ConversationHandler, MessageHandler, Filters
from flask import Flask, jsonify, render_template
from dotenv import load_dotenv

# === Global Variables ===

# Initialize Schedule Times
open_time = "06:00"  # Default opening time
close_time = "19:00"  # Default closing time

# Initialize authenticated users dictionary
authenticated_users = {}

# Initialize Telegram Conversation States
AUTHENTICATED = 1
WAITING_FOR_PASSWORD = 0


# === Initialization ===

# Initialize Logging
logging.basicConfig(filename='chicken.log', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Environment Variables
load_dotenv()
TELEGRAM_API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')
TARGET_CHAT_ID = os.getenv('TARGET_CHAT_ID')
BOT_PASSWORD = os.getenv('BOT_PASSWORD')
logger.info("Initialized Telegram bot")

# Initialize GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup([3, 5, 7], GPIO.OUT)

# Initialize PWM
pwm = GPIO.PWM(7, 100)
pwm.start(0)
logger.info("PWM initialized")

# Initialize Flask
app = Flask(__name__)

# Initialize Door Status
door_status = "Closed"
progress = 0  # Door opening/closing progress


# === Helper Functions ===

def log_message(message):
    """Logs a message with a timestamp to the console and a file."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"{current_time} - {message}"
    print(formatted_message)
    with open("door_log.txt", "a") as log_file:
        log_file.write(formatted_message + "\n")


def ease_motor(direction, duration):
    """Eases the motor speed in and out over a given duration."""
    global progress
    GPIO.output(3, direction)
    GPIO.output(5, not direction)
    for duty in range(0, 101, 5):  # Increase speed
        pwm.ChangeDutyCycle(duty)
        progress = duty
        time.sleep(0.1)
    time.sleep(duration - 0.8)
    for duty in range(100, -1, -5):  # Decrease speed
        pwm.ChangeDutyCycle(duty)
        progress = 100 - duty
        time.sleep(0.1)
        
        
async def update_telegram_progress(context: CallbackContext, chat_id, message_id, direction):
    """Updates the Telegram message to show the door's progress."""
    global progress  # make sure to use the global variable

    while progress < 100:  # Loop until the door is fully open/closed
        time.sleep(1)  # Wait for a short period of time
        text = f"{direction} door: {'#' * (progress // 10)}{'-' * (10 - progress // 10)} {progress}%"
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
        
    # Final 100% update
    text = f"{direction} door: {'#' * 10} 100%"
    await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)


def read_last_n_logs(n=25):
    """Reads the last n lines from the log file."""
    with open("door_log.txt", "r") as log_file:
        lines = log_file.readlines()
        last_n_lines = lines[-n:]
    return last_n_lines


# === Door Control Functions ===

def open_door():
    """Opens the chicken coop door."""
    global door_status
    ease_motor(True, 10)
    log_message("Door opened")
    door_status = "Opened"

def close_door():
    """Closes the chicken coop door."""
    global door_status
    ease_motor(False, 10)
    log_message("Door closed")
    door_status = "Closed"
    
    
# === Scheduler Functions ===

def scheduled_open_door():
    """Scheduled task to open the chicken coop door."""
    open_door()  # Call the existing open_door function
    send_telegram_message("🐔 Good Morning, Chickens! Time to rise and shine! 🌞 Door opened. 🐔")


def scheduled_close_door():
    """Scheduled task to close the chicken coop door."""
    close_door()  # Call the existing close_door function
    send_telegram_message("🐔 Goodnight, feathery friends! Dream of corn and worms! 🌙 Door closed. 🐔")
    
def update_schedule():
    """Updates the scheduler with new times."""
    global open_time, close_time
    schedule.clear('door-opening')
    schedule.clear('door-closing')
    schedule.every().day.at(open_time).do(scheduled_open_door).tag('door-opening')
    schedule.every().day.at(close_time).do(scheduled_close_door).tag('door-closing')
    

# === Telegram Messages ===

def send_telegram_message(message):
    """Sends a message via Telegram using a synchronous bot."""
    bot = Bot(token=TELEGRAM_API_TOKEN)
    bot.send_message(chat_id=TARGET_CHAT_ID, text=message)


# === Telegram Bot Commands ===

# Start the bot
async def tg_start(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Please enter the password.")
    context.session['authenticated'] = False  # Set initial authentication state
    return WAITING_FOR_PASSWORD  # Go to the state waiting for password

# Check the password
async def tg_password(update: Update, context: CallbackContext):
    entered_password = update.message.text
    if entered_password == BOT_PASSWORD:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Authenticated. You can now use the bot.")
        context.session['authenticated'] = True  # Update authentication state
        return AUTHENTICATED  # End the conversation or go to authenticated state
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Wrong password. Try again.")
        return WAITING_FOR_PASSWORD  # Go back to waiting for the password


# Check if the user is authenticated
def is_authenticated(chat_id):
    return authenticated_users.get(chat_id, False)


# Open the door
async def tg_open_door(update: Update, context: CallbackContext):
    """Telegram command to open the door."""
    chat_id = update.effective_chat.id
    if not context.session.get('authenticated', False):
        await context.bot.send_message(chat_id=chat_id, text="Please authenticate first.")
        return
    global progress
    progress = 0  # Reset progress
    message = await context.bot.send_message(chat_id=update.effective_chat.id, text="Opening door: ---------- 0%")
    
    # Start the door opening in a new thread
    door_thread = Thread(target=open_door)
    door_thread.start()
    
    # Update the progress in Telegram
    await update_telegram_progress(context, update.effective_chat.id, message.message_id, "Opening")
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Door opened.")


# Close the door
async def tg_close_door(update: Update, context: CallbackContext):
    """Telegram command to close the door."""
    chat_id = update.effective_chat.id
    if not context.session.get('authenticated', False):
        await context.bot.send_message(chat_id=chat_id, text="Please authenticate first.")
        return
    global progress
    progress = 0  # Reset progress
    message = await context.bot.send_message(chat_id=update.effective_chat.id, text="Closing door: ---------- 0%")
    
    # Start the door closing in a new thread
    door_thread = Thread(target=close_door)
    door_thread.start()
    
    # Update the progress in Telegram
    await update_telegram_progress(context, update.effective_chat.id, message.message_id, "Closing")
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Door closed.")


# Check the door status
async def tg_door_status(update: Update, context: CallbackContext):
    """Telegram command to check the door status."""
    chat_id = update.effective_chat.id
    if not context.session.get('authenticated', False):
        await context.bot.send_message(chat_id=chat_id, text="Please authenticate first.")
        return
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"The door is currently {door_status}.")
   
   
# Save the schedule to a file   
def save_schedule_to_file():
    """Save the current schedule to a file."""
    with open("schedule.json", "w") as f:
        json.dump({"open_time": open_time, "close_time": close_time}, f)

# Load the schedule from a file
async def tg_set_schedule(update: Update, context: CallbackContext):
    """Telegram command to set the schedule."""
    chat_id = update.effective_chat.id
    if not context.session.get('authenticated', False):
        await context.bot.send_message(chat_id=chat_id, text="Please authenticate first.")
        return
    global open_time, close_time
    try:
        open_time, close_time = context.args
        update_schedule()
        save_schedule_to_file()  # Save the updated schedule to a file
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Schedule updated. Door will open at {open_time} and close at {close_time}."
        )
    except ValueError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Invalid arguments. Usage: /setschedule <open_time> <close_time>"
        )


# Load the schedule from a file
def load_schedule_from_file():
    """Load the schedule from a file."""
    global open_time, close_time
    try:
        with open("schedule.json", "r") as f:
            schedule_data = json.load(f)
            open_time = schedule_data.get("open_time", "06:00")
            close_time = schedule_data.get("close_time", "19:00")
    except FileNotFoundError:
        open_time = "06:00"
        close_time = "19:00"


# Get the schedule
async def tg_get_schedule(update: Update, context: CallbackContext):
    """Telegram command to get the current schedule."""
    chat_id = update.effective_chat.id
    if not context.session.get('authenticated', False):
        await context.bot.send_message(chat_id=chat_id, text="Please authenticate first.")
        return
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Door is scheduled to open at {open_time} and close at {close_time}."
    )


# Telegram error handler
async def error_handler(update: Update, context: CallbackContext):
    """Handles errors for the Telegram bot."""
    logger.error(f"Error handling update {update} - context: {context.error}")
    

# Get the last N log entries
async def tg_get_logs(update: Update, context: CallbackContext):
    """Telegram command to get the last N log entries, default is 25."""
    chat_id = update.effective_chat.id
    if not context.session.get('authenticated', False):
        await context.bot.send_message(chat_id=chat_id, text="Please authenticate first.")
        return
    try:
        num_logs = int(context.args[0]) if context.args else 25  # Use the first argument as the number of logs, default to 25
    except ValueError:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Invalid argument. Usage: /logs <number>")
        return
    
    logs = read_last_n_logs(num_logs)  # Pass the number to the function
    formatted_logs = "\n".join([f"- `{line.strip()}`" for line in logs])  # Format each log entry with Markdown
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"📜 Last {num_logs} log entries:\n\n{formatted_logs}", parse_mode="Markdown")
    

# Show the help message
async def tg_help(update: Update, context: CallbackContext):
    """Telegram command to show available commands and their descriptions."""
    chat_id = update.effective_chat.id
    if not context.session.get('authenticated', False):
        await context.bot.send_message(chat_id=chat_id, text="Please authenticate first.")
        return
    help_text = """
    🤖 *Chicken Door Controller Bot Commands:*

    - `/open`: Opens the chicken coop door
    - `/close`: Closes the chicken coop door
    - `/status`: Shows the current status of the door
    - `/setschedule [open_time] [close_time]`: Sets the door opening and closing schedule
    - `/getschedule`: Gets the current door opening and closing schedule
    - `/logs [number]`: Shows the last N log entries, default is 25
    - `/help`: Shows this help message

    For example, to set the schedule to open at 06:30 and close at 19:45, use `/setschedule 06:30 19:45`.
    """
    await context.bot.send_message(chat_id=update.effective_chat.id, text=help_text, parse_mode="Markdown")


# === Flask API Endpoints ===

@app.route('/api/open_door', methods=['POST'])
def api_open_door():
    """API endpoint to open the door."""
    open_door()
    return jsonify(status='success')


@app.route('/api/close_door', methods=['POST'])
def api_close_door():
    """API endpoint to close the door."""
    close_door()
    return jsonify(status='success')


@app.route('/api/door_status', methods=['GET'])
def api_door_status():
    """API endpoint to get the door status."""
    return jsonify(status=door_status)


@app.route('/api/progress', methods=['GET'])
def api_progress():
    """API endpoint to get the door opening/closing progress."""
    return jsonify(progress=progress)


@app.route('/api/set_schedule', methods=['POST'])
def api_set_schedule():
    """API endpoint to set the schedule."""
    global open_time, close_time
    new_open_time = request.json.get('open_time')
    new_close_time = request.json.get('close_time')
    if new_open_time and new_close_time:
        open_time = new_open_time
        close_time = new_close_time
        update_schedule()
        return jsonify(status='success')
    return jsonify(status='error', message='Invalid parameters')


@app.route('/api/get_schedule', methods=['GET'])
def api_get_schedule():
    """API endpoint to get the current schedule."""
    return jsonify(open_time=open_time, close_time=close_time)


@app.route('/')
def index():
    """Landing page."""
    return render_template('index.html')


# === Main Program ===

if __name__ == '__main__':
    # Initial Schedule Setup
    load_schedule_from_file()  # Load the schedule from a file
    update_schedule()  # Update the schedule based on loaded times

    # Telegram Bot Setup
    application = ApplicationBuilder().token(TELEGRAM_API_TOKEN).build()
    application.add_handler(CommandHandler('password', tg_password))
    application.add_handler(CommandHandler('open', tg_open_door))
    application.add_handler(CommandHandler('close', tg_close_door))
    application.add_handler(CommandHandler('status', tg_door_status))
    application.add_handler(CommandHandler('setschedule', tg_set_schedule))
    application.add_handler(CommandHandler('getschedule', tg_get_schedule))
    application.add_handler(CommandHandler('logs', tg_get_logs)) 
    application.add_handler(CommandHandler('help', tg_help))
    
    # Telegram Error Handler
    application.add_error_handler(error_handler)
    
    # Telegram Conversation Handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', tg_start)],
        states={
            WAITING_FOR_PASSWORD: [MessageHandler(Filters.text, tg_password)]
        },
        fallbacks=[]
    )
    application.add_handler(conv_handler)


    # Start Telegram Bot
    application.run_polling()
    logger.info("Bot started")
    
    # Start Flask Thread
    flask_thread = Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 5000})
    flask_thread.daemon = True
    flask_thread.start()

    # Start Scheduler Thread
    scheduler_thread = Thread(target=scheduler_thread)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    # Main Loop
    try:
        logger.info("Entering main loop")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log_message("Exiting...")
        pwm.stop()
        GPIO.cleanup()
