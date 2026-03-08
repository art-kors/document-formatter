import networkx as nx
from typing import List, Optional, Dict
import json

class KnowledgeGraph:
    def __init__(self):
        self.graph = nx.MultiDiGraph()
        self.entity_map = {}

    def add_entity(self, entity):
        """Добавление сущности в граф"""
        self.graph.add_node(
            entity.id,
            name=entity.name,
            type=entity.type,
            content=entity.content,
            metadata=entity.metadata
        )
        self.entity_map[entity.id] = entity

    def add_relation(self, relation):
        """Добавление связи в граф"""
        self.graph.add_edge(
            relation.source,
            relation.target,
            type=relation.type,
            **relation.properties
        )

    def build_from_entities(self, entities: List, relations: List):
        """Построение графа из сущностей и связей"""
        for entity in entities:
            self.add_entity(entity)

        for relation in relations:
            self.add_relation(relation)

    def get_neighbors(self, node_id: str, depth: int = 1) -> List:
        """Получение соседних узлов"""
        neighbors = []
        for i in range(1, depth + 1):
            neighbors.extend(nx.single_source_shortest_path_length(
                self.graph, node_id, cutoff=i
            ).keys())
        return list(set(neighbors))

    def find_path(self, source: str, target: str) -> Optional[List]:
        """Поиск пути между сущностями"""
        try:
            path = nx.shortest_path(self.graph, source, target)
            return path
        except nx.NetworkXNoPath:
            return None

    def get_subgraph(self, node_ids: List) -> nx.Graph:
        """Получение подграфа"""
        return self.graph.subgraph(node_ids)

    def to_dict(self) -> Dict:
        """Экспорт графа в словарь"""
        return {
            'nodes': [
                {
                    'id': node,
                    **self.graph.nodes[node]
                }
                for node in self.graph.nodes()
            ],
            'edges': [
                {
                    'source': u,
                    'target': v,
                    **data
                }
                for u, v, data in self.graph.edges(data=True)
            ]
        }

    def save(self, path: str):
        """Сохранение графа"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def load(self, path: str):
        """Загрузка графа"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.graph = nx.MultiDiGraph()
        for node in data['nodes']:
            node_id = node.pop('id')
            self.graph.add_node(node_id, **node)

        for edge in data['edges']:
            source = edge.pop('source')
            target = edge.pop('target')
            self.graph.add_edge(source, target, **edge)