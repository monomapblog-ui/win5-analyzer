# WIN5分析AIシステムを500時間かけて作った話──競馬×プログラミングで挑む最強の馬券

---

## 1. はじめに（なぜWIN5に目をつけたか）

正直に言うと、最初はWIN5なんてまったく興味がなかった。

競馬は学生時代から好きで、週末に友人と競馬場へ足を運んでは単勝や馬連をちまちま買う程度のライトなファンだった。馬の走りを見るのが楽しいし、パドックで馬の状態を見極めようとするあの独特の緊張感も好きだ。でも「WIN5で億を狙う」みたいな夢物語には正直ピンとこなかった。

転機は2023年の秋だった。当時、副業でPythonを使ったデータ分析の仕事をしていた私は、ふとしたきっかけでWIN5の払戻金データを眺める機会があった。2021年の某日のWIN5払戻金が「6億円超」というニュースを見て、「これ、本当に6億円が一人に入るのか？」と思って調べ始めたのだ。

調べてみると、WIN5というのは驚くほど「数学的に面白い」賭けだということがわかってきた。単純な確率論でいえばとんでもなく難しい。でも、その難しさの中に「パターン」があるんじゃないか──そう直感したのが、このプロジェクトの出発点だった。

それから約1年半、合計500時間以上をこのシステムの開発に費やすことになる。PythonとFlaskでWebアプリを作り、6年分のデータをスクレイピングし、統計的なパターンを探し、UIを何度も作り直した。仕事が終わった深夜に一人でコードを書き続けた夜が何十回あったかわからない。

このnoteは、その記録だ。技術的な話も書くけれど、それ以上に「なぜそう考えたか」「どこで詰まったか」「何を学んだか」を正直に書きたいと思っている。競馬ファンにもプログラマーにも読んでもらえるように、できるだけ丁寧に説明していく。

---

## 2. WIN5とは何か（一般読者向けの説明）

まず、WIN5を知らない人のために説明しておく。

WIN5とは、JRA（日本中央競馬会）が毎週開催している特殊な馬券で、**その日に指定された5つのレースすべての1着馬を的中させる**という賭けだ。1票100円から買えるが、5レース全部当てなければ一切払戻がない。「全か無か」の極めてシビアな馬券である。

なぜこんなものが面白いかというと、**キャリーオーバー制度**があるからだ。もし的中者がゼロだった場合、その週の賞金は次週に持ち越される。これが積み重なると、払戻金が数億円規模になることがある。実際に10億円を超えたケースもあり、それが「WIN5は夢の馬券」と言われる所以だ。

計算してみよう。仮に各レースに10頭が出走していて、それぞれの1着を当てるとすると、確率は単純に「10の5乗分の1」、つまり1/100,000だ。実際のレースは頭数が多いので、純粋な確率はさらに低くなる。8頭×5レースでも1/32,768、12頭×5レースなら1/248,832にもなる。

だから普通の人は「当たるわけない」と思って手を出さない。

でも私はここで逆の発想をした。「当たるわけない」からこそ、**少しでも確率を上げる体系的なアプローチに価値がある**のではないか、と。

WIN5の購入方法は、各レースで「どの馬が1着になるか」を選んで組み合わせを作るというものだ。例えばレース1で馬番1・2を選び、レース2で馬番3を選び……というように選択肢を組み合わせていく。1レースで2頭選んで5レース全部で2頭ずつ選んだ場合、2×2×2×2×2＝32通りの組み合わせが生まれ、100円×32＝3,200円の投資になる。

ここに「どの馬を選ぶか」という問題と、「何通り買うか」という問題が生じる。この両方を最適化しようとしたのが、今回のシステムだ。

重要な概念として「人気順」がある。競馬では出走前にオッズ（配当倍率）が形成され、それが低いほど（＝多くの人が買っているほど）「人気が高い」とされる。1番人気は最もオッズが低い馬、10番人気は比較的オッズが高い馬、という具合だ。WIN5を制した馬の「人気順」に注目することで、重要なパターンが見えてくる──というのが、このプロジェクトの核心だ。

---

## 3. 「人気の和」という発見

システム開発で最初に行ったのは、過去のWIN5結果データを「眺める」作業だった。

とりあえず2018年から2023年までの約6年分、328回分のWIN5結果を収集した（これ自体に苦労したのだが、それは後述する）。そして各回について「5レースそれぞれで何番人気の馬が勝ったか」を記録し、スプレッドシートに並べ始めた。

最初は「どの人気の馬がよく勝つか」を見ていたが、それだと情報が多すぎてパターンが見えにくい。そこで思いついたのが、**5レース分の人気順をすべて足し合わせた値**、つまり「人気の和」という指標だ。

例えばある回のWIN5で、各レースの勝ち馬の人気順が「2・3・1・4・2」だったとすると、人気の和は「2+3+1+4+2＝12」になる。別の回で「5・3・4・6・3」だったとすると「5+3+4+6+3＝21」だ。

この「人気の和」を、328回分全部計算してヒストグラムにしてみた。すると──

**見事な分布が現れた。**

人気の和は最小で5（全レースで1番人気が勝ち）、理論上の最大は各レースの頭数次第で変わるが、データ上では40を超えることはほとんどない。そして分布の山は**15〜22の範囲**に集中していたのだ。

具体的な数字を言うと、人気の和が15〜22の範囲に収まったケースは、328回中約144回、**実に44%**にも達していた。

これは何を意味するか。「過去のWIN5の約半分は、5レース合計で15〜22番人気相当の馬たちが勝っている」ということだ。「超人気薄の馬が勝ちまくる大荒れ」でも「全レース1番人気が独占する堅い展開」でもなく、**程よい混戦が約半数を占める**という事実が浮かび上がった。

もちろん、残り56%はこの範囲外だ。人気の和が5〜14の「比較的堅い決着」が約20%、23以上の「荒れた決着」が約36%ある。でも「44%を狙い撃ちできる」というのは、無策で買うより遥かに有利な条件だ。

この「人気の和15〜22」を私は**ターゲットゾーン**と名付けた。

