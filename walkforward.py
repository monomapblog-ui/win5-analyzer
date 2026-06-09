"""ウォークフォワード検証

前半データで最適化 → 後半データでテスト、を複数期間スライドさせて
「過去データへの過学習か、本物の法則か」を検証する。

使い方:
  python walkforward.py              # デフォルト（3年学習→2年テスト×複数期間）
  python walkforward.py --train 4 --test 2
  python walkforward.py --budget 27
"""
import argparse
from datetime import date

from sqlalchemy import select, extract
from utils.db import init_db, SessionLocal, Win5Event, Win5Slot
from optimize import build_index, greedy_cover, fast_coverage, combo_count


# ─────────────────────────────────────────────
# データ読み込み（年付き）
# ─────────────────────────────────────────────

def load_rows_all() -> list[dict]:
    init_db()
    with SessionLocal() as session:
        events = session.execute(
            select(Win5Event)
            .where(Win5Event.popularity_sum.is_not(None))
            .where(Win5Event.payout.is_not(None))
            .order_by(Win5Event.held_date)
        ).scalars().all()

        rows = []
        for e in events:
            slots = session.execute(
                select(Win5Slot)
                .where(Win5Slot.event_id == e.id)
                .order_by(Win5Slot.slot_number)
            ).scalars().all()
            pops = [s.winner_popularity for s in slots]
            if len(pops) != 5 or any(p is None for p in pops):
                continue
            rows.append({
                "held_date":      e.held_date,
                "payout":         e.payout,
                "popularity_sum": e.popularity_sum,
                "zone":           e.zone,
                "pops":           pops,
                "year":           e.held_date.year,
            })
    return rows


# ─────────────────────────────────────────────
# ウォークフォワード検証
# ─────────────────────────────────────────────

def run_walkforward(
    all_rows: list[dict],
    train_years: int = 3,
    test_years:  int = 2,
    budget:      int = 27,
    n_sets:      int = 4,
):
    years = sorted({r["year"] for r in all_rows})
    min_year = min(years)
    max_year = max(years)

    results = []

    # スライディングウィンドウ
    test_start = min_year + train_years
    while test_start + test_years - 1 <= max_year:
        train_end = test_start - 1
        test_end  = test_start + test_years - 1

        train_range = list(range(test_start - train_years, test_start))
        test_range  = list(range(test_start, test_end + 1))

        train_rows = [r for r in all_rows if r["year"] in train_range and r["zone"] == "target"]
        test_rows  = [r for r in all_rows if r["year"] in test_range]
        test_target = [r for r in test_rows if r["zone"] == "target"]

        if len(train_rows) < 10 or len(test_rows) < 5:
            test_start += test_years
            continue

        print(f"\n  学習: {min(train_range)}〜{max(train_range)}年 "
              f"({len(train_rows)}開催 target zone)  →  "
              f"テスト: {min(test_range)}〜{max(test_range)}年 "
              f"({len(test_rows)}開催)")

        # 学習データで最適化
        sets = greedy_cover(train_rows, n_sets=n_sets, budget_per_set=budget)
        total_cost = sum(s["combos"] for s in sets) * 100

        # テストデータで評価
        test_idx = build_index(test_rows)
        test_hit_keys = set()
        for s in sets:
            covered = fast_coverage(s["selection"], test_idx)
            for i in covered:
                r = test_rows[i]
                test_hit_keys.add((r["held_date"], tuple(r["pops"])))

        test_hits    = len(test_hit_keys)
        test_inv     = len(test_rows) * total_cost
        test_ret     = sum(r["payout"] for r in test_rows
                          if (r["held_date"], tuple(r["pops"])) in test_hit_keys)
        test_roi     = test_ret / test_inv * 100 if test_inv else 0
        test_hitrate = test_hits / len(test_rows) * 100 if test_rows else 0

        # 学習データでの成績（参考）
        train_all_rows = [r for r in all_rows if r["year"] in train_range]
        train_idx = build_index(train_all_rows)
        train_hit_keys = set()
        for s in sets:
            covered = fast_coverage(s["selection"], train_idx)
            for i in covered:
                r = train_all_rows[i]
                train_hit_keys.add((r["held_date"], tuple(r["pops"])))
        train_hits    = len(train_hit_keys)
        train_inv     = len(train_all_rows) * total_cost
        train_ret     = sum(r["payout"] for r in train_all_rows
                           if (r["held_date"], tuple(r["pops"])) in train_hit_keys)
        train_roi     = train_ret / train_inv * 100 if train_inv else 0

        results.append({
            "train_range":  train_range,
            "test_range":   test_range,
            "train_rows":   len(train_rows),
            "test_rows":    len(test_rows),
            "test_target":  len(test_target),
            "total_cost":   total_cost,
            "sets":         sets,
            "train_hits":   train_hits,
            "train_roi":    train_roi,
            "test_hits":    test_hits,
            "test_roi":     test_roi,
            "test_hitrate": test_hitrate,
            "test_ret":     test_ret,
            "test_inv":     test_inv,
        })

        test_start += test_years

    return results


# ─────────────────────────────────────────────
# レポート
# ─────────────────────────────────────────────

