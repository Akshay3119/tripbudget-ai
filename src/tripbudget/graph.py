import asyncio
import time
from datetime import timedelta
from typing import Literal, TypedDict

from pydantic import Field, create_model

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from psycopg.types.json import Jsonb

from .budget import infeasibility_reason, mandatory_lower_bound
from .errors import DomainError
from .planning import build_proposal, enumerate_repairs, validate_for_commit
from .resources import Budget
from .schemas import PlanChoice, RepairSelection, SpecialistResult, StrictModel, TripRequest, utcnow


class State(TypedDict, total=False):
    episode: str
    uid: str
    request: dict
    revision: int
    pass_index: int
    repair_enabled: bool
    simulate_429: bool
    retrieval: dict
    choice: dict
    proposal: dict
    observations: list
    approval_id: str
    outcome: str
    ledger_id: str
    repair_candidates: list


class Workflow:
    def __init__(self, settings, store, catalog, corpus, providers):
        self.s, self.store, self.catalog, self.corpus, self.providers = (
            settings,
            store,
            catalog,
            corpus,
            providers,
        )
        self.gate = asyncio.Semaphore(2)

    def build_graph(self, conn, budget):
        async def load(state):
            request = TripRequest.model_validate(state["request"])
            saved = await self.store.preferences(state["uid"], request.group_id)
            if request.use_saved_preferences and saved["data"]:
                for traveler in request.travelers:
                    traveler.diet = saved["data"]["diet"]
                    traveler.maximum_walk_meters = min(
                        traveler.maximum_walk_meters, saved["data"]["maximum_walk_meters"]
                    )
                await self.store.execute(
                    "UPDATE episodes SET request=%s WHERE id=%s",
                    (Jsonb(request.model_dump(mode="json")), state["episode"]),
                )
            await self.store.event(
                state["episode"],
                "preferences_loaded",
                {
                    "version": saved["version"],
                    "applied": bool(saved["data"] and request.use_saved_preferences),
                    "values": saved["data"],
                },
            )
            return {"request": request.model_dump(mode="json"), "observations": [], "pass_index": 0}

        async def retrieve(state):
            request = TripRequest.model_validate(state["request"])
            for identifier in request.required_activities:
                self.catalog.option(identifier, utcnow())
            self.catalog.compact(request.cities, utcnow())
            for origin, destination in zip(request.cities, request.cities[1:], strict=False):
                self.catalog.route(origin, destination, utcnow())
            proof = infeasibility_reason(request, self.catalog)
            if proof:
                await self.store.event(state["episode"], "infeasibility_proof", proof)
                raise DomainError(
                    "PROVEN_INFEASIBLE", "A mandatory cost or walking lower bound exceeds the constraint"
                )
            result = await self.corpus.retrieve_and_refine(state["request"], self.providers, budget)
            return {"retrieval": result}

        async def supervisor(state):
            request = state["request"]
            options = self.catalog.compact(request["cities"], utcnow())
            previous = state.get("proposal", {})
            task = "repair" if state.get("pass_index", 0) else "supervisor"
            candidates = state.get("repair_candidates", []) if task == "repair" else []
            if candidates:
                selection_schema = create_model(
                    "RepairMenuSelection",
                    __base__=RepairSelection,
                    candidate_index=(int, Field(ge=0, lt=len(candidates))),
                )
                selection = await self.providers.complete(
                    task,
                    selection_schema,
                    {
                        "instruction": "Select one independently validated repair candidate by its zero-based index. "
                        "Explain how it addresses the critic's violations. Prices and caps are immutable.",
                        "constraints": request,
                        "violations": previous.get("violations", []),
                        "candidates": candidates,
                    },
                    budget,
                    simulate_429=state.get("simulate_429", False),
                )
                choice = PlanChoice.model_validate(candidates[selection.candidate_index]["choice"])
                choice.explanation = selection.explanation
                await self.store.event(state["episode"], "repair_selected", selection.model_dump())
            else:
                # Fixed properties and per-city ID enums close the open-dictionary ambiguity.
                fields = {}
                for city in request["cities"]:
                    identifiers = tuple(o["id"] for o in options if o["city"] == city)
                    fields[city] = (
                        list[Literal[identifiers]],
                        Field(min_length=1, max_length=len(identifiers)),
                    )
                activity_schema = create_model("CityActivities", __base__=StrictModel, **fields)
                choice_schema = create_model(
                    "ContextualPlanChoice", __base__=PlanChoice, activities=(activity_schema, ...)
                )
                answer = await self.providers.complete(
                    task,
                    choice_schema,
                    {
                        "instruction": "Propose a balanced complete trip. Include all supplied activity IDs for each "
                        "requested city ordered by preference. Choose standard or economy lodging and one or two "
                        "activities/day. All mandatory costs and the 10% buffer must fit every cap. "
                        "Never change caps or prices. Activity object keys must exactly match requested city codes.",
                        "constraints": request,
                        "catalog": options,
                        "prior_violations": previous.get("violations", []),
                        "observations": state.get("observations", []),
                    },
                    budget,
                    simulate_429=state.get("simulate_429", False),
                )
                choice = PlanChoice.model_validate(answer.model_dump())
            # Only documented city keys and catalog IDs are accepted by the assembler.
            if set(choice.activities) != set(request["cities"]):
                raise DomainError("INVALID_OPTION", "Supervisor must provide exactly the requested cities")
            await self.store.event(
                state["episode"],
                "plan_proposed",
                {
                    "pass": state.get("pass_index", 0) + 1,
                    "choice": choice.model_dump(),
                    "expected_cost_cents": choice.expected_cost_cents,
                },
            )
            return {"choice": choice.model_dump()}

        def specialist(name, instruction):
            async def node(state):
                compact = self.catalog.compact(state["request"]["cities"], utcnow())
                # Documents are untrusted actual retrieval results, not executable instructions.
                chunks = [{"id": c["id"], "text": c["text"]} for c in state["retrieval"]["chunks"][:6]]
                try:
                    result = await self.providers.complete(
                        name,
                        SpecialistResult,
                        {
                            "specialty": instruction,
                            "constraints": state["request"],
                            "proposal": state["choice"],
                            "catalog": [{k: o[k] for k in ("id", "city", "price_cents")} for o in compact],
                            "untrusted_retrieved_documents": chunks,
                            "instruction": "Inspect this proposal in your specialty using the actual option data. "
                            "Return only activity IDs appearing in catalog.id, or an empty list when none are relevant. Route codes and lodging names are not activity IDs. Return a concise observation. No side effects.",
                        },
                        budget,
                        simulate_429=state.get("simulate_429", False),
                    )
                except DomainError as exc:
                    if exc.code not in {"PROVIDER_UNAVAILABLE", "LOCAL_UNAVAILABLE"}:
                        raise
                    # An unavailable advisory worker cannot certify or alter any authoritative fact.
                    await self.store.event(
                        state["episode"], "specialist_unavailable", {"agent": name, "error": exc.code}
                    )
                    observation = {
                        "agent": name,
                        "option_ids": [],
                        "observation": "Advisory model unavailable; deterministic checks still required.",
                        "available": False,
                    }
                    return {"observations": [*state.get("observations", []), observation]}
                valid_ids = {x["id"] for x in compact}
                invalid = [x for x in result.option_ids if x not in valid_ids]
                if invalid:
                    await self.store.event(
                        state["episode"], "advisory_ids_rejected", {"agent": name, "ids": invalid}
                    )
                    result.option_ids = [x for x in result.option_ids if x in valid_ids]
                # Specialists have no write authority; their prose never supplies prices or approval.
                observation = {"agent": name, **result.model_dump()}
                await self.store.event(state["episode"], "specialist_observation", observation)
                return {"observations": [*state.get("observations", []), observation]}

            return node

        async def assemble(state):
            episode = await self.store.owned_episode(state["episode"], state["uid"])
            request = TripRequest.model_validate(state["request"])
            choice = PlanChoice.model_validate(state["choice"])
            proposal = build_proposal(request, choice, self.catalog, episode["revision"])
            await self.store.event(
                state["episode"],
                "catalog_facts_read",
                {"facts": proposal["facts_read"], "digest": self.catalog.sha256},
            )
            await self.store.event(
                state["episode"],
                "critic",
                {
                    "pass": state.get("pass_index", 0) + 1,
                    "valid": proposal["valid"],
                    "total_cents": proposal["total_cents"],
                    "traveler_totals": proposal["traveler_totals"],
                    "violations": proposal["violations"],
                    "expected_cost_cents": choice.expected_cost_cents,
                },
            )
            candidates = enumerate_repairs(request, self.catalog) if not proposal["valid"] else []
            if candidates:
                await self.store.event(
                    state["episode"], "repair_options_computed", {"candidates": candidates}
                )
            return {"proposal": proposal, "revision": episode["revision"], "repair_candidates": candidates}

        def after_critic(state):
            if state["proposal"]["valid"]:
                return "persist"
            if state.get("repair_enabled", True) and state.get("pass_index", 0) < 2:
                return "repair"
            return "failed"

        async def repair(state):
            return {"pass_index": state.get("pass_index", 0) + 1}

        async def failed(state):
            request = TripRequest.model_validate(state["request"])
            lower = mandatory_lower_bound(request)
            proof = any(t.budget_cents < lower for t in request.travelers)
            code = "PROVEN_INFEASIBLE" if proof else "NO_FEASIBLE_PLAN_FOUND"
            await self.store.execute("UPDATE episodes SET status=%s WHERE id=%s", (code, state["episode"]))
            await self.store.event(
                state["episode"], "terminal", {"outcome": code, "meal_lower_bound_cents": lower}
            )
            return {"outcome": code}

        async def persist(state):
            episode = await self.store.owned_episode(state["episode"], state["uid"])
            evidence_expiry = min(
                [utcnow() + timedelta(minutes=30), episode["created_at"] + timedelta(hours=24)]
                + [
                    __import__("datetime").datetime.fromisoformat(
                        self.catalog.activities[x["id"]]["expires_at"]
                    )
                    for x in state["proposal"]["facts_read"]
                ]
            )
            approval = await self.store.persist_proposal(
                state["episode"], state["uid"], state["revision"], state["proposal"], evidence_expiry
            )
            await self.store.event(
                state["episode"],
                "approval_pending",
                {
                    "approval_id": approval["id"],
                    "revision": approval["revision"],
                    "hash": approval["hash"],
                    "expires_at": approval["expires_at"].isoformat(),
                },
            )
            return {"approval_id": approval["id"], "outcome": "PENDING_APPROVAL"}

        def approval(state):
            response = interrupt({"approval_id": state["approval_id"], "revision": state["revision"]})
            # A resume payload is only a pointer. Authority is reread from the server decision row.
            if response.get("approval_id") != state["approval_id"]:
                raise DomainError("APPROVAL_REQUIRED", "Resume does not match the pending approval", 409)
            return {}

        async def dispatch(state):
            row = await self.store.one(
                "SELECT * FROM approvals WHERE id=%s AND uid=%s", (state["approval_id"], state["uid"])
            )
            if not row or row["status"] not in {"DECIDED", "CONSUMED"}:
                raise DomainError("APPROVAL_REQUIRED", "No persisted human decision", 409)
            action = row["decision"]["action"]
            if action == "approve":
                ledger = await self.store.commit_approved(
                    state["uid"], state["approval_id"], lambda p, r: validate_for_commit(p, r, self.catalog)
                )
                return {"outcome": "COMMITTED", "ledger_id": ledger["id"]}
            if action == "cancel":
                await self.store.execute(
                    "UPDATE episodes SET status='CANCELLED' WHERE id=%s", (state["episode"],)
                )
                return {"outcome": "CANCELLED"}
            request = await self.store.change_constraints(state["episode"], state["uid"], row["decision"])
            return {
                "request": request,
                "pass_index": 0,
                "observations": [],
                "proposal": {},
                "outcome": "REPLAN",
            }

        builder = StateGraph(State)
        for name, function in {
            "load": load,
            "retrieve": retrieve,
            "supervisor": supervisor,
            "transit": specialist(
                "transit_specialist", "Transit windows, station transfers, walking and gateway times"
            ),
            "lodging": specialist(
                "lodging_specialist", "Room occupancy, all-in nightly rates, meal and dietary coverage"
            ),
            "attractions": specialist(
                "attractions_specialist", "Admission facts, source consistency, holiday closures"
            ),
            "assemble": assemble,
            "repair": repair,
            "failed": failed,
            "persist": persist,
            "approval": approval,
            "dispatch": dispatch,
        }.items():
            builder.add_node(name, function)
        builder.add_edge(START, "load")
        for a, b in [
            ("load", "retrieve"),
            ("retrieve", "supervisor"),
            ("supervisor", "transit"),
            ("transit", "lodging"),
            ("lodging", "attractions"),
            ("attractions", "assemble"),
            ("repair", "supervisor"),
            ("persist", "approval"),
            ("approval", "dispatch"),
        ]:
            builder.add_edge(a, b)
        builder.add_conditional_edges("assemble", after_critic)
        builder.add_conditional_edges(
            "dispatch", lambda state: "supervisor" if state["outcome"] == "REPLAN" else END
        )
        builder.add_edge("failed", END)
        saver = AsyncPostgresSaver(conn)
        # The official saver and business operations must serialize their use of this one session.
        saver.lock = self.store.current_lock.get()
        return builder.compile(checkpointer=saver)

    async def run(self, episode, uid, options):
        async with self.gate, self.store.invocation(episode, uid) as conn:
            row = await self.store.owned_episode(episode, uid)
            if row["status"] in {"COMMITTED", "CANCELLED", "PROVEN_INFEASIBLE", "NO_FEASIBLE_PLAN_FOUND"}:
                return {"outcome": row["status"]}
            # A killed process leaves its start marker. Charge elapsed wall time conservatively on recovery.
            await self.store.execute(
                "UPDATE episodes SET active_ms=active_ms+CASE WHEN active_started_at IS NULL THEN 0 "
                "ELSE GREATEST(0,EXTRACT(EPOCH FROM (now()-active_started_at))*1000)::bigint END, "
                "active_started_at=NULL WHERE id=%s",
                (episode,),
            )
            budget = Budget(self.store, episode, uid)
            graph = self.build_graph(conn, budget)
            config = {"configurable": {"thread_id": episode}, "recursion_limit": 64}
            snapshot = await graph.aget_state(config)
            if not snapshot.values:
                inp = {
                    "episode": episode,
                    "uid": uid,
                    "request": row["request"],
                    "revision": row["revision"],
                    "pass_index": 0,
                    "repair_enabled": options.repair_enabled,
                    "simulate_429": options.simulate_cloud_429,
                }
            elif snapshot.interrupts:
                pending = await self.store.one(
                    "SELECT * FROM approvals WHERE id=%s", (snapshot.values["approval_id"],)
                )
                if pending["status"] == "PENDING":
                    return {"outcome": "PENDING_APPROVAL"}
                inp = Command(resume={"approval_id": pending["id"]})
            else:
                inp = None
            await self.store.execute(
                "UPDATE episodes SET status='RUNNING',active_started_at=now() WHERE id=%s", (episode,)
            )
            started = time.monotonic()
            try:
                async with asyncio.timeout(max(0.1, await budget.remaining_seconds())):
                    result = await graph.ainvoke(inp, config, durability="sync")
                return {
                    "outcome": result.get("outcome", "PENDING_APPROVAL"),
                    "ledger_id": result.get("ledger_id"),
                }
            except DomainError as exc:
                await self.store.execute("UPDATE episodes SET status=%s WHERE id=%s", (exc.code, episode))
                await self.store.event(episode, "terminal", {"outcome": exc.code, "message": exc.message})
                raise
            except TimeoutError:
                await self.store.execute(
                    "UPDATE episodes SET status='RESOURCE_LIMIT' WHERE id=%s", (episode,)
                )
                raise DomainError("RESOURCE_LIMIT", "Active execution deadline reached") from None
            finally:
                elapsed = int((time.monotonic() - started) * 1000)
                if not conn.closed:
                    await self.store.execute(
                        "UPDATE episodes SET active_ms=active_ms+%s,active_started_at=NULL,updated_at=now() WHERE id=%s",
                        (elapsed, episode),
                    )
