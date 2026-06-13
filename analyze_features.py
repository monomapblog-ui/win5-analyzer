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

    # ── 推奨フィルタ（仮） ──
    print(f"\n■ 「買う週」フィルタ試案")
    print(f"  条件: 5レース平均1番人気オッズ ≤ 3.5倍 かつ 最大1番人気オッズ ≤ 6.0倍")
    filtered = [
        r for r in rows
        if r["avg_fav1_odds"] is not None and r["avg_fav1_odds"] <= 3.5
        and r["max_fav1_odds"] is not None and r["max_fav1_odds"] <= 6.0
    ]
    tgt_f = [r for r in filtered if r["zone"] == "target"]
    if filtered:
        print(f"  該当開催: {len(filtered)}回 / {n}回（{len(filtered)/n*100:.1f}%に絞り込み）")
        print(f"  ターゲット率: {len(tgt_f)/len(filtered)*100:.1f}%  （全体: {len(target)/n*100:.1f}%）")
        avg_pay_f = int(sum(r["payout"] for r in tgt_f) / len(tgt_f)) if tgt_f else 0
        print(f"  平均払戻（的中時）: {avg_pay_f:,}円")
    else:
        print("  該当なし（データ不足）")

    # ── 今週の特徴量チェック用ヒント ──
    print(f"\n■ 毎週チェックすべき指標")
    print(f"  1. 5レースの1番人気オッズを確認 → 平均3.5倍以下なら「固い週」")
    print(f"  2. 最も荒れそうなレースの1番人気オッズ → 6倍超なら「スキップ推奨」")
    print(f"  3. 重・不良馬場が2レース以上 → 高ゾーン化リスク高（スキップ候補）")


def main():
    rows = load_data()
    report(rows)


if __name__ == "__main__":
    main()
