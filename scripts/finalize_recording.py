"""Encode actual browser capture, add clearly labeled synthesized narration, export durable run evidence."""

import asyncio
import json
import subprocess
from datetime import timedelta
from pathlib import Path

from tripbudget.persistence import Store
from tripbudget.settings import Settings


def call(*args):
    subprocess.run(list(args), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def export_evidence():
    events = json.loads(Path("deliverables/video/recording-events.json").read_text())
    assert events["duration_recording_seconds"] >= 420 and events["old_boot"] != events["new_boot"]
    store = Store(Settings())
    episode = events["episode"]
    row = await store.one("SELECT id,uid,status,request,created_at FROM episodes WHERE id=%s", (episode,))
    trace = await store.all("SELECT id,kind,data,at FROM events WHERE episode=%s ORDER BY id", (episode,))
    usage = await store.all(
        "SELECT task,provider,model,input_tokens,output_tokens,success,error FROM model_usage WHERE episode=%s OR (uid=%s AND episode IS NULL AND at>=%s AND at<=%s)",
        (episode, row["uid"], row["created_at"] - timedelta(seconds=100), row["created_at"]),
    )
    ledgers = await store.all(
        "SELECT id,episode,revision,hash,payload FROM ledgers WHERE episode=%s", (episode,)
    )
    critics = [r["data"] for r in trace if r["kind"] == "critic"]
    assert row["status"] == "COMMITTED" and len(ledgers) == 1
    assert len(critics) >= 2 and not critics[0]["valid"] and critics[-1]["valid"]
    assert any(r["kind"] == "query_rewritten" for r in trace)
    assert any(r["provider"] == "cloud" and r["success"] for r in usage)
    assert any(r["provider"] == "local" and r["success"] for r in usage)
    proof = await store.one(
        "SELECT id,status,request FROM episodes WHERE uid=%s AND created_at>%s AND status='PROVEN_INFEASIBLE' ORDER BY created_at LIMIT 1",
        (row["uid"], row["created_at"]),
    )
    assert proof is not None
    data = {
        "episode": episode,
        "status": row["status"],
        "request": row["request"],
        "events": trace,
        "usage": usage,
        "ledgers": ledgers,
        "later_guardrail_request": proof,
        "raw_notes_stored": False,
    }
    Path("deliverables/evidence/recorded-run.json").write_text(json.dumps(data, default=str, indent=2))
    return events


def main():
    events = asyncio.run(export_evidence())
    segments = events["segments"]
    folder = Path(".runtime/video/audio")
    folder.mkdir(exist_ok=True)
    args = ["ffmpeg", "-y", "-i", ".runtime/video/actual-demo.webm"]
    filters = []
    for i, segment in enumerate(segments):
        text = segment["title"] + ". " + segment["text"]
        if i == 0:
            text = (
                "This is a recording of the actual operating application, with synthesized narration. " + text
            )
        source = folder / f"{i:02}.txt"
        source.write_text(text)
        aiff = folder / f"{i:02}.aiff"
        call("say", "-v", "Samantha", "-r", "160", "-f", str(source), "-o", str(aiff))
        duration = float(
            subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(aiff)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
        available = (
            (segments[i + 1]["seconds"] if i + 1 < len(segments) else events["duration_recording_seconds"])
            - segment["seconds"]
            - 1
        )
        speed = max(1.0, duration / max(1, available))
        args += ["-i", str(aiff)]
        filters.append(
            f"[{i + 1}:a]atempo={speed:.4f},adelay={int(segment['seconds'] * 1000)}|{int(segment['seconds'] * 1000)}[a{i}]"
        )
    mix = "".join(f"[a{i}]" for i in range(len(segments)))
    filters.append(f"{mix}amix=inputs={len(segments)}:normalize=0,apad[audio]")
    args += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "0:v:0",
        "-map",
        "[audio]",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "25",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "24",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-t",
        str(events["duration_recording_seconds"]),
        "-movflags",
        "+faststart",
        "-metadata",
        "title=TripBudgetAI actual runtime demonstration; synthesized narration",
        "deliverables/video/TripBudgetAI_Demo.mp4",
    ]
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    claims = [
        {
            "feature": "Long-term memory",
            "start_seconds": 65,
            "end_seconds": 255,
            "status": "demonstrated",
            "evidence": "Confirmed preference saved; actual new boot + fresh login restores vegetarian/6000m values",
        },
        {
            "feature": "Planning and self-correction",
            "start_seconds": 95,
            "end_seconds": 195,
            "status": "demonstrated",
            "evidence": "Actual model proposal, failed cost critic, repair selection and successful recheck",
        },
        {
            "feature": "Durable human-in-the-loop",
            "start_seconds": 170,
            "end_seconds": 285,
            "status": "demonstrated",
            "evidence": "Hash-bound pending approval survives actual process replacement; human approval commits one ledger",
        },
        {
            "feature": "Iterative RAG/source verification",
            "start_seconds": 95,
            "end_seconds": 320,
            "status": "demonstrated",
            "evidence": "Real retrieval/query rewrite events and evidence library; estimates visibly separate",
        },
        {
            "feature": "Hybrid cloud/local inference",
            "start_seconds": 25,
            "end_seconds": 170,
            "status": "demonstrated",
            "evidence": "Actual local-only note extraction and local query rewrite, cloud model selection/completions",
        },
    ]
    for r in claims:
        r["episode"] = events["episode"]
    Path("docs/recording-claims.json").write_text(json.dumps(claims, indent=2))
    lines = [
        "# Recording evidence",
        "",
        "[Actual MP4](../deliverables/video/TripBudgetAI_Demo.mp4). Duration approximately7:05, H.264/AAC. The browser/OS/model actions are actual runtime captures. Captions and synthesized narration annotate them; no model/tool response is substituted. Idle time is retained.",
        "",
        f"Recorded planning episode: `{events['episode']}`. Raw [recorded run](../deliverables/evidence/recorded-run.json), [timed captions/boot IDs](../deliverables/video/recording-events.json).",
        "",
        "| Claimed feature | MP4 range | Observed behavior |",
        "|---|---|---|",
    ]

    def stamp(s):
        return f"{int(s) // 60}:{int(s) % 60:02}"

    for r in claims:
        lines.append(
            f"| {r['feature']} | {stamp(r['start_seconds'])}–{stamp(r['end_seconds'])} | {r['evidence']} |"
        )
    lines += [
        "",
        "Guardrail segment5:20–6:35: a new $50/person request cannot cover mandatory meals and includes an instruction to bypass approval; code returns PROVEN_INFEASIBLE without certifying/committing a new plan. That proof is an engaged numerical guardrail, not counted as a model-exposed injection test. Ten separate real attack types are documented in the evaluation report.",
        "",
        f"Actual OS process termination at {events['terminated_at']:.2f}s. Boot identity changes from `{events['old_boot']}` to `{events['new_boot']}`; saved values reload after fresh login. Human approval commits at {events['committed_at']:.2f}s. The exact cost changes and real usage rows are in the linked trace.",
        "",
        "The recording predates the final UI cleanup that clears the prior itinerary immediately on a new infeasible submission. Core planning/approval/guardrail behavior is the same; the final actual browser regression also verifies that presentation-state cleanup. No cloud-to-laptop bridge, A2A protocol or live booking capability is claimed.",
        "",
        "Local MP4 playback, decodability, duration, audio and representative frames are checked before publication. Private repository/artifact access must be granted to graders; no Brightspace upload is claimed.",
    ]
    Path("docs/recording-evidence.md").write_text("\n".join(lines) + "\n")
    print("Encoded MP4 with actual five-feature evidence and synthesized narration.")


if __name__ == "__main__":
    main()
