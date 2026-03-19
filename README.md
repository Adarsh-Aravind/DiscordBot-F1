# Bit Beast Bot

Bit Beast Bot is a modular and efficient Discord bot built with Python and `discord.py`. Designed for seamless server management and user engagement, it features a Cog-based architecture that provides various administrative tools, automated moderation, content notifications, and entertainment modules.

## Features

- **Automated Moderation (Anti-Spam)**: Actively monitors messages to detect and mitigate spam, including excessive links, mentions, and formatting abuse. Enforces timeouts and deletions automatically.
- **YouTube Notifications**: Monitors specified YouTube channels and alerts your Discord server of new video uploads with rich embedded messages.
- **Formula 1 Integration**: Delivers real-time F1 driver and constructor standings, upcoming race schedules with track layouts, and historical race data.
- **Experience and Leveling System**: Tracks user engagement through an SQLite database, passively awarding XP and roles to active participants.
- **Remote Channel Messaging**: Empowers bot administrators to proxy messages to specific channels or reply to direct messages securely.

## Requirements

- Python 3.8 or higher
- `discord.py` and other required libraries (see `requirements.txt`)
- A valid Discord Bot Token

## Installation and Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Adarsh-Aravind/Discord-Bot.git
   cd Discord-Bot
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Create a `.env` file in the root directory and define the following variables:
   ```env
   DISCORD_TOKEN=your_bot_token_here
   ```

4. **Bot Ownership Configuration:**
   Update the `OWNER_ID` variable in `cogs/messaging.py` and `cogs/general.py` with your personal Discord User ID to permit administrative commands.

5. **Run the bot:**
   ```bash
   python main.py
   ```
   *Note: An SQLite database will be automatically generated upon initial boot to handle leveling and YouTube notification history.*

## Command Reference

The default command prefix is `#`.

### Administrator Commands
- `#reply <user_id> <message>`: Sends a direct message to a user.
- `#say <channel_id> <message>`: Relays a message to a specific channel.
- `#setpresence <type> <text>`: Updates the bot's rich presence status (e.g., playing, watching).
- `#levelreset [user]`: Resets XP and level data for a specific user, or truncates the database if left blank.

### Public Commands
- `#help`: Displays a list of available commands.
- `#status`: Shows current server statistics and health metrics.
- `#ping`: Evaluates the bot API response latency.
- `#rank`: Displays the user's localized XP and level progression.

**F1 Module Commands**
- `#f1`: Displays a snapshot of the current season standings and next race.
- `#f1next`: Provides schedule and track information for the upcoming race.
- `#f1last`: Retrieves results for the most recently completed race.
- `#f1c {circuit}`: Queries details and history for a specific circuit.
- `#f1con`: Outputs constructor standings.
- `#f1dri`: Outputs driver standings.

## Contributing

Contributions, issues, and feature requests are welcome. Feel free to check the issues page or fork the repository to implement new Cogs and functionality.
