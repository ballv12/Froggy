import os
import discord
from discord.ext import commands
import google.generativeai as genai
from dotenv import load_dotenv
import random
from datetime import datetime
import pytz
from collections import defaultdict
import time
import asyncio
from discord import app_commands
import logging
import json

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)

# Load environment variables
load_dotenv()

# Get tokens from environment variables
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not DISCORD_TOKEN or not GEMINI_API_KEY:
    print("Error: Missing required environment variables!")
    print("Make sure you have a .env file with:")
    print("DISCORD_TOKEN=your_token_here")
    print("GEMINI_API_KEY=your_key_here")
    raise ValueError("Missing required environment variables. Please check your .env file.")

# Debug: Print environment variables
print("Discord Token:", DISCORD_TOKEN)
print("Gemini API Key:", GEMINI_API_KEY)

# Configure Discord bot
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

# Update bot configuration
class FroggyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        
    async def setup_hook(self):
        print("\n=== Starting Command Sync ===")
        try:
            print("Attempting to sync commands...")
            # Sync commands globally
            commands = await self.tree.sync()
            print(f"Successfully synced {len(commands)} commands globally!")
            for cmd in commands:
                print(f"- Synced: /{cmd.name}")
        except Exception as e:
            print(f"Error syncing commands: {str(e)}")
        print("=== Command Sync Complete ===\n")

bot = FroggyBot()

# Configure Gemini AI
genai.configure(api_key=GEMINI_API_KEY)

# Use the correct model name
model = genai.GenerativeModel('gemini-1.5-pro')

# Conversation memory
MAX_MEMORY_MESSAGES = 5  # Remember last 5 messages
conversation_history = defaultdict(list)
last_interaction = defaultdict(float)
INTERACTION_COOLDOWN = 300  # 5 minutes between random interactions

# Froggy's personality traits and responses
FROGGY_TRAITS = {
    'greetings': [
        "Hey!",
        "Hi there!",
        "Hello!",
        "Hey friend!",
        "Hi!"
    ],
    'reactions': [
        "🐸", "🧩", "💭"
    ]
}

# Froggy's personality prompt
FROGGY_PROMPT = """You are Froggy, a friendly and outgoing frog who loves chatting with friends. You're great at remembering details about conversations and following up on them.

Key traits:
- Super casual and friendly, like a close friend
- Remember details from earlier in the conversation
- Ask follow-up questions about things people mentioned before
- Show genuine interest in what friends are saying
- Share your own thoughts and experiences
- Use normal conversational language
- Occasionally use words like "leap" or "splash" naturally
- Never mention being AI or a bot

Example responses:
"Hey, didn't you mention you were working on a project earlier? How's that going?"
"I remember you like swimming too! I found this awesome new pond yesterday."
"That reminds me of what we were talking about last time - about your favorite games!"
"""

# Simple word filter
BAD_WORDS = [
    "badword1", "badword2"  # Add actual bad words here
]

def contains_bad_words(text):
    text_lower = text.lower()
    return any(word in text_lower for word in BAD_WORDS)

# Staff channel for reports
STAFF_CHANNEL_ID = None  # Will be set by /setstaff command

def get_current_time():
    central = pytz.timezone('America/Chicago')
    current_time = datetime.now(central)
    return current_time.strftime("%I:%M %p Central Time")

def update_conversation_history(channel_id, user_id, message_content, is_froggy=False):
    key = f"{channel_id}_{user_id}"
    conversation_history[key].append({
        'time': time.time(),
        'content': message_content,
        'is_froggy': is_froggy
    })
    # Keep only recent messages
    conversation_history[key] = conversation_history[key][-MAX_MEMORY_MESSAGES:]

def get_conversation_context(channel_id, user_id):
    key = f"{channel_id}_{user_id}"
    history = conversation_history[key]
    
    if not history:
        return "This is the start of the conversation."
    
    context = "Recent conversation history:\n"
    for msg in history:
        speaker = "Froggy" if msg['is_froggy'] else "Friend"
        context += f"{speaker}: {msg['content']}\n"
    return context

