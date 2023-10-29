# chickenDoorController.py

# Imports
import logging
import os
import time
import schedule
from threading import Thread
from datetime import datetime
import RPi.GPIO as GPIO
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext
from flask import Flask, jsonify, render_template
from dotenv import load_dotenv

# === Global Variables ===

# Initialize Schedule Times
open_time = "06:00"  # Default opening time
close_time = "19:00"  # Default closing time

# === Initialization ===

# Initialize Logging
logging.basicConfig(filename='chicken.log', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Environment Variables
load_dotenv()
TELEGRAM_API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')
TARGET_CHAT_ID = os.getenv('TARGET_CHAT_ID')
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
    send_telegram_message("Good Morning! Door opened.")


def scheduled_close_door():
    """Scheduled task to close the chicken coop door."""
    close_door()  # Call the existing close_door function
    send_telegram_message("Goodnight! Door closed.")
    
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

# Open the door
async def tg_open_door(update: Update, context: CallbackContext):
    """Telegram command to open the door."""
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
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"The door is currently {door_status}.")
   
   
# Set the schedule 
async def tg_set_schedule(update: Update, context: CallbackContext):
    """Telegram command to set the schedule."""
    global open_time, close_time
    # Get the new times from the command args
    try:
        open_time, close_time = context.args
        update_schedule()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Schedule updated. Door will open at {open_time} and close at {close_time}."
        )
    except ValueError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Invalid arguments. Usage: /setschedule <open_time> <close_time>"
        )


# Get the schedule
async def tg_get_schedule(update: Update, context: CallbackContext):
    """Telegram command to get the current schedule."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Door is scheduled to open at {open_time} and close at {close_time}."
    )


# Telegram error handler
async def error_handler(update: Update, context: CallbackContext):
    """Handles errors for the Telegram bot."""
    logger.error(f"Error handling update {update} - context: {context.error}")
    

async def tg_get_logs(update: Update, context: CallbackContext):
    """Telegram command to get the last 25 log entries."""
    logs = read_last_n_logs()
    formatted_logs = "\n".join([f"- `{line.strip()}`" for line in logs])  # Format each log entry with Markdown
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"📜 Last 25 log entries:\n\n{formatted_logs}", parse_mode="Markdown")


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
    # Telegram Bot Setup
    application = ApplicationBuilder().token(TELEGRAM_API_TOKEN).build()
    application.add_handler(CommandHandler('open', tg_open_door))
    application.add_handler(CommandHandler('close', tg_close_door))
    application.add_handler(CommandHandler('status', tg_door_status))
    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler('setschedule', tg_set_schedule))
    application.add_handler(CommandHandler('getschedule', tg_get_schedule))
    application.add_handler(CommandHandler('logs', tg_get_logs)) 
    
    # Start Telegram Bot
    application.run_polling()
    logger.info("Bot started")
    
    # Initial Schedule Setup
    update_schedule()

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