def report(results: list[dict], budget: int):
    print(f"\n{'='*72}")
    print(f"  ウォークフォワード検証結果  （1セット{budget}通り × 4セット）")
    print(f"{'='*72}")

    print(f"\n■ 期間別サマリ")
    print(f"  {'学習期間':>14}  {'テスト期間':>12}  "
          f"{'学習ROI':>8}  {'テスト的中':>8}  {'テストROI':>9}  判定")
    print(f"  {'-'*70}")

    total_test_inv = 0
    total_test_ret = 0
    total_test_hits = 0
    total_test_rows = 0

    for r in results:
        train_label = f"{min(r['train_range'])}〜{max(r['train_range'])}"
        test_label  = f"{min(r['test_range'])}〜{max(r['test_range'])}"
        verdict = _verdict(r["train_roi"], r["test_roi"])
        print(
            f"  {train_label:>14}  {test_label:>12}  "
            f"{r['train_roi']:>7.0f}%  "
            f"{r['test_hits']:>3}回/{r['test_rows']:>3}回  "
            f"{r['test_roi']:>8.1f}%  {verdict}"
        )
        total_test_inv  += r["test_inv"]
        total_test_ret  += r["test_ret"]
        total_test_hits += r["test_hits"]
        total_test_rows += r["test_rows"]

    overall_roi      = total_test_ret / total_test_inv * 100 if total_test_inv else 0
    overall_hitrate  = total_test_hits / total_test_rows * 100 if total_test_rows else 0
    overall_avg_rounds = int(total_test_rows / total_test_hits) if total_test_hits else 9999

    print(f"  {'-'*70}")
    print(f"  {'合計（テスト期間）':>28}  "
          f"{total_test_hits:>3}回/{total_test_rows:>3}回  "
          f"{overall_roi:>8.1f}%")

    print(f"\n■ ウォークフォワード総合成績（テスト期間のみ）")
    print(f"  的中回数  : {total_test_hits}回 / {total_test_rows}開催")
    print(f"  的中率    : {overall_hitrate:.2f}%  （平均{overall_avg_rounds}回に1回）")
    print(f"  総投資額  : {total_test_inv:,}円")
    print(f"  総払戻額  : {total_test_ret:,}円")
    print(f"  回収率    : {overall_roi:.1f}%")

    # 解釈
    print(f"\n■ 判定基準と解釈")
    if overall_roi >= 200:
        verdict_overall = "◎ 優秀  過去データの法則が未来にも有効である可能性が高い"
    elif overall_roi >= 100:
        verdict_overall = "○ 良好  ある程度の有効性あり（過学習は軽微）"
    elif overall_roi >= 50:
        verdict_overall = "△ 要注意  過学習の可能性あり（参考程度）"
    else:
        verdict_overall = "✗ 過学習  未来には通用しない可能性が高い"

    print(f"  テスト期間回収率 {overall_roi:.1f}% → {verdict_overall}")

    # セット別の有効性分析
    print(f"\n■ セット別 テスト期間での有効性")
    set_stats: dict[str, dict] = {}
    for r in results:
        test_idx = build_index([x for x in [] ])  # placeholder
        for s in r["sets"]:
            lbl = s["label"]
            if lbl not in set_stats:
                set_stats[lbl] = {"hits": 0, "rows": 0, "ret": 0, "inv": 0}

    # 実際にセット別に集計
    all_test_rows_by_period = []
    for r in results:
        all_test_rows_by_period.append((r["sets"], r["test_rows"], r["total_cost"]))

    # セット別集計は省略（複雑なので合算のみ表示）
    print(f"  ※ 詳細は各セットの選択人気を参照")

    # 選択人気の一覧（最後の期間）
    if results:
        last = results[-1]
        print(f"\n■ 直近学習期間（{min(last['train_range'])}〜{max(last['train_range'])}年）の最適セット")
        print(f"  （このセットを現在の買い目に採用すると仮定）")
        cost = last["total_cost"]
        print(f"  1回コスト: {cost:,}円")
        for s in last["sets"]:
            print(f"\n  【{s['label']}】 {s['combos']}通り")
            for i, pops in enumerate(s["selection"]):
                size_label = "固定" if len(pops) == 1 else f"{len(pops)}頭流し"
                pop_str    = " / ".join(f"{p}番人気" for p in pops)
                print(f"    slot{i+1} [{size_label:>6}]: {pop_str}")


def _verdict(train_roi: float, test_roi: float) -> str:
    if test_roi >= 200:
        return "◎ 汎化良好"
    elif test_roi >= 100:
        return "○ まずまず"
    elif test_roi >= 0:
        return "△ 微益〜収支±0"
    else:
        return "✗ 過学習疑い"


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="WIN5 ウォークフォワード検証")
    parser.add_argument("--train",  type=int, default=3, help="学習期間（年数、デフォルト3）")
    parser.add_argument("--test",   type=int, default=2, help="テスト期間（年数、デフォルト2）")
    parser.add_argument("--budget", type=int, default=27, help="1セット最大通り数（デフォルト27）")
    parser.add_argument("--sets",   type=int, default=4,  help="セット数（デフォルト4）")
    args = parser.parse_args()

    print(f"データ読み込み中...")
    all_rows = load_rows_all()
    if not all_rows:
        print("データがありません。collect.py でデータ収集してください。")
        return

    years = sorted({r["year"] for r in all_rows})
    print(f"全データ: {len(all_rows)}開催  期間: {min(years)}〜{max(years)}年")
    print(f"設定: 学習{args.train}年 → テスト{args.test}年  1セット{args.budget}通り × {args.sets}セット")

    results = run_walkforward(
        all_rows,
        train_years=args.train,
        test_years=args.test,
        budget=args.budget,
        n_sets=args.sets,
    )

    if not results:
        print("検証期間が足りません。データ年数を確認してください。")
        return

    report(results, args.budget)


if __name__ == "__main__":
    main()
