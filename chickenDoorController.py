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
import RPi.GPIO as GPIO
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext
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

if GPIO is not None:
    # GPIO has been initialized
    logger.info("GPIO initialized")
else:
    # GPIO has not been initialized
    logger.info("GPIO not found") 

# Initialize PWM
pwm = GPIO.PWM(7, 100)
pwm.start(0)

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
    with open("door_log.txt", "a") as log_file:
        log_file.write(formatted_message + "\n")


# Modify the ease_motor function to frequently check the stop_requested flag
def ease_motor(direction, duration):
    """Eases the motor speed in and out over a given duration."""
    global stop_requested
    with motor_lock:  # Acquire the lock before checking the flag
        if stop_requested:
            stop_requested = False  # Reset the flag
            return  # Exit the function if stop is requested

    GPIO.output(3, direction)
    GPIO.output(5, not direction)
    for duty in range(0, 101, 5):  # Increase speed
        with motor_lock:  # Check the flag within the lock
            if stop_requested:
                stop_requested = False  # Reset the flag
                break  # Exit if stop is requested
        pwm.ChangeDutyCycle(duty)
        time.sleep(0.1)

    # Replace the long sleep with multiple short checks
    start_time = time.time()
    while time.time() - start_time < duration - 0.8:
        with motor_lock:  # Check the flag within the lock
            if stop_requested:
                stop_requested = False  # Reset the flag
                break  # Exit if stop is requested
        time.sleep(0.1)  # Sleep for a short time to allow frequent checks

    for duty in range(100, -1, -5):  # Decrease speed
        with motor_lock:  # Check the flag within the lock
            if stop_requested:
                stop_requested = False  # Reset the flag
                break  # Exit if stop is requested
        pwm.ChangeDutyCycle(duty)
        time.sleep(0.1)


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
   
   
# Save the schedule to a file   
def save_schedule_to_file():
    """Save the current schedule to a file."""
    try:
        with open("schedule.json", "w") as f:
            json.dump({"open_time": open_time, "close_time": close_time}, f)
        return True
    except Exception as e:
        logger.error(f"Error saving schedule to file: {e}")
        return False


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
    - `/status`: Shows the current status of the door
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
application.add_handler(CommandHandler('status', tg_door_status))
application.add_handler(CommandHandler('setschedule', tg_set_schedule))
application.add_handler(CommandHandler('getschedule', tg_get_schedule))
application.add_handler(CommandHandler('logs', tg_get_logs)) 
application.add_handler(CommandHandler('help', tg_help))
application.add_error_handler(error_handler)

# Start Telegram Bot
application.run_polling()
logger.info("Bot started")