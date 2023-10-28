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


# === Telegram Bot Commands ===

async def tg_open_door(update: Update, context: CallbackContext):
    """Telegram command to open the door."""
    open_door()
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Door opened.")


async def tg_close_door(update: Update, context: CallbackContext):
    """Telegram command to close the door."""
    close_door()
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Door closed.")


async def tg_door_status(update: Update, context: CallbackContext):
    """Telegram command to check the door status."""
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"The door is currently {door_status}.")


async def error_handler(update: Update, context: CallbackContext):
    """Handles errors for the Telegram bot."""
    logger.error(f"Error handling update {update} - context: {context.error}")


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
    application.run_polling()
    logger.info("Bot started")

    # Scheduler Setup
    schedule.every().day.at("06:00").do(open_door)
    schedule.every().day.at("20:00").do(close_door)

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
