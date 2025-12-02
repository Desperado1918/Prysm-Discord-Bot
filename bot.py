import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
from dotenv import load_dotenv
import uuid # To generate unique task IDs

# --- Setup: Load Environment Variables ---
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
FIREBASE_DATABASE_URL = os.getenv('FIREBASE_DATABASE_URL')

if not DISCORD_TOKEN or not FIREBASE_DATABASE_URL:
    print("Error: DISCORD_TOKEN or FIREBASE_DATABASE_URL not found in .env file.")
    print("Please see README.md for setup instructions.")
    exit()

# --- Setup: Firebase ---
try:
    cred = credentials.Certificate('serviceAccountKey.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': FIREBASE_DATABASE_URL
    })
    db = firestore.client()
    print("Firebase connection successful.")
except FileNotFoundError:
    print("Error: 'serviceAccountKey.json' not found.")
    print("Please download it from your Firebase project settings and place it in the same directory.")
    exit()
except Exception as e:
    print(f"Error initializing Firebase: {e}")
    exit()

# --- Setup: Bot ---
# We need all intents for full functionality (especially members and message content)
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# This will store active task timers
# { 'user_id_task_id': asyncio.Task }
active_timers = {}

# --- Helper Functions ---

def get_user_config_ref(user_id):
    """Gets the Firestore doc reference for a user's configuration."""
    return db.collection('users').document(str(user_id)).collection('config').document('main')

def get_user_schedule_ref(user_id, date_str):
    """Gets the Firestore doc reference for a user's schedule on a specific date."""
    return db.collection('users').document(str(user_id)).collection('schedules').document(date_str)

def get_user_habits_ref(user_id, date_str):
    """Gets the Firestore doc reference for a user's habits on a specific date."""
    return db.collection('users').document(str(user_id)).collection('habits').document(date_str)

def get_today_date_str():
    """Returns today's date as 'YYYY-MM-DD'."""
    return datetime.now().strftime('%Y-%m-%d')

async def get_or_create_schedule(user_id, start_hour):
    """
    Fetches today's schedule from Firestore. If it doesn't exist,
    it creates a new one based on the user's start_hour.
    """
    today_str = get_today_date_str()
    schedule_ref = get_user_schedule_ref(user_id, today_str)
    schedule_doc = await asyncio.to_thread(schedule_ref.get)

    if schedule_doc.exists:
        return schedule_doc.to_dict()
    else:
        # Create a new schedule for today
        new_schedule = {
            'date': today_str,
            'slots': []
        }
        current_hour = start_hour
        for i in range(4):
            new_schedule['slots'].append({
                'slot_number': i + 1,
                'start_hour': current_hour,
                'total_minutes': 240,
                'remaining_minutes': 240,
                'tasks': [] # Task: {id, name, duration, status ('pending', 'in_progress', 'completed')}
            })
            current_hour = (current_hour + 4) % 24
        
        await asyncio.to_thread(schedule_ref.set, new_schedule)
        return new_schedule

def get_time_range_str(start_hour):
    """Helper to format slot time ranges."""
    end_hour = (start_hour + 4) % 24
    return f"{start_hour:02d}:00 - {end_hour:02d}:00"

async def task_notification_timer(user, task_name, duration_minutes):
    """The coroutine that waits and then DMs the user."""
    await asyncio.sleep(duration_minutes * 60)
    try:
        await user.send(f"🔔 **Time's up!** Your task **'{task_name}'** is due to end.\n\nDon't forget to mark it as complete with `/done` to log your reflection!")
    except discord.Forbidden:
        print(f"Failed to send DM to {user.name} (DMs probably disabled).")
    except Exception as e:
        print(f"Error in task_notification_timer: {e}")
    
    # Clean up timer from active list
    timer_key = f"{user.id}_{task_name}" # Note: This simple key might fail if tasks have same name
    if timer_key in active_timers:
        del active_timers[timer_key]


# --- Bot Modals (Pop-up Forms) ---

