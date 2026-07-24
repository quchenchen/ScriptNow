import asyncio
import json
from dataclasses import asdict

from scriptnow.platform.config import get_settings
from scriptnow.platform.database import Database
from scriptnow.platform.integrity import IntegrityAuditor


async def main() -> int:
    database = Database.create(get_settings().database_url)
    try:
        report = await IntegrityAuditor(database).audit()
        print(json.dumps({**asdict(report), "ok": report.ok}, ensure_ascii=False, indent=2))
        return 0 if report.ok else 1
    finally:
        await database.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
