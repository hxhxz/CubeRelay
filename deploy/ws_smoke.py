import asyncio
import sys

import websockets


async def main() -> None:
    async with websockets.connect(sys.argv[1]) as websocket:
        message = await asyncio.wait_for(websocket.recv(), timeout=15)
        print(message[:120])


asyncio.run(main())
