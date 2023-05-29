
# Discord GameBot

This Discord bot is designed to provide various functionalities related to Steam games. It allows users to search for games, link their Discord account with their Steam account, update their list of owned games, mark games as installed or uninstalled, list installed games, list players who own a specific game, and send messages to players who own or have a specific game installed.

## Setup

### Prerequisites

- Python 3.8 or higher
- SQLite (for the database)

### Installation

1. Clone the repository:

   ```bash
   git clone <repository_url>
   ```
2.  Install the required packages:
    
    `pip install -r requirements.txt` 
    

### Configuration

1.  Create a new application on the [Discord Developer Portal](https://discord.com/developers/applications).
    
2.  Generate a bot token for your application and copy it.
    
3.  Rename the `.env.example` file to `.env` and update the following variables:
    
    `DISCORD_TOKEN=<your_discord_bot_token>`
    `STEAM_API_KEY=<your_steam_api_key>`
    
    Replace `<your_discord_bot_token>` with the Discord bot token you copied. Replace `<your_steam_api_key>` with your Steam API key. You can obtain it from the [Steam Developer Portal](https://steamcommunity.com/dev/apikey).
    

### Database

The bot uses an SQLite database to store user and game information. The default database file is `bot.db`. You can change the file name in the `.env` file by updating the `DATABASE_FILE` variable.

To initialize the database tables and indexes, run the following command:

`python bot.py --init-db` 
## Usage

### Discord Commands
The following commands are available:
-   `/searchgame <game_name>`: Search for a game on Steam.
-   `/invite`: Generate an invite link for the bot.
-   `/linksteam <steam_id>`: Link your Discord account to your Steam account.
-   `/updategames`: Update your list of owned games.
-   `/markinstalled <game>`: Mark a game as installed.
-   `/markuninstalled <game>`: Mark a game as uninstalled.
-   `/listinstalledgames`: List all games marked as installed by the user.
-   `/players <game>`: List all players in the server who own a certain game.
-   `/sendmessage <game> <message> [installed_only]`: Send a message to players who own or have a game installed.

Note: Replace `<game_name>`, `<steam_id>`, `<game>`, and `<message>` with the actual values.

### Running the Bot

To run the bot, execute the following command:

`python bot.py` 

The bot will log in to Discord and be ready to respond to commands.