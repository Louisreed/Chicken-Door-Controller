# chickenDoorController.py

# Imports
import logging
import os
import time
import json
import schedule
import threading
from threading import Thread
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext
from dotenv import load_dotenv
from io import BytesIO


# Raspberry Pi Imports
import RPi.GPIO as GPIO
import picamera
import requests
import openai


# === Initialization ===

# Initialize Logging
logging.basicConfig(filename='chicken.log', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Environment Variables
load_dotenv()
TELEGRAM_API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')
TARGET_CHAT_ID = os.getenv('TARGET_CHAT_ID')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if GPIO is not None:
    # Initialize GPIO
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup([3, 5, 7], GPIO.OUT)
    logger.info("GPIO setup")
    
    # GPIO has been initialized
    logger.info("GPIO initialized")
else:
    # GPIO has not been initialized
    logger.error("GPIO not initialized")

# Initialize PWM
if GPIO is not None:
    pwm = GPIO.PWM(7, 100)
    pwm.start(0)
    logger.info("PWM setup")
else:
    logger.error("PWM not initialized") 

# Initialize Door Status
door_status = "Closed"

# === Global Variables ===

# Initialize Schedule Times
open_time = "06:00"  # Default opening time
close_time = "19:00"  # Default closing time

# Flag to signal motor stop
stop_requested = False  
motor_lock = threading.Lock()  # Lock for synchronizing access to the stop_requested flag

# === Helper Functions ===

def log_message(message):
    """Logs a message with a timestamp to the console and a file."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"{current_time} - {message}"
    print(formatted_message)
    with open("chicken.log", "a") as log_file:
        log_file.write(formatted_message + "\n")


def ease_motor(direction, duration):
    """Eases the motor speed in and out over a given duration."""
    global stop_requested
    
    # Start the motor in the specified direction
    GPIO.output(3, direction)
    GPIO.output(5, not direction)

    # Increase speed
    for duty in range(0, 101, 5):
        with motor_lock:
            if stop_requested:
                # Stop the motor
                pwm.ChangeDutyCycle(0)
                GPIO.output([3, 5], GPIO.LOW)
                stop_requested = False  # Reset the flag
                return  # Exit if stop is requested
        pwm.ChangeDutyCycle(duty)
        time.sleep(0.1)

    # Maintain the speed for the duration minus ramp up and down time
    start_time = time.time()
    while time.time() - start_time < duration - 0.8:  # Adjust time for ramp up and down
        with motor_lock:
            if stop_requested:
                # Stop the motor
                pwm.ChangeDutyCycle(0)
                GPIO.output([3, 5], GPIO.LOW)
                stop_requested = False
                return  # Exit if stop is requested
        time.sleep(0.1)  # Sleep for a short time to allow frequent checks

    # Decrease speed
    for duty in range(100, -1, -5):
        with motor_lock:
            if stop_requested:
                # Stop the motor
                pwm.ChangeDutyCycle(0)
                GPIO.output([3, 5], GPIO.LOW)
                stop_requested = False
                return  # Exit if stop is requested
        pwm.ChangeDutyCycle(duty)
        time.sleep(0.1)

    # Stop the motor after operation is complete if stop hasn't been requested
    with motor_lock:
        if not stop_requested:
            pwm.ChangeDutyCycle(0)
            GPIO.output([3, 5], GPIO.LOW)


def read_last_n_logs(n=25):
    """Reads the last n lines from the log file."""
    with open("door_log.txt", "r") as log_file:
        lines = log_file.readlines()
        last_n_lines = lines[-n:]
    return last_n_lines


def format_time(time_str):
    """Formats a time string to HH:MM."""
    try:
        time_obj = datetime.strptime(time_str, "%H:%M")
        return time_obj.strftime("%H:%M")
    except ValueError:
        return None
    
# === Camera Functions ===

def capture_image():
    """Captures an image and returns the image data as a byte stream."""
    logger.info("Attempting to capture an image")
    stream = BytesIO()
    try:
        with picamera.PiCamera() as camera:
            camera.resolution = (1024, 768)
            camera.start_preview()
            time.sleep(2)  # Camera warm-up time
            camera.capture(stream, 'jpeg')
    except Exception as e:
        logger.error(f"Error capturing image: {e}")
        return None
    stream.seek(0)
    logger.info("Image captured successfully")
    return stream


def extract_egg_count_from_response(egg_count_response):
    """Extracts the egg count from the OpenAI response."""
    # find a number in the response, if none return 0
    # for illustration purposes, let's assume the response is a string
    # with a number in it
    for egg in egg_count_response.split():
        try:
            return int(egg)
        except ValueError:
            continue
    return 0

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
    
def stop_motor():
    """Stops the motor immediately."""
    global stop_requested
    with motor_lock:  # Acquire the lock before setting the flag
        stop_requested = True  # Signal that a stop has been requested
        
    
# === Scheduler Functions ===

def run_scheduler():
    """Main loop to run the scheduler."""
    while True:
        schedule.run_pending()
        time.sleep(1)

def scheduled_open_door():
    """Scheduled task to open the chicken coop door."""
    logger.info("Scheduled open door function called.")
    open_door()  # Call the existing open_door function
    # bot_instance.send_message(chat_id=TARGET_CHAT_ID, text="🐔 Good Morning, Chickens! Time to rise and shine! 🌞 Door opened. 🐔")

def scheduled_close_door():
    """Scheduled task to close the chicken coop door."""
    logger.info("Scheduled close door function called.")
    close_door()  # Call the existing close_door function
    # bot_instance.send_message(chat_id=TARGET_CHAT_ID, text="🐔 Goodnight, feathery friends! Dream of corn and worms! 🌙 Door closed. 🐔")
    
def update_schedule():
    """Updates the scheduler with new times."""
    global open_time, close_time
    schedule.clear('door-opening')
    schedule.clear('door-closing')
    schedule.every().day.at(open_time).do(scheduled_open_door).tag('door-opening')
    schedule.every().day.at(close_time).do(scheduled_close_door).tag('door-closing')
    
def save_schedule_to_file():
    """Save the current schedule to a file."""
    try:
        with open("schedule.json", "w") as f:
            json.dump({"open_time": open_time, "close_time": close_time}, f)
        return True
    except Exception as e:
        logger.error(f"Error saving schedule to file: {e}")
        return False

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
    

# === Telegram Bot Commands ===


# Open the door
async def tg_open_door(update: Update, context: CallbackContext):
    """Telegram command to open the door."""
    # Start the door opening in a new thread
    door_thread = Thread(target=open_door)
    door_thread.start()
    
    # Send opening message in Telegram
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Door opening...")

    # Check the door_thread in the background
    def check_door_thread():
        door_thread.join()
        # Ensure the stop wasn't requested before sending the closed message
        if not stop_requested:
            context.bot.send_message(chat_id=update.effective_chat.id, text="Door open.")
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text="Door opening was interrupted.")

    # Start a new thread to check when the door_thread has finished without blocking
    Thread(target=check_door_thread).start()


# Close the door
async def tg_close_door(update: Update, context: CallbackContext):
    """Telegram command to close the door."""
    # Start the door closing in a new thread
    door_thread = Thread(target=close_door)
    door_thread.start()
    
    # Send closing message in Telegram
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Door closing...")

    # Check the door_thread in the background
    def check_door_thread():
        door_thread.join()
        # Ensure the stop wasn't requested before sending the closed message
        if not stop_requested:
            context.bot.send_message(chat_id=update.effective_chat.id, text="Door closed.")
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text="Door closing was interrupted.")

    # Start a new thread to check when the door_thread has finished without blocking
    Thread(target=check_door_thread).start()


# Stop the motor
async def tg_stop_motor(update: Update, context: CallbackContext):
    """Telegram command to stop the motor."""
    stop_motor()  # Signal to stop the motor
    # The message will be sent immediately
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Stopping motor...")
    # You might want to wait a bit to ensure the motor stops
    time.sleep(1)  # Give a moment for the motor to respond to the stop signal
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Motor stopped.")


# Check the door status
async def tg_door_status(update: Update, context: CallbackContext):
    """Telegram command to check the door status."""
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"The door is currently {door_status}.")
   

# Load the schedule from a file
async def tg_set_schedule(update: Update, context: CallbackContext):
    """Telegram command to set the schedule."""
    global open_time, close_time
    try:
        open_time, close_time = context.args
        
        # Format the times
        open_time = format_time(open_time)
        close_time = format_time(close_time)
        
        if not open_time or not close_time:
            raise ValueError("Invalid time format. Ensure times are in HH:MM format.")
        
        save_schedule_to_file()
        update_schedule()
        logger.info(f"Updated scheduled times - Open: {open_time}, Close: {close_time}")
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Schedule updated. Door will open at {open_time} and close at {close_time}."
        )
    except ValueError as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Invalid arguments. Usage: /setschedule 00:00 00:00"
        )


# Get the schedule
async def tg_get_schedule(update: Update, context: CallbackContext):
    """Telegram command to get the current schedule."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Door is scheduled to open at {open_time} and close at {close_time}."
    )


