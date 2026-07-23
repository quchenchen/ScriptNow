import asyncio
import json
from dataclasses import asdict

from scriptflow_v7.platform.config import get_settings
from scriptflow_v7.platform.database import Database
from scriptflow_v7.platform.integrity import IntegrityAuditor


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
