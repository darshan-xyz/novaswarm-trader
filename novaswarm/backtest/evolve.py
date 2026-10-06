"""Self-Evolving Strategy Loop — the AI learns and improves autonomously.

The complete cycle:
    1. BACKTEST current strategy on recent data
    2. EVALUATE metrics (Sharpe, WFE, Monte Carlo)
    3. ADAPT parameters if performance drops
    4. VALIDATE via walk-forward + Monte Carlo
    5. DEPLOY if validated, REJECT if overfit
    6. REFLECT on what changed and why
    7. PERSIST everything to Postgres

Usage::

    from novaswarm.backtest.evolve import run_evolution_cycle

    report = await run_evolution_cycle("RELIANCE")
    # Automatically backtests, validates, adapts, and persists
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class EvolutionReport:
    """Output of a single evolution cycle."""

    symbol: str
    timestamp: str = ""

    # Current strategy performance
    current_sharpe: float = 0.0
    current_win_rate: float = 0.0
    current_return: float = 0.0

    # Walk-forward validation
    wfe_pct: float = 0.0
    wfe_passed: bool = False

    # Monte Carlo robustness
    mc_median_return: float = 0.0
    mc_probability_of_loss: float = 0.0
    mc_robust: bool = False

    # Adaptation
    params_changed: bool = False
    old_params: dict = field(default_factory=dict)
    new_params: dict = field(default_factory=dict)
    improvement: str = ""

    # Decision
    deploy: bool = False
    reason: str = ""

    # Reflection
    lesson: str = ""


async def run_evolution_cycle(
    symbol: str,
    days: int = 180,
) -> EvolutionReport:
    """Run one complete evolution cycle for a symbol.

    Steps:
        1. Fetch historical data
        2. Backtest with current params
        3. Run walk-forward validation
        4. Run Monte Carlo
        5. If underperforming, adapt params
        6. Validate adapted params
        7. Deploy or reject
        8. Persist and reflect

    Args:
        symbol: Stock symbol.
        days: Days of history for backtesting.

    Returns:
        EvolutionReport with full details.
    """
    report = EvolutionReport(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    try:
        from novaswarm.data.pipeline import get_historical_ohlcv
        from novaswarm.backtest.engine import BacktestConfig, run_backtest
        from novaswarm.backtest.walk_forward import walk_forward_test
        from novaswarm.backtest.monte_carlo import run_monte_carlo
        from novaswarm.backtest.persistence import (
            save_backtest_result, save_wfo_result, save_monte_carlo_result,
            save_strategy_params, get_active_params,
        )

        # Fetch data
        now_utc = datetime.now(timezone.utc)
        end_date = now_utc.strftime("%Y-%m-%d")
        start_date = (now_utc - timedelta(days=days)).strftime("%Y-%m-%d")

        df = await asyncio.to_thread(
            get_historical_ohlcv, symbol, start_date, end_date
        )

        if df is None or len(df) < 30:
            report.reason = f"Insufficient data ({len(df) if df is not None else 0} bars)"
            return report

        # Ensure Date column is present for backtest and walk-forward engines
        if "Date" not in df.columns:
            for col in ["date", "datetime", "timestamp"]:
                if col in df.columns:
                    df = df.rename(columns={col: "Date"})
                    break
        if "Date" not in df.columns:
            df = df.reset_index()
            for col in ["Date", "date", "datetime", "index", df.columns[0]]:
                if col in df.columns:
                    df = df.rename(columns={col: "Date"})
                    break

        # Get current params or use defaults
        default_params = {
            "rsi_buy_threshold": 35,
            "rsi_sell_threshold": 65,
            "stop_loss_pct": 3.0,
            "target_pct": 6.0,
            "rsi_period": 14,
        }
        active = get_active_params(symbol, "RSI_MEAN_REVERSION")
        if active and isinstance(active, dict) and "params" in active and isinstance(active["params"], dict):
            params = {**default_params, **active["params"]}
        else:
            params = default_params.copy()
        report.old_params = params.copy()

        # Step 1: Backtest with current params
        config = BacktestConfig(
            stop_loss_pct=float(params.get("stop_loss_pct", 3.0)) / 100.0,
            target_pct=float(params.get("target_pct", 6.0)) / 100.0,
        )

        def generate_signals(data: pd.DataFrame, p: dict | None = None) -> pd.DataFrame:
            current_p = p or params
            data = data.copy()
            period = int(current_p.get("rsi_period", 14))
            buy_th = float(current_p.get("rsi_buy_threshold", 35))
            sell_th = float(current_p.get("rsi_sell_threshold", 65))

            close_s = data["Close"] if "Close" in data.columns else data["close"]
            delta = close_s.diff()
            gain = delta.where(delta > 0, 0.0).rolling(period).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
            with np.errstate(divide="ignore", invalid="ignore"):
                rs = np.where(loss == 0, np.where(gain == 0, 1.0, 100.0), gain / loss)
                rsi = 100.0 - (100.0 / (1.0 + rs))

            date_col = data["Date"] if "Date" in data.columns else (data["date"] if "date" in data.columns else data.index)
            sig_vals = np.where(rsi < buy_th, 1, np.where(rsi > sell_th, -1, 0))
            if len(sig_vals) > period + 1:
                sig_vals[:period + 1] = 0
            else:
                sig_vals[:] = 0
            sig_vals[np.isnan(rsi)] = 0

            return pd.DataFrame({
                "date": date_col,
                "signal": sig_vals,
                "confidence": 50,
            })

        signals = generate_signals(df)
        bt_result = run_backtest(signals, df, config, symbol)

        report.current_sharpe = bt_result.sharpe_ratio
        report.current_win_rate = bt_result.win_rate_pct
        report.current_return = bt_result.total_return_pct

        # Save backtest
        save_backtest_result(
            symbol, "RSI_MEAN_REVERSION",
            bt_result.start_date, bt_result.end_date,
            bt_result.total_return_pct, bt_result.annual_return_pct,
            bt_result.sharpe_ratio, bt_result.sortino_ratio, bt_result.calmar_ratio,
            bt_result.max_drawdown_pct, bt_result.win_rate_pct, bt_result.profit_factor,
            bt_result.total_trades, params,
        )

        # Step 2: Walk-Forward Validation
        try:
            wfo = walk_forward_test(generate_signals, df, symbol,
                                    in_sample_months=3, out_of_sample_months=1,
                                    config=config)
            report.wfe_pct = wfo.wfe_pct
            report.wfe_passed = wfo.wfe_pct >= 50 and wfo.total_periods > 0
            save_wfo_result(symbol, wfo.total_periods, wfo.wfe_pct,
                           wfo.avg_oos_return, wfo.avg_oos_sharpe, wfo.consistency_pct,
                           [{"is_ret": p.in_sample_return, "oos_ret": p.out_sample_return,
                             "wfe": p.wfe} for p in wfo.periods])
        except Exception as e:
            logger.warning("WFO failed: %s", e)

        # Step 3: Monte Carlo
        if bt_result.trades:
            trade_pnls = [t.pnl for t in bt_result.trades]
            mc = run_monte_carlo(trade_pnls, n_simulations=500)
            report.mc_median_return = mc.median_return_pct
            report.mc_probability_of_loss = mc.probability_of_loss_pct
            report.mc_robust = mc.probability_of_loss_pct < 60 and mc.n_simulations > 0
            save_monte_carlo_result(symbol, mc.n_simulations, mc.median_return_pct,
                                   mc.p5_return_pct, mc.p95_return_pct, mc.worst_max_dd_pct,
                                   mc.median_sharpe, mc.probability_of_loss_pct,
                                   mc.probability_of_ruin_pct)

        # Step 4: Adapt if underperforming
        needs_adaptation = (
            bt_result.sharpe_ratio < 0.5
            or bt_result.win_rate_pct < 40
            or bt_result.total_return_pct < -5
        )

        best_sharpe = bt_result.sharpe_ratio
        best_params = params.copy()
        best_result = bt_result

        if needs_adaptation:
            # Try parameter variations
            for rsi_buy in [25, 30, 35, 40]:
                for rsi_sell in [60, 65, 70, 75]:
                    for sl in [2.0, 3.0, 4.0, 5.0]:
                        test_params = {
                            **params,
                            "rsi_buy_threshold": rsi_buy,
                            "rsi_sell_threshold": rsi_sell,
                            "stop_loss_pct": sl,
                        }

                        test_cfg = BacktestConfig(
                            stop_loss_pct=sl / 100.0,
                            target_pct=float(params.get("target_pct", 6.0)) / 100.0,
                        )
                        test_sigs = generate_signals(df, test_params)
                        test_result = run_backtest(test_sigs, df, test_cfg, symbol)

                        if test_result.sharpe_ratio > best_sharpe and test_result.total_trades >= 3:
                            best_sharpe = test_result.sharpe_ratio
                            best_params = test_params.copy()
                            best_result = test_result

            if best_params != params:
                report.params_changed = True
                report.new_params = best_params
                report.improvement = f"Sharpe: {bt_result.sharpe_ratio:.2f} → {best_sharpe:.2f}"
                params = best_params

                # Re-validate adapted parameters via Walk-Forward and Monte Carlo
                adapted_cfg = BacktestConfig(
                    stop_loss_pct=float(best_params.get("stop_loss_pct", 3.0)) / 100.0,
                    target_pct=float(best_params.get("target_pct", 6.0)) / 100.0,
                )
                try:
                    wfo = walk_forward_test(generate_signals, df, symbol,
                                            in_sample_months=3, out_of_sample_months=1,
                                            config=adapted_cfg)
                    report.wfe_pct = wfo.wfe_pct
                    report.wfe_passed = wfo.wfe_pct >= 50 and wfo.total_periods > 0
                    save_wfo_result(symbol, wfo.total_periods, wfo.wfe_pct,
                                   wfo.avg_oos_return, wfo.avg_oos_sharpe, wfo.consistency_pct,
                                   [{"is_ret": p.in_sample_return, "oos_ret": p.out_sample_return,
                                     "wfe": p.wfe} for p in wfo.periods])
                except Exception as e:
                    logger.warning("Adapted WFO failed: %s", e)

                if best_result.trades:
                    trade_pnls = [t.pnl for t in best_result.trades]
                    mc = run_monte_carlo(trade_pnls, n_simulations=500)
                    report.mc_median_return = mc.median_return_pct
                    report.mc_probability_of_loss = mc.probability_of_loss_pct
                    report.mc_robust = mc.probability_of_loss_pct < 60 and mc.n_simulations > 0
                    save_monte_carlo_result(symbol, mc.n_simulations, mc.median_return_pct,
                                           mc.p5_return_pct, mc.p95_return_pct, mc.worst_max_dd_pct,
                                           mc.median_sharpe, mc.probability_of_loss_pct,
                                           mc.probability_of_ruin_pct)

                # Persist adapted backtest result
                save_backtest_result(
                    symbol, "RSI_MEAN_REVERSION",
                    best_result.start_date, best_result.end_date,
                    best_result.total_return_pct, best_result.annual_return_pct,
                    best_result.sharpe_ratio, best_result.sortino_ratio, best_result.calmar_ratio,
                    best_result.max_drawdown_pct, best_result.win_rate_pct, best_result.profit_factor,
                    best_result.total_trades, params,
                )

        # Step 5: Deploy decision
        effective_result = best_result if report.params_changed else bt_result
        is_overfit = (report.wfe_pct > 0 and not report.wfe_passed and not report.mc_robust)
        meets_threshold = (effective_result.sharpe_ratio >= 1.0 or (report.params_changed and effective_result.sharpe_ratio >= 0.5))

        if meets_threshold and not is_overfit:
            report.deploy = True
            report.reason = f"Sharpe {effective_result.sharpe_ratio:.2f}, WFE {report.wfe_pct:.0f}%"
            save_strategy_params(
                symbol, "RSI_MEAN_REVERSION", params,
                {"sharpe": effective_result.sharpe_ratio, "return": effective_result.total_return_pct}
            )
        elif is_overfit:
            report.deploy = False
            report.reason = f"Rejected: Overfit detected (WFE {report.wfe_pct:.0f}% < 50%, MC fragile)"
        else:
            report.deploy = False
            report.reason = f"Sharpe {effective_result.sharpe_ratio:.2f} below threshold"

        # Step 6: Generate reflection
        report.lesson = (
            f"{symbol} RSI strategy: Sharpe={effective_result.sharpe_ratio:.2f}, "
            f"Win={effective_result.win_rate_pct:.0f}%, Return={effective_result.total_return_pct:+.1f}%. "
            f"{'Params adapted: ' + report.improvement if report.params_changed else 'No adaptation needed'}. "
            f"{'Deployed' if report.deploy else 'Not deployed'}: {report.reason}."
        )

        # Notify
        try:
            from novaswarm.notifications import notify

            await notify(
                f"Strategy Evolution: {symbol}\n\n"
                f"Sharpe: {effective_result.sharpe_ratio:.2f}\n"
                f"Win Rate: {effective_result.win_rate_pct:.0f}%\n"
                f"Return: {effective_result.total_return_pct:+.1f}%\n"
                f"WFE: {report.wfe_pct:.0f}%\n"
                f"MC P(Loss): {report.mc_probability_of_loss:.0f}%\n\n"
                f"{'Params adapted' if report.params_changed else 'No changes'}\n"
                f"{'DEPLOYED' if report.deploy else 'NOT DEPLOYED'}: {report.reason}\n\n"
                f"Lesson: {report.lesson}"
            )
        except Exception:
            pass

        return report

    except Exception as exc:
        logger.exception("Evolution cycle failed")
        report.reason = f"Error: {exc}"
        return report


def format_evolution_report(report: EvolutionReport) -> str:
    """Format evolution report for display."""
    lines = [
        f"STRATEGY EVOLUTION: {report.symbol}",
        f"Time: {report.timestamp}",
        "",
        "Current Performance:",
        f"  Sharpe: {report.current_sharpe:.2f}",
        f"  Win Rate: {report.current_win_rate:.0f}%",
        f"  Return: {report.current_return:+.1f}%",
        "",
        "Validation:",
        f"  WFE: {report.wfe_pct:.0f}% {'PASS' if report.wfe_passed else 'FAIL'}",
        f"  MC P(Loss): {report.mc_probability_of_loss:.0f}% {'ROBUST' if report.mc_robust else 'FRAGILE'}",
        "",
    ]

    if report.params_changed:
        lines.append("Adaptation:")
        lines.append(f"  {report.improvement}")
        lines.append(f"  Old: {report.old_params}")
        lines.append(f"  New: {report.new_params}")
    else:
        lines.append("No parameter changes needed.")

    lines.append("")
    lines.append(f"Decision: {'DEPLOYED' if report.deploy else 'NOT DEPLOYED'}")
    lines.append(f"Reason: {report.reason}")
    lines.append("")
    lines.append(f"Lesson: {report.lesson}")

    return "\n".join(lines)
