Discord Slot Scheduler Bot

This is a Python Discord bot designed to help users manage their daily schedules using 4-hour time slots, track habits, and automate journaling.

Features (in this prototype)

/setup: A modal-based command for new users to configure their bot.

Sets the 8-hour "sleep" period (by defining the first "awake" hour).

Sets the channel where journal entries will be posted.

Defines custom positive habits (e.g., "Meditate", "Gym").

Defines custom negative habits (e.g., "Smoke", "Sugary Drinks").

/addtask: Adds a new task with a specific duration (in minutes). The bot automatically finds the next available 4-hour slot that can fit the task.

/starttask: Prompts the user to select a task from their schedule to "start." This begins a timer, and the bot will DM the user when the task's duration is over.

/schedule: Displays an embed showing the 4 active slots for the day, the tasks within them, and the remaining time in each.

/done: Prompts the user to select a completed task. This triggers a Reflection Modal asking about difficulties, interruptions, and feelings, saving the response.

/checkin: A comprehensive, interactive command.

The bot messages the user privately.

It asks about each positive and negative habit one by one using "Yes" / "No" buttons.

After the last question, it prompts the user to write their journal entry for the day.

The bot "waits" for their reply.

Once the user replies, the bot generates a daily summary (with a status title, paragraph, and emoji scoreboard) and posts it to the user's designated journal channel.

⚠️ !! IMPORTANT !! Setup Instructions

This bot requires Python, a Discord Bot Token, and a Google Firebase project for the database.

1. Project Setup

Create a new folder for your bot.

Place the files from this project (bot.py, requirements.txt, .env) into that folder.

Install the required Python libraries:

pip install -r requirements.txt


2. Discord Bot Token

Go to the Discord Developer Portal.

Create a "New Application".

Go to the "Bot" tab.

Click "Add Bot".

Enable all "Privileged Gateway Intents" (Presence, Server Members, and Message Content). This is necessary for the bot to function correctly.

Click "Reset Token" and copy the token.

Paste this token into your .env file:

DISCORD_TOKEN=YOUR_BOT_TOKEN_GOES_HERE


Go to the "OAuth2" -> "URL Generator" tab.

Select the bot and applications.commands scopes.

In "Bot Permissions", select "Administrator" (for ease of setup) or more granular permissions like "Send Messages", "Manage Channels", "Use-Slash-Commands", etc.

Copy the generated URL, paste it into your browser, and invite the bot to your server.

3. Firebase (Firestore) Setup

This bot uses Firestore to store all user data.

Go to the Firebase Console.

Create a "New Project".

Inside your project, go to "Build" -> "Firestore Database".

Click "Create database".

Start in Test Mode (this allows read/write access). Select a region.

In the Firebase Console, go to Project Settings (gear icon) -> Service Accounts.

Click "Generate new private key". A serviceAccountKey.json file will download.

Place this serviceAccountKey.json file in the same folder as your bot.py.

Back in the Firebase Console, go to "Firestore Database".

At the top of the data panel, you'll see a URL like https://[YOUR_PROJECT_ID].firebaseio.com or similar. This is your Database URL.

Paste this URL into your .env file:

FIREBASE_DATABASE_URL=https://YOUR_PROJECT_ID.firebaseio.com


4. Run the Bot

Once all the above is complete, you can run the bot from your terminal:

python bot.py


Go to your Discord server and try typing /setup!