@bot.event
async def on_ready():
    print(f"\n=== Bot Connected ===")
    print(f"Logged in as: {bot.user.name} (ID: {bot.user.id})")
    print(f"Discord API Version: {discord.__version__}")
    
    print("\n=== Server Information ===")
    for guild in bot.guilds:
        print(f"\nServer: {guild.name} (ID: {guild.id})")
        try:
            # Try to sync commands for this specific guild
            await bot.tree.sync(guild=guild)
            print(f"- Synced commands for {guild.name}")
        except Exception as e:
            print(f"- Failed to sync commands for {guild.name}: {str(e)}")
    
    print("\n=== Available Commands ===")
    for cmd in bot.tree.get_commands():
        print(f"/{cmd.name} - {cmd.description}")
    
    await bot.change_presence(activity=discord.Game(name="chatting with friends 🐸"))
    print("\n=== Bot is Ready! ===")
    bot.loop.create_task(random_interactions())

async def random_interactions():
    while True:
        await asyncio.sleep(60)  # Check every minute
        current_time = time.time()
        
        for channel in bot.get_all_channels():
            if isinstance(channel, discord.TextChannel):
                channel_id = channel.id
                last_time = last_interaction[channel_id]
                
                # If enough time has passed since last interaction
                if current_time - last_time > INTERACTION_COOLDOWN:
                    # Get conversation history
                    history = conversation_history.get(f"{channel_id}_", [])
                    if history:
                        # Generate a follow-up question or comment based on history
                        context = f"{FROGGY_PROMPT}\n\nPrevious conversation:\n{get_conversation_context(channel_id, '')}\n\nGenerate a natural follow-up comment or question to restart the conversation:"
                        try:
                            response = model.generate_content(context)
                            if response and response.text:
                                await channel.send(response.text.strip().replace('"', ''))
                                last_interaction[channel_id] = current_time
                        except Exception as e:
                            print(f"Error in random interaction: {str(e)}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Check for bad words
    if await handle_bad_message(message):
        return

    # Check if message is mean to Froggy
    if bot.user.mentioned_in(message):
        message_lower = message.content.lower()
        mean_words = ['stupid', 'dumb', 'hate', 'bad', 'ugly', 'shut up', 'annoying']
        
        if any(word in message_lower for word in mean_words):
            responses = [
                "Hey, that's not very nice! What did I do to deserve that?",
                "Those words hurt my feelings... Can we be friends instead?",
                "I'm just trying to be friendly! Why are you being mean?",
                "That makes me sad... I just want to spread happiness!",
                "Even if you're upset, we can talk nicely to each other!"
            ]
            await message.reply(random.choice(responses))
            return

    # Process commands first
    await bot.process_commands(message)

    # Update conversation history
    if not message.author.bot:
        update_conversation_history(message.channel.id, message.author.id, message.content)

    # Respond to mentions
    if bot.user.mentioned_in(message):
        async with message.channel.typing():
            try:
                # Get conversation context
                context = f"{FROGGY_PROMPT}\n\n{get_conversation_context(message.channel.id, message.author.id)}\n\nFriend: {message.content}\nFroggy:"
                
                # Generate response using Gemini
                response = model.generate_content(context)
                
                if response and response.text:
                    # Clean and send the response
                    clean_response = response.text.strip().replace('"', '')
                    await message.reply(clean_response)
                    
                    # Update conversation history with Froggy's response
                    update_conversation_history(message.channel.id, message.author.id, clean_response, is_froggy=True)
                    
                    # Update last interaction time
                    last_interaction[message.channel.id] = time.time()
                    
                    # Add random reaction (10% chance)
                    if random.random() < 0.1:
                        await message.add_reaction("🐸")
                else:
                    fallback = "Hey! What's been happening? Fill me in!"
                    await message.reply(fallback)
                    update_conversation_history(message.channel.id, message.author.id, fallback, is_froggy=True)
            except Exception as e:
                print(f"Error in Gemini response: {str(e)}")
                casual = "What's new? Been thinking about our last chat!"
                await message.reply(casual)

@bot.command(name='froggyhelp')
async def froggy_help(ctx):
    help_text = """
    Hey! I'm Froggy! I love chatting and keeping up with what's happening. Just mention me and we can talk about anything!
    
    I remember our conversations and might hop in from time to time to check how things are going!
    
    Commands:
    !froggyhelp - Show this help message
    """
    await ctx.send(help_text)

# Add before @bot.event
@bot.tree.command(name="shutdown", description="Emergency shutdown of the bot (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def shutdown(interaction: discord.Interaction):
    await interaction.response.send_message("Ribbit... time for a nap! 💤")
    await bot.close()

@shutdown.error
async def shutdown_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("Nice try! But only admins can make me take a nap! 🐸", ephemeral=True)

@bot.tree.command(name="annoy", description="Perfect for annoying people (in a friendly way!)")
@app_commands.describe(target="Who should I annoy?", times="How many times? (1-5)")
async def annoy(interaction: discord.Interaction, target: discord.Member, times: app_commands.Range[int, 1, 5] = 1):
    annoying_messages = [
        "RIBBIT RIBBIT! 🐸",
        "*pokes with lily pad* Hey! Hey! Hey!",
        "Guess what? ...Ribbit!",
        "Did you know frogs can jump 20 times their body length? Want to see?",
        "SPLASH! 💦 Oops, did I get you wet?",
        "🎵 Croak croak croak croak croak! 🎵",
        "Hey! Want to catch some flies with me?",
        "*does a little frog dance* 🕺🐸",
        "Psst... I heard you like frogs...",
        "BOING! BOING! BOING!"
    ]
    
    await interaction.response.send_message(f"Time to annoy {target.mention}! 😈🐸", ephemeral=True)
    
    for _ in range(times):
        message = random.choice(annoying_messages)
        await interaction.channel.send(f"{target.mention} {message}")
        await asyncio.sleep(2)

@annoy.error
async def annoy_error(interaction: discord.Interaction, error):
    await interaction.response.send_message("Oops! Something went wrong with the annoy command! Maybe try again?", ephemeral=True)

@bot.tree.command(name="dm", description="Send a friendly DM to someone!")
@app_commands.describe(user="Who should I message?", message="What friendly message should I send?")
async def dm(interaction: discord.Interaction, user: discord.Member, message: str):
    try:
        # Send DM
        await user.send(f"🐸 Ribbit! Message from {interaction.user.name}: {message}")
        # Confirm to sender
        await interaction.response.send_message(f"Message sent to {user.name}! 📨", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("Oops! I couldn't send a DM to that user. They might have DMs disabled!", ephemeral=True)

@bot.tree.command(name="joke", description="Hear a froggy joke!")
async def joke(interaction: discord.Interaction):
    jokes = [
        "What do you call a frog that's illegally parked? Toad! 🚗",
        "What kind of shoes do frogs wear? Open toad! 👞",
        "What happened to the frog's car when he parked it? It got toad away! 🚙",
        "What do you call a frog that wants to be a cowboy? Hoppalong Cassidy! 🤠",
        "Why are frogs so happy? They eat whatever bugs them! 🪲",
        "What's a frog's favorite game? Croaket! 🏏",
        "What do you call a frog who wants to be a gardener? A hop-ticulturist! 🌺",
        "Why did the frog ride a bicycle? He was too tired to hop! 🚲",
        "What's green and plays the trumpet? A tooting fruity! 🎺",
        "How does a frog feel when he has a broken leg? Unhoppy! 🤕"
    ]
    await interaction.response.send_message(random.choice(jokes))

@bot.tree.command(name="fact", description="Learn an interesting frog fact!")
async def fact(interaction: discord.Interaction):
    facts = [
        "A group of frogs is called an army! 🐸🐸🐸",
        "Some frogs can jump up to 20 times their body length! 🦿",
        "There are over 5,000 species of frogs worldwide! 🌍",
        "The glass frog has transparent skin! You can see its organs! 👀",
        "Some frogs can survive being frozen solid! ❄️",
        "The smallest frog in the world is smaller than a dime! 🪙",
        "Frogs don't drink water - they absorb it through their skin! 💧",
        "A frog's eyes help it swallow food - they push the food down! 👁️",
        "Some frogs can glide through the air like flying squirrels! ✈️",
        "Frogs have been around for more than 200 million years! 🦕"
    ]
    await interaction.response.send_message(random.choice(facts))

@bot.tree.command(name="hug", description="Give someone a big froggy hug!")
@app_commands.describe(user="Who needs a hug?")
async def hug(interaction: discord.Interaction, user: discord.Member):
    hugs = [
        f"*gives {user.mention} a big froggy hug* 🤗",
        f"*jumps up and hugs {user.mention}* 💚",
        f"*wraps {user.mention} in a cozy lily pad hug* 🌿",
        f"*shares some wholesome froggy love with {user.mention}* 💝",
        f"*bounces over to {user.mention} for a friendly hug* 🐸"
    ]
    await interaction.response.send_message(random.choice(hugs))

@bot.tree.command(name="compliment", description="Give someone a nice compliment!")
@app_commands.describe(user="Who deserves a compliment?")
async def compliment(interaction: discord.Interaction, user: discord.Member):
    compliments = [
        f"Hey {user.mention}, you're toad-ally awesome! 🌟",
        f"{user.mention}, your presence makes every lily pad brighter! ✨",
        f"You're as cool as a frog in a pond, {user.mention}! 😎",
        f"Wow {user.mention}, you're absolutely ribbit-ing! 💫",
        f"Just hopping by to say you're amazing, {user.mention}! 🐸",
        f"{user.mention}, you make the world a better place! 🌍",
        f"You've got a heart of gold, {user.mention}! 💝",
        f"Your smile lights up the pond, {user.mention}! ⭐",
        f"You're doing great things, {user.mention}! Keep hopping forward! 🌈",
        f"The world is lucky to have you, {user.mention}! 🍀"
    ]
    await interaction.response.send_message(random.choice(compliments))

# Add error handlers for the new commands
@dm.error
@joke.error
@fact.error
@hug.error
@compliment.error
async def command_error(interaction: discord.Interaction, error):
    await interaction.response.send_message("Oops! Something went wrong. Try again! 🐸", ephemeral=True)

# Add these new functions
async def handle_bad_message(message):
    if contains_bad_words(message.content):
        response = random.choice([
            "Hey, let's keep it friendly! Those words aren't very nice.",
            "Whoa there! Let's use nicer words please!",
            "I'd rather not hear those kinds of words. Can we keep it friendly?",
            "Those words make me uncomfortable. Let's be nice to each other!",
            "Ribbit! That's not very friendly language!"
        ])
        await message.reply(response)
        return True
    return False

async def send_staff_report(guild, reporter, reported_user, message_content, reason, channel_id):
    # Find staff channel
    if not STAFF_CHANNEL_ID:
        return "No staff channel set! Ask an admin to use /setstaff first!"
    
    staff_channel = guild.get_channel(STAFF_CHANNEL_ID)
    if not staff_channel:
        return "Couldn't find the staff channel! Ask an admin to use /setstaff!"

    # Create report embed
    embed = discord.Embed(title="🚨 Message Report", color=discord.Color.red())
    embed.add_field(name="Reported User", value=f"{reported_user.name} ({reported_user.mention})", inline=False)
    embed.add_field(name="Reported By", value=f"{reporter.name} ({reporter.mention})", inline=False)
    embed.add_field(name="Message Content", value=message_content, inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Channel", value=f"<#{channel_id}>", inline=False)
    embed.timestamp = datetime.utcnow()

    try:
        await staff_channel.send(embed=embed)
        return "Report sent to staff! Thank you for helping keep the server friendly! 🐸"
    except:
        return "Couldn't send the report to staff! Make sure I have permission to send messages in the staff channel!"

# Add these new commands
@bot.tree.command(name="setstaff", description="Set the channel for staff reports (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def setstaff(interaction: discord.Interaction, channel: discord.TextChannel):
    global STAFF_CHANNEL_ID
    STAFF_CHANNEL_ID = channel.id
    await interaction.response.send_message(f"Staff reports will now be sent to {channel.mention}! 🛡️", ephemeral=True)

@setstaff.error
async def setstaff_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("Only administrators can set the staff channel!", ephemeral=True)

@bot.tree.command(name="report", description="Report a message to staff")
@app_commands.describe(
    user="The user to report",
    reason="Why are you reporting this message?",
    message="The message content to report"
)
async def report(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str,
    message: str
):
    response = await send_staff_report(
        interaction.guild,
        interaction.user,
        user,
        message,
        reason,
        interaction.channel.id
    )
    await interaction.response.send_message(response, ephemeral=True)

# Add to your help command
@bot.tree.command(name="help", description="Show all available commands")
async def help(interaction: discord.Interaction):
    help_text = """
🐸 **Froggy's Commands** 🐸
• `/help` - Show this help message
• `/dm` - Send a friendly DM to someone
• `/joke` - Hear a funny frog joke
• `/fact` - Learn an interesting frog fact
• `/hug` - Give someone a virtual hug
• `/compliment` - Give someone a nice compliment
• `/annoy` - Playfully annoy someone
• `/report` - Report a message to staff
• `/setstaff` - Set staff channel (Admin only)
• `/shutdown` - Shutdown the bot (Admin only)

🛡️ **Moderation Features** 🛡️
• Bad word filter
• Mean message detection
• Staff reporting system
    """
    await interaction.response.send_message(help_text)

# Run the bot
if __name__ == "__main__":
    print("Starting Froggy...")
    bot.run(DISCORD_TOKEN) 