ターゲットゾーンの概念が固まったところで、次の課題が浮かんだ。「どの馬の組み合わせを買えば、人気の和がターゲットゾーンに収まるか」を効率的に計算する必要がある。

これが「ピュアゾーンセット」という概念につながる。ピュアゾーンセットとは、**選んだ馬の組み合わせがすべてターゲットゾーン（人気の和15〜22）に収まるような買い目の集合**のことだ。数学的に保証された「外れない組み合わせ」ではなく、「少なくとも人気の和の条件は満たしている」組み合わせということになる。

例えば5レースそれぞれで「3番人気まで選ぶ」と設定した場合、最小の人気の和は「1+1+1+1+1=5」、最大は「3+3+3+3+3=15」だ。この設定だと最大値が15でターゲットゾーンの下限に触れるだけなので、あまり適切ではない。では「各レースで1〜6番人気を選ぶ」としたら？最小5、最大30となり、ターゲットゾーンをカバーしつつ範囲が広がりすぎる。

この調整を自動化し、かつ予算制約（5〜10万円程度、最大10枚のIPATチケット）に収まるよう最適化するのが、システムの核心的なアルゴリズムとなった。

---

## 4. データ収集との戦い（netkeibaスクレイピングの苦労）

アイデアは固まった。次は「データ」だ。

過去のWIN5結果を取得するために、日本最大の競馬情報サイト「netkeiba.com」をスクレイピングすることにした。netkeibaにはWIN5の結果ページがあり、過去のデータを一覧で見ることができる。

最初は楽観的だった。「Pythonのrequestsとbeautifulsoup4で普通にスクレイピングすればいいだろう」と思っていた。

**甘かった。**

まず直面したのは、ページのURL構造の問題だ。netkeibaのWIN5結果ページは、特定のURLパターンに従っているが、そのパターンが微妙に変わっていたり、古いデータと新しいデータでレイアウトが異なっていたりする。2018年のページと2023年のページでは、HTMLの構造が微妙に変わっており、同じセレクタでは取れないケースが出てきた。

```python
# 最初に書いた素朴なコード（これではうまくいかなかった）
import requests
from bs4 import BeautifulSoup

def fetch_win5_result(date):
    url = f"https://race.netkeiba.com/odds/win5.html?kaisai_date={date}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # このセレクタが年によって違う...
    result_table = soup.find('table', class_='Win5ResultTable')
    return result_table
```

このコードを書いて実行したら、半分以上の日付でデータが取れなかった。エラーではなく、単に`None`が返ってくる。デバッグのためにHTMLを保存して中身を見てみると、「テーブルのクラス名が違う」「データがそもそもHTMLに含まれていない」などの問題が次々と出てきた。

「HTMLに含まれていない」というのが最大の謎だった。ブラウザで見ると確かにデータが表示されているのに、requestsで取得したHTMLにはそのデータが存在しない。

これはJavaScriptの問題だった。

netkeibaのページ、特にオッズ関連のデータは、ページ読み込み後にJavaScriptが非同期でデータを取得して表示する仕組みになっていた。requestsはHTMLを静的に取得するだけなので、JavaScriptが実行されず、データが空のままになるのだ。

この問題への最初の対処は「Selenium」だった。Seleniumを使えばブラウザを自動操作できるので、JavaScriptが実行された後のHTMLを取得できる。

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

options = Options()
options.add_argument('--headless')  # ヘッドレスモードで実行
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

driver = webdriver.Chrome(options=options)

def fetch_win5_result_selenium(date):
    url = f"https://race.netkeiba.com/odds/win5.html?kaisai_date={date}"
    driver.get(url)
    time.sleep(3)  # JavaScriptの実行を待つ
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    # ...データ抽出処理
```

Seleniumで動かしてみると、確かにデータが取れるようになった。しかし問題がある。**遅い**のだ。

1回のリクエストに3〜5秒かかるとして、328回分のWIN5、それぞれ5レース分のデータを取ると、単純計算で328×5×5秒＝約8,200秒、つまり**2時間以上**かかる計算だ。しかも途中でタイムアウトしたり、ブラウザがクラッシュしたりする問題も出てきた。

「もっとスマートな方法があるはずだ」と思って、ブラウザの開発者ツールを開いてネットワークタブを眺め始めた。これが大きな転機になる。

---

## 5. オッズが取れない問題とその解決（JavaScriptレンダリング問題、APIエンドポイント発見）

ブラウザの開発者ツール（Chrome DevTools）のNetworkタブでnetkeibaのページを開いてリロードすると、数十件のHTTPリクエストがずらりと並ぶ。その中に、見慣れないURLがあった。

```
https://race.netkeiba.com/api/api_get_jra_odds.html?type=b7&race_id=...
```

「api」という文字列が気になった。これはもしかして、JavaScriptがこのURLにリクエストを送ってオッズデータを取得しているのではないか？

そのURLを直接ブラウザで開いてみた。

**ビンゴだった。**

JSONライクなレスポンスが返ってきた。フォーマットを見てみると：

```javascript
// レスポンスの中身（一部抜粋・整形）
data.odds["1"]["01"] = ["3.7", "", "1"]
data.odds["1"]["02"] = ["5.2", "", "2"]
data.odds["1"]["03"] = ["8.1", "", "3"]
// ...
```

このデータ構造を解読すると：
- `data.odds["1"]` → 1レース目
- `["01"]` → 馬番01
- `["3.7", "", "1"]` → [オッズ値, 空文字, 人気順位]

つまり、**各馬の現在のオッズと人気順位がこのAPIから直接取得できる**ということだ。Seleniumでブラウザをレンダリングする必要はなかった。このAPIエンドポイントに直接requestsでアクセスすればよかったのだ。

```python
import requests
import re

