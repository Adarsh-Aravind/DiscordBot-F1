# Discord Bot F1

A modular and efficient Discord bot built with Python and `discord.py`. Designed for seamless server management and user engagement, it features a modular architecture that provides various administrative tools, automated moderation, content notifications, and entertainment modules with a focus on Formula 1.

## Key Features

*   **Automated Moderation**: Actively monitors messages to detect and mitigate spam, including excessive links, mentions, and formatting abuse. Includes designated promotion channel rules (restricting posts to YouTube links only) and restricts `@everyone`/`@here` mentions to admin roles.
*   **YouTube Notifications**: Monitors specified YouTube channels and alerts your Discord server of new video uploads.
*   **Kick Live Notifications**: Polls specified Kick channels and alerts your Discord server when a streamer goes live.
*   **Creator Milestones**: Announces follower/subscriber milestones for tracked YouTube and Kick channels.
*   **Formula 1 Integration**: Delivers real-time F1 driver and constructor standings, upcoming race schedules with track layouts, and historical race data.
*   **Experience & Leveling**: Tracks user engagement through a local SQLite database, awarding XP and managing level progression.
*   **Warning & Timeout System**: Allows moderators to issue warnings and automatically applies timeouts upon reaching thresholds (e.g., 3rd or 5th warning).
*   **Remote Messaging**: Empowers bot administrators to proxy messages to specific channels or reply to direct messages securely.

## System Requirements

*   Python 3.8 or higher
*   Dependencies listed in `requirements.txt`
*   A valid Discord Bot Token

## Installation & Setup

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/Adarsh-Aravind/DiscordBot-F1.git
    cd DiscordBot-F1
    ```

2.  **Install Dependencies**
    It is recommended to use a virtual environment.
    ```bash
    pip install -r requirements.txt
    ```

3.  **Environment Configuration**
    Create a `.env` file in the root directory to store your sensitive credentials:
    ```env
    DISCORD_TOKEN=your_bot_token_here

    # YouTube upload alerts: Discord channel IDs to post in
    YT_CHANNEL_1=discord_channel_id
    YT_CHANNEL_2=discord_channel_id
    YT_CHANNEL_3=discord_channel_id

    # Kick live alerts: Discord channel ID to post "went live" notifications in
    KICK_CHANNEL_1=discord_channel_id
    ```
    *The Kick channel(s) to monitor are configured in the `CHANNELS` map in `cogs/kick.py` (default: `abitbeast`).*

4.  **Bot Ownership Configuration**
    Update the `OWNER_IDS` set in `main.py` with the Personal Discord User IDs of the bot administrators to permit administrative commands.

5.  **Running the Bot**
    ```bash
    python main.py
    ```
    *Note: An SQLite database will be automatically generated upon the initial run to handle leveling and YouTube notification history.*

## Command Reference

The default command prefix is `#`.

### Administrative & Moderation Commands
*   `#reply <user_id> <message>`: Sends a direct message to a user.
*   `#say <channel_id> <message>`: Relays a message to a specific channel.
*   `#setpresence <type> <text>`: Updates the bot's rich presence status.
*   `#levelreset [user]`: Resets XP and level data for a specific user, or truncates the database if left blank.
*   `#warn <member> <reason>`: Warns a member and applies auto-timeouts on specific thresholds.
*   `#warnings <member>`: Lists a member's warnings.
*   `#clearwarns <member>`: Clears all warnings for a member.
*   `#delwarn <id>`: Deletes a specific warning.

### General Commands
*   `#help`: Displays a list of available commands.
*   `#status`: Shows current server statistics and health metrics.
*   `#ping`: Evaluates the bot API response latency.
*   `#rank`: Displays the user's localized XP and level progression.

### Formula 1 Commands
*   `#f1`: Displays a snapshot of the current season standings and next race.
*   `#f1next`: Provides schedule and track information for the upcoming race.
*   `#f1last`: Retrieves results for the most recently completed race.
*   `#f1c {circuit}`: Queries details and history for a specific circuit.
*   `#f1con`: Outputs constructor standings.
*   `#f1dri`: Outputs driver standings.

## Architecture

This bot utilizes `discord.ext.commands.Cog` to compartmentalize functionality:
*   `general`: Basic bot operations and status checks.
*   `messaging`: Administrative proxy messaging.
*   `leveling`: Local database-driven user experience tracking.
*   `antispam`: Message monitoring and automated moderation.
*   `youtube`: Automated YouTube upload feeds.
*   `kick`: Kick live-stream "went live" notifications.
*   `milestones`: YouTube and Kick subscriber/follower milestone announcements.
*   `f1`: Real-time and historical Formula 1 data retrieval.
*   `warnings`: Moderator warning and automatic timeout system.

## License

This project is provided as-is without any warranties. Please adhere to Discord's Developer Terms of Service when operating your bot instances.
