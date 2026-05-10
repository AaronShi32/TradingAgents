"""Daily stock analysis report with Feishu webhook push.

Usage:
    python daily_report.py                    # Analyze all configured tickers
    python daily_report.py --tickers NVDA,AAPL  # Override tickers
    python daily_report.py --dry-run          # Print report without pushing to Feishu
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ─── Configuration ───────────────────────────────────────────────────────────

DEFAULT_TICKERS = ["NVDA", "AAPL", "TSLA", "GOOGL", "MSFT", "META", "AMZN"]

FEISHU_WEBHOOK_URL = os.getenv(
    "FEISHU_WEBHOOK_URL",
    "https://open.feishu.cn/open-apis/bot/v2/hook/2dfb5a72-1167-4eae-879c-e4d325d59ead",
)

# Beijing timezone
BJT = timezone(timedelta(hours=8))


def get_config():
    """Build TradingAgents config for daily report."""
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "copilot"
    config["deep_think_llm"] = "claude-opus-4.7"
    config["quick_think_llm"] = "gpt-4o"
    config["max_debate_rounds"] = 1
    config["output_language"] = "Chinese"
    config["data_vendors"] = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    }
    return config


def analyze_ticker(ta: TradingAgentsGraph, ticker: str, trade_date: str) -> dict:
    """Run analysis for a single ticker and return structured result."""
    logger.info("Analyzing %s for %s...", ticker, trade_date)
    start = time.time()
    try:
        final_state, decision = ta.propagate(ticker, trade_date)
        elapsed = time.time() - start
        logger.info("✓ %s completed in %.1fs", ticker, elapsed)
        return {
            "ticker": ticker,
            "success": True,
            "decision": decision,
            "final_trade_decision": final_state.get("final_trade_decision", ""),
            "elapsed": elapsed,
        }
    except Exception as e:
        elapsed = time.time() - start
        logger.error("✗ %s failed after %.1fs: %s", ticker, elapsed, e)
        return {
            "ticker": ticker,
            "success": False,
            "error": str(e),
            "elapsed": elapsed,
        }


def run_analysis(tickers: list[str], trade_date: str) -> list[dict]:
    """Run analysis for all tickers sequentially."""
    config = get_config()
    ta = TradingAgentsGraph(debug=False, config=config)

    results = []
    for ticker in tickers:
        result = analyze_ticker(ta, ticker, trade_date)
        results.append(result)

    return results


# ─── Report Formatting ───────────────────────────────────────────────────────

def format_report_text(results: list[dict], trade_date: str) -> str:
    """Format results into a readable text report."""
    now = datetime.now(BJT).strftime("%Y-%m-%d %H:%M")
    lines = [f"📊 TradingAgents 日报 | {trade_date}", f"生成时间: {now}", ""]

    for r in results:
        if r["success"]:
            decision = r.get("final_trade_decision", r.get("decision", "N/A"))
            lines.append(f"{'─' * 40}")
            lines.append(f"🏷 {r['ticker']}")
            lines.append(f"{decision}")
            lines.append("")
        else:
            lines.append(f"{'─' * 40}")
            lines.append(f"🏷 {r['ticker']} ❌ 分析失败: {r['error']}")
            lines.append("")

    # Summary
    successful = [r for r in results if r["success"]]
    lines.append(f"{'═' * 40}")
    lines.append(f"✅ 成功: {len(successful)}/{len(results)}")
    total_time = sum(r["elapsed"] for r in results)
    lines.append(f"⏱ 总耗时: {total_time:.0f}s")

    return "\n".join(lines)


def build_feishu_card(results: list[dict], trade_date: str) -> dict:
    """Build a Feishu interactive card message."""
    now = datetime.now(BJT).strftime("%Y-%m-%d %H:%M")

    elements = []

    # Header info
    elements.append({
        "tag": "markdown",
        "content": f"**分析日期**: {trade_date}  |  **生成时间**: {now}",
    })
    elements.append({"tag": "hr"})

    # Each ticker result
    for r in results:
        if r["success"]:
            decision_text = r.get("final_trade_decision", r.get("decision", "N/A"))
            # Truncate if too long for card (Feishu has limits)
            if len(decision_text) > 800:
                decision_text = decision_text[:800] + "\n\n... (详情已截断)"

            elements.append({
                "tag": "markdown",
                "content": f"**🏷 {r['ticker']}**\n{decision_text}",
            })
        else:
            elements.append({
                "tag": "markdown",
                "content": f"**🏷 {r['ticker']}** ❌ 失败: {r['error'][:200]}",
            })
        elements.append({"tag": "hr"})

    # Summary
    successful = [r for r in results if r["success"]]
    total_time = sum(r["elapsed"] for r in results)
    elements.append({
        "tag": "markdown",
        "content": f"✅ 成功 {len(successful)}/{len(results)}  |  ⏱ 总耗时 {total_time:.0f}s",
    })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📊 TradingAgents 日报 | {trade_date}",
                },
                "template": "blue",
            },
            "elements": elements,
        },
    }


# ─── Feishu Push ─────────────────────────────────────────────────────────────

def push_to_feishu(results: list[dict], trade_date: str) -> bool:
    """Push the report to Feishu via webhook."""
    if not FEISHU_WEBHOOK_URL:
        logger.warning("No FEISHU_WEBHOOK_URL configured, skipping push.")
        return False

    payload = build_feishu_card(results, trade_date)

    try:
        resp = requests.post(
            FEISHU_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp_data = resp.json()
        if resp_data.get("code") == 0 or resp_data.get("StatusCode") == 0:
            logger.info("✓ Report pushed to Feishu successfully.")
            return True
        else:
            logger.error("Feishu push failed: %s", resp_data)
            return False
    except Exception as e:
        logger.error("Feishu push error: %s", e)
        return False


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TradingAgents Daily Report")
    parser.add_argument(
        "--tickers", type=str, default=None,
        help="Comma-separated tickers (default: config list)",
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Analysis date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print report without pushing to Feishu",
    )
    args = parser.parse_args()

    # Determine tickers
    tickers = args.tickers.split(",") if args.tickers else DEFAULT_TICKERS
    tickers = [t.strip().upper() for t in tickers]

    # Determine trade date (use previous trading day for pre-market)
    if args.date:
        trade_date = args.date
    else:
        # Use yesterday if before market open, today otherwise
        now_et = datetime.now(timezone(timedelta(hours=-4)))  # US Eastern
        trade_date = now_et.strftime("%Y-%m-%d")

    logger.info("=" * 50)
    logger.info("TradingAgents Daily Report")
    logger.info("Tickers: %s", ", ".join(tickers))
    logger.info("Date: %s", trade_date)
    logger.info("=" * 50)

    # Run analysis
    results = run_analysis(tickers, trade_date)

    # Print report
    report = format_report_text(results, trade_date)
    print("\n" + report)

    # Push to Feishu
    if not args.dry_run:
        push_to_feishu(results, trade_date)
    else:
        logger.info("Dry run — skipping Feishu push.")


if __name__ == "__main__":
    main()