def fetch_odds_from_api(race_id):
    """
    netkeibaの内部APIからオッズデータを取得する
    race_idの形式: YYYYMMDD場コード回数日数レース番号
    例: 202401050102 (2024年01月05日、京都1回1日目2レース)
    """
    url = f"https://race.netkeiba.com/api/api_get_jra_odds.html"
    params = {
        'type': 'b7',
        'race_id': race_id,
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://race.netkeiba.com/',
    }
    
    response = requests.get(url, params=params, headers=headers)
    text = response.text
    
    # JavaScriptライクなレスポンスをパース
    # data.odds["1"]["01"] = ["3.7", "", "1"]
    pattern = r'data\.odds\["(\d+)"\]\["(\d+)"\]\s*=\s*\["([^"]*)",\s*"([^"]*)",\s*"([^"]*)"\]'
    matches = re.findall(pattern, text)
    
    odds_data = {}
    for race_num, horse_num, odds_val, _, popularity in matches:
        horse_num_int = int(horse_num)
        odds_data[horse_num_int] = {
            'odds': float(odds_val) if odds_val else None,
            'popularity': int(popularity) if popularity else None
        }
    
    return odds_data
```

このAPIを使ったコードは劇的に速くなった。1リクエスト0.3〜0.5秒程度で完了する。328回×5レース分のデータ収集が、Seleniumの2時間以上から**15〜20分程度**に短縮された。

しかし、まだ問題は残っていた。

このAPIはリアルタイムのオッズデータを返す。つまり「過去のオッズ」は取得できない。過去の結果（どの馬が何番人気で勝ったか）は別のページから取得する必要があり、しかも「その時点での人気順」は現在のAPIでは確認できない。

過去の結果ページの構造を調べると、結果ページには「最終オッズ」と「人気順位」が記録されていることがわかった。ただし、ページによってHTMLの構造が異なる。

試行錯誤の末、年度別に異なるパーサーを用意し、それぞれのページ構造に対応するコードを書いた。レース結果の「着順テーブル」から人気順を取得するのが最も確実だとわかったのは、何十回もHTMLを手動で確認した後のことだった。

```python
def parse_race_result(race_id):
    """レース結果ページから着順と人気順を取得"""
    url = f"https://race.netkeiba.com/race/result.html?race_id={race_id}"
    response = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 結果テーブルを取得（複数の候補を試みる）
    result_table = (
        soup.find('table', id='All_Result_Table') or
        soup.find('table', class_='RaceTable01 RaceCommon_Table ResultRefund_Table')
    )
    
    if not result_table:
        # フォールバック: より広いセレクタで試みる
        tables = soup.find_all('table')
        for table in tables:
            if table.find('th', string='着順'):
                result_table = table
                break
    
    first_place_row = None
    for row in result_table.find_all('tr'):
        cells = row.find_all('td')
        if cells and cells[0].text.strip() == '1':
            first_place_row = cells
            break
    
    if first_place_row:
        horse_num = int(first_place_row[2].text.strip())
        popularity = int(first_place_row[-3].text.strip())  # 人気列
        return {'horse_num': horse_num, 'popularity': popularity}
    
    return None
```

このような地道な作業を繰り返して、最終的に**328回のWIN5結果、合計1640スロットのデータ**を収集・構造化することができた。レースIDと日付の対応表を作り、各スロット（WIN5の各レース枠）ごとに「勝ち馬の人気順」を記録したデータベースが完成した。

---

## 6. 買い目生成アルゴリズムの設計

データが揃ったところで、いよいよ「買い目生成」のアルゴリズムを設計する段階に入った。

問題を整理すると：
- 5つのレースそれぞれで「何頭まで選ぶか」を決める
- 選んだ馬の全組み合わせのうち、人気の和がターゲットゾーン（15〜22）に収まるもののみを買う
- 合計点数（≒投資金額÷100円）を予算内に収める

これをナイーブに実装すると、「全レースで1〜10番人気を選んで全組み合わせを生成」→「人気の和でフィルタ」という流れになる。しかしこれでは組み合わせ数が膨大になりすぎる。

そこで「ピュアゾーンセット」という概念を導入した。

**ピュアゾーンセットの定義：**
各レースで選ぶ馬の人気順の最小値と最大値が決まっているとき、生成される全組み合わせがすべてターゲットゾーン内に収まるような選択肢の集合のこと。

例えば：
- レース1: 1〜4番人気（最小1、最大4）
- レース2: 1〜4番人気（最小1、最大4）
- レース3: 1〜5番人気（最小1、最大5）
- レース4: 1〜5番人気（最小1、最大5）
- レース5: 1〜4番人気（最小1、最大4）

この設定での人気の和の範囲：
- 最小: 1+1+1+1+1 = 5
- 最大: 4+4+5+5+4 = 22

最大が22でターゲットゾーンの上限に収まっており、最小が5なので下限の15を下回る組み合わせも含まれる。このため「ピュア」ではなく、フィルタリングが必要な状態だ。

真の「ピュアゾーン」を達成するには、最小値の合計が15以上、最大値の合計が22以下である必要がある。しかしこれを厳密に満たしながら点数を最大化するのは難しい。

実際には「ターゲットゾーン内に収まる確率が高い選択をしつつ、外れる組み合わせをフィルタで除去する」ハイブリッドアプローチを採用した。

```python
from itertools import product

def generate_buy_combinations(slot_selections, target_min=15, target_max=22, budget_limit=100):
    """
    slot_selections: 各スロットで選ぶ馬の人気順のリスト
    例: [[1,2,3], [1,2,4], [1,2,3,5], [1,2,3,5], [1,2,3,4]]
    
    target_min, target_max: ターゲットゾーンの範囲
    budget_limit: 最大点数（100点 = 10,000円）
    """
    
    # 全組み合わせを生成
    all_combinations = list(product(*slot_selections))
    
    # ターゲットゾーンでフィルタ
    zone_combinations = [
        combo for combo in all_combinations
        if target_min <= sum(combo) <= target_max
    ]
    
    print(f"全組み合わせ: {len(all_combinations)}通り")
    print(f"ターゲットゾーン内: {len(zone_combinations)}通り")
    print(f"絞り込み率: {len(zone_combinations)/len(all_combinations)*100:.1f}%")
    
    if len(zone_combinations) > budget_limit:
        # 予算超過の場合は点数上位を選択（後述のスコアリングシステムで処理）
        print(f"予算超過: {len(zone_combinations)}点 > {budget_limit}点上限")
        return zone_combinations[:budget_limit]  # 暫定処理
    
    return zone_combinations
