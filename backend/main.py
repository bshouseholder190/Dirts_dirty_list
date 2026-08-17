"""FastAPI backend for the live trading dashboard."""
import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from runner import RunnerManager
from strategy_loader import load_all_strategies
from evolution import EvolutionEngine
from market_scanner import scan_top50
from paper_trader import PaperTradingSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
STRATEGIES_DIR = os.getenv(
    "STRATEGIES_DIR",
    r"C:\Users\bshou\projects\trading-app\strategies"
)
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# ── App init ──────────────────────────────────────────────────────────────────
app = FastAPI(title="Live Trading Dashboard")

strategies = load_all_strategies(STRATEGIES_DIR)
log.info(f"Loaded {len(strategies)} strategies from {STRATEGIES_DIR}")
for s in strategies:
    log.info(f"  • {s['name']} [{s['ticker']}]")

manager = RunnerManager(strategies, poll_interval=POLL_INTERVAL)
sim_manager = RunnerManager(strategies, poll_interval=60, sim_mode=True)
evo = EvolutionEngine()
paper = PaperTradingSession(strategies)

# Active WebSocket connections
_connections: set[WebSocket] = set()


async def _broadcast(payload: dict):
    dead = set()
    msg = json.dumps(payload)
    for ws in _connections:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _connections.difference_update(dead)


manager.on_event(_broadcast)
sim_manager.on_event(_broadcast)
evo.on_update(_broadcast)
paper.on_event(_broadcast)

# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    asyncio.create_task(manager.start())
    asyncio.create_task(sim_manager.start())
    asyncio.create_task(_state_broadcaster())


@app.post("/api/sim/reset")
async def reset_sim():
    global sim_manager
    sim_manager.stop()
    sim_manager = RunnerManager(strategies, poll_interval=60, sim_mode=True)
    sim_manager.on_event(_broadcast)
    asyncio.create_task(sim_manager.start())
    return {"status": "reset"}

@app.get("/api/sim/strategies")
def get_sim_strategies():
    states = sim_manager.all_states()
    # Add P&L summary per strategy
    for s, runner in zip(states, sim_manager.runners):
        s["sim_capital"] = round(runner.capital, 2)
        s["sim_pnl"] = round(runner.capital - runner.start_capital, 2)
        s["sim_pnl_pct"] = round((runner.capital - runner.start_capital) / runner.start_capital * 100, 2)
    return {"strategies": states}


async def _state_broadcaster():
    while True:
        await asyncio.sleep(10)
        if _connections:
            await _broadcast({"type": "state", "strategies": manager.all_states()})


# ── HTTP endpoints ─────────────────────────────────────────────────────────────
@app.get("/api/strategies")
def get_strategies():
    return {"strategies": manager.all_states()}


# ── Evolution endpoints ───────────────────────────────────────────────────────
@app.post("/api/evolution/seed")
async def evo_seed(ticker: str = "SOUN", population: int = 10):
    evo.seed(ticker, population)
    return evo.state()

@app.post("/api/evolution/run")
async def evo_run():
    asyncio.create_task(evo.run_generation())
    return {"status": "running"}

@app.post("/api/evolution/auto")
async def evo_auto(generations: int = 10):
    asyncio.create_task(evo.auto_evolve(generations))
    return {"status": "auto-evolving", "generations": generations}

@app.post("/api/evolution/stop")
async def evo_stop():
    evo.stop()
    return {"status": "stopped"}

@app.post("/api/evolution/reset")
async def evo_reset():
    evo.reset()
    return evo.state()

@app.get("/api/evolution")
def evo_state():
    return evo.state()


# ── Paper Trading endpoints ───────────────────────────────────────────────────
@app.post("/api/paper/start")
async def paper_start(capital: float = 10000.0, poll_interval: int = 60):
    if paper.running:
        return {"status": "already running"}
    paper.reset(strategies, capital)
    paper.on_event(_broadcast)
    asyncio.create_task(paper.start(poll_interval))
    return {"status": "started", "capital": capital, "strategies": len(strategies)}

@app.post("/api/paper/stop")
async def paper_stop():
    paper.stop()
    return {"status": "stopped"}

@app.post("/api/paper/reset")
async def paper_reset(capital: float = 10000.0):
    paper.reset(strategies, capital)
    paper.on_event(_broadcast)
    return {"status": "reset", "capital": capital}

@app.get("/api/paper/state")
def paper_state():
    return {"accounts": paper.all_states(), "running": paper.running,
            "started_at": paper.started_at}


@app.post("/api/evolution/run-all-strategies")
async def evo_run_all(generations: int = 10, population: int = 10):
    asyncio.create_task(_evolve_all_strategies_compete(generations, population))
    return {"status": "started", "strategies": [f"{s['name']} ({s['ticker']})" for s in strategies]}


@app.get("/api/market/top50")
async def get_top50():
    stocks = await scan_top50()
    return {"stocks": stocks, "scanned_at": datetime.now().isoformat()}


