"""WIN5 レース特徴量分析

収集した特徴量から「買う週の条件」を探す。

使い方:
  python analyze_features.py
"""
from sqlalchemy import select
from utils.db import init_db, SessionLocal, Win5Event, Win5Slot, Win5RaceFeature


def load_data():
    init_db()
    rows = []
    with SessionLocal() as session:
        events = session.execute(
            select(Win5Event)
            .where(Win5Event.popularity_sum.is_not(None))
            .where(Win5Event.payout.is_not(None))
            .order_by(Win5Event.held_date)
        ).scalars().all()

        for e in events:
            slots = session.execute(
                select(Win5Slot).where(Win5Slot.event_id == e.id)
                .order_by(Win5Slot.slot_number)
            ).scalars().all()

            slot_feats = []
            for s in slots:
                feat = session.execute(
                    select(Win5RaceFeature).where(Win5RaceFeature.slot_id == s.id)
                ).scalar_one_or_none()
                slot_feats.append(feat)

            if any(f is None for f in slot_feats):
                continue  # 特徴量未収集の開催はスキップ

            rows.append({
                "held_date":      e.held_date,
                "payout":         e.payout,
                "popularity_sum": e.popularity_sum,
                "zone":           e.zone,
                "slots":          slot_feats,
                # 集計特徴量
                "avg_field_size": sum(f.field_size or 0 for f in slot_feats) / 5,
                "min_field_size": min((f.field_size or 99) for f in slot_feats),
                "avg_fav1_odds":  _safe_avg([f.fav1_odds for f in slot_feats]),
                "max_fav1_odds":  _safe_max([f.fav1_odds for f in slot_feats]),
                "min_fav1_odds":  _safe_min([f.fav1_odds for f in slot_feats]),
                "avg_winner_odds":_safe_avg([f.winner_odds for f in slot_feats]),
                "has_dirt":       any(f.course_type == "ダート" for f in slot_feats),
                "n_heavy":        sum(1 for f in slot_feats if f.track_condition in ("重", "不良")),
            })
    return rows


def _safe_avg(vals):
    v = [x for x in vals if x is not None]
    return sum(v) / len(v) if v else None

def _safe_max(vals):
    v = [x for x in vals if x is not None]
    return max(v) if v else None

def _safe_min(vals):
    v = [x for x in vals if x is not None]
    return min(v) if v else None


