"""
chickenDoorController.py

This script controls the opening and closing of a chicken coop door.
It uses a Raspberry Pi's GPIO pins to control a motor, which opens and closes the door.
The door is scheduled to open at 6:00 and close at 20:00 every day.
The script also listens for user input to manually open or close the door.
"""
from telegram.ext import Updater, CommandHandler
from datetime import datetime
import schedule
from threading import Thread
import time
import RPi.GPIO as GPIO
from flask import Flask, jsonify, render_template
from dotenv import load_dotenv
import os
import sys
import select

# Load environment variables from .env file
load_dotenv()

# Get Telegram API token
TELEGRAM_API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')

# Initialize Telegram Bot
updater = Updater(token=TELEGRAM_API_TOKEN, use_context=True)
dispatcher = updater.dispatcher

# Disable warnings
GPIO.setwarnings(False)

# Initialize GPIO
GPIO.setmode(GPIO.BOARD)
GPIO.setup(3, GPIO.OUT)
GPIO.setup(5, GPIO.OUT)
GPIO.setup(7, GPIO.OUT)

# Initialize PWM
pwm = GPIO.PWM(7, 100)
pwm.start(0)

# Initialize Flask app
app = Flask(__name__)

# Initialize your door status
door_status = "Closed"

# Initialize door opening/closing progress
progress = 0


# Custom logging
def log_message(message):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"{current_time} - {message}"
    
    # Print to console
    print(formatted_message)
    
    # Write to file
    with open("door_log.txt", "a") as log_file:
        log_file.write(formatted_message + "\n")


# Function to ease in and out motor speed
def ease_motor(direction, duration):
    global progress
    GPIO.output(3, direction)
    GPIO.output(5, not direction)
    
    # Gradually increase the motor speed from 0 to 100
    for duty in range(0, 101, 5):
        pwm.ChangeDutyCycle(duty)
        progress = duty
        time.sleep(0.1)
    
    time.sleep(duration - 0.8)
    
    # Gradually decrease the motor speed from 100 to 0
    for duty in range(100, -1, -5):
        pwm.ChangeDutyCycle(duty)
        progress = 100 - duty
        time.sleep(0.1)
    
    GPIO.output(7, False)


# Function to open and close the door
def open_door():
    global door_status
    ease_motor(True, 10)
    log_message(f"Door opened")
    door_status = "opened"

def close_door():
    global door_status
    ease_motor(False, 10)
    log_message(f"Door closed")
    door_status = "closed"
    
# Telegram command to open door
def tg_open_door(update, context):
    open_door()
    update.message.reply_text("Door opened.")

# Telegram command to close door
def tg_close_door(update, context):
    close_door()
    update.message.reply_text("Door closed.")

# Add command handlers
dispatcher.add_handler(CommandHandler('open', tg_open_door))
dispatcher.add_handler(CommandHandler('close', tg_close_door))

# Start the Bot
updater.start_polling()

    
# Function to listen for user input    
@app.route('/api/open_door', methods=['POST'])
def api_open_door():
    global door_status
    ease_motor(True, 10)
    log_message("Door opened")
    door_status = "Open"
    return jsonify(status='success')

@app.route('/api/close_door', methods=['POST'])
def api_close_door():
    global door_status
    ease_motor(False, 10)
    log_message("Door closed")
    door_status = "Closed"
    return jsonify(status='success')


# Function to get door status
@app.route('/api/door_status', methods=['GET'])
def api_door_status():
    global door_status
    return jsonify(status=door_status)


# Function to get door opening/closing progress
@app.route('/api/progress', methods=['GET'])
def api_progress():
    global progress
    return jsonify(progress=progress)


# Landing page
@app.route('/')
def index():
    return render_template('index.html')


# Schedule tasks
schedule.every().day.at("06:00").do(open_door)
schedule.every().day.at("20:00").do(close_door)


# Main loop for Flask app
def flask_thread():
    app.run(host='0.0.0.0', port=5000)


# Main loop for scheduler
def scheduler_thread():
    while True:
        schedule.run_pending()
        time.sleep(1)


# Start Flask thread
flask_thread = Thread(target=flask_thread)
flask_thread.daemon = True
flask_thread.start()


# Start scheduler thread
scheduler_thread = Thread(target=scheduler_thread)
scheduler_thread.daemon = True
scheduler_thread.start()


# Main loop
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    log_message(f"Exiting...")
    pwm.stop()
    GPIO.cleanup()