```

しかし、このアルゴリズムには問題があった。「どのスロットで何頭選ぶか」の設定（`slot_selections`の中身）は、毎週変わるはずだ。人気が高い馬が多いレースなら上位2〜3頭に絞れるかもしれないし、混戦模様なら5〜6頭必要かもしれない。

この「各スロットの選択数」をどう決めるか、が次の課題になった。

---

## 7. 1640件のデータが語るスロット別パターン

1640スロット分のデータを、「スロット別」（WIN5で指定される5レースのどの位置か）に分析してみた。

WIN5では毎回5つのレースが指定されるが、それをスロット1（S1）からスロット5（S5）と呼ぶことにする。S1が最初のレース、S5が最後のレースだ。これらはレースの格（重賞かどうか）や時間帯が異なることが多い。

分析の結果、興味深いパターンが見えてきた。

**勝ち馬の人気順分布（スロット別）：**

| 人気順 | S1 | S2 | S3 | S4 | S5 |
|--------|----|----|----|----|-----|
| 1番人気 | 31.4% | 28.7% | 26.5% | 25.3% | 30.2% |
| 2番人気 | 18.6% | 19.2% | 16.8% | 17.1% | 18.9% |
| 3番人気 | 13.1% | 12.4% | 13.7% | 12.8% | 14.1% |
| 4番人気 | 9.8% | 10.1% | 10.2% | 10.9% | 8.7% |
| 5番人気 | 7.2% | 8.3% | 9.1% | 9.7% | 7.6% |
| 6番人気以下 | 19.9% | 21.3% | 23.7% | 24.2% | 20.5% |

この表から読み取れることが2つある。

1つ目：**S1、S2、S5は1〜4番人気で約70%をカバー**できる。これらのスロットは比較的「堅い」傾向がある。

2つ目：**S3、S4は5番人気まで含めないと70%のカバーに届かない**。これらのスロットは荒れやすく、上位5頭まで押さえる必要がある。

この発見は買い目生成の設計に直接反映させた。「デフォルト設定」として、S1・S2・S5では1〜4番人気、S3・S4では1〜5番人気を選択するようにした。

```python
# デフォルトのスロット設定
DEFAULT_SLOT_CONFIG = {
    'S1': {'min_pop': 1, 'max_pop': 4},  # 1〜4番人気
    'S2': {'min_pop': 1, 'max_pop': 4},  # 1〜4番人気
    'S3': {'min_pop': 1, 'max_pop': 5},  # 1〜5番人気
    'S4': {'min_pop': 1, 'max_pop': 5},  # 1〜5番人気
    'S5': {'min_pop': 1, 'max_pop': 4},  # 1〜4番人気
}

# この設定での組み合わせ数: 4×4×5×5×4 = 1,600通り
# ターゲットゾーン(15-22)でフィルタ後の期待値: 約400〜600通り（週によって変動）
```

1,600通りを400〜600通りに絞り込んでもまだ予算（最大10枚=1,000通り）の範囲内なので、この設定は概ね機能する。ただし週によっては800通りを超えることもあり、その場合はユーザーが手動でスロットの上限人気順を絞る機能も実装した。

さらに分析を深めると、「時間帯」と「レースの格」にも相関があることがわかってきた。

WIN5で指定されるレースには、G1（最高格のレース）、G2、G3、リステッド、それ以外の平場戦が含まれる。G1やG2は一般的に「実力のある馬がより公正に力を発揮できる」とされており、人気上位の馬が勝ちやすい傾向がある。一方、平場の下級戦は展開や馬場状態の影響を受けやすく、穴馬が来やすい。

これを加味した「動的設定調整」機能も後々実装することになるが、まずは静的なデフォルト設定で動くシステムを完成させることを優先した。

---

## 8. 急落オッズという最強シグナル

分析を続ける中で、もう一つ重要な発見があった。**オッズの動き**だ。

競馬のオッズは、発売開始（通常前日夕方）から締め切り（レース直前）まで変動し続ける。大量の馬券が特定の馬に集中すれば、その馬のオッズは下がる（人気が上がる）。

「前日夜から当日朝にかけてオッズが急落した馬」、つまり**短時間に多くの馬券が集中して購入された馬**は、何らかの「情報」を持った買い手が参入してきた可能性が高い。これが競馬の世界で「本命馬」とか「情報馬」と呼ばれるものだ。

もちろん「インサイダー情報」なんて存在しないはずだが（公式にはそういうことになっている）、調教師や馬主の関係者、あるいは馬の状態を間近で見ているトレーナーらが「今日はこの馬が絶好調だ」と判断して買えば、それは自然とオッズに反映される。

WIN5の分析において、「オッズが前日比で30%以上下落した馬」（つまり人気が急騰した馬）を注目馬として自動でマークする機能を実装した。

```python
def detect_odds_sharp_drop(morning_odds, current_odds, threshold=0.7):
    """
    オッズの急落を検出する
    threshold: 前の値に対する比率（0.7 = 30%以上下落）
    """
    if morning_odds is None or current_odds is None:
        return False
    
    if morning_odds <= 0:
        return False
    
    ratio = current_odds / morning_odds
    return ratio <= threshold

def analyze_odds_movement(race_id, snapshots):
    """
    複数時点のオッズスナップショットから動きを分析
    
    snapshots: [
        {'time': 'prev_night', 'odds_data': {...}},
        {'time': 'morning', 'odds_data': {...}},
        {'time': 'pre_deadline', 'odds_data': {...}},
    ]
    """
    results = {}
    
    for horse_num in snapshots[0]['odds_data']:
        prev_night_odds = snapshots[0]['odds_data'].get(horse_num, {}).get('odds')
        morning_odds = snapshots[1]['odds_data'].get(horse_num, {}).get('odds')
        pre_deadline_odds = snapshots[2]['odds_data'].get(horse_num, {}).get('odds')
        
        movement = {
            'horse_num': horse_num,
            'prev_night': prev_night_odds,
            'morning': morning_odds,
            'pre_deadline': pre_deadline_odds,
            'sharp_drop_morning': detect_odds_sharp_drop(prev_night_odds, morning_odds),
            'sharp_drop_final': detect_odds_sharp_drop(morning_odds, pre_deadline_odds),
        }
        
        # 急落フラグ: どちらかの区間で30%以上下落
        movement['is_hot'] = movement['sharp_drop_morning'] or movement['sharp_drop_final']
        results[horse_num] = movement
    
    return results