# Capture and send a picture    
async def tg_send_picture(update: Update, context: CallbackContext):
    """Telegram command to capture and send a picture."""
    logger.info("Received picture command")
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Capturing image...")
    
    image_stream = capture_image()
    if image_stream:
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_stream)
        logger.info("Image sent to user")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Failed to capture image.")
        logger.error("Failed to capture image")
        
      
# Count the eggs        
async def tg_count_eggs(update: Update, context: CallbackContext):
    """Telegram command to count the eggs."""
    chat_id = update.effective_chat.id
    logger.info("Received command to count eggs")
    await context.bot.send_message(chat_id=chat_id, text="Taking a photo...")

    image_stream = capture_image()
    if image_stream:
        logger.info("Image captured, sending to Telegram")
        message = await context.bot.send_photo(chat_id=chat_id, photo=image_stream)
        logger.info("Image sent to Telegram, retrieving file_id")
        
        photo_file_id = message.photo[-1].file_id
        file = await context.bot.get_file(photo_file_id)
        file_path = file.file_path
        image_url = f"https://api.telegram.org/file/bot{TELEGRAM_API_TOKEN}/{file_path}"
        
        logger.info(f"Image URL obtained: {image_url}")
        try:
            logger.info("Sending image URL to OpenAI for analysis")
            egg_count_response = await analyze_image_with_openai(image_url)
            logger.info(f"Received response from OpenAI: {egg_count_response}")
            egg_count = extract_egg_count_from_response(egg_count_response)
            await context.bot.send_message(chat_id=chat_id, text=f"Number of eggs detected: {egg_count}")
        except Exception as e:
            logger.error(f"Error during OpenAI analysis: {e}")
            await context.bot.send_message(chat_id=chat_id, text="Error processing image.")
    else:
        logger.error("Failed to capture the image")
        await context.bot.send_message(chat_id=chat_id, text="Failed to capture the image.")


