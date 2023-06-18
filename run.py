import os
import sys
import sqlite3
from dotenv import load_dotenv
import discord
from discord import Embed
from discord.ext import commands
from discord_slash import SlashCommand, SlashContext
import requests
from bs4 import BeautifulSoup
import json
import logging
from decouple import config
from fuzzywuzzy import fuzz
from typing import Optional


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
STEAM_API_KEY = config('STEAM_API_KEY')
TOKEN = config('DISCORD_TOKEN')

# Get the database file name from environment variable or fallback to default name
DATABASE_FILE = os.getenv('DATABASE_FILE', 'bot.db')

# Check if the database file exists, create it if it doesn't
if not os.path.exists(DATABASE_FILE):
    conn = sqlite3.connect(DATABASE_FILE)
    conn.close()

# Create SQLite database connection
conn = sqlite3.connect(DATABASE_FILE)
cursor = conn.cursor()

# Create database tables and indexes
def create_database_tables():
    # Create Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            discord_id INTEGER PRIMARY KEY,
            steam_id INTEGER UNIQUE NOT NULL
        )
    ''')

    # Create Games table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Games (
            app_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
    ''')

    # Modify UserGames table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS UserGames (
            discord_id INTEGER,
            app_id INTEGER,
            interested BOOLEAN DEFAULT FALSE,
            PRIMARY KEY (discord_id, app_id),
            FOREIGN KEY (discord_id) REFERENCES Users (discord_id),
            FOREIGN KEY (app_id) REFERENCES Games (app_id)
        )
    ''')

    # Create indexes for improved query performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_discord_id ON Users (discord_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_app_id ON Games (app_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_usergames_discord_id ON UserGames (discord_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_usergames_app_id ON UserGames (app_id)')

    # Commit the transaction
    conn.commit()

# Call the function to create database tables and indexes
create_database_tables()

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
    # Check if the game exists in the database
    cursor.execute('''
        SELECT app_id FROM Games
        WHERE name LIKE ?
    ''', ('%' + game_name + '%',))
    result = cursor.fetchone()
    if result:
        app_id = result[0]
        return get_game_info(app_id)
    
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
        # Calculate the fuzzy match ratio for each search result
        matches = [(result, fuzz.partial_ratio(game_name, result.get('data-ds-appid'))) for result in search_results]
        # Sort the matches based on the match ratio in descending order
        matches.sort(key=lambda x: x[1], reverse=True)
        # Select the search result with the highest match ratio
        first_result = matches[0][0]
        game_url = first_result.get('href')
        game_app_id = game_url.split('/')[4]
        return get_game_info(game_app_id)
    else:
        logger.warning(f"No search results found for game: {game_name}")
        return None

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

def get_steam_profile(steam_id: str):
    base_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
    params = {
        'key': STEAM_API_KEY,
        'steamids': steam_id
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Error occurred while retrieving Steam profile: {e}")
        return None

    data = response.json()
    players = data.get('response', {}).get('players', [])
    if players:
        player_data = players[0]
        return {
            'name': player_data['personaname'],
            'steam_id': player_data['steamid'],
            'profile_image': player_data['avatarfull']
        }
    else:
        logger.warning(f"No profile data available for Steam ID: {steam_id}")
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
        embed.set_footer(text="\u24d8 Accuracy may vary, please use App ID to get exact results.")
        await ctx.send(embed=embed, hidden=True)
    else:
        await ctx.send("No game information found.", hidden=True)

def update_owned_games(steam_id: str, discord_id: int):
    base_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    params = {
        'key': STEAM_API_KEY,
        'steamid': steam_id,
        'include_appinfo': 1
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Error occurred while getting owned games: {e}")
        return False

    data = response.json()
    games = data.get('response', {}).get('games', [])
    
    for game in games:
        app_id = game['appid']
        game_name = game['name']

        # Insert game into Games table (ignore if already exists)
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO Games (app_id, name)
                VALUES (?, ?)
            ''', (app_id, game_name))
        except sqlite3.Error as e:
            logger.error(f"Error occurred while inserting game into Games table: {e}")
            continue

        # Insert game into UserGames table
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO UserGames (discord_id, app_id)
                VALUES (?, ?)
            ''', (discord_id, app_id))
        except sqlite3.Error as e:
            logger.error(f"Error occurred while inserting game into UserGames table: {e}")
            continue

    # Commit the transaction
    conn.commit()

    return True

@slash.slash(
    name="invite",
    description="Generates an invite link for the bot.",
    default_permission=False
)
async def invite(ctx):
    permissions = discord.Permissions()
    invite_link = discord.utils.oauth_url(ctx.bot.user.id, permissions=permissions)
    await ctx.author.send(f"Invite link for the bot: {invite_link}")
    await ctx.send("I've sent you a direct message with the invite link!", hidden=True)

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
        await ctx.send("Invalid Steam ID. Please enter a valid Steam ID64.", hidden=True)
        return
    
    # Validate Steam ID against third party
    if not validate_steam_id(steam_id):
        await ctx.send("Invalid Steam ID. Please enter a valid Steam ID.", hidden=True)
        return

    # Get the Steam profile information
    profile_info = get_steam_profile(steam_id)
    if not profile_info:
        await ctx.send("Failed to retrieve Steam profile information.", hidden=True)
        return

    steam_name = profile_info['name']
    steam_id = profile_info['steam_id']
    profile_image = profile_info['profile_image']

    try:
        # Insert the user's Discord ID and Steam ID into the Users table
        try:
            cursor.execute('''
                INSERT INTO Users (discord_id, steam_id)
                VALUES (?, ?)
            ''', (ctx.author.id, steam_id))
        except sqlite3.Error as e:
            logger.error(f"Error occurred while linking Steam ID to Discord ID: {e}")
            await ctx.send("Failed to link your Discord account to your Steam account.", hidden=True)
            return

        # Commit the transaction
        conn.commit()

        # Create an embed to display the Steam profile information
        embed = discord.Embed(title="Steam Profile Linked", description="Your Steam profile has been successfully linked!", color=discord.Color.green())
        embed.add_field(name="Steam Name", value=steam_name, inline=False)
        embed.add_field(name="Steam ID", value=steam_id, inline=False)
        embed.set_thumbnail(url=profile_image)

        await ctx.send(embed=embed, hidden=True)
        
        if update_owned_games(steam_id, ctx.author.id):
            await ctx.send("Successfully linked your Discord account to your Steam account and updated your game list.", hidden=True)
        else:
            await ctx.send("Successfully linked your Discord account to your Steam account, but failed to update your game list.", hidden=True)
    except sqlite3.IntegrityError:
        await ctx.send("This Steam ID is already linked to a different Discord account.", hidden=True)

@slash.slash(
    name="unlinksteam",
    description="Unlinks your currently linked Steam profile from your Discord account."
)
async def _unlinksteam(ctx: SlashContext):
    try:
        # Retrieve the linked Steam ID for the Discord user
        cursor.execute('''
            SELECT steam_id
            FROM Users
            WHERE discord_id = ?
        ''', (ctx.author.id,))
        result = cursor.fetchone()

        if result:
            steam_id = result[0]

            # Delete the user's information from the Users and UserGames tables
            try:
                cursor.execute('''
                    DELETE FROM Users
                    WHERE discord_id = ?
                ''', (ctx.author.id,))
                cursor.execute('''
                    DELETE FROM UserGames
                    WHERE discord_id = ?
                ''', (ctx.author.id,))
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Error occurred while unlinking Steam profile from Discord account: {e}")
                await ctx.send("Failed to unlink Steam profile. Please try again later.", hidden=True)
                return

            await ctx.send("Successfully unlinked Steam profile from your Discord account.", hidden=True)
        else:
            await ctx.send("Your Discord account is not linked to any Steam profile.", hidden=True)
    except Exception as e:
        logger.error(f"Error occurred while unlinking Steam profile: {e}")
        await ctx.send("Failed to unlink Steam profile. Please try again later.", hidden=True)


@slash.slash(
    name="updategames",
    description="Updates your list of owned games."
)
async def _updategames(ctx: SlashContext):
    # Get the user's Steam ID from the Users table
    cursor.execute('''
        SELECT steam_id
        FROM Users
        WHERE discord_id = ?
    ''', (ctx.author.id,))

    result = cursor.fetchone()
    if result:
        steam_id = result[0]

        if update_owned_games(steam_id, ctx.author.id):
            await ctx.send("Successfully updated your game list.", hidden=True)
        else:
            await ctx.send("Failed to update your game list.", hidden=True)
    else:
        await ctx.send("Your Discord account is not linked to any Steam account.", hidden=True)

@slash.slash(
    name="markinterest",
    description="Marks a game as interest.",
    options=[
        {
            "name": "game",
            "description": "The app ID or name of the game.",
            "type": 3,
            "required": True
        }
    ]
)
async def _markinterest(ctx: SlashContext, game: str):
    # Check if the user has linked their Steam account
    cursor.execute('''
        SELECT steam_id FROM Users
        WHERE discord_id = ?
    ''', (ctx.author.id,))
    result = cursor.fetchone()
    if result is None:
        await ctx.send("You must link your Steam account before marking games as interested.", hidden=True)
        return

    if game.isnumeric():
        app_id = game
        game_info = get_game_info(app_id)
        if game_info is None:
            await ctx.send("Invalid App ID.", hidden=True)
            return
        game_name = game_info['name']
    else:
        game_info = search_steam_game(game)
        if game_info:
            app_id = game_info['app_id']
            game_name = game_info['name']
        else:
            await ctx.send("Game not found.", hidden=True)
            return

    # Check if the game is owned by the user
    cursor.execute('''
        SELECT * FROM UserGames
        WHERE discord_id = ? AND app_id = ?
    ''', (ctx.author.id, app_id))

    result = cursor.fetchone()
    if result:
        # The game is owned by the user, mark it as interested
        try:
            cursor.execute('''
                UPDATE UserGames
                SET interested = TRUE
                WHERE discord_id = ? AND app_id = ?
            ''', (ctx.author.id, app_id))
        except sqlite3.Error as e:
            logger.error(f"Error occurred while marking game: {e}")
            await ctx.send("Failed to mark the game.", hidden=True)
            return

        conn.commit()
        await ctx.send(f"Successfully marked {game_name}.", hidden=True)
    else:
        await ctx.send(f"You don't own {game_name}.", hidden=True)


@slash.slash(
    name="removeinterest",
    description="Unmarks a game as interetsted.",
    options=[
        {
            "name": "game",
            "description": "Name or App ID of the game to be unmarked.",
            "type": 3,
            "required": True
        }
    ]
)
async def _removeinterest(ctx: SlashContext, game: str):
    # Check if the user has linked their Steam account
    cursor.execute('''
        SELECT steam_id FROM Users
        WHERE discord_id = ?
    ''', (ctx.author.id,))
    result = cursor.fetchone()
    if result is None:
        await ctx.send("You must link your Steam account before removing games from your interests.", hidden=True)
        return

    app_id = None
    game_name = None

    if game.isdigit():  # App ID was provided
        app_id = int(game)
        cursor.execute("SELECT name FROM Games WHERE app_id = ?", (app_id,))
        game_info = cursor.fetchone()
        if game_info:
            game_name = game_info[0]
    else:  # Game name was provided
        cursor.execute("SELECT app_id FROM Games WHERE name = ?", (game,))
        game_info = cursor.fetchone()
        if game_info:
            app_id = game_info[0]
            game_name = game

    if app_id is None:
        await ctx.send(f"No game found with the name or App ID '{game}'", hidden=True)
        return

    try:
        cursor.execute('''
            UPDATE UserGames 
            SET interested = 0
            WHERE discord_id = ? AND app_id = ?
        ''', (str(ctx.author.id), app_id))
        conn.commit()

        await ctx.send(f"Game '{game_name}' has been unmarked.", hidden=True)
    except sqlite3.Error as e:
        logger.error(f"Error occurred while unmarking game: {e}")
        await ctx.send("Failed to unmark the game.", hidden=True)


@slash.slash(
    name="listinterestedgames",
    description="Lists all games marked as interested by the user.",
)
async def _listinterestedgames(ctx: SlashContext):
    try:
        cursor.execute('''
            SELECT Games.name
            FROM UserGames 
            INNER JOIN Games ON UserGames.app_id = Games.app_id
            WHERE UserGames.discord_id = ? AND UserGames.interested = 1
        ''', (str(ctx.author.id),))

        results = cursor.fetchall()
        if not results:
            await ctx.send("You've not marked any games as interested.", hidden=True)
            return

        interested_games = [game_name for game_name, in results]

        # Formatting the list of games using Discord's Markdown
        interested_str = "**Interested Games**:\n" + "\n".join(f"• {game_name}" for game_name in interested_games)

        if len(interested_str) > 2000:
            for chunk in [interested_str[i:i + 2000] for i in range(0, len(interested_str), 2000)]:
                await ctx.send(chunk, hidden=True)
        else:
            await ctx.send(interested_str, hidden=True)
    except sqlite3.Error as e:
        logger.error(f"Error occurred while listing interested games: {e}")
        await ctx.send("Failed to list interested games.", hidden=True)

@slash.slash(
    name="players",
    description="Lists all players in the server who own a certain game.",
    options=[
        {
            "name": "game",
            "description": "Name or App ID of the game.",
            "type": 3,
            "required": True
        }
    ]
)
async def _players(ctx: SlashContext, game: str):
    app_id = None
    game_name = None

    if game.isdigit():  # App ID was provided
        app_id = int(game)
        cursor.execute("SELECT name FROM Games WHERE app_id = ?", (app_id,))
        game_info = cursor.fetchone()
        if game_info:
            game_name = game_info[0]
    else:  # Game name was provided
        cursor.execute("SELECT app_id FROM Games WHERE name = ?", (game,))
        game_info = cursor.fetchone()
        if game_info:
            app_id = game_info[0]
            game_name = game

    if app_id is None:
        await ctx.send(f"No game found with the name or App ID '{game}'", hidden=True)
        return

    try:
        # Fetch all users who own this game and whether they have marked interest
        cursor.execute('''
            SELECT discord_id, interested FROM UserGames 
            WHERE app_id = ?
        ''', (app_id,))
        game_interst = {row[0]: bool(row[1]) for row in cursor.fetchall()}

        if not game_interst:
            await ctx.send(f"No players in this server own the game '{game_name}'", hidden=True)
            return

        member_list = []
        for discord_id, intersted in game_interst.items():
            user = await bot.fetch_user(int(discord_id))
            name = f"{user.name} (Interested)" if intersted else user.name
            member_list.append(name)

        member_names = "\n".join(member_list)

        # Create embed
        embed = Embed(title=game_name, url=f"https://store.steampowered.com/app/{app_id}")
        embed.add_field(name="Players", value=member_names, inline=False)

        await ctx.send(embed=embed, hidden=True)
    except sqlite3.Error as e:
        logger.error(f"Error occurred while listing players: {e}")
        await ctx.send("Failed to list players.", hidden=True)

@slash.slash(
    name="sendmessage",
    description="Send a message to players who own or have marked interest in the game.",
    options=[
        {
            "name": "game",
            "description": "Name or App ID of the game.",
            "type": 3,
            "required": True
        },
        {
            "name": "message",
            "description": "Message to be sent.",
            "type": 3,
            "required": True
        },
        {
            "name": "interest_only",
            "description": "Send message only to players who marked interest in the game.",
            "type": 5,
            "required": False
        }
    ]
)
async def _sendmessage(ctx: SlashContext, game: str, message: str, interest_only: bool = False):
    app_id = None
    game_name = None

    if game.isdigit():  # App ID was provided
        app_id = int(game)
        cursor.execute("SELECT name FROM Games WHERE app_id = ?", (app_id,))
        game_info = cursor.fetchone()
        if game_info:
            game_name = game_info[0]
    else:  # Game name was provided
        cursor.execute("SELECT app_id FROM Games WHERE name = ?", (game,))
        game_info = cursor.fetchone()
        if game_info:
            app_id = game_info[0]
            game_name = game

    if app_id is None:
        await ctx.send(f"No game found with the name or App ID '{game}'", hidden=True)
        return

    try:
        # Fetch all users who own or have interest
        cursor.execute('''
            SELECT discord_id, interested FROM UserGames 
            WHERE app_id = ?
        ''', (app_id,))
        game_players = {str(row[0]): bool(row[1]) for row in cursor.fetchall()}

        if not game_players:
            await ctx.send(f"No players found for the game '{game_name}'", hidden=True)
            return

        player_list = []

        for discord_id, interested in game_players.items():
            try:
                member = await ctx.guild.fetch_member(int(discord_id))
                if member:
                    if interest_only and not interested:
                        continue
                    player_list.append(member.mention)
            except discord.NotFound:
                pass

        if not player_list:
            await ctx.send("No players found for the specified criteria.", hidden=True)
            return

        message_content = f"Message from {ctx.author.mention}: {message}"
        mention_list = " ".join(player_list)

        await ctx.send(f"Sending message to {len(player_list)} players...", hidden=True)
        await ctx.send(f"{mention_list}\n\n{message_content}")
    except sqlite3.Error as e:
        logger.error(f"Error occurred while sending message to players: {e}")
        await ctx.send("Failed to send message to players.", hidden=True)

@slash.slash(
    name="sendgamemessage",
    description="Send game information with a message and an optional event link.",
    options=[
        {
            "name": "game",
            "description": "Name or App ID of the game.",
            "type": 3,
            "required": True
        },
        {
            "name": "message",
            "description": "Message to be sent.",
            "type": 3,
            "required": True
        },
        {
            "name": "event_link",
            "description": "Optional Discord event link.",
            "type": 3,
            "required": False
        }
    ]
)
async def _sendgamemessage(ctx: SlashContext, game: str, message: str, event_link: Optional[str] = None):
    app_id = None
    game_name = None

    if game.isdigit():  # App ID was provided
        app_id = int(game)
        game_info = get_game_info(app_id)
        if game_info:
            game_name = game_info['name']
    else:  # Game name was provided
        game_info = search_steam_game(game)
        if game_info:
            app_id = game_info['app_id']
            game_name = game_info['name']

    if app_id is None:
        await ctx.send(f"No game found with the name or App ID '{game}'", hidden=True)
        return

    if game_info:
        embed = discord.Embed(title=game_info['name'], url=game_info['steam_url'], color=discord.Color.blue())
        embed.set_image(url=game_info['header_image'])
        embed.add_field(name="Steam Store Page", value=game_info['steam_url'], inline=False)
        if event_link:
            embed.add_field(name="Event Link", value=event_link, inline=False)
        await ctx.send(embed=embed, content=message, hidden=False)
    else:
        await ctx.send("No game information found.", hidden=True)

@slash.slash(
    name="sendmultigamemessage",
    description="Send game information with a message and an optional event link for multiple games.",
    options=[
        {
            "name": "games",
            "description": "List of games to send information for.",
            "type": 3,
            "required": True,
            "choices": []  # Placeholder for dynamic choices
        },
        {
            "name": "title",
            "description": "Message Title to be sent.",
            "type": 3,
            "required": True
        },
        {
            "name": "message",
            "description": "Message to be sent.",
            "type": 3,
            "required": False
        },
        {
            "name": "event_link",
            "description": "Optional Discord event link.",
            "type": 3,
            "required": False
        }
    ]
)
async def _sendmultigamemessage(ctx: SlashContext, games: str, title: str, message: str, event_link: Optional[str] = None):
    game_list = games.split(",")  # Split the input string into a list of games

    # Retrieve game choices from the database
    cursor.execute("SELECT app_id, name FROM Games")
    game_choices = [(name, str(app_id)) for app_id, name in cursor.fetchall()]

    options = [
        {
            "name": "game",
            "description": "Name or App ID of the game.",
            "type": 3,
            "required": True,
            "choices": game_choices
        },
        {
            "name": "title",
            "description": "Message Title to be sent.",
            "type": 3,
            "required": True
        },
        {
            "name": "message",
            "description": "Message to be sent.",
            "type": 3,
            "required": False  # Not required for individual game choices
        },
        {
            "name": "event_link",
            "description": "Optional Discord event link.",
            "type": 3,
            "required": False  # Not required for individual game choices
        }
    ]

    # Update the choices of the 'games' option dynamically
    for option in options:
        if option["name"] == "games":
            option["choices"] = game_choices
            break

    # Create an embed for the event link if provided
    event_embed = None
    if event_link:
        event_embed = discord.Embed(color=discord.Color.green())
        event_embed.title = title
        event_embed.description = message
        event_embed.add_field(name="Event Link", value=event_link, inline=False)
    else:
        event_embed = discord.Embed(color=discord.Color.green())
        event_embed.title = title
        event_embed.description = message

    game_embeds = []
    for i, game in enumerate(game_list):
        app_id = None
        game_name = None

        if game.isdigit():  # App ID was provided
            app_id = int(game)
            cursor.execute("SELECT name FROM Games WHERE app_id = ?", (app_id,))
            game_info = cursor.fetchone()
            if game_info:
                game_name = game_info[0]
        else:  # Game name was provided
            cursor.execute("SELECT app_id FROM Games WHERE name = ?", (game,))
            game_info = cursor.fetchone()
            if game_info:
                app_id = game_info[0]
                cursor.execute("SELECT name FROM Games WHERE app_id = ?", (app_id,))
                game_name = cursor.fetchone()[0]

        if app_id is None:
            await ctx.send(f"No game found with the name or App ID '{game}'", hidden=True)
            continue

        if game_name:
            game_info = get_game_info(app_id)
            if game_info:
                embed = discord.Embed(title=game_name, url=game_info['steam_url'], color=discord.Color.blue())
                embed.set_image(url=game_info['header_image'])
                embed.add_field(name="Steam Store Page", value=game_info['steam_url'], inline=False)

                game_embeds.append(embed)
            else:
                await ctx.send("No game information found.", hidden=True)
                continue

    # Send the event link embed if provided
    if event_embed:
        await ctx.send(embed=event_embed)

    # Send the game information embeds
    for embed in game_embeds:
        await ctx.send(embed=embed)

bot.run(TOKEN)
