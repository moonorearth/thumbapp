import os
import io
import cv2
import numpy as np
import discord
from discord import app_commands
from fastapi import FastAPI, File, UploadFile, Header, HTTPException, status
import uvicorn
from threading import Thread
import aiohttp

# --- 1. FASTAPI IMAGE PROCESSING API ---
app = FastAPI()

API_SECRET_KEY = os.environ.get("API_SECRET_KEY", "your-secret-key")
MODEL_PATH = "face_detection_yunet_2023mar.onnx"  # Ensure this file is in your repo!

def verify_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ")[1]
    if token != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/")
def health_check():
    return {"status": "Render Bot & API are alive!"}

@app.post("/api/thumb")
async def generate_thumbnail(file: UploadFile = File(...), authorization: str = Header(None)):
    verify_token(authorization)
    
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file.")

    h, w, _ = img.shape
    
    # Initialize YuNet Face Detector
    if not os.path.exists(MODEL_PATH):
        raise HTTPException(status_code=500, detail="Face detection model file missing on server.")
        
    face_detector = cv2.FaceDetectorYN.create(
        model=MODEL_PATH,
        config="",
        input_size=(w, h),
        score_threshold=0.9
    )
    
    _, faces = face_detector.detect(img)
    
    if faces is None or len(faces) == 0:
        raise HTTPException(status_code=400, detail="No face detected in the image.")
        
    # Process face and crop to 1024x1024
    face = faces[0]
    box = face[:4].astype(int)
    x, y, fw, fh = box
    
    # Center crop / padding logic (adjust as per your exact processing script)
    center_x, center_y = x + fw // 2, y + fh // 2
    crop_size = max(fw, fh) * 3  # multiplier for context
    
    x1 = max(0, center_x - crop_size // 2)
    y1 = max(0, center_y - crop_size // 2)
    x2 = min(w, center_x + crop_size // 2)
    y2 = min(h, center_y + crop_size // 2)
    
    cropped = img[y1:y2, x1:x2]
    resized = cv2.resize(cropped, (1024, 1024), interpolation=cv2.INTER_LANCZOS4)
    
    success, encoded_image = cv2.imencode('.png', resized)
    if not success:
        raise HTTPException(status_code=500, detail="Image encoding failed.")
        
    return Response(content=encoded_image.tobytes(), media_type="image/png")

from fastapi.responses import Response

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

@client.tree.command(name="thumb", description="Upload an image to generate a 1024x1024 face thumbnail.")
@app_commands.describe(image="Upload your image (PNG, JPG, WEBP, TIFF)")
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
                await interaction.followup.send(content="✨ **Here is your 1024x1024 face thumbnail:**", file=discord_file)

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