@app.post("/api/evolution/run-market-scan")
async def evo_market_scan(generations: int = 10, population: int = 10, top_n: int = 50):
    asyncio.create_task(_evolve_market_scan(generations, population, top_n))
    return {"status": "scanning", "message": f"Scanning top {top_n} stocks…"}


async def _evolve_market_scan(generations: int, population: int, top_n: int):
    from lessons_writer import append_lessons, update_strategy_params
    from pathlib import Path

    await _broadcast({"type": "market_scan", "status": "scanning",
                      "message": "Fetching top 50 most-traded stocks + sentiment…"})

    stocks = await scan_top50()
    stocks = stocks[:top_n]

    await _broadcast({"type": "market_scan", "status": "ready",
                      "stocks": stocks,
                      "message": f"Found {len(stocks)} stocks. Starting evolution…"})

    results = []
    for i, stock in enumerate(stocks):
        ticker   = stock["ticker"]
        vol_fac  = stock.get("volume_factor", 1.0)
        sent_score = stock.get("sentiment", {}).get("score", 0.0)

        await _broadcast({
            "type": "market_scan",
            "status": "evolving",
            "current": i + 1,
            "total": len(stocks),
            "ticker": ticker,
            "name": stock.get("name", ticker),
            "volume_factor": vol_fac,
            "sentiment_score": sent_score,
        })

        engine = EvolutionEngine()
        engine.seed(ticker, population, vol_fac, sent_score)

        for _ in range(generations):
            await engine.run_generation()
            await asyncio.sleep(0.1)

        bots_state = engine._bots_state()
        history    = engine.history
        best       = bots_state[0] if bots_state else None
        gen_stats  = history[-1] if history else {}

        # Write lessons file
        try:
            path = append_lessons(ticker, engine.generation, bots_state, history)
        except Exception as e:
            log.error(f"[market-scan] lessons error {ticker}: {e}")
            path = None

        result = {
            "ticker": ticker,
            "name": stock.get("name", ticker),
            "price": stock.get("price", 0),
            "change_pct": stock.get("change_pct", 0),
            "volume_factor": vol_fac,
            "sentiment": stock.get("sentiment", {}),
            "best_fitness": gen_stats.get("best", 0),
            "avg_fitness":  gen_stats.get("avg", 0),
            "winning_genome": best["genome"] if best else None,
            "lessons_path": str(path) if path else None,
        }
        results.append(result)

        await _broadcast({"type": "market_scan", "status": "ticker_done", **result})
        await asyncio.sleep(0.5)

    # Sort by best fitness descending
    results.sort(key=lambda x: x["best_fitness"], reverse=True)

    await _broadcast({
        "type": "market_scan",
        "status": "complete",
        "results": results,
        "message": f"Done! {len(results)} stocks evolved. Top pick: {results[0]['ticker']} ({results[0]['best_fitness']:+.1f}%)",
    })


