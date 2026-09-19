import asyncio
from telethon import TelegramClient
import sys

sys.stdout.reconfigure(encoding='utf-8')

api_id = 33316824
api_hash = 'f24ba90df909312f3368a3ee2f68487b'
target_bot = 'Geminii_auto_bot'

client = TelegramClient('my_forwarder', api_id, api_hash)

async def test_bot():
    await client.connect()
    if not await client.is_user_authorized():
        print('Not authorized!')
        return
    print('Client authorized! Getting entity for', target_bot)
    entity = await client.get_entity(target_bot)
    print('Target bot found:', entity.id, entity.username)
    
    # Get last message from target_bot without sending anything
    messages = await client.get_messages(entity, limit=3)
    print(f'Last {len(messages)} messages from {target_bot}:')
    for m in messages:
        snippet = m.text[:100].replace('\n', ' ') if m.text else '[no text]'
        print(f'[{m.date}] {snippet}')
    await client.disconnect()

asyncio.run(test_bot())
