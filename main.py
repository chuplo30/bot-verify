import discord
from discord.ext import commands
from discord import app_commands
import secrets
import time
import threading
import os
from flask import Flask

# ====== FLASK KEEP-ALIVE ======
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

TOKEN = os.getenv("DISCORD_TOKEN")
VERIFY_ROLE_ID = 1551157925043507200
VERIFY_CHANNEL_ID = 1551209870944899165
TOKEN_TTL = 300

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

pending_tokens = {}


def get_valid_token(user_id: int):
    data = pending_tokens.get(user_id)
    if not data:
        return None
    if time.time() > data["expires_at"]:
        pending_tokens.pop(user_id, None)
        return None
    return data


class TokenModal(discord.ui.Modal, title="Account Verification"):
    token_input = discord.ui.TextInput(
        label="Enter the token sent to your DM",
        placeholder="Example: A1B2C3D4",
        required=True,
        min_length=8,
        max_length=8,
    )

    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This is not your verification window.", ephemeral=True
            )
            return

        entered = self.token_input.value.strip().upper()
        data = get_valid_token(self.user_id)

        if not data:
            await interaction.response.send_message(
                "Token has expired. Click Verify to get a new token.", ephemeral=True
            )
            return

        if entered != data["token"]:
            await interaction.response.send_message(
                "Incorrect token.", ephemeral=True
            )
            return

        guild = interaction.guild
        role = guild.get_role(VERIFY_ROLE_ID)
        member = guild.get_member(self.user_id)

        if not role or not member:
            await interaction.response.send_message(
                "Role or member not found.", ephemeral=True
            )
            return

        try:
            await member.add_roles(role, reason="Verified")
            pending_tokens.pop(self.user_id, None)
            await interaction.response.send_message(
                "Verified.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Bot lacks permission to assign the role.", ephemeral=True
            )


class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.success,
        custom_id="verify_button",
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        if isinstance(user, discord.Member):
            if any(r.id == VERIFY_ROLE_ID for r in user.roles):
                await interaction.response.send_message(
                    "You are already verified.", ephemeral=True
                )
                return

        data = get_valid_token(user.id)

        if data:
            token = data["token"]
            is_new = False
        else:
            token = secrets.token_hex(4).upper()
            pending_tokens[user.id] = {
                "token": token,
                "expires_at": time.time() + TOKEN_TTL,
            }
            is_new = True

        try:
            await user.send(token)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Could not send DM. Enable Allow DMs from server members and try again.",
                ephemeral=True,
            )
            if is_new:
                pending_tokens.pop(user.id, None)
            return

        await interaction.response.send_modal(TokenModal(user_id=user.id))


@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Sync error: {e}")
    print(f"Bot online: {bot.user}")


@bot.tree.command(name="setupverify", description="Send the verification panel to this channel")
@app_commands.checks.has_permissions(administrator=True)
async def setupverify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Verification",
        description=(
            "**To minimize bots on our Discord server, we ask for verification.**\n\n"
            "Click the button below to verify yourself.\n"
            "The bot will send a token to your DM.\n"
            "Enter the token in the window that appears to complete verification."
        ),
        color=discord.Color.blurple(),
    )
    await interaction.channel.send(embed=embed, view=VerifyView())
    await interaction.response.send_message("Verification panel sent.", ephemeral=True)

keep_alive()   # chạy Flask trước
bot.run(TOKEN)
