import os
import discord
from discord import app_commands
from fastapi import FastAPI
import uvicorn
from threading import Thread

# --- FASTAPI WEB SERVER (Keeps Render Free Web Service Alive) ---
app = FastAPI()

@app.get("/")
def health_check():
    return {"status": "Bot is alive!"}

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

# --- DISCORD BOT CONFIGURATION ---
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")

class PingBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Logged in as {self.user} (ID: {self.user.id})")

client = PingBot()

@client.tree.command(name="ping", description="Replies with Pong!")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong! Bot is working.")

# --- RUN BOTH WEB SERVER AND DISCORD BOT ---
if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN environment variable is missing!")
        exit(1)

    # Start FastAPI in a background thread so it runs alongside the bot
    web_thread = Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()

    # Run the Discord bot on the main thread
    client.run(DISCORD_BOT_TOKEN)
