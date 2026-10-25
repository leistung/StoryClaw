"""Neo4j 图谱存储：实体/关系入库与检索（按 user_book 隔离）。"""
from __future__ import annotations

import logging
from typing import Any

from ..config import settings

log = logging.getLogger("storyclaw.rag.neo4j")

try:
    from neo4j import GraphDatabase
    _HAS_NEO4J = True
except Exception as e:  # pragma: no cover
    _HAS_NEO4J = False
    log.warning("neo4j 驱动导入失败（图谱不可用）: %s", e)
    GraphDatabase = None


class Neo4jStore:
    def __init__(self) -> None:
        self._driver = None

    @property
    def available(self) -> bool:
        return self._driver is not None

    def connect(self) -> bool:
        if self._driver:
            return True
        if not _HAS_NEO4J:
            return False
        try:
            self._driver = GraphDatabase.driver(
                settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
            )
            self._driver.verify_connectivity()
            return True
        except Exception as e:
            log.warning("Neo4j 连接失败（图谱不可用）: %s", e)
            self._driver = None
            return False

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

    # ---------- 写入 ----------
    def upsert_chapter(
        self, user_id: int, book_id: int, chapter_id: int,
        entities: list[dict], relations: list[dict],
    ) -> tuple[int, int]:
        """入库实体与关系，返回 (实体数, 关系数)。同名实体跨章节合并。"""
        if not self.connect():
            return 0, 0
        try:
            with self._driver.session() as session, session.begin_transaction() as s:
                s.run(
                    "MERGE (u:User {user_id:$user_id}) "
                    "MERGE (b:Book {book_id:$book_id, user_id:$user_id}) "
                    "MERGE (c:Chapter {book_id:$book_id, chapter_id:$chapter_id}) "
                    "MERGE (u)-[:WROTE]->(b) "
                    "MERGE (b)-[:HAS_CHAPTER]->(c)",
                    user_id=user_id, book_id=book_id, chapter_id=chapter_id,
                )
                # 清掉该章节的旧 APPEARS_IN（实体本身保留，跨章合并）
                s.run(
                    "MATCH (c:Chapter {book_id:$book_id, chapter_id:$chapter_id})<-[r:APPEARS_IN]-() DELETE r",
                    book_id=book_id, chapter_id=chapter_id,
                )
                s.run(
                    "MATCH (a:StoryEntity {user_id:$user_id, book_id:$book_id})-[r:REL {chapter_id:$chapter_id}]->() DELETE r",
                    user_id=user_id, book_id=book_id, chapter_id=chapter_id,
                )
                ent_count = 0
                for ent in entities:
                    name = (ent.get("name") or "").strip()
                    etype = (ent.get("type") or "character").strip() or "character"
                    desc = (ent.get("description") or "").strip()
                    if not name:
                        continue
                    s.run(
                        "MERGE (e:StoryEntity {user_id:$user_id, book_id:$book_id, chapter_id:$chapter_id, name:$name}) "
                        "ON CREATE SET e.entity_type=$etype, e.description=$desc "
                        "ON MATCH SET e.entity_type=$etype, e.description=$desc "
                        "MERGE (c:Chapter {book_id:$book_id, chapter_id:$chapter_id}) "
                        "MERGE (e)-[:APPEARS_IN {chapter_id:$chapter_id}]->(c)",
                        user_id=user_id, book_id=book_id, name=name,
                        etype=etype, desc=desc, chapter_id=chapter_id,
                    )
                    ent_count += 1
                rel_count = 0
                for rel in relations:
                    frm = (rel.get("from") or "").strip()
                    to = (rel.get("to") or "").strip()
                    rtype = (rel.get("type") or "RELATES_TO").strip() or "RELATES_TO"
                    if not frm or not to or frm == to:
                        continue
                    s.run(
                        # from/to 是 Cypher 保留字，参数名用 from_name/to_name
                        "MATCH (a:StoryEntity {user_id:$user_id, book_id:$book_id, chapter_id:$chapter_id, name:$from_name}) "
                        "MATCH (b:StoryEntity {user_id:$user_id, book_id:$book_id, chapter_id:$chapter_id, name:$to_name}) "
                        "MERGE (a)-[:REL {type:$rtype, chapter_id:$chapter_id}]->(b)",
                        user_id=user_id, book_id=book_id,
                        from_name=frm, to_name=to, rtype=rtype, chapter_id=chapter_id,
                    )
                    rel_count += 1
                return ent_count, rel_count
        except Exception as e:
            log.warning("Neo4j upsert 失败: %s", e)
            raise RuntimeError("Neo4j 写入失败，索引不可激活") from e

    # ---------- 查询 ----------
    def query_related(self, user_id: int, book_id: int, query_text: str, limit: int = 8, allowed_chapter_ids: list[int] | None = None) -> dict:
        """匹配实体 + 一跳关系。"""
        if not self.connect():
            raise RuntimeError('Neo4j 不可用')
        try:
            with self._driver.session() as s:
                rows = s.run(
                    "MATCH (e:StoryEntity {user_id:$user_id, book_id:$book_id}) "
                    "WHERE e.name CONTAINS $q OR (size(e.name) >= 2 AND $q CONTAINS e.name) OR e.description CONTAINS $q "
                    "MATCH (e)-[ap:APPEARS_IN]->(c:Chapter) "
                    "WHERE $allowed IS NULL OR c.chapter_id IN $allowed "
                    "RETURN e.name AS name, e.entity_type AS type, e.description AS description, "
                    "c.chapter_id AS chapter_id LIMIT $limit",
                    user_id=user_id, book_id=book_id, q=query_text, limit=limit, allowed=allowed_chapter_ids,
                ).data()
                entities = []
                for r in rows:
                    entities.append({
                        "name": r["name"], "type": r["type"] or "character",
                        "description": (r["description"] or "")[:100],
                        "chapter_id": r["chapter_id"],
                    })
                names = [e["name"] for e in entities]
                relations = []
                if names:
                    rels = s.run(
                        "MATCH (a:StoryEntity {user_id:$user_id, book_id:$book_id})-[r:REL]->"
                        "(b:StoryEntity {user_id:$user_id, book_id:$book_id}) "
                        "WHERE (a.name IN $names OR b.name IN $names) "
                        "AND ($allowed IS NULL OR r.chapter_id IN $allowed) "
                        "RETURN a.name AS frm, r.type AS type, b.name AS to, r.chapter_id AS chapter_id "
                        "LIMIT 50",
                        user_id=user_id, book_id=book_id, names=names, allowed=allowed_chapter_ids,
                    ).data()
                    relations = [
                        {"from": r["frm"], "to": r["to"], "type": r["type"],
                         "chapter_id": r["chapter_id"]}
                        for r in rels
                    ]
                return {"entities": entities, "relations": relations}
        except Exception as e:
            log.warning("Neo4j query 失败: %s", e)
            raise RuntimeError('Neo4j 检索失败') from e

    def book_graph(self, user_id: int, book_id: int, limit: int = 200) -> dict:
        """整本书图谱（数据库页展示用）。"""
        if not self.connect():
            return {"entities": [], "relations": []}
        try:
            with self._driver.session() as s:
                ents = s.run(
                    "MATCH (e:StoryEntity {user_id:$user_id, book_id:$book_id}) "
                    "RETURN e.name AS name, e.entity_type AS type, e.description AS description LIMIT $limit",
                    user_id=user_id, book_id=book_id, limit=limit,
                ).data()
                rels = s.run(
                    "MATCH (a:StoryEntity {user_id:$user_id, book_id:$book_id})-[r:REL]->"
                    "(b:StoryEntity {user_id:$user_id, book_id:$book_id}) "
                    "RETURN a.name AS frm, r.type AS type, b.name AS to LIMIT $limit",
                    user_id=user_id, book_id=book_id, limit=limit,
                ).data()
                return {
                    "entities": [
                        {"name": r["name"], "type": r["type"] or "character",
                         "description": (r["description"] or "")[:100]}
                        for r in ents
                    ],
                    "relations": [
                        {"from": r["frm"], "to": r["to"], "type": r["type"]} for r in rels
                    ],
                }
        except Exception as e:
            log.warning("Neo4j book_graph 失败: %s", e)
            return {"entities": [], "relations": []}

    def related_to_name(self, user_id: int, book_id: int, name: str, limit: int = 20) -> dict:
        """按名称模糊匹配实体及关系（角色/场景/物品配置页「从数据库加载」用）。"""
        if not self.connect():
            return {"entities": [], "relations": []}
        try:
            with self._driver.session() as s:
                rows = s.run(
                    "MATCH (e:StoryEntity {user_id:$user_id, book_id:$book_id}) "
                    "WHERE e.name CONTAINS $name "
                    "OPTIONAL MATCH (e)-[ap:APPEARS_IN]->(c:Chapter) "
                    "RETURN e.name AS name, e.entity_type AS type, e.description AS description, "
                    "c.chapter_id AS chapter_id LIMIT $limit",
                    user_id=user_id, book_id=book_id, name=name, limit=limit,
                ).data()
                entities = [
                    {"name": r["name"], "type": r["type"] or "character",
                     "description": (r["description"] or "")[:100], "chapter_id": r["chapter_id"]}
                    for r in rows
                ]
                names = [e["name"] for e in entities]
                relations = []
                if names:
                    rels = s.run(
                        "MATCH (a:StoryEntity {user_id:$user_id, book_id:$book_id})-[r:REL]->"
                        "(b:StoryEntity {user_id:$user_id, book_id:$book_id}) "
                        "WHERE a.name IN $names OR b.name IN $names "
                        "RETURN a.name AS frm, r.type AS type, b.name AS to, r.chapter_id AS chapter_id "
                        "LIMIT 50",
                        user_id=user_id, book_id=book_id, names=names,
                    ).data()
                    relations = [
                        {"from": r["frm"], "to": r["to"], "type": r["type"],
                         "chapter_id": r["chapter_id"]}
                        for r in rels
                    ]
                return {"entities": entities, "relations": relations}
        except Exception as e:
            log.warning("Neo4j related_to_name 失败: %s", e)
            return {"entities": [], "relations": []}

    def entity_count(self, user_id: int, book_id: int, chapter_id: int | None = None) -> int:
        if not self.connect():
            return 0
        try:
            with self._driver.session() as s:
                if chapter_id is not None:
                    rec = s.run(
                        "MATCH (e:StoryEntity {user_id:$u, book_id:$b})-[:APPEARS_IN]->"
                        "(c:Chapter {chapter_id:$cid}) RETURN count(DISTINCT e) AS n",
                        u=user_id, b=book_id, cid=chapter_id,
                    ).single()
                else:
                    rec = s.run(
                        "MATCH (e:StoryEntity {user_id:$u, book_id:$b}) RETURN count(e) AS n",
                        u=user_id, b=book_id,
                    ).single()
                return int(rec["n"]) if rec and rec["n"] is not None else 0
        except Exception:
            return 0

    def delete_chapter_strict(self,user_id,book_id,chapter_id):
        if not self.connect():raise RuntimeError('Neo4j unavailable for cleanup')
        with self._driver.session() as session,session.begin_transaction() as tx:
            tx.run('MATCH (:StoryEntity {user_id:$uid,book_id:$bid})-[r:REL {chapter_id:$cid}]->() DELETE r',uid=user_id,bid=book_id,cid=chapter_id).consume()
            tx.run('MATCH (c:Chapter {book_id:$bid,chapter_id:$cid}) DETACH DELETE c',bid=book_id,cid=chapter_id).consume()
            tx.run('MATCH (e:StoryEntity {user_id:$uid,book_id:$bid,chapter_id:$cid}) DETACH DELETE e',uid=user_id,bid=book_id,cid=chapter_id).consume()
