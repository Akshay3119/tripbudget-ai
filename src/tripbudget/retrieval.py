import asyncio
import json
import threading

import chromadb
from chromadb.config import Settings as ChromaSettings
from fastembed import TextEmbedding

from .errors import DomainError
from .persistence import digest
from .schemas import QueryRewrite


class Corpus:
    def __init__(self, settings, collection_name="travel"):
        self.s = settings
        self.collection_name = collection_name
        self._encoder = None
        self._collection = None
        self.lock = threading.Lock()

    def encoder(self):
        if self._encoder is None:
            self._encoder = TextEmbedding("BAAI/bge-small-en-v1.5", cache_dir=str(self.s.embedding_cache))
        return self._encoder

    def collection(self):
        if self._collection is None:
            client = chromadb.PersistentClient(
                path=str(self.s.data_dir / "chroma"),
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=False,
                ),
            )
            self._collection = client.get_or_create_collection(
                self.collection_name, metadata={"hnsw:space": "cosine"}
            )
        return self._collection

    def build(self, documents=None):
        documents = documents or json.loads((self.s.corpus_dir / "catalog.json").read_text())["documents"]
        vectors = list(self.encoder().embed([x["text"] for x in documents]))
        self.collection().upsert(
            ids=[x["id"] for x in documents],
            documents=[x["text"] for x in documents],
            embeddings=[v.tolist() for v in vectors],
            metadatas=[{k: x[k] for k in ["source_id", "activity_id", "city", "kind"]} for x in documents],
        )

    def search(self, query, city=None, k=5):
        with self.lock:
            collection = self.collection()
            if not collection.count():
                raise DomainError("CORPUS_NOT_READY", "Build the real embedding index first", 503)
            vector = next(self.encoder().query_embed([query])).tolist()
            where = {"city": {"$in": [city, "ALL"]}} if city else None
            result = collection.query(
                query_embeddings=[vector],
                n_results=k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
            return [
                {"id": identifier, "text": text, **metadata, "distance": round(distance, 5)}
                for identifier, text, metadata, distance in zip(
                    result["ids"][0],
                    result["documents"][0],
                    result["metadatas"][0],
                    result["distances"][0],
                    strict=True,
                )
            ]

    async def retrieve_and_refine(self, request, providers, budget):
        all_results = {}
        rounds = []
        for city in request["cities"][:3]:
            query = f"{city} group trip cultural activities"
            for attempt in range(3):
                records = await asyncio.to_thread(self.search, query, city, 5)
                for record in records:
                    all_results[record["id"]] = record
                # Require both numerical-policy and schedule context, not merely a close vector.
                kinds = {x["kind"] for x in records}
                relevant = "price" in kinds and "schedule" in kinds
                round_ = {
                    "city": city,
                    "round": attempt + 1,
                    "query": query,
                    "relevant": relevant,
                    "source_ids": [x["source_id"] for x in records],
                    "chunks": records,
                    "retrieval_hash": digest(records),
                }
                rounds.append(round_)
                await budget.store.event(budget.episode, "retrieval", round_)
                if relevant or attempt == 2:
                    break
                rewrite = await providers.complete(
                    "query_rewrite",
                    QueryRewrite,
                    {
                        "city": city,
                        "query": query,
                        "missing": sorted({"price", "schedule"} - kinds),
                        "instruction": "Rewrite this PUBLIC city query to find admission costs and opening hours. Include the city code.",
                    },
                    budget,
                )
                query = rewrite.query
                await budget.store.event(budget.episode, "query_rewritten", rewrite.model_dump())
            if len(all_results) >= 16:
                break
        return {"chunks": list(all_results.values()), "rounds": rounds}
