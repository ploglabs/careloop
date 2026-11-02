"""`careloop seed | serve | simulate`."""

import argparse
import asyncio


def main() -> None:
    parser = argparse.ArgumentParser(prog="careloop")
    sub = parser.add_subparsers(dest="cmd", required=True)
    seed = sub.add_parser("seed", help="Reset the database with synthetic demo data")
    seed.add_argument("--no-history", action="store_true", help="Skip simulated past check-ins")
    serve = sub.add_parser("serve", help="Run the API server")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    sim = sub.add_parser("simulate", help="Run one scripted synthetic call for a plan and print it")
    sim.add_argument("plan_id", type=int)
    sim.add_argument("lines", nargs="+", help="Patient replies, in order")
    sim.add_argument("--llm", action="store_true", help="Use the LLM brain instead of the offline one")
    args = parser.parse_args()

    if args.cmd == "seed":
        from careloop.seed import build

        build(history=not args.no_history)
        print("Seeded synthetic demo data.")
    elif args.cmd == "serve":
        import uvicorn

        uvicorn.run("careloop.api.app:app", host=args.host, port=args.port, reload=args.reload)
    elif args.cmd == "simulate":
        from careloop.agent.simulate import run_scripted_call

        conv, log = asyncio.run(run_scripted_call(args.plan_id, args.lines, offline=not args.llm))
        for who, text in log:
            print(f"{who:>8}: {text}")
        print(f"\nurgency: {conv.session.level.name}  answers: {conv.session.answers}")
