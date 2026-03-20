import json
from typing import Dict, List, Optional

import networkx as nx

from app.schemas.standard import StandardNode, StandardRelation


class KnowledgeGraph:
    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def add_entity(self, entity: StandardNode) -> None:
        self.graph.add_node(
            entity.id,
            name=entity.name,
            type=entity.type,
            content=entity.content,
            metadata=entity.metadata,
        )

    def add_relation(self, relation: StandardRelation) -> None:
        self.graph.add_edge(
            relation.source,
            relation.target,
            type=relation.type,
            **relation.properties,
        )

    def build_from_entities(self, entities: List[StandardNode], relations: List[StandardRelation]) -> None:
        for entity in entities:
            self.add_entity(entity)
        for relation in relations:
            self.add_relation(relation)

    def get_node(self, node_id: str) -> Optional[Dict]:
        if node_id not in self.graph.nodes:
            return None
        return {"id": node_id, **self.graph.nodes[node_id]}

    def get_neighbors(self, node_id: str, depth: int = 1) -> List[str]:
        neighbors = []
        for current_depth in range(1, depth + 1):
            neighbors.extend(
                nx.single_source_shortest_path_length(
                    self.graph,
                    node_id,
                    cutoff=current_depth,
                ).keys()
            )
        return list(set(neighbors))

    def get_related_nodes(
        self,
        node_id: str,
        *,
        edge_types: Optional[List[str]] = None,
        neighbor_types: Optional[List[str]] = None,
    ) -> List[str]:
        return [edge["neighbor_id"] for edge in self.get_related_edges(node_id, edge_types=edge_types, neighbor_types=neighbor_types)]

    def get_related_edges(
        self,
        node_id: str,
        *,
        edge_types: Optional[List[str]] = None,
        neighbor_types: Optional[List[str]] = None,
    ) -> List[Dict]:
        if node_id not in self.graph.nodes:
            return []

        related: List[Dict] = []
        for source, target, data in self.graph.edges(node_id, data=True):
            if edge_types and data.get("type") not in edge_types:
                continue
            neighbor_type = self.graph.nodes[target].get("type")
            if neighbor_types and neighbor_type not in neighbor_types:
                continue
            related.append(
                {
                    "source": source,
                    "target": target,
                    "type": data.get("type", ""),
                    "neighbor_id": target,
                    "neighbor_type": neighbor_type,
                    "direction": "out",
                }
            )

        for source, target, data in self.graph.in_edges(node_id, data=True):
            if edge_types and data.get("type") not in edge_types:
                continue
            neighbor_type = self.graph.nodes[source].get("type")
            if neighbor_types and neighbor_type not in neighbor_types:
                continue
            related.append(
                {
                    "source": source,
                    "target": target,
                    "type": data.get("type", ""),
                    "neighbor_id": source,
                    "neighbor_type": neighbor_type,
                    "direction": "in",
                }
            )

        deduped: List[Dict] = []
        seen = set()
        for item in related:
            key = (item["neighbor_id"], item["type"], item["direction"])
            if key in seen:
                continue
            deduped.append(item)
            seen.add(key)
        return deduped

    def find_nodes_by_type(self, node_type: str) -> List[Dict]:
        return [
            {"id": node_id, **data}
            for node_id, data in self.graph.nodes(data=True)
            if data.get("type") == node_type
        ]

    def find_path(self, source: str, target: str) -> Optional[List[str]]:
        try:
            return nx.shortest_path(self.graph, source, target)
        except nx.NetworkXNoPath:
            return None

    def to_dict(self) -> dict:
        return {
            "nodes": [{"id": node, **self.graph.nodes[node]} for node in self.graph.nodes()],
            "edges": [
                {"source": source, "target": target, **data}
                for source, target, data in self.graph.edges(data=True)
            ],
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(self.to_dict(), file, ensure_ascii=False, indent=2)