def report(rows):
    n = len(rows)
    if n == 0:
        print("特徴量データがありません。collect_features.py を先に実行してください。")
        return

    target = [r for r in rows if r["zone"] == "target"]
    print(f"\n{'='*65}")
    print(f"  WIN5 特徴量分析  （{n}開催 / ターゲットゾーン{len(target)}回）")
    print(f"{'='*65}")

    # ── 1番人気オッズ別 ターゲット率 ──
    print(f"\n■ 5レース平均・1番人気オッズ別 ターゲットゾーン率")
    print(f"  {'1人気avg':>10}  {'開催数':>6}  {'TGT率':>7}  {'平均払戻':>12}")
    brackets = [
        ("〜1.9倍", lambda r: r["avg_fav1_odds"] is not None and r["avg_fav1_odds"] < 2.0),
        ("2.0〜2.9", lambda r: r["avg_fav1_odds"] is not None and 2.0 <= r["avg_fav1_odds"] < 3.0),
        ("3.0〜3.9", lambda r: r["avg_fav1_odds"] is not None and 3.0 <= r["avg_fav1_odds"] < 4.0),
        ("4.0倍〜", lambda r: r["avg_fav1_odds"] is not None and r["avg_fav1_odds"] >= 4.0),
    ]
    for label, cond in brackets:
        grp = [r for r in rows if cond(r)]
        if not grp:
            continue
        tgt = [r for r in grp if r["zone"] == "target"]
        avg_pay = int(sum(r["payout"] for r in tgt) / len(tgt)) if tgt else 0
        print(f"  {label:>10}  {len(grp):>6}  {len(tgt)/len(grp)*100:>6.1f}%  {avg_pay:>12,}円")

    # ── 最大1番人気オッズ（一番荒れそうなレース）別 ──
    print(f"\n■ 最も荒れやすいレースの1番人気オッズ別 ターゲットゾーン率")
    print(f"  {'max1人気':>10}  {'開催数':>6}  {'TGT率':>7}  {'平均払戻':>12}")
    brackets2 = [
        ("〜2.9倍", lambda r: r["max_fav1_odds"] is not None and r["max_fav1_odds"] < 3.0),
        ("3.0〜4.9", lambda r: r["max_fav1_odds"] is not None and 3.0 <= r["max_fav1_odds"] < 5.0),
        ("5.0〜7.9", lambda r: r["max_fav1_odds"] is not None and 5.0 <= r["max_fav1_odds"] < 8.0),
        ("8.0倍〜", lambda r: r["max_fav1_odds"] is not None and r["max_fav1_odds"] >= 8.0),
    ]
    for label, cond in brackets2:
        grp = [r for r in rows if cond(r)]
        if not grp:
            continue
        tgt = [r for r in grp if r["zone"] == "target"]
        avg_pay = int(sum(r["payout"] for r in tgt) / len(tgt)) if tgt else 0
        print(f"  {label:>10}  {len(grp):>6}  {len(tgt)/len(grp)*100:>6.1f}%  {avg_pay:>12,}円")

    # ── 出走頭数（平均）別 ──
    print(f"\n■ 平均出走頭数別 ターゲットゾーン率")
    print(f"  {'平均頭数':>10}  {'開催数':>6}  {'TGT率':>7}  {'平均払戻':>12}")
    brackets3 = [
        ("〜11頭", lambda r: r["avg_field_size"] < 12),
        ("12〜13頭", lambda r: 12 <= r["avg_field_size"] < 14),
        ("14〜15頭", lambda r: 14 <= r["avg_field_size"] < 16),
        ("16頭〜", lambda r: r["avg_field_size"] >= 16),
    ]
    for label, cond in brackets3:
        grp = [r for r in rows if cond(r)]
        if not grp:
            continue
        tgt = [r for r in grp if r["zone"] == "target"]
        avg_pay = int(sum(r["payout"] for r in tgt) / len(tgt)) if tgt else 0
        print(f"  {label:>10}  {len(grp):>6}  {len(tgt)/len(grp)*100:>6.1f}%  {avg_pay:>12,}円")

    # ── 馬場状態（荒れ） ──
    print(f"\n■ 不良馬場レース数別 ターゲットゾーン率")
    for n_heavy in [0, 1, 2, 3]:
        label = f"重・不良{n_heavy}レース" if n_heavy > 0 else "全レース良・稍重"
        grp = [r for r in rows if r["n_heavy"] == n_heavy]
        if not grp:
            continue
        tgt = [r for r in grp if r["zone"] == "target"]
        avg_pay = int(sum(r["payout"] for r in tgt) / len(tgt)) if tgt else 0
        print(f"  {label:>16}: {len(grp):>4}開催  TGT{len(tgt)/len(grp)*100:>5.1f}%  平均払戻{avg_pay:>10,}円")

    # ── スキップ条件（データから導出） ──
    print(f"\n■ スキップ推奨条件（データ根拠あり）")

    skip_small = [r for r in rows if r["avg_field_size"] < 12]
    skip_heavy = [r for r in rows if r["n_heavy"] >= 3]
    skip_any   = [r for r in rows if r["avg_field_size"] < 12 or r["n_heavy"] >= 3]
    buy_weeks  = [r for r in rows if r not in skip_any]
    tgt_buy    = [r for r in buy_weeks if r["zone"] == "target"]

    print(f"  【スキップ条件1】平均出走頭数 < 12頭")
    s1 = [r for r in skip_small if r["zone"] == "target"]
    print(f"    該当: {len(skip_small)}回  ターゲット率: {len(s1)/len(skip_small)*100:.1f}%  ← 低いのでスキップ")

    print(f"  【スキップ条件2】重・不良馬場 3レース以上")
    s2 = [r for r in skip_heavy if r["zone"] == "target"]
    if skip_heavy:
        print(f"    該当: {len(skip_heavy)}回  ターゲット率: {len(s2)/len(skip_heavy)*100:.1f}%  ← 低いのでスキップ")

    print(f"\n  ▶ どちらかに該当 → スキップ: {len(skip_any)}回 / {n}回")
    print(f"  ▶ 購入する週: {len(buy_weeks)}回 / {n}回（{len(buy_weeks)/n*100:.1f}%）")
    print(f"    ターゲット率: {len(tgt_buy)/len(buy_weeks)*100:.1f}%  （全体平均: {len(target)/n*100:.1f}%）")
    avg_pay_buy = int(sum(r["payout"] for r in tgt_buy) / len(tgt_buy)) if tgt_buy else 0
    print(f"    的中時平均払戻: {avg_pay_buy:,}円")

    # ── 期待値比較 ──
    print(f"\n■ 期待値比較（1回50,400円投資として）")
    cost = 50_400
    for label, grp in [("全週購入", rows), ("フィルタ後購入", buy_weeks)]:
        tgt_g = [r for r in grp if r["zone"] == "target"]
        if not grp:
            continue
        hit_rate = len(tgt_g) / len(grp)
        avg_pay  = sum(r["payout"] for r in tgt_g) / len(tgt_g) if tgt_g else 0
        ev = hit_rate * avg_pay - cost
        roi = hit_rate * avg_pay / cost * 100
        print(f"  {label}: 的中率{hit_rate*100:.1f}%  期待値{ev:+,.0f}円/回  回収率{roi:.1f}%")

    # ── 今週判断フロー ──
    print(f"\n■ 毎週の購入判断フロー")
    print(f"  1. 5レースの出走頭数を確認 → 平均12頭未満ならスキップ")
    print(f"  2. 馬場状態を確認 → 重・不良が3レース以上ならスキップ")
    print(f"  3. 上記以外 → 購入（5万円〜8万円でターゲットゾーンを広くカバー）")


def main():
    rows = load_data()
    report(rows)


if __name__ == "__main__":
    main()
