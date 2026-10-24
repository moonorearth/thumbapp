import os
import io
import discord
from discord import app_commands
from fastapi import FastAPI, File, UploadFile, Header, HTTPException, Response
from fastapi.responses import FileResponse
import uvicorn
from threading import Thread
import aiohttp

# Import our advanced image processor
from thumb_processor import process_image_bytes

# --- 1. FASTAPI IMAGE PROCESSING API & WEB UI ---
app = FastAPI()

API_SECRET_KEY = os.environ.get("API_SECRET_KEY", "your-secret-key")

def verify_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ")[1]
    if token != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/", response_class=FileResponse)
def serve_ui():
    """Serves the web user interface index.html at root url"""
    return FileResponse("index.html")

@app.post("/api/thumb")
async def generate_thumbnail(file: UploadFile = File(...), authorization: str = Header(None)):
    verify_token(authorization)
    
    try:
        contents = await file.read()
        result_bytes = process_image_bytes(contents)
        return Response(content=result_bytes, media_type="image/png")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

# --- 2. DISCORD BOT CONFIGURATION ---
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
ALLOWED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.tiff', '.bmp')

class UnifiedBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Logged in as {self.user} (ID: {self.user.id})")

client = UnifiedBot()

@client.tree.command(name="ping", description="Replies with Pong!")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong! Bot is working.")

@client.tree.command(name="thumb", description="Upload an image to generate your advanced 1024x1024 face thumbnail.")
@app_commands.describe(image="Upload your image (PNG, JPG, WEBP, etc.)")
async def thumb(interaction: discord.Interaction, image: discord.Attachment):
    filename_lower = image.filename.lower()
    if not filename_lower.endswith(ALLOWED_EXTENSIONS):
        await interaction.response.send_message("❌ Invalid file type! Please upload a valid image file.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    try:
        image_bytes = await image.read()
        port = int(os.environ.get("PORT", 8080))
        local_api_url = f"http://127.0.0.1:{port}/api/thumb"

        headers = {"Authorization": f"Bearer {API_SECRET_KEY}"}
        
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field('file', image_bytes, filename=image.filename, content_type=image.content_type or 'application/octet-stream')
            
            async with session.post(local_api_url, data=form, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    await interaction.followup.send(f"❌ Processing Error ({response.status}): {error_text}")
                    return

                result_bytes = await response.read()
                discord_file = discord.File(fp=io.BytesIO(result_bytes), filename="thumb_1024.png")
                await interaction.followup.send(content="✨ **Here is your high-end face thumbnail:**", file=discord_file)

    except Exception as e:
        await interaction.followup.send(f"❌ An unexpected error occurred: `{str(e)}`")

# --- 3. RUN BOTH CONCURRENTLY ---
if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN is missing!")
        exit(1)

    # Start FastAPI web server in background thread
    web_thread = Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()

    # Run Discord bot on main thread
    client.run(DISCORD_BOT_TOKEN)
