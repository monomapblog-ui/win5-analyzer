# WIN5 買い目生成システム 進捗メモ

## 現状のシステム概要

- **Flask Webアプリ** (`app.py`) — localhost:5000 で動作
- **買い目ロジック** (`buy.py`) — 人気の和15〜22（ターゲットゾーン）を数学的に保証
- **オッズ取得** (`collectors/shutuba.py`) — netkeiba APIから正確な人気順を取得
- **週判定** (`/api/check`) — 平均出走頭数<12頭 or 重・不良3レース以上でSKIP推奨

---

## 解決済みの問題（2026-06-14）

### オッズが全部Noneだった
- **原因**: netkeiba のオッズはJavaScriptで動的ロードされており、HTMLパースでは取れない
- **解決**: `https://race.netkeiba.com/api/api_get_jra_odds.html?race_id=XXX&type=1&action=update` を直接叩く
- **レスポンス形式**: `data.odds["1"]["01"] = ["3.7", "", "1"]` → [単勝オッズ, "", 人気順位]

### 馬番順に人気を仮割り当てしていた
- **原因**: オッズNoneのフォールバックが馬番昇順=人気順と誤って割り当て
- **解決**: APIから正確な人気順位（第3要素）を直接取得

---

## 実装済み機能一覧

### 馬選択（除外）機能
- 「② 馬を選択」→ 5レース分の馬がチェックボックスで表示
- チェックを外した馬を除外して買い目生成
- API: `POST /api/horses`、`POST /api/generate` の `excluded` フィールド

### コンパクト表示
- 上段: レース別 全チケット共通の応援馬番（ユニオン）→ R1は何番か一目でわかる
- 下段: チケット別 買い目一覧

### オッズ変動モニター（大口購入シグナル検出）
- `utils/db.py` に `OddsSnapshot` テーブル追加（race_id, horse_number, odds, popularity, snapshot_at, label）
- API: `POST /api/snapshot`（現在のオッズを時刻ラベルで保存）
- API: `POST /api/odds_movement`（スナップショット間の変動を比較）
- 急落アラート条件: **オッズ30%以上下落** or **人気3つ以上上昇** → 🔴 表示

### 締切前ワンボタン（🚀）
- 「記録 → 急落確認 → 買い目生成」を1ボタンで実行
- 14:30〜35頃に押す

### 再スナップ＆再生成（変動パネル内）
- 変動パネルに「📸 再スナップ」「📸＋🎯 再スナップ＆再生成」ボタン
- 10分前・5分前に押して変動を更新 → 急落馬を確認 → 馬を選択し直して再生成

---

## 推奨運用フロー（来週から）

| 時間 | 操作 |
|------|------|
| 前日夜 | 「📸 オッズ記録」ボタン（自動で時刻ラベルが付く） |
| 当日朝 | 「📸 オッズ記録」ボタン |
| **14:30〜35** | **🚀 締切前ワンボタン** → 変動確認＋買い目が自動表示 |
| **14:35〜40** | 変動パネルで🔴急落馬を確認 → 「② 馬を選択」で調整 → 「③ 買い目を生成」 |
| **14:40〜45** | 「📸＋🎯 再スナップ＆再生成」で最終確認・修正 |
| 14:45〜50 | IPAT手動入力 |

---

## 残課題・次にやること

### 優先度高
- **スロット別 人気勝率分析**: 過去データからスロット1〜5で何人気が来やすいか分析
  - 仮説: R1〜R3は堅い（1〜3人気）、R4〜R5は荒れやすい
  - データ検証してスロット別推奨人気帯をシステムに組み込む
  - 必要スクリプト: `analyze_slots.py`（未作成）
  - ローカルのDBに1640件あるので実行可能

### 優先度中
- **騎手信頼度分析**: WIN5対象レースでの騎手別 人気別勝率
  - `winner_jockey` を Win5RaceFeature に追加して収集
  - `analyze_jockey.py` を作成

---

## データ状況

### ローカル環境（ユーザーPC）
- **1640件収集済み**（2026-06-14時点）
- `python analyze_features.py` で週スキップ条件の分析済み
- スキップ条件: 平均出走頭数<12頭（TGT率16.7%）、重・不良3レース以上（TGT率18.2%）

### リモート環境（claude.ai/code）
- **DBが空** — git cloneのたびにリセットされる
- 再収集するには `python collect.py --last 6`（3〜5時間）

---

## スロット別人気勝率分析の手順（次のセッション）

ローカルで実行してもらい、結果を共有してもらう：

```powershell
cd C:\Users\admin\win5-analyzer
git pull origin claude/serene-hypatia-s7WOF
python analyze_slots.py
```

出力結果をもとにスロット別の推奨人気帯をシステムに組み込む。

---

## ファイル構成

```
win5-analyzer/
├── app.py                  # Flask Webアプリ（メイン）
├── buy.py                  # 純粋ゾーン買い目生成ロジック
├── collect.py              # WIN5過去データ収集
├── collect_features.py     # レース特徴量収集
├── analyze_features.py     # 特徴量分析（スキップ条件導出）
├── analyze_slots.py        # ★未作成 スロット別人気勝率分析
├── backtest.py             # バックテスト
├── collectors/
│   ├── netkeiba.py         # netkeibaスクレイパー（WIN5結果・レース結果）
│   └── shutuba.py          # オッズ取得（APIベース・netkeiba API直叩き）
├── utils/
│   └── db.py               # SQLAlchemyモデル（OddsSnapshotテーブル追加済み）
├── templates/index.html    # WebUI
└── PROGRESS.md             # このファイル
```

## Gitブランチ

- ブランチ: `claude/serene-hypatia-s7WOF`
- リポジトリ: `monomapblog-ui/win5-analyzer`
