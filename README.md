# Discord Bot F1

A modular and efficient Discord bot built with Python and `discord.py`. Designed for seamless server management and user engagement, it features a modular architecture that provides various administrative tools, automated moderation, content notifications, and entertainment modules with a focus on Formula 1.

## Key Features

*   **Automated Moderation**: Detects message flooding and copy-paste repetition, invite links, mass mentions and emoji spam, with automatic timeouts. Enforces promotion-channel rules (YouTube links only) and restricts `@everyone`/`@here` to admins. Staff (administrators, or anyone with Manage Messages / Timeout Members) are exempt from every filter.
*   **YouTube Notifications**: Monitors specified YouTube channels and alerts your Discord server of new video uploads.
*   **Kick Live Notifications**: Polls specified Kick channels and alerts your Discord server when a streamer goes live.
*   **Creator Milestones**: Announces follower/subscriber milestones for tracked YouTube and Kick channels.
*   **Formula 1 Integration**: Delivers real-time F1 driver and constructor standings, upcoming race schedules with track layouts, and historical race data.
*   **Experience & Leveling**: Tracks engagement in a local SQLite database, awarding XP on a 60-second per-user cooldown (so quality chat is rewarded, not raw message count) with automatic level-reward roles.
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
    Copy the provided template and fill in your token:
    ```bash
    cp .env.example .env
    ```
    `.env.example` documents every setting. The only value you must supply is
    `DISCORD_TOKEN`; the channel IDs are already filled in for this server.

    **Tracked YouTube channels** — each variable is the *Discord* channel that
    creator's uploads are announced in. The YouTube channel IDs live in the
    `CHANNELS` map in `cogs/youtube.py`:

    | Variable | YouTube channel | YouTube ID |
    |---|---|---|
    | `YT_ABITBEAST` | A Bit-Beast | `UCWOMTp0BLi41FTn6ouh_mdg` |
    | `YT_LETSBEAST` | Let's Beast | `UCCYq8CHiJR3Y8IEME0SgNUQ` |
    | `YT_BYTEBEAST` | ByteBeast | `UCrFnDVz-JgIUdyizwd6YX9g` |
    | `YT_REDSHIF8` | Redshif8 | `UCKK4jwSOaKBSTqQjNRbndng` |

    ByteBeast and A Bit-Beast intentionally announce to the same Discord channel.
    A channel with its variable unset (or `0`) is simply skipped.

    *The Kick channel(s) to monitor are configured in the `CHANNELS` map in `cogs/kick.py` (default: `abitbeast`).*

    > **Note:** Kick is only polled between `KICK_ACTIVE_START` and `KICK_ACTIVE_END`
    > in `STREAM_TIMEZONE`. Streams starting outside that window are not announced —
    > widen the range if the schedule changes.

    > **Note:** The first time the bot sees a newly added YouTube channel it
    > records that channel's existing videos silently, so adding a creator never
    > floods the server with alerts for old uploads.

4.  **Bot Ownership Configuration**
    Update the `OWNER_IDS` set in `main.py` with the Personal Discord User IDs of the bot administrators to permit administrative commands.

5.  **Enable Privileged Intents**
    In the [Discord Developer Portal](https://discord.com/developers/applications) → your app → *Bot*,
    enable both **Message Content Intent** and **Server Members Intent**. The bot
    will fail to log in without them.

6.  **Running the Bot**
    ```bash
    python main.py
    ```
    *Note: An SQLite database will be automatically generated upon the initial run to handle leveling and YouTube notification history.*

7.  **Register Slash Commands**
    Run `#sync` once in the server as a bot owner so the `/` commands appear.

## Command Reference

The default command prefix is `#`.

### Administrative & Moderation Commands
*   `#reply <user_id> <message>`: Sends a direct message to a user.
*   `#say <channel_id> <message>`: Relays a message to a specific channel.
*   `#setpresence <type> <text>`: Updates the bot's rich presence status.
*   `#levelreset <@user|all>`: Resets XP for one member, or `all` to wipe everyone.
*   `#sync`: Registers slash commands with Discord (run once after deploying).
*   `#warn <member> <reason>`: Warns a member and applies auto-timeouts on specific thresholds.
*   `#warnings <member>`: Lists a member's warnings.
*   `#clearwarns <member>`: Clears all warnings for a member.
*   `#delwarn <id>`: Deletes a specific warning.

### General Commands
*   `#help`: Displays a list of available commands.
*   `#status`: Shows current server statistics and health metrics.
*   `#ping`: Evaluates the bot API response latency.
*   `#rank [@user]`: Displays XP, level and leaderboard position.
*   `#leaderboard` (`#top`): Top 10 members by XP.

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