```

このオッズ変動追跡のために、システムは3つの時点でオッズのスナップショットを保存するようにした：
1. **前日夜**（WIN5販売開始直後、通常前日15時頃から）
2. **当日朝**（レース当日の8〜9時頃）
3. **締切直前**（各レースの締切15分前）

3時点のデータを比較することで、「じわじわ人気が上がっている馬」「最終局面で急に買われた馬」「ずっと人気がある本命馬」などが可視化できるようになった。

実際にこの機能を使ってみると、「前日夜は5番人気（オッズ12.3倍）だったのに、当日朝には3番人気（オッズ6.8倍）になっていた馬」が2着以内に来るケースが体感として多いと感じた。もちろんこれはバックテストで統計的に検証する必要があるが、少なくとも「注目すべき馬を見つける」機能としては十分に機能している。

UIでは急落馬を赤色でハイライト表示し、ユーザーがひと目で注目馬を確認できるようにした。この「オッズ急落ハイライト」は、ユーザー（自分自身だが）が最もよく参照する機能の一つになっている。

---

## 9. UIの進化（コンパクト表示、スマホ対応）

最初に作ったWebUIは、正直言って酷いものだった。

Flaskでとりあえず動くものを作った段階では、HTMLテーブルがずらりと並んだだけの無骨な画面だった。5レース分の出馬表が縦に並んでいて、画面をスクロールしないと全体が見えない。スマホで開いたら横スクロールが必要で、選択操作もやりにくい。

「これは実用にならない」と思って、UIの全面的な作り直しを決断した。

課題は明確だった：
1. **情報密度**：5レース分の出馬情報（各レース最低10〜18頭）を1画面に収める
2. **操作性**：どの馬を「含める」「除外する」を素早く切り替えられる
3. **スマホ対応**：競馬場やPAT端末の前でスマホから操作できること
4. **オッズ変動の視認性**：前日比でオッズが動いた馬がひと目でわかること

**コンパクト表示の実現：**

5レースを横並びにする「ヨコ5列レイアウト」を採用した。各列（スロット）に出馬情報をコンパクトに表示し、縦スクロールなしで全体が見える設計にした。

```html
<!-- 5スロットを横並びにするFlexレイアウト -->
<div class="slots-container" style="display: flex; gap: 8px; overflow-x: auto;">
  {% for slot in slots %}
  <div class="slot-card" style="min-width: 200px; flex: 1;">
    <div class="slot-header">
      <span class="slot-name">S{{ slot.number }}</span>
      <span class="race-name">{{ slot.race_name }}</span>
    </div>
    <div class="horse-list">
      {% for horse in slot.horses %}
      <div class="horse-row {% if horse.is_hot %}hot-horse{% endif %}"
           data-horse-id="{{ horse.id }}"
           onclick="toggleHorse(this)">
        <span class="horse-num">{{ horse.number }}</span>
        <span class="horse-name">{{ horse.name }}</span>
        <span class="popularity">{{ horse.popularity }}人</span>
        <span class="odds {% if horse.odds_dropped %}odds-drop{% endif %}">
          {{ horse.odds }}倍
        </span>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endfor %}
</div>
```

**除外UI：**

馬をクリック（タップ）すると「選択中」→「除外」→「選択中」とトグルする仕組みにした。除外された馬はグレーアウトして視覚的にはっきりわかるようにした。

```javascript
function toggleHorse(element) {
    const horseId = element.dataset.horseId;
    const slotNum = element.closest('.slot-card').dataset.slotNum;
    
    if (element.classList.contains('excluded')) {
        // 除外を解除
        element.classList.remove('excluded');
        removeExclusion(slotNum, horseId);
    } else {
        // 除外する
        element.classList.add('excluded');
        addExclusion(slotNum, horseId);
    }
    
    // リアルタイムで点数を再計算して表示
    updateCombinationCount();
}

function updateCombinationCount() {
    // 各スロットの選択済み馬の人気順を取得
    const slotSelections = getSlotSelections();
    
    // サーバーに送ってターゲットゾーン内の組み合わせ数を計算
    fetch('/api/count_combinations', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({selections: slotSelections})
    })
    .then(r => r.json())
    .then(data => {
        document.getElementById('combo-count').textContent = data.count + '通り';
        document.getElementById('total-cost').textContent = 
            (data.count * 100).toLocaleString() + '円';
        
        // 予算超過の場合は警告表示
        if (data.count > 1000) {
            document.getElementById('combo-count').classList.add('over-budget');
        }
    });
}
```

**IPATコード生成：**

WIN5の馬券購入はIPAT（インターネット投票）で行うが、IPATには独自の入力形式がある。各レースで選んだ馬番をカンマ区切りで入力する必要がある。この形式への変換を自動化し、「コピーボタン」一つでIPATに貼り付けられるようにした。

```python
def generate_ipat_code(slot_horse_selections):
    """
    スロットごとの選択馬番リストをIPAT入力形式に変換
    
    slot_horse_selections: {
        1: [1, 3, 5],  # スロット1で馬番1,3,5を選択
        2: [2, 4],     # スロット2で馬番2,4を選択
        ...
    }
    """
    ipat_parts = []
    for slot_num in sorted(slot_horse_selections.keys()):
        horses = sorted(slot_horse_selections[slot_num])
        # IPAT形式: 馬番をゼロパディング2桁でカンマ区切り
        horse_str = ','.join(f'{h:02d}' for h in horses)
        ipat_parts.append(horse_str)
    
    return ' / '.join(ipat_parts)