class SetupModal(discord.ui.Modal, title='Welcome! Let\'s get you set up.'):
    start_hour = discord.ui.TextInput(
        label='What hour do you usually wake up? (0-23)',
        placeholder='e.g., 7 for 7 AM',
        min_length=1,
        max_length=2
    )
    
    journal_channel = discord.ui.TextInput(
        label='Channel ID for your Journal',
        placeholder='Right-click a channel and "Copy Channel ID"',
        min_length=18,
        max_length=20
    )

    positive_habits = discord.ui.TextInput(
        label='Positive Habits (one per line)',
        style=discord.TextStyle.paragraph,
        placeholder='Meditate\nGo to the gym\nRead a book'
    )

    negative_habits = discord.ui.TextInput(
        label='Negative Habits (one per line)',
        style=discord.TextStyle.paragraph,
        placeholder='Smoke\nEat junk food\nSugary drinks'
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            hour = int(self.start_hour.value)
            if not (0 <= hour <= 23):
                raise ValueError("Hour out of range")
        except ValueError:
            await interaction.response.send_message("Invalid hour. Please use a number between 0 and 23.", ephemeral=True)
            return

        try:
            channel_id = int(self.journal_channel.value)
            channel = bot.get_channel(channel_id)
            if not channel:
                raise ValueError("Channel not found")
        except Exception:
            await interaction.response.send_message(f"Could not find channel with ID `{self.journal_channel.value}`. Make sure I have access to it!", ephemeral=True)
            return
        
        # Process habits
        pos_habits = [h.strip() for h in self.positive_habits.value.split('\n') if h.strip()]
        neg_habits = [h.strip() for h in self.negative_habits.value.split('\n') if h.strip()]
        
        # Save to Firestore
        config_data = {
            'start_hour': hour,
            'journal_channel_id': channel_id,
            'positive_habits': pos_habits,
            'negative_habits': neg_habits
        }
        
        config_ref = get_user_config_ref(interaction.user.id)
        await asyncio.to_thread(config_ref.set, config_data)
        
        await interaction.response.send_message(
            f"🎉 **Setup complete!**\n\n"
            f"Your day will be structured from **{hour:02d}:00**.\n"
            f"Your journal entries will be posted in {channel.mention}.\n"
            f"I'll track your {len(pos_habits)} positive and {len(neg_habits)} negative habits.\n\n"
            f"You can now use `/addtask` to start planning your day!",
            ephemeral=True
        )

class ReflectionModal(discord.ui.Modal, title='Task Reflection'):
    def __init__(self, task_id, schedule_ref):
        super().__init__()
        self.task_id = task_id
        self.schedule_ref = schedule_ref

    difficulties = discord.ui.TextInput(
        label='What difficulties were encountered?',
        style=discord.TextStyle.paragraph,
        placeholder='e.g., The concept was harder than I thought, I felt tired...',
        required=False
    )
    
    interruptions = discord.ui.TextInput(
        label='Were there any interruptions?',
        style=discord.TextStyle.paragraph,
        placeholder='e.g., Friends messaged me, I got a phone call, I went to get a snack...',
        required=False
    )
    
    feelings = discord.ui.TextInput(
        label='How did you feel during the task?',
        style=discord.TextStyle.paragraph,
        placeholder='e.g., Focused, distracted, motivated, bored...',
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        reflection_data = {
            'difficulties': self.difficulties.value,
            'interruptions': self.interruptions.value,
            'feelings': self.feelings.value,
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        
        # We need to find the task in the schedule and update it
        try:
            doc = await asyncio.to_thread(self.schedule_ref.get)
            if not doc.exists:
                await interaction.response.send_message("Error: Could not find schedule.", ephemeral=True)
                return

            schedule = doc.to_dict()
            task_found = False
            for slot in schedule['slots']:
                for task in slot['tasks']:
                    if task['id'] == self.task_id:
                        task['status'] = 'completed'
                        task['reflection'] = reflection_data
                        task_found = True
                        break
                if task_found:
                    break
            
            if task_found:
                # Save the entire schedule back
                await asyncio.to_thread(self.schedule_ref.set, schedule)
                await interaction.response.send_message(f"Reflection saved! Task marked as complete.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Error: Could not find the task to save reflection.", ephemeral=True)
                
        except Exception as e:
            print(f"Error saving reflection: {e}")
            await interaction.response.send_message(f"An error occurred while saving: {e}", ephemeral=True)


# --- Bot Views (Buttons) ---

class CheckInView(discord.ui.View):
    def __init__(self, user, config):
        super().__init__(timeout=300)  # 5 minute timeout
        self.user = user
        self.positive_habits = config.get('positive_habits', [])
        self.negative_habits = config.get('negative_habits', [])
        self.all_habits = [(h, 'pos') for h in self.positive_habits] + [(h, 'neg') for h in self.negative_habits]
        self.current_index = 0
        self.answers = {}
        self.message = None

    async def start(self, interaction: discord.Interaction):
        """Starts the check-in process by sending the first question."""
        if not self.all_habits:
            await interaction.response.send_message("You haven't set up any habits yet! Use `/setup` first.", ephemeral=True)
            return
        
        # Send the initial message ephemerally
        await interaction.response.send_message("Starting your daily check-in... (Check your DMs!)", ephemeral=True)
        
        # Send the actual interactive message to DMs
        try:
            self.message = await self.user.send(content=self.get_question_text(), view=self)
        except discord.Forbidden:
            await interaction.followup.send("I can't DM you! Please enable DMs from server members.", ephemeral=True)

    def get_question_text(self):
        """Gets the text for the current question."""
        habit, habit_type = self.all_habits[self.current_index]
        prefix = "Did you" if habit_type == 'pos' else "Did you avoid"
        if habit_type == 'pos':
            # Customize common positive habits
            if "gym" in habit.lower():
                prefix = "Did you go to the"
            elif "meditate" in habit.lower():
                prefix = "Did you"
            elif "protein" in habit.lower():
                prefix = "Did you take your"
        else:
            # Customize common negative habits
            if "smoke" in habit.lower():
                prefix = "Did you avoid"
            elif "sugary" in habit.lower():
                prefix = "Did you avoid"

        return f"**Question {self.current_index + 1} of {len(self.all_habits)}**\n\n{prefix} **{habit}** today?"

    async def next_question(self, interaction: discord.Interaction):
        """Moves to the next question or ends the check-in."""
        self.current_index += 1
        if self.current_index < len(self.all_habits):
            # Edit the message with the new question
            await interaction.response.edit_message(content=self.get_question_text(), view=self)
        else:
            # End of questions
            self.stop() # Stop the view, disable buttons
            await interaction.response.edit_message(content="✅ **Check-in complete!**\n\nAll habits recorded.", view=None)
            await self.prompt_for_journal(interaction)

    async def prompt_for_journal(self, interaction: discord.Interaction):
        """Saves habit data and asks for the journal entry."""
        # Save habit data to Firestore
        today_str = get_today_date_str()
        habits_ref = get_user_habits_ref(self.user.id, today_str)
        await asyncio.to_thread(habits_ref.set, self.answers)
        
        await self.user.send(
            "Great job!\n\n"
            "**How was your day overall?**\n"
            "Write your journal entry below. I'll wait for 10 minutes."
        )

        def check(m):
            # Check if the message is from the same user and in the same DM channel
            return m.author.id == self.user.id and m.channel.id == self.user.dm_channel.id

        try:
            # Wait for the user's journal entry
            message = await bot.wait_for('message', check=check, timeout=600.0) # 10 minute timeout
            journal_text = message.content
            await self.user.send("Journal entry received! Generating your daily summary...")
            await self.generate_and_post_summary(journal_text)

        except asyncio.TimeoutError:
            await self.user.send("Looks like you got busy. I'll skip the journal entry for today, but your habits are saved!")
            # Still generate a summary, but without the journal text
            await self.generate_and_post_summary(None)
        except Exception as e:
            await self.user.send(f"An error occurred while waiting for your journal: {e}")
            print(f"Error in prompt_for_journal: {e}")

    async def generate_and_post_summary(self, journal_text):
        """Generates the daily summary and posts it to the journal channel."""
        # 1. Get user config for journal channel
        config_ref = get_user_config_ref(self.user.id)
        config_doc = await asyncio.to_thread(config_ref.get)
        if not config_doc.exists:
            await self.user.send("I can't find your config! Please use `/setup` again.")
            return
        
        config = config_doc.to_dict()
        journal_channel_id = config.get('journal_channel_id')
        channel = bot.get_channel(journal_channel_id)
        if not channel:
            await self.user.send(f"I can't find your journal channel (ID: {journal_channel_id}). Maybe it was deleted?")
            return

        # 2. Analyze answers
        total_habits = len(self.all_habits)
        score = 0
        scoreboard = ""
        
        for (habit, habit_type), answered_yes in self.answers.items():
            if habit_type == 'pos' and answered_yes:
                score += 1
                scoreboard += f"✅ {habit}\n"
            elif habit_type == 'pos' and not answered_yes:
                scoreboard += f"❌ {habit}\n"
            elif habit_type == 'neg' and not answered_yes: # Not answering yes == avoiding
                score += 1
                scoreboard += f"✅ Avoided {habit}\n"
            elif habit_type == 'neg' and answered_yes:
                scoreboard += f"❌ Indulged in {habit}\n"

        percentage = (score / total_habits) * 100 if total_habits > 0 else 0

        # 3. Generate Title and Summary
        if percentage == 100:
            status_title = "The Pinnacle of Discipline"
            summary_text = f"{self.user.name} had a perfect day, demonstrating flawless discipline. They completed all {total_habits} goals, remaining steadfast and focused. An outstanding performance."
        elif percentage >= 80:
            status_title = "The Master Practitioner"
            summary_text = f"{self.user.name} showed exceptional focus, achieving {score}/{total_habits} of their goals. A few minor slips couldn't overshadow a day of strong commitment and progress."
        elif percentage >= 60:
            status_title = "The Steady Hand"
            summary_text = f"{self.user.name} had a solid day. With {score}/{total_habits} habits completed, they built positive momentum and successfully navigated most of the day's challenges."
        elif percentage >= 40:
            status_title = "A Day of Mixed Results"
            summary_text = f"{self.user.name}'s day was a mix of wins and challenges, hitting {score}/{total_habits} targets. This day provides valuable lessons on what to focus on tomorrow."
        elif percentage > 0:
            status_title = "The Uphill Battle"
            summary_text = f"{self.user.name} struggled with focus today, completing {score}/{total_habits} habits. While it was a tough day, every completed habit is a small victory to build on."
        else:
            status_title = "The Day of Reflection"
            summary_text = f"It was a challenging day for {self.user.name}, with {score}/{total_habits} habits met. Today is best used as a day of rest and reflection to come back stronger tomorrow."

        # 4. Create Embed
        embed = discord.Embed(
            title=f"Daily Journal: {get_today_date_str()}",
            description=f"**Status: {status_title}**\n\n*{summary_text}*",
            color=discord.Color.blue()
        )
        embed.set_author(name=self.user.name, icon_url=self.user.avatar.url if self.user.avatar else discord.Embed.Empty)
        
        if scoreboard:
            embed.add_field(name="Habit Scoreboard", value=scoreboard, inline=False)
        
        if journal_text:
            embed.add_field(name="Journal Entry", value=f"```{journal_text}```", inline=False)
        else:
            embed.add_field(name="Journal Entry", value="*No journal entry provided.*", inline=False)

        # 5. Post to channel
        try:
            await channel.send(embed=embed)
        except Exception as e:
            await self.user.send(f"I failed to post your summary to {channel.mention}. Do I have 'Send Messages' and 'Embed Links' permissions? Error: {e}")

    @discord.ui.button(label='Yes', style=discord.ButtonStyle.green)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_habit = self.all_habits[self.current_index]
        self.answers[current_habit] = True
        await self.next_question(interaction)

    @discord.ui.button(label='No', style=discord.ButtonStyle.red)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_habit = self.all_habits[self.current_index]
        self.answers[current_habit] = False
        await self.next_question(interaction)

    async def on_timeout(self):
        # Handle the case where the user doesn't respond
        if self.message:
            await self.message.edit(content="Your check-in timed out. Please use `/checkin` to try again.", view=None)


# --- Bot Events ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('Syncing slash commands...')
    try:
        # Sync commands to make them appear
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} commands.')
    except Exception as e:
        print(f'Error syncing commands: {e}')
    print('------')

# --- Bot Commands ---

@bot.tree.command(name="setup", description="Configure your schedule, habits, and journal.")
async def setup(interaction: discord.Interaction):
    """Initiates the setup modal."""
    await interaction.response.send_modal(SetupModal())

@bot.tree.command(name="schedule", description="View your 4-slot schedule for today.")
async def schedule(interaction: discord.Interaction):
    """Displays today's schedule in an embed."""
    config_ref = get_user_config_ref(interaction.user.id)
    config_doc = await asyncio.to_thread(config_ref.get)
    if not config_doc.exists:
        await interaction.response.send_message("You must run `/setup` first!", ephemeral=True)
        return
    
    config = config_doc.to_dict()
    start_hour = config.get('start_hour')
    
    await interaction.response.defer(ephemeral=True) # Defer while we fetch/create
    
    try:
        schedule_data = await get_or_create_schedule(interaction.user.id, start_hour)
        
        embed = discord.Embed(
            title=f"Today's Schedule ({schedule_data['date']})",
            color=discord.Color.purple()
        )
        embed.set_author(name=interaction.user.name, icon_url=interaction.user.avatar.url if interaction.user.avatar else discord.Embed.Empty)
        
        if not schedule_data.get('slots'):
             embed.description = "No slots found. Something is wrong with your schedule."
        else:
            for slot in schedule_data['slots']:
                time_range = get_time_range_str(slot['start_hour'])
                task_list_str = ""
                if not slot['tasks']:
                    task_list_str = "*Empty*"
                else:
                    for task in slot['tasks']:
                        status_emoji = "◻️" # pending
                        if task['status'] == 'in_progress':
                            status_emoji = "▶️"
                        elif task['status'] == 'completed':
                            status_emoji = "✅"
                        task_list_str += f"{status_emoji} {task['name']} ({task['duration']}m)\n"
                
                embed.add_field(
                    name=f"Slot {slot['slot_number']} ({time_range})",
                    value=task_list_str + f"\n*Remaining: {slot['remaining_minutes']}m*",
                    inline=False
                )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        print(f"Error in /schedule: {e}")
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


@bot.tree.command(name="addtask", description="Add a new task to your schedule.")
@app_commands.describe(name="The name of the task", duration="The duration of the task in minutes")
async def addtask(interaction: discord.Interaction, name: str, duration: int):
    """Adds a task to the next available slot."""
    config_ref = get_user_config_ref(interaction.user.id)
    config_doc = await asyncio.to_thread(config_ref.get)
    if not config_doc.exists:
        await interaction.response.send_message("You must run `/setup` first!", ephemeral=True)
        return
    
    config = config_doc.to_dict()
    start_hour = config.get('start_hour')
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        schedule_data = await get_or_create_schedule(interaction.user.id, start_hour)
        
        slot_found = None
        for slot in schedule_data['slots']:
            if slot['remaining_minutes'] >= duration:
                slot_found = slot
                break
        
        if slot_found:
            new_task = {
                'id': str(uuid.uuid4()), # Unique ID for every task
                'name': name,
                'duration': duration,
                'status': 'pending'
            }
            slot_found['tasks'].append(new_task)
            slot_found['remaining_minutes'] -= duration
            
            # Save the updated schedule
            schedule_ref = get_user_schedule_ref(interaction.user.id, schedule_data['date'])
            await asyncio.to_thread(schedule_ref.set, schedule_data)
            
            time_range = get_time_range_str(slot_found['start_hour'])
            await interaction.followup.send(
                f"✅ Task **'{name}'** ({duration}m) has been added to **Slot {slot_found['slot_number']} ({time_range})**.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ No available slot found that can fit **{duration}** minutes. Try adding a shorter task or completing existing ones.",
                ephemeral=True
            )
            
    except Exception as e:
        print(f"Error in /addtask: {e}")
        await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)


@bot.tree.command(name="starttask", description="Start a timer for one of your pending tasks.")
async def starttask(interaction: discord.Interaction):
    """Shows a dropdown of pending tasks to start."""
    config_ref = get_user_config_ref(interaction.user.id)
    config_doc = await asyncio.to_thread(config_ref.get)
    if not config_doc.exists:
        await interaction.response.send_message("You must run `/setup` first!", ephemeral=True)
        return

    config = config_doc.to_dict()
    start_hour = config.get('start_hour')
    
    await interaction.response.defer(ephemeral=True)
    
    schedule_data = await get_or_create_schedule(interaction.user.id, start_hour)
    
    pending_tasks = []
    for slot in schedule_data['slots']:
        for task in slot['tasks']:
            if task['status'] == 'pending':
                pending_tasks.append(task)
    
    if not pending_tasks:
        await interaction.followup.send("You have no pending tasks to start!", ephemeral=True)
        return

    # Create a select menu
    options = []
    for task in pending_tasks[:25]: # Max 25 options
        options.append(discord.SelectOption(label=f"{task['name']} ({task['duration']}m)", value=task['id']))

    select = discord.ui.Select(placeholder="Choose a task to start...", options=options)

    async def select_callback(select_interaction: discord.Interaction):
        """Callback for when a task is selected."""
        task_id = select_interaction.data['values'][0]
        
        # Find the task in the schedule again
        doc = await asyncio.to_thread(get_user_schedule_ref(interaction.user.id, get_today_date_str()).get)
        schedule = doc.to_dict()
        
        task_to_start = None
        task_found = False
        for slot in schedule['slots']:
            for task in slot['tasks']:
                if task['id'] == task_id:
                    task_to_start = task
                    task['status'] = 'in_progress' # Mark as in progress
                    task_found = True
                    break
            if task_found:
                break
        
        if not task_to_start:
            await select_interaction.response.send_message("Error: Task not found.", ephemeral=True)
            return

        # Save the "in_progress" status
        schedule_ref = get_user_schedule_ref(interaction.user.id, get_today_date_str())
        await asyncio.to_thread(schedule_ref.set, schedule)

        # Start the notification timer
        timer_key = f"{interaction.user.id}_{task_to_start['id']}"
        if timer_key in active_timers:
            active_timers[timer_key].cancel() # Cancel old timer if any
            
        timer_task = asyncio.create_task(
            task_notification_timer(interaction.user, task_to_start['name'], task_to_start['duration'])
        )
        active_timers[timer_key] = timer_task
        
        await select_interaction.response.send_message(
            f"▶️ Timer started for **'{task_to_start['name']}'** ({task_to_start['duration']}m). I'll DM you when it's over!",
            ephemeral=True
        )
        # Disable the view
        view.stop()
        await interaction.edit_original_response(view=view)


    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.followup.send("Which task would you like to start?", view=view, ephemeral=True)


@bot.tree.command(name="done", description="Mark a task as completed and write a reflection.")
async def done(interaction: discord.Interaction):
    """Shows a dropdown of 'in_progress' or 'pending' tasks to complete."""
    config_ref = get_user_config_ref(interaction.user.id)
    config_doc = await asyncio.to_thread(config_ref.get)
    if not config_doc.exists:
        await interaction.response.send_message("You must run `/setup` first!", ephemeral=True)
        return

    config = config_doc.to_dict()
    start_hour = config.get('start_hour')
    
    await interaction.response.defer(ephemeral=True)
    
    schedule_data = await get_or_create_schedule(interaction.user.id, start_hour)
    
    tasks_to_complete = []
    for slot in schedule_data['slots']:
        for task in slot['tasks']:
            if task['status'] in ['pending', 'in_progress']:
                tasks_to_complete.append(task)
    
    if not tasks_to_complete:
        await interaction.followup.send("You have no tasks to mark as complete!", ephemeral=True)
        return

    # Create a select menu
    options = []
    for task in tasks_to_complete[:25]: # Max 25 options
        options.append(discord.SelectOption(label=f"{task['name']} ({task['duration']}m)", value=task['id']))

    select = discord.ui.Select(placeholder="Choose a task to complete...", options=options)

    async def select_callback(select_interaction: discord.Interaction):
        """Callback for when a task is selected to complete."""
        task_id = select_interaction.data['values'][0]
        
        # Cancel any active timer for this task
        timer_key = f"{interaction.user.id}_{task_id}"
        if timer_key in active_timers:
            active_timers[timer_key].cancel()
            del active_timers[timer_key]
        
        schedule_ref = get_user_schedule_ref(interaction.user.id, get_today_date_str())
        
        # Send the reflection modal
        modal = ReflectionModal(task_id=task_id, schedule_ref=schedule_ref)
        await select_interaction.response.send_modal(modal)

        # Disable the view
        view.stop()
        await interaction.edit_original_response(view=view)


    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.followup.send("Which task did you complete?", view=view, ephemeral=True)


@bot.tree.command(name="checkin", description="Start your interactive daily check-in and journal.")
async def checkin(interaction: discord.Interaction):
    """Starts the daily check-in process in DMs."""
    config_ref = get_user_config_ref(interaction.user.id)
    config_doc = await asyncio.to_thread(config_ref.get)
    if not config_doc.exists:
        await interaction.response.send_message("You must run `/setup` first!", ephemeral=True)
        return
    
    config = config_doc.to_dict()
    
    # Create the view
    view = CheckInView(user=interaction.user, config=config)
    # Start the process. This will send its own ephemeral response
    # and then DM the user.
    await view.start(interaction)


# --- Run the Bot ---
if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("Bot token not found. Please set DISCORD_TOKEN in your .env file.")