async def analyze_image_with_openai(image_url):
    """Sends the image URL to OpenAI for analysis."""
    prompt = f"There is a photo of a chicken coop. Can you tell me how many eggs are visible in this photo? {image_url}"
    
    try:
        logger.info("Making request to OpenAI API")
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        answer = response['choices'][0]['message']['content']
        logger.info(f"Response from OpenAI: {answer}")
        return answer.strip()
    except Exception as e:
        logger.error(f"Error in OpenAI API call: {e}")
        return "Error in analyzing image."
 

# Telegram error handler
async def error_handler(update: Update, context: CallbackContext):
    """Handles errors for the Telegram bot."""
    logger.error(f"Error handling update {update} - context: {context.error}")
    

# Get the last N log entries
async def tg_get_logs(update: Update, context: CallbackContext):
    """Telegram command to get the last N log entries, default is 25."""
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
    help_text = """
    🤖 *Chicken Door Controller Bot Commands:*

    - `/open`: Opens the chicken coop door
    - `/close`: Closes the chicken coop door
    - `/stop`: Stops the chicken coop door while opening/closing
    - `/status`: Shows the current status of the door
    - `/picture`: Captures and sends a picture from the camera
    - `/setschedule [open_time] [close_time]`: Sets the door opening and closing schedule
    - `/getschedule`: Gets the current door opening and closing schedule
    - `/logs [number]`: Shows the last N log entries, default is 25
    - `/help`: Shows this help message

    For example, to set the schedule to open at 06:30 and close at 19:45, use `/setschedule 06:30 19:45`.
    """
    await context.bot.send_message(chat_id=update.effective_chat.id, text=help_text, parse_mode="Markdown")


# === Main Program ===

# Initial Schedule Setup
load_schedule_from_file()  # Load the schedule from a file
logger.info(f"Scheduled times - Open: {open_time}, Close: {close_time}")
update_schedule()  # Update the schedule based on loaded times

# Start Scheduler Thread
scheduler_thread = Thread(target=run_scheduler)
scheduler_thread.start()

# Telegram Bot Setup
application = ApplicationBuilder().token(TELEGRAM_API_TOKEN).build()
application.add_handler(CommandHandler('open', tg_open_door))
application.add_handler(CommandHandler('close', tg_close_door))
application.add_handler(CommandHandler('stop', tg_stop_motor))
application.add_handler(CommandHandler('picture', tg_send_picture))
application.add_handler(CommandHandler('eggs', tg_count_eggs))
application.add_handler(CommandHandler('status', tg_door_status))
application.add_handler(CommandHandler('setschedule', tg_set_schedule))
application.add_handler(CommandHandler('getschedule', tg_get_schedule))
application.add_handler(CommandHandler('logs', tg_get_logs)) 
application.add_handler(CommandHandler('help', tg_help))
application.add_error_handler(error_handler)

# Start Telegram Bot
logger.info("Starting Telegram bot polling")
application.run_polling()
logger.info("Bot started")