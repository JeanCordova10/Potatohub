import os
from neo4j import AsyncGraphDatabase, AsyncDriver

_driver: AsyncDriver | None = None


async def init_driver() -> None:
    global _driver
    uri  = os.getenv("NEO4J_URI_LOCAL", "bolt://localhost:7687")
    auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "potatohub123"))
    _driver = AsyncGraphDatabase.driver(uri, auth=auth)
    await _driver.verify_connectivity()


async def close_driver() -> None:
    global _driver
    if _driver:
        await _driver.close()
        _driver = None


def get_driver() -> AsyncDriver:
    return _driver


async def ensure_constraints() -> None:
    async with _driver.session() as s:
        await s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (r:Recipe)     REQUIRE r.id   IS UNIQUE")
        await s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (u:User)       REQUIRE u.id   IS UNIQUE")
        await s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (i:Ingredient) REQUIRE i.name IS UNIQUE")
        await s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Category)   REQUIRE c.name IS UNIQUE")
        await s.run("CREATE INDEX viewed_ts IF NOT EXISTS FOR ()-[r:VIEWED]-() ON (r.timestamp)")
        await s.run("CREATE INDEX saved_ts  IF NOT EXISTS FOR ()-[r:SAVED]-()  ON (r.timestamp)")
