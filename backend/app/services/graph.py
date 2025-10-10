from __future__ import annotations

import uuid
from typing import Iterable

from fastapi import HTTPException, status

from app.core.config import settings
from app.models import GraphContext, KnowledgeEntry, User


class GraphService:
    def __init__(self) -> None:
        self._driver = None
        if settings.neo4j_enabled:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            )

    def __del__(self) -> None:  # noqa: D401 - ensure driver closes on cleanup
        if self._driver:
            self._driver.close()

    def _ensure_driver(self):
        if not self._driver:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Graph service is not configured",
            )
        return self._driver

    def sync_entry(self, *, entry: KnowledgeEntry, owner: User) -> None:
        driver = self._ensure_driver()
        tags: Iterable[str] = entry.tags or []
        with driver.session() as session:
            session.execute_write(
                self._sync_entry_tx,
                entry_id=str(entry.id),
                title=entry.title,
                content=entry.content,
                created_at=entry.created_at.isoformat(),
                updated_at=entry.updated_at.isoformat(),
                user_id=str(owner.id),
                email=owner.email,
                full_name=owner.full_name or "",
                tags=list(tags),
            )

    @staticmethod
    def _sync_entry_tx(tx, **params):
        query = """
        MERGE (u:User {id: $user_id})
          SET u.email = $email,
              u.full_name = $full_name
        MERGE (e:Entry {id: $entry_id})
          SET e.title = $title,
              e.content = $content,
              e.created_at = $created_at,
              e.updated_at = $updated_at
        MERGE (u)-[:OWNS]->(e)
        WITH e
        MATCH (e)-[r:MENTIONS]->(:Concept)
        DELETE r
        WITH e
        UNWIND $tags AS concept_name
            MERGE (c:Concept {name: concept_name})
            MERGE (e)-[:MENTIONS]->(c)
        """
        tx.run(query, params)

    def get_connections(self, *, concept: str) -> GraphContext:
        driver = self._ensure_driver()
        with driver.session() as session:
            records = session.run(
                """
                MATCH (c:Concept {name: $concept})-[r]-(neighbor)
                RETURN c, r, neighbor
                """,
                concept=concept,
            )
            nodes: dict[str, dict] = {}
            edges: list[dict[str, str]] = []
            for record in records:
                concept_node = record["c"]
                neighbor = record["neighbor"]
                rel = record["r"]
                nodes[str(concept_node.element_id)] = {
                    "id": concept_node["name"],
                    "label": "Concept",
                    "name": concept_node["name"],
                }
                neighbor_id = neighbor.get("id", neighbor.get("name", neighbor.element_id))
                nodes[str(neighbor.element_id)] = {
                    "id": str(neighbor_id),
                    "label": next(iter(neighbor.labels), "Node"),
                    "name": neighbor.get("title") or neighbor.get("name") or neighbor.get("email"),
                }
                edges.append(
                    {
                        "source": concept_node["name"],
                        "target": str(neighbor_id),
                        "type": rel.type,
                    }
                )
            return GraphContext(nodes=list(nodes.values()), edges=edges)

    def get_entry_context(self, *, entry_id: uuid.UUID) -> GraphContext:
        driver = self._ensure_driver()
        with driver.session() as session:
            records = session.run(
                """
                MATCH (e:Entry {id: $entry_id})-[r]-(neighbor)
                RETURN e, r, neighbor
                """,
                entry_id=str(entry_id),
            )
            nodes: dict[str, dict] = {}
            edges: list[dict[str, str]] = []
            for record in records:
                entry = record["e"]
                neighbor = record["neighbor"]
                rel = record["r"]
                entry_id_str = entry["id"]
                nodes[str(entry.element_id)] = {
                    "id": entry_id_str,
                    "label": "Entry",
                    "name": entry.get("title"),
                }
                neighbor_id = neighbor.get("id", neighbor.get("name", neighbor.element_id))
                nodes[str(neighbor.element_id)] = {
                    "id": str(neighbor_id),
                    "label": next(iter(neighbor.labels), "Node"),
                    "name": neighbor.get("title") or neighbor.get("name") or neighbor.get("email"),
                }
                edges.append(
                    {
                        "source": entry_id_str,
                        "target": str(neighbor_id),
                        "type": rel.type,
                    }
                )
            return GraphContext(nodes=list(nodes.values()), edges=edges)