async def _evolve_all_strategies_compete(generations: int, population: int):
    """
    Run all 5 strategies competitively:
    - Each strategy gets its own bot population per generation
    - After each generation, winners BREED ACROSS strategies
    - Bottom performers DIE and are replaced by children of top performers
    - Lessons written after all generations complete
    """
    from lessons_writer import append_lessons, update_strategy_params, find_strategy_file
    from evolution import EvolutionEngine, Genome, Bot
    import random

    if not strategies:
        return

    await _broadcast({
        "type": "evo_all_progress",
        "status": "start",
        "message": f"Starting competitive evolution — {len(strategies)} strategies, {generations} generations",
        "total": len(strategies),
    })

    # Seed one engine per strategy
    engines = []
    for s in strategies:
        engine = EvolutionEngine()
        engine.seed(s["ticker"], population)
        engine._strategy_name = s["name"]
        engine._strategy_file = s.get("file", "")
        engines.append(engine)
        await _broadcast({
            "type": "evo_all_progress",
            "status": "seeded",
            "name": s["name"],
            "ticker": s["ticker"],
        })

    # Run generations competitively
    for gen in range(generations):
        gen_results = []

        # Each engine runs one generation
        for engine in engines:
            result = await engine.run_generation()
            gen_results.append({
                "engine": engine,
                "name": engine._strategy_name,
                "ticker": engine.bots[0].genome.ticker if engine.bots else "?",
                "best": engine.history[-1]["best"] if engine.history else 0,
                "avg":  engine.history[-1]["avg"]  if engine.history else 0,
            })

        # Sort strategies by best fitness this generation
        gen_results.sort(key=lambda x: x["best"], reverse=True)
        top_engines    = [r["engine"] for r in gen_results[:max(1, len(gen_results)//2)]]
        bottom_engines = [r["engine"] for r in gen_results[max(1, len(gen_results)//2):]]

        # Cross-breed: top engine winners breed INTO bottom engines
        all_top_bots = []
        for eng in top_engines:
            top_half = eng.bots[:max(1, len(eng.bots)//2)]
            all_top_bots.extend(top_half)

        for eng in bottom_engines:
            # Kill bottom half of this engine's population
            keep = max(2, len(eng.bots)//2)
            survivors = eng.bots[:keep]
            # Fill with cross-bred children from top engines
            while len(eng.bots) < population:
                if len(all_top_bots) >= 2:
                    parents = random.sample(all_top_bots, 2)
                    child_genome = Genome.crossover(
                        parents[0].genome, parents[1].genome
                    ).mutate()
                    # Adapt to this engine's ticker
                    child_genome.ticker = eng.bots[0].genome.ticker if eng.bots else parents[0].genome.ticker
                    child = Bot(id=eng._next_id, genome=child_genome, generation=gen+1)
                    eng._next_id += 1
                    eng.bots.append(child)
                else:
                    break

        # Broadcast generation results
        await _broadcast({
            "type": "evo_all_progress",
            "status": "generation",
            "generation": gen + 1,
            "total_generations": generations,
            "results": [
                {
                    "name": r["name"],
                    "ticker": r["ticker"],
                    "best": r["best"],
                    "avg": r["avg"],
                    "rank": i + 1,
                    "survived": r["engine"] in top_engines,
                }
                for i, r in enumerate(gen_results)
            ],
        })
        await asyncio.sleep(0.3)

    # Final results + write lessons
    final = []
    for engine in engines:
        bots_state = engine._bots_state()
        if not bots_state:
            continue
        winner = bots_state[0]
        # Write lessons
        try:
            path = append_lessons(engine.bots[0].genome.ticker, engine.generation, bots_state, engine.history)
        except Exception:
            path = None
        # Update strategy params with winning genome
        strat_file = engine._strategy_file
        if strat_file and Path(strat_file).exists():
            try:
                update_strategy_params(strat_file, winner["genome"])
            except Exception:
                pass
        gen_stats = engine.history[-1] if engine.history else {}
        final.append({
            "name": engine._strategy_name,
            "ticker": winner["genome"]["ticker"],
            "best_fitness": gen_stats.get("best", 0),
            "winning_genome": winner["genome"],
            "lessons_path": str(path) if path else None,
        })

    final.sort(key=lambda x: x["best_fitness"], reverse=True)
    await _broadcast({
        "type": "evo_all_progress",
        "status": "complete",
        "results": final,
        "message": f"Done! Winner: {final[0]['name']} ({final[0]['best_fitness']:+.1f}%)" if final else "Complete",
    })


async def _evolve_all_strategies(generations: int, population: int):
    from lessons_writer import append_lessons, update_strategy_params, find_strategy_file
    from evolution import EvolutionEngine

    total = len(strategies)
    for i, strategy in enumerate(strategies):
        ticker = strategy["ticker"]
        name   = strategy["name"]
        log.info(f"[evo-all] {i+1}/{total} evolving {name} ({ticker})")

        await _broadcast({
            "type": "evo_all_progress",
            "current": i + 1,
            "total": total,
            "ticker": ticker,
            "name": name,
            "status": "running",
        })

        engine = EvolutionEngine()
        engine.seed(ticker, population)

        for _ in range(generations):
            await engine.run_generation()
            await asyncio.sleep(0.2)

        bots_state = engine._bots_state()
        history    = engine.history

        # Write lessons
        try:
            path = append_lessons(ticker, engine.generation, bots_state, history)
            log.info(f"[evo-all] lessons → {path}")
        except Exception as e:
            log.error(f"[evo-all] lessons error: {e}")
            path = None

        # Update strategy .md params with winning genome
        winning_genome = bots_state[0]["genome"] if bots_state else None
        updated_params = False
        if winning_genome:
            strat_path = find_strategy_file(ticker) or strategy.get("file")
            if strat_path and Path(strat_path).exists():
                try:
                    update_strategy_params(strat_path, winning_genome)
                    updated_params = True
                    log.info(f"[evo-all] params updated → {strat_path}")
                except Exception as e:
                    log.error(f"[evo-all] param update error: {e}")

        gen_stats = history[-1] if history else {}
        await _broadcast({
            "type": "evo_all_progress",
            "current": i + 1,
            "total": total,
            "ticker": ticker,
            "name": name,
            "status": "done",
            "best_fitness": gen_stats.get("best", 0),
            "avg_fitness":  gen_stats.get("avg", 0),
            "winning_genome": winning_genome,
            "lessons_path": str(path) if path else None,
            "updated_params": updated_params,
        })

        await asyncio.sleep(1)

    await _broadcast({
        "type": "evo_all_progress",
        "status": "complete",
        "total": total,
        "message": f"All {total} strategies evolved and updated",
    })


@app.get("/api/strategies/{strategy_id}")
def get_strategy(strategy_id: str):
    for r in manager.runners:
        if r.id == strategy_id:
            return r.state()
    return {"error": "not found"}, 404


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _connections.add(websocket)
    log.info(f"[ws] client connected ({len(_connections)} total)")

    # Send current state immediately on connect
    await websocket.send_text(json.dumps({
        "type": "state",
        "strategies": manager.all_states()
    }))

    try:
        while True:
            await websocket.receive_text()  # keep alive / ping
    except WebSocketDisconnect:
        _connections.discard(websocket)
        log.info(f"[ws] client disconnected ({len(_connections)} total)")


# ── Serve frontend ─────────────────────────────────────────────────────────────
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))
