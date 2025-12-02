Discord Slot Scheduler Bot
This is a Python Discord bot designed to help users manage their daily schedules using 4-hour time slots, track habits, and automate journaling.Features (in this prototype)/setup: A modal-based command for new users to configure their bot.

/addtask: Adds a new task with a specific duration (in minutes).
/starttask: Prompts the user to select a task from their schedule to "start."
/schedule: Displays an embed showing the 4 active slots for the day./done: Prompts the user to select a completed task and triggers a reflection modal.
/checkin: A comprehensive, interactive command for daily habits and journaling.

⚠️ !! IMPORTANT !! Setup InstructionsThis bot requires Python, a Discord Bot Token, and a Google Firebase project for the database.
1. Project SetupCreate a new folder for your bot.
Place the files from this project (bot.py, requirements.txt, .env) into that folder.
Install the required Python libraries:pip install -r requirements.txt
2. Discord Bot TokenGo to the Discord Developer Portal.
Create a "New Application".
Go to the "Bot" tab.
Click "Add Bot".
Enable all "Privileged Gateway Intents" (Presence, Server Members, and Message Content). 
This is necessary for the bot to function correctly.

Click "Reset Token" and copy the token.
Paste this token into your .env file.
Go to the "OAuth2" -> "URL Generator" tab.
Select the bot and applications.commands scopes.In "Bot Permissions", select "Administrator".Copy the generated URL, paste it into your browser, and invite the bot to your server.

3. Firebase (Firestore) SetupGo to the Firebase Console.
Create a "New Project".
Inside your project, go to "Build" -> "Firestore Database".Click "Create database".Start in Test Mode (this allows read/write access). 
Select a region.In the Firebase Console, go to Project Settings (gear icon) -> Service Accounts.
Click "Generate new private key". 
A serviceAccountKey.json file will download.
Place this serviceAccountKey.json file in the same folder as your bot.py.Back in the Firebase Console, go to "Firestore Database".
At the top of the data panel, you'll see a URL like https://[YOUR_PROJECT_ID].firebaseio.com.Paste this URL into your .env file.4. Run the BotOnce all the above is complete, you can run the bot from your terminal: python bot.py
