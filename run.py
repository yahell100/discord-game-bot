import os
import sys
import sqlite3
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord_slash import SlashCommand, SlashContext
import requests
from bs4 import BeautifulSoup
import json
import logging

# Configure logger
logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)

# Create a console handler and set its formatter
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))

# Create a file handler and set its formatter
file_handler = logging.FileHandler(filename='bot.log', encoding='utf-8', mode='w')
file_handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))

# Add both handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Load environment variables from .env file
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Get the database file name from environment variable or fallback to default name
DATABASE_FILE = os.getenv('DATABASE_FILE', 'bot.db')

# Get your Steam API key from the environment variables
STEAM_API_KEY = os.getenv('STEAM_API_KEY')

# Check if the database file exists, create it if it doesn't
if not os.path.exists(DATABASE_FILE):
    conn = sqlite3.connect(DATABASE_FILE)
    conn.close()

# Create SQLite database connection
conn = sqlite3.connect(DATABASE_FILE)
cursor = conn.cursor()

# Create Users table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS Users (
        discord_id INTEGER PRIMARY KEY,
        steam_id INTEGER UNIQUE NOT NULL
    )
''')

# Create UserGames table
cursor.execute('''
    CREATE TABLE IF NOT EXISTS UserGames (
        discord_id INTEGER,
        app_id INTEGER,
        PRIMARY KEY (discord_id, app_id),
        FOREIGN KEY (discord_id) REFERENCES Users (discord_id)
    )
''')

# Commit the transaction
conn.commit()

# Create bot and slash command instances
bot = commands.Bot(command_prefix='/', intents=discord.Intents.default())
slash = SlashCommand(bot, sync_commands=True)

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name}')

    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='all the games'))

def get_game_info(app_id):
    base_url = f"http://store.steampowered.com/api/appdetails?appids={app_id}"
    try:
        response = requests.get(base_url)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Error occurred while getting game info: {e}")
        return None

    data = response.json()
    if str(app_id) in data and 'data' in data[str(app_id)]:
        game_data = data[str(app_id)]['data']
        return {
            'name': game_data['name'],
            'header_image': game_data['header_image'],
            'steam_url': f"https://store.steampowered.com/app/{app_id}/",
            'app_id': app_id
        }
    else:
        logger.warning(f"Invalid app ID or no data available for app ID: {app_id}")
        return None

def search_steam_game(game_name):
    base_url = "https://store.steampowered.com/search/"
    params = {'term': game_name}
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Error occurred while searching for game: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    search_results = soup.find_all('a', {'class': 'search_result_row'})
    if search_results:
        first_result = search_results[0]
        game_url = first_result.get('href')
        game_app_id = game_url.split('/')[4]
        return get_game_info(game_app_id)
    else:
        logger.warning(f"No search results found for game: {game_name}")
        return None

@slash.slash(name="searchgame", description="Search a game on Steam", options=[{
    "name": "game_name",
    "description": "Name of the game to search",
    "type": 3,
    "required": True
}])
async def _searchgame(ctx: SlashContext, game_name: str):
    game_info = search_steam_game(game_name)
    if game_info:
        embed = discord.Embed(title=game_info['name'], url=game_info['steam_url'], color=discord.Color.blue())
        embed.set_image(url=game_info['header_image'])
        embed.add_field(name="App ID", value=game_info['app_id'], inline=False)
        embed.add_field(name="Steam Store Page", value=game_info['steam_url'], inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("No game information found.")

@slash.slash(
    name="invite",
    description="Generates an invite link for the bot.",
    default_permission=False
)
async def invite(ctx):
    permissions = discord.Permissions()
    invite_link = discord.utils.oauth_url(ctx.bot.user.id, permissions=permissions)
    await ctx.author.send(f"Invite link for the bot: {invite_link}")
    await ctx.send("I've sent you a direct message with the invite link!")

def validate_steam_id(steam_id: str) -> bool:
    base_url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
    params = {
        'key': STEAM_API_KEY,
        'steamids': steam_id
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Error occurred while validating Steam ID: {e}")
        return False

    data = response.json()
    players = data.get('response', {}).get('players', [])
    if players:
        return True
    else:
        return False

@slash.slash(
    name="linksteam",
    description="Links your Discord account to your Steam account.",
    options=[
        {
            "name": "steam_id",
            "description": "Your Steam ID in Steam ID 64 format.",
            "type": 3,
            "required": True
        }
    ]
)
async def _linksteam(ctx: SlashContext, steam_id: str):
    # Check if the Steam ID is numeric and starts with '7656119'
    if not steam_id.isnumeric() or not steam_id.startswith('7656119'):
        await ctx.send("Invalid Steam ID. Please enter a valid Steam ID64.")
        return
    
    # Validate Steam ID against third party
    if not validate_steam_id(steam_id):
        await ctx.send("Invalid Steam ID. Please enter a valid Steam ID.")
        return

    try:
        # Insert the user's Discord ID and Steam ID into the Users table
        cursor.execute('''
            INSERT INTO Users (discord_id, steam_id)
            VALUES (?, ?)
        ''', (ctx.author.id, steam_id))

        # Commit the transaction
        conn.commit()

        await ctx.send("Successfully linked your Discord account to your Steam account.")
    except sqlite3.IntegrityError:
        await ctx.send("This Steam ID is already linked to a different Discord account.")

bot.run(TOKEN)
