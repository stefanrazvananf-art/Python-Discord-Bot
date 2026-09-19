import asyncio
import datetime
import random
import discord
from discord import app_commands
from discord.ext import commands

# --- BOT SETUP ---
# Specify your Discord Guild ID here for instant command syncing during testing.
# Set GUILD_ID = None when deploying globally (global command registration takes up to an hour).
GUILD_ID = None  # Replace with integer guild ID (e.g. 123456789012345678) if testing locally

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# --- TICKET SYSTEM VIEWS ---

class TicketControlView(discord.ui.View):
    """View attached to the ticket control panel inside an open ticket channel."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="close_ticket_button",
        emoji="🔒",
    )
    async def close_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "Closing ticket in 5 seconds...", ephemeral=False
        )
        await asyncio.sleep(5)
        await interaction.channel.delete(reason="Ticket closed by user/staff.")


class CreateTicketView(discord.ui.View):
    """View attached to the initial embed prompt created by /ticket."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Create Ticket",
        style=discord.ButtonStyle.primary,
        custom_id="create_ticket_button",
        emoji="📩",
    )
    async def create_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        guild = interaction.guild
        user = interaction.user

        # Prevent duplicate tickets
        existing_channel = discord.utils.get(
            guild.text_channels, name=f"ticket-{user.name.lower()}"
        )
        if existing_channel:
            return await interaction.response.send_message(
                f"You already have an open ticket: {existing_channel.mention}",
                ephemeral=True,
            )

        # Set permissions for the ticket channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, attach_files=True
            ),
            guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True
            ),
        }

        # Create private text channel
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{user.name}",
            overwrites=overwrites,
            reason=f"Ticket created by {user.name}",
        )

        # Send greeting in the new ticket channel
        embed = discord.Embed(
            title=f"Welcome to your ticket, {user.name}!",
            description="Please describe your issue or question in detail. A staff member will be with you shortly.",
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Click the button below when you are ready to close this ticket.")

        await ticket_channel.send(
            content=f"{user.mention}, your ticket has been created!",
            embed=embed,
            view=TicketControlView(),
        )

        await interaction.response.send_message(
            f"Your ticket has been opened in {ticket_channel.mention}!", ephemeral=True
        )


# --- GIVEAWAY SYSTEM VIEW ---

class GiveawayView(discord.ui.View):
    """View for managing giveaway entries."""

    def __init__(self):
        super().__init__(timeout=None)
        self.entries = set()

    @discord.ui.button(
        label="Enter Giveaway",
        style=discord.ButtonStyle.success,
        custom_id="giveaway_entry_button",
        emoji="🎉",
    )
    async def enter_giveaway(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user_id = interaction.user.id
        if user_id in self.entries:
            self.entries.remove(user_id)
            await interaction.response.send_message(
                "You left the giveaway.", ephemeral=True
            )
        else:
            self.entries.add(user_id)
            await interaction.response.send_message(
                "You entered the giveaway! Good luck!", ephemeral=True
            )


# --- BOT EVENTS ---

@bot.event
async def on_ready():
    # Register persistent views so buttons continue working after a bot restart
    bot.add_view(CreateTicketView())
    bot.add_view(TicketControlView())

    # Sync slash commands
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"Synced commands locally to guild {GUILD_ID}.")
    else:
        await bot.tree.sync()
        print("Synced global commands.")

    print(f"Bot logged in as {bot.user} (ID: {bot.user.id})")


# --- BOT COMMANDS ---

@bot.tree.command(
    name="ticket",
    description="Display the ticket creation panel in the current channel.",
)
@app_commands.checks.has_permissions(administrator=True)
async def ticket_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Support Ticket System",
        description="Need assistance or have a question? Click the button below to open a private support ticket.",
        color=discord.Color.green(),
    )
    embed.set_footer(text="Our staff team will respond as soon as possible.")

    await interaction.response.send_message(embed=embed, view=CreateTicketView())


@bot.tree.command(
    name="giveaway",
    description="Start a giveaway in the current channel.",
)
@app_commands.describe(
    duration_seconds="Duration of the giveaway in seconds",
    prize="What the winners will receive",
    winners="Number of winners (default: 1)",
)
@app_commands.checks.has_permissions(administrator=True)
async def giveaway_command(
    interaction: discord.Interaction,
    duration_seconds: int,
    prize: str,
    winners: int = 1,
):
    if duration_seconds <= 0:
        return await interaction.response.send_message(
            "Duration must be greater than 0 seconds.", ephemeral=True
        )

    end_time = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
    time_timestamp = f"<t:{int(end_time.timestamp())}:R>"

    embed = discord.Embed(
        title="🎉 GIVEAWAY 🎉",
        description=f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** {time_timestamp}\n\nClick the button below to enter!",
        color=discord.Color.gold(),
    )
    embed.set_footer(text="Hosted by " + interaction.user.display_name)

    giveaway_view = GiveawayView()
    await interaction.response.send_message(embed=embed, view=giveaway_view)

    # Wait out the giveaway duration
    await asyncio.sleep(duration_seconds)

    # Fetch total participants
    participant_ids = list(giveaway_view.entries)

    if not participant_ids:
        result_embed = discord.Embed(
            title="🎉 GIVEAWAY ENDED 🎉",
            description=f"**Prize:** {prize}\n**Winner(s):** No participants entered.",
            color=discord.Color.dark_gray(),
        )
        await interaction.edit_original_response(embed=result_embed, view=None)
        return

    # Select random winner(s)
    winner_count = min(winners, len(participant_ids))
    winning_ids = random.sample(participant_ids, winner_count)
    winner_mentions = [f"<@{uid}>" for uid in winning_ids]

    result_embed = discord.Embed(
        title="🎉 GIVEAWAY ENDED 🎉",
        description=f"**Prize:** {prize}\n**Winner(s):** {', '.join(winner_mentions)}",
        color=discord.Color.purple(),
    )

    await interaction.edit_original_response(embed=result_embed, view=None)
    await interaction.channel.send(
        f"Congratulations {', '.join(winner_mentions)}! You won **{prize}**!"
    )


# Error handler for missing permissions
@ticket_command.error
@giveaway_command.error
async def command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You do not have permission to run this command.", ephemeral=True
        )


# --- RUN BOT ---
# Replace 'YOUR_BOT_TOKEN_HERE' with your actual bot token
bot.run("YOUR_BOT_TOKEN_HERE")
