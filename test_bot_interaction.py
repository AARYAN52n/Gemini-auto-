import asyncio
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
import sys

sys.stdout.reconfigure(encoding='utf-8')

api_id = 33316824
api_hash = 'f24ba90df909312f3368a3ee2f68487b'
target_bot = '@Recieved_gemini_bot'

client = TelegramClient('my_forwarder', api_id, api_hash)

async def check_and_join():
    await client.connect()
    messages = await client.get_messages(target_bot, limit=1)
    if not messages:
        return
    msg = messages[0]
    print('Bot message:', msg.text)
    channel_url = None
    if msg.buttons:
        for row in msg.buttons:
            for b in row:
                print(f"Button: {b.text}, url={getattr(b, 'url', None)}")
                if getattr(b, 'url', None):
                    channel_url = b.url

    # If there is a channel URL, let's join it!
    if channel_url:
        print(f"Attempting to join channel: {channel_url}")
        try:
            entity = await client.get_entity(channel_url)
            await client(JoinChannelRequest(entity))
            print("Successfully joined channel!")
        except Exception as e:
            print(f"Error joining channel: {e}")

    # Now click "I've Joined" or send /start again!
    print("Clicking 'I've Joined' or sending /start...")
    try:
        await msg.click(1) # second button: "I've Joined"
        await asyncio.sleep(2)
    except Exception as e:
        print(f"Click error: {e}")
        await client.send_message(target_bot, '/start')
        await asyncio.sleep(2)

    # Check new message
    messages2 = await client.get_messages(target_bot, limit=2)
    for m in messages2:
        if not m.out:
            print("New message from bot:", m.text)
            if m.buttons:
                print("New buttons:", [[b.text for b in row] for row in m.buttons])

    await client.disconnect()

asyncio.run(check_and_join())
