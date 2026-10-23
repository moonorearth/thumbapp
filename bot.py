import os
import io
import discord
from discord import app_commands
from fastapi import FastAPI
import uvicorn
from threading import Thread
import aiohttp

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
VERCEL_API_URL = os.environ.get("VERCEL_API_URL", "https://whole-lamps-work.loca.lt/api/thumb") # Replace with your localtunnel URL + /api/thumb
API_SECRET_KEY = os.environ.get("API_SECRET_KEY", "your-secret-key") # Must match your local API key

ALLOWED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.tiff', '.bmp')

class ThumbnailBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Logged in as {self.user} (ID: {self.user.id})")

client = ThumbnailBot()

@client.tree.command(name="ping", description="Replies with Pong!")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong! Bot is working.")

@client.tree.command(name="thumb", description="Upload an image to generate a 1024x1024 face thumbnail.")
@app_commands.describe(image="Upload your image (PNG, JPG, WEBP, TIFF)")
async def thumb(interaction: discord.Interaction, image: discord.Attachment):
    # --- STEP 1: VALIDATE FILE EXTENSION ---
    filename_lower = image.filename.lower()
    if not filename_lower.endswith(ALLOWED_EXTENSIONS):
        await interaction.response.send_message(
            f"❌ **Invalid file type!** Please upload a valid image file ending in ` {', '.join(ALLOWED_EXTENSIONS)} `.",
            ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)

    try:
        # --- STEP 2: READ IMAGE BYTES ---
        image_bytes = await image.read()

        # --- STEP 3: SEND TO API WITH LOCAL-TUNNEL BYPASS HEADER ---
        headers = {
            "Authorization": f"Bearer {API_SECRET_KEY}",
            "bypass-tunnel-reminder": "true"  # Crucial for localtunnel!
        }
        
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field('file', image_bytes, filename=image.filename, content_type=image.content_type or 'application/octet-stream')
            
            async with session.post(VERCEL_API_URL, data=form, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    if response.status == 401:
                        await interaction.followup.send("❌ **Unauthorized:** API key configuration is incorrect.")
                    elif response.status == 400:
                        await interaction.followup.send("❌ **Processing Error:** Could not detect a face or the uploaded file is corrupted/invalid.")
                    else:
                        await interaction.followup.send(f"❌ **Server Error ({response.status}):** {error_text}")
                    return

                result_bytes = await response.read()
                if len(result_bytes) == 0:
                    await interaction.followup.send("❌ **Error:** The server returned an empty file.")
                    return

                discord_file = discord.File(fp=io.BytesIO(result_bytes), filename="thumb_1024.png")
                await interaction.followup.send(
                    content="✨ **Here is your 1024x1024 face thumbnail:**",
                    file=discord_file
                )

    except aiohttp.ClientError as e:
        await interaction.followup.send(f"❌ **Network Error:** Failed to connect to the thumbnail server. Details: `{e}`")
    except Exception as e:
        await interaction.followup.send(f"❌ **An unexpected error occurred:** `{str(e)}`")

# --- RUN WEB SERVER & DISCORD BOT ---
if __name__ == "__main__":
    web_thread = Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()

    client.run(DISCORD_BOT_TOKEN)