# 出力例: "01,03,05 / 02,04 / 01,02,03,06 / 01,02,04,05 / 01,02,03"
```

スマホ対応については、CSSのメディアクエリを使って小さな画面では縦並びレイアウトに切り替えるようにした。ただしスマホの縦画面では5スロットを一覧するのが難しいため、「スワイプで切り替え」できるカルーセル形式も追加実装した。

UIを作り直すたびに「もっとこうしたい」が出てきて、気づけばUI関連だけで100時間以上使っていた。プログラマーあるある、かもしれない。

---

## 10. クラウドデプロイ（Render.com）

ローカルで動くシステムができたところで、次はクラウドへのデプロイだ。

最初はVPSを借りることも考えたが、費用と管理の手間を考えてPaaSを使うことにした。候補はHeroku、Railway、Render.comの3つだった。

Herokuは以前使ったことがあるが、無料プランの廃止以降はコスト面が気になる。Railwayはシンプルだが、PostgreSQLの永続化に若干不安があった。Render.comは無料プラン（インスタンスが15分アイドルでスリープする制限あり）があり、PostgreSQLも永続ディスクで提供されていた。

WIN5は週1回（毎週日曜が中心）しか使わないシステムなので、「アイドル時にスリープ」するRender.comの無料プランでも実用上は問題ない。毎週土曜の夜にアクセスすればスリープから復帰するし、日曜の朝には普通に使えている。

**デプロイの構成：**
- Webサービス: Flask アプリ（Python 3.11）
- データベース: PostgreSQL（Render.com マネージド）
- 定期タスク: Render.comのCronジョブ機能（オッズスナップショット取得）

`render.yaml`（Render.comのIaC設定ファイル）：

```yaml
services:
  - type: web
    name: win5-analyzer
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "gunicorn app:app"
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: win5-db
          property: connectionString
      - key: SECRET_KEY
        generateValue: true
      - key: FLASK_ENV
        value: production

  - type: cron
    name: win5-odds-snapshot
    env: python
    schedule: "0 8 * * 0"  # 毎週日曜 8:00 UTC (17:00 JST)
    buildCommand: "pip install -r requirements.txt"
    startCommand: "python scripts/take_odds_snapshot.py"

databases:
  - name: win5-db
    databaseName: win5_analyzer
    user: win5_user
    plan: free
```

デプロイ自体は比較的スムーズに進んだが、いくつか詰まりポイントがあった。

**詰まりポイント1: PostgreSQLとSQLiteの差異**

ローカル開発ではSQLiteを使っていたが、Render.comではPostgreSQLを使う。SQLAlchemyを使っていたのでほとんど透過的に動くはずだったが、いくつかの箇所で方言の違いが問題になった。

SQLiteでは`strftime('%Y', created_at)`が使えるが、PostgreSQLでは`EXTRACT(YEAR FROM created_at)`か`date_part('year', created_at)`を使う必要がある。

```python
# 方言に依存しないSQLAlchemyの書き方
from sqlalchemy import extract

# ローカル（SQLite）でもPostgreSQLでも動く
year_filter = extract('year', Event.created_at) == target_year
results = db.session.query(Event).filter(year_filter).all()
```

**詰まりポイント2: データベースマイグレーション**

開発中にテーブル構造を何度も変更したが、Render.comのPostgreSQLに対してFlask-Migrateを使ったマイグレーションを正しく適用する手順を確立するまで時間がかかった。

最終的には、Render.comのビルドコマンドにマイグレーションを組み込んだ：

```bash
# buildCommand
pip install -r requirements.txt && flask db upgrade
```

**詰まりポイント3: スリープ復帰の遅さ**

Render.comの無料プランでは、インスタンスがスリープした後の初回アクセスに30〜60秒かかることがある。これは競馬当日の朝に「ページが開かない！」というストレスの元になった。

対策として、「ウォームアップリクエスト」を自動で送る簡単なcronスクリプトをRender.com上に設定した。毎週土曜の夜にpingを送り、日曜の朝に向けてインスタンスを起こしておく。

```yaml
  - type: cron
    name: win5-warmup
    env: python
    schedule: "0 20 * * 6"  # 毎週土曜 20:00 UTC (日曜5:00 JST)
    startCommand: "python -c \"import requests; requests.get('https://win5-analyzer.onrender.com/health')\""
