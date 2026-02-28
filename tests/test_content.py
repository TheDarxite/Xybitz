import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# import asyncio
# from app.database import AsyncSessionLocal

import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import select
from app.models import Article

async def check():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Article.id, Article.title, Article.raw_content, Article.summary_status)
            .where(Article.summary_status == "failed")
            .limit(5)
        )
        for id, title, content, status in result.all():
            length = len(content or "")
            print(f"ID {id}: content_length={length} | {title[:60]}")

asyncio.run(check())
