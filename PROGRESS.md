# WIN5 買い目生成システム 進捗メモ

## 現状のシステム概要

- **Flask Webアプリ** (`app.py`) — localhost:5000 で動作
- **買い目ロジック** (`buy.py`) — 人気の和15〜22（ターゲットゾーン）を数学的に保証
- **オッズ取得** (`collectors/shutuba.py`) — netkeiba APIから正確な人気順を取得
- **週判定** (`/api/check`) — 平均出走頭数<12頭 or 重・不良3レース以上でSKIP推奨

## 今日（2026-06-14）解決した問題

### オッズが全部Noneだった
- **原因**: netkeiba のオッズはJavaScriptで動的ロードされており、HTMLパースでは取れない
- **解決**: `https://race.netkeiba.com/api/api_get_jra_odds.html?race_id=XXX&type=1&action=update` を直接叩く
- **レスポンス形式**: `data.odds["1"]["01"] = ["3.7", "", "1"]` → [単勝オッズ, "", 人気順位]

### 馬番順に人気を仮割り当てしていた
- **原因**: オッズNoneのフォールバックが馬番昇順=人気順と誤って割り当て
- **解決**: APIから正確な人気順位（第3要素）を直接取得

## 追加した機能

### 馬選択（除外）機能
- UIで「② 馬を選択」ボタン → 5レース分の馬がチェックボックスで表示
- 除外したい馬のチェックを外す
- 「③ 買い目を生成」で除外馬を抜いた15〜22の買い目を生成
- API: `POST /api/horses` で馬リスト取得、`POST /api/generate` の `excluded` フィールドで除外馬番を送信

### コンパクト表示の改善
- 上段: レース別 全チケット共通の応援馬番（ユニオン） → 「R1は何番を応援すればいいか」が一目でわかる
- 下段: チケット別 買い目一覧

## 残課題・次にやること

### 優先度高
- **スロット別 人気勝率分析**: 過去データからスロット1〜5それぞれで何人気が来やすいか分析
  - R1〜R3は堅い（1〜3人気が来やすい）、R4〜R5は荒れやすい傾向がある（仮説）
  - データで検証してスロット別推奨人気帯をシステムに組み込む
  - 必要スクリプト: `analyze_slots.py`（未作成）

### 優先度中
- **騎手信頼度分析**: WIN5対象レースでの騎手別 人気別勝率
  - `winner_jockey` を Win5RaceFeature に追加して収集
  - `analyze_jockey.py` を作成

## データ状況

### ローカル環境（ユーザーPC）
- **1640件収集済み**（2026-06-14時点）
- `python analyze_features.py` で週スキップ条件の分析済み
- スキップ条件: 平均出走頭数<12頭（TGT率16.7%）、重・不良3レース以上（TGT率18.2%）

### リモート環境（claude.ai/code）
- **DBが空** — git cloneのたびにリセットされる
- 再収集するには `python collect.py --last 6`（3〜5時間）

## スロット別人気勝率分析の手順（次回）

ローカルで以下を実行してもらい、結果を共有してもらう：

```python
# analyze_slots.py（作成予定）
# → スロット別 人気勝率分布を出力
# → 結果をもとに各スロットの推奨人気帯をシステムに組み込む
```

または夜に `python collect.py --last 6` をリモートで流してDBを再構築してから分析。

## ファイル構成

```
win5-analyzer/
├── app.py                  # Flask Webアプリ（メイン）
├── buy.py                  # 純粋ゾーン買い目生成ロジック
├── collect.py              # WIN5過去データ収集
├── collect_features.py     # レース特徴量収集
├── analyze_features.py     # 特徴量分析（スキップ条件導出）
├── backtest.py             # バックテスト
├── collectors/
│   ├── netkeiba.py         # netkeibaスクレイパー（WIN5結果・レース結果）
│   └── shutuba.py          # オッズ取得（APIベース）
├── utils/
│   └── db.py               # SQLAlchemyモデル（Win5Event, Win5Slot, Win5RaceFeature等）
├── templates/index.html    # WebUI
└── PROGRESS.md             # このファイル
```

## Gitブランチ

- ブランチ: `claude/serene-hypatia-s7WOF`
- リポジトリ: `monomapblog-ui/win5-analyzer`