```

---

## 11. 実際に使ってみた結果と反省

さて、実際にこのシステムを使って購入してみた結果はどうだったか。

正直に書く。

**2024年の成績（システム本格稼働後）：**

| 期間 | 参加回数 | 投資総額 | 払戻総額 | 損益 |
|------|----------|----------|----------|------|
| 2024年上期 | 22回 | 約88万円 | 約12万円 | -76万円 |
| 2024年下期 | 20回 | 約74万円 | 約31万円 | -43万円 |

合計で**-119万円**。当たり前といえば当たり前だが、なかなか厳しい数字だ。

「えっ、それだけ投資してその結果？意味なくない？」と思った方もいるだろう。ただ、冷静に考えてほしいのだが、WIN5の期待値は公式の控除率から計算すると約80%、つまり100円投資すると期待値は80円だ。なので162万円投資したとすると期待値ベースの返戻は約130万円、実際の払戻43万円はそれより低い。これはサンプル数が少なすぎて運の要素が大きいことを意味している。

一方で、「ターゲットゾーン戦略が機能しているか」という観点での評価も行った。

私が購入した42回のうち、実際の「人気の和」がターゲットゾーン（15〜22）に収まったケースが**19回（45.2%）**だった。統計的には44%という数字を出していたので、実測値がほぼ一致している。つまり**戦略の前提自体は正しい**と言える。

問題は、「ターゲットゾーンに収まった19回で的中できたか」だ。残念ながら19回のうち、買い目に勝ち馬が全部含まれていたケースは**3回**だった。しかし3回とも払戻は低く（最高でも18,000円）、投資額を大きく下回った。

この「的中したのに利益が出ない」問題は根本的な課題だ。

WIN5は的中者が少ないほど高配当になる。ターゲットゾーン戦略は「的中確率を上げる」方向に働くが、それは同時に「多くの人が同じような考え方をしているなら払戻が低くなる」ことも意味する。人気馬を中心に買うということは、同じことをしている人が多い可能性がある。

この矛盾を解決するには、「正しく人気がある馬」と「過大評価されている馬」を区別する能力が必要だ。現状のシステムはオッズの絶対値と変動は追跡できるが、「この馬のオッズは適正か」という判断はできていない。

---

**大きな反省点：**

**反省1: バックテストの検証が甘かった**

328回分のデータを使ってバックテストを行ったが、「ターゲットゾーン内に収まる確率」の検証が中心だった。実際の買い目（どの馬番を選ぶか）まで含めたバックテストができていなかった。

現在のシステムは「オッズから人気順を算出し、それを使って買い目を生成する」が、過去データには「最終オッズ」しか記録されていない。ゆえに「この回にこのシステムを使っていたらどんな買い目が生成され、的中していたか」を正確に再現することが難しかった。

今後は、より詳細なオッズスナップショットのデータ収集を行い、完全なバックテストができる体制を作る必要がある。

**反省2: 投資額の管理が甘かった**

「5〜10万円/週」という予算設定をしていたが、実際には高い週も低い週もあり、管理が甘かった。特にキャリーオーバーが積み上がっているときに「もう少し多く買おう」という誘惑に負けたことが何度かあった。

システムが「今週の推奨投資額」を計算して、ユーザーに提示する機能があれば良かったかもしれない。

**反省3: 心理的バイアスに負けた**

「この馬は絶対来ない」という思い込みで、オッズが急落していた馬を除外し、その馬が来て的中を逃したケースが複数あった。

UIの除外機能は「直感で使えるように」設計したが、それが仇になることがある。システムの推奨通りに買う規律が必要だった。

---

## 12. 500時間かけて学んだこと

1年半、500時間以上をこのプロジェクトに費やしてきた。競馬で収益を上げるという目標には（まだ）達せていないが、得たものは多い。

**技術面で学んだこと：**

まず、**Webスクレイピングの現実**を学んだ。「HTMLを取得するだけ」と思っていたが、JavaScriptレンダリング問題、レート制限、HTMLの年次変化、ページ構造の変動など、実際には無数の障壁がある。今回はAPIエンドポイントの発見によって多くの問題を回避できたが、これは「Webの仕組みを深く理解していないと見つけられない」ものだ。

DevToolsのNetworkタブを根気よく眺め続けることで、見つけられた。

次に、**データモデリングの重要性**を痛感した。最初はRaceテーブルとResultテーブルを作ればいいと思っていたが、「スロット」「スナップショット」「除外設定」「購入記録」など、設計すべきエンティティが次第に明らかになってきた。最初から全部設計するのは難しいが、後から変更するとマイグレーションが面倒になる。適切な粒度でテーブルを設計することの難しさを実感した。

```python
# 最終的なデータモデル（SQLAlchemy）
class Win5Event(db.Model):
    """WIN5開催イベント"""
    id = db.Column(db.Integer, primary_key=True)
    event_date = db.Column(db.Date, nullable=False, unique=True)
    carryover_amount = db.Column(db.BigInteger, default=0)
    result_published = db.Column(db.Boolean, default=False)
    
    slots = db.relationship('Win5Slot', back_populates='event', cascade='all, delete-orphan')

class Win5Slot(db.Model):
    """WIN5の各スロット（5つのレース枠）"""
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('win5_event.id'), nullable=False)
    slot_number = db.Column(db.Integer, nullable=False)  # 1〜5
    race_id = db.Column(db.String(20), nullable=False)   # netkeibaのレースID
    race_name = db.Column(db.String(100))
    venue = db.Column(db.String(50))
    race_number = db.Column(db.Integer)
    
    event = db.relationship('Win5Event', back_populates='slots')
    horses = db.relationship('Horse', back_populates='slot', cascade='all, delete-orphan')
    snapshots = db.relationship('OddsSnapshot', back_populates='slot')

class Horse(db.Model):
    """出走馬"""
    id = db.Column(db.Integer, primary_key=True)
    slot_id = db.Column(db.Integer, db.ForeignKey('win5_slot.id'), nullable=False)
    horse_number = db.Column(db.Integer, nullable=False)
    horse_name = db.Column(db.String(100))
    is_excluded = db.Column(db.Boolean, default=False)
    
    slot = db.relationship('Win5Slot', back_populates='horses')

class OddsSnapshot(db.Model):
    """オッズスナップショット（特定時点のオッズデータ）"""
    id = db.Column(db.Integer, primary_key=True)
    slot_id = db.Column(db.Integer, db.ForeignKey('win5_slot.id'), nullable=False)
    snapshot_type = db.Column(db.String(20))  # 'prev_night', 'morning', 'pre_deadline'
    taken_at = db.Column(db.DateTime, nullable=False)
    odds_json = db.Column(db.Text)  # JSON形式で保存
    
    slot = db.relationship('Win5Slot', back_populates='snapshots')
```

**思考面で学んだこと：**

「データがあれば答えが出る」という思い込みを捨てることができた。

328回分のデータを集めて分析したが、それでも「次の結果を確実に予測する」ことは不可能だ。確率と統計は「傾向を知る」ツールであり、「個別の結果を予測する」ツールではない。これは頭では理解していたつもりだったが、実際に数字と向き合い続けることで、より深く腑に落ちた。

また、「自分がバイアスを持っている」ことへの自覚も深まった。データ分析をしていると、「自分の仮説を支持するデータ」を無意識に重視してしまう「確証バイアス」がある。WIN5の分析でも、「これは機能するはずだ」という思いが強すぎて、反証になるデータを見落としていた部分があったと思う。

**プロダクト開発の観点から学んだこと：**

「作りたいもの」と「使いやすいもの」は必ずしも一致しない。

最初に作ったUIは、技術的には面白い機能がたくさんあったが、実際に使うときに「どこに何があるか」わかりにくかった。競馬当日の朝、時間がない中で素早く操作するためのUIとして、シンプルさが最優先だと気づいたのは、使い始めて3ヶ月後のことだった。

「MVP（最小限動くもの）をとにかく早く作って使ってみる」という教訓は、副業でアプリ開発をしているときも学んでいたはずだったが、「自分のプロジェクト」だと完璧主義が顔を出してしまいがちだ。

---

## 13. 今後の展望

500時間かけて作ったシステムだが、まだ「道半ば」だと思っている。

**短期的にやりたいこと：**

**完全バックテスト機能の実装**

現在のシステムは「どんな買い目を生成したか」を記録しているが、「その買い目で過去のデータに適用したらどうなったか」を検証する機能が不十分だ。

毎週の購入記録を積み重ねながら、同時に「もしこの設定で過去○週に適用していたら」というシミュレーションができるバックテストエンジンを実装する予定だ。

**機械学習によるスロット別重要度の学習**

現在は「S3・S4は荒れやすいから5番人気まで選ぶ」という手動の経験則を使っているが、これを機械学習で自動化できないか検討している。

具体的には、各週の「レースの属性」（重賞格、出走頭数、芝/ダート、距離など）を特徴量として、「何番人気まで選べば目標カバー率を達成できるか」を学習するモデルを作りたい。

```python
# 将来的に実装したい機能のイメージ
class SlotOptimizer:
    """
    各スロットの特性から最適な人気順上限を学習・予測する
    """
    def __init__(self, model_path=None):
        self.model = self._load_or_create_model(model_path)
    
    def predict_optimal_cutoff(self, slot_features):
        """
        スロットの特徴から「何番人気まで選ぶべきか」を予測
        
        slot_features: {
            'race_grade': 'G2',       # レースグレード
            'field_size': 14,          # 出走頭数
            'surface': 'turf',         # 芝/ダート
            'distance': 2000,          # 距離
            'venue': '東京',           # 開催場
            'season': 'autumn',        # 季節
            'carryover': 500000000,    # キャリーオーバー金額
        }
        """
        features = self._encode_features(slot_features)
        return int(self.model.predict([features])[0])
```

**AI馬評価の組み込み**

各馬の調教タイムや近走成績、騎手・厩舎の成績などをスコア化して、「オッズに対して過小評価されている馬」を検出する機能を検討している。これは既存の競馬AIが取り組んでいるアプローチだが、WIN5専用に最適化した形で実装できれば独自の価値が出る。

**長期的な方向性：**

老直に言うと、「このシステムで確実に儲かる」とは思っていない。公営ギャンブルである以上、期待値はシステム的に100%を下回る（WIN5は約80%）。いかに分析を精緻化しても、長期的な期待値を100%以上にすることはほぼ不可能だ。

ただ、このプロジェクトが持つ価値は別のところにある。

一つは「学習の場」としての価値だ。Pythonでのデータ分析、Webスクレイピング、Flaskでのアプリ開発、PostgreSQLの設計、クラウドデプロイ──これらの技術を「実際に動くプロジェクト」として実装することで、書籍やチュートリアルでは得られない実践的な知識が積み上がった。

もう一つは「楽しさ」だ。毎週日曜の朝、このシステムを開きながらコーヒーを飲んで出馬表を眺める時間が、純粋に楽しい。システムが教えてくれるオッズ動向を見ながら「この馬、明らかに買われてるな」とか「このレースは荒れそうだから絞るか」と考える時間は、単純に競馬観戦の楽しさを高めてくれている。

---

## 14. まとめ

WIN5分析システムを500時間かけて作った話を、長々と書いてきた。

振り返ってみると、このプロジェクトは「競馬で勝つため」に始まったが、気づいてみれば「プログラミングとデータ分析を学ぶための最高の教材」になっていた。

技術的な成果をまとめると：
- **6年分328回のWIN5データ（1640スロット）を収集・構造化**
- **「人気の和」を指標としたターゲットゾーン戦略（15〜22が44%）を発見**
- **netkeibaの内部APIエンドポイント発見によるオッズ取得の自動化**
- **3時点のオッズスナップショット追跡による急落馬検出**
- **Render.comへのクラウドデプロイ、PostgreSQL永続化**
- **スマホ対応のモバイルファーストUI、コンパクト5スロット表示**

一方で正直に言えば、このシステムを使って「大きく儲かった」わけではない。2024年通年で見ると、むしろ赤字だ。

でも後悔はしていない。

データを眺め、パターンを探し、コードを書き、動かして、また修正する──この繰り返しの中で、プログラマーとして、データアナリストとして、そして競馬ファンとして、確実に成長できたと思っている。

「人気の和」というシンプルな指標が、6年分のデータでこれだけはっきりしたパターンを見せてくれたときの興奮は今でも覚えている。netkeibaのAPIエンドポイントを発見したときの「これだ！」という感覚も忘れられない。

競馬×プログラミングというニッチな組み合わせだけれど、もし同じような興味を持っている人がいれば、ぜひ参考にしてほしい。そして「もっといい方法がある」「ここはこう改善できる」というアイデアがあれば、ぜひコメントで教えてほしい。

WIN5は難しい。でも、だからこそ面白い。

---

### 使用技術スタック

```
Backend:
  - Python 3.11
  - Flask 3.0
  - SQLAlchemy 2.0
  - Flask-Migrate
  - requests + BeautifulSoup4
  - APScheduler（定期タスク）

Database:
  - PostgreSQL 15（本番: Render.com）
  - SQLite（ローカル開発）

Frontend:
  - Jinja2テンプレート
  - Vanilla JavaScript
  - CSS（Flexbox/Grid）
  - Bootstrap 5（一部）

Infrastructure:
  - Render.com（Web + PostgreSQL + Cron）
  - GitHub（バージョン管理）
  - Gunicorn（WSGIサーバー）

Data Source:
  - netkeiba.com（スクレイピング + 内部API）
  - JRA公式サイト（WIN5情報補完）
```

---

*このnoteが参考になったら「スキ」を押してもらえると嬉しいです。質問やフィードバックはコメント欄にどうぞ。*

*次回は「バックテストエンジンの実装」について書く予定です。*
