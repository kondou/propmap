# PropMap ユーザーガイド

---

## 1. はじめに

### PropMapとは

PropMapは、アマチュア無線コンテストの公開ログデータおよび RBN（Reverse Beacon Network）スポットデータを集約し、指定したグリッドロケーターを中心とした大圏方位図（Azimuthal Equidistant Map）上に、過去の HF 帯の電波伝搬状況をヒートマップとして可視化するツール。過去のデータをベースとしていて、同時期のコンテストでの電波伝播状況の傾向の把握に有用。過去データの再生そして、実時間に過去データの時間を合わせることでリアルタイムでの同時刻の過去データの参照が可能

コンテスト参加時の運用計画、バンドチェンジのタイミング把握、過去コンテストの伝搬傾向分析、リアルタイム参照が可能

### 動作環境・必要なもの

- macOS Tahoe / Windows 11（動作確認済み）
- Python 3（インストール手順は「[Python 3 のインストール](#python-3-のインストール)」参照）
- モダンブラウザ（Safari、Chrome、Edge 等）
- 参照したいコンテストの JSON データファイル（`~/heatmap/data/` に配置済みのこと）。[事前データ準備の章を参照してのデータの作成が必要](#10-事前データ準備)

### 前提条件
- 参照したいコンテストの公開ログの取得
- 公開ログのヘッダ(**GRID-LOCATOR**)での正しいグリッドロケータの記載(4桁あれば必要十分)
- グリッドロケータ未記載の局は cty.dat によるコールサインからの推定値を使用可能（**est. QSO** / **est. RBN** として通常データとは区別して表示）
- 関連する RBN の生データ(RBN から参照する場合)
- RBN で使用するモードは CW のみ
- RBN で使用する spot は公開ログのうちグリッドロケータが記載された局が対象（**est. RBN** では cty.dat 推定値の局も含む）
- 公開ログ間での QSO のクロスチェックに合致し、双方の局のグリッドロケータが判明している QSO のみデータとして採用
- クロスチェックは双方のログに相手局が同一バンド、同一時刻(時間差は 15 分以内)に載っていることとし、ナンバーの整合性は不問
- クロスチェックでのコールサインは完全合致あるいは 2 文字以内の不一致なら合致とみなす
- バンド不一致の場合、それぞれの局のログ時刻から 15 分以内での当該バンドでの QSO 数の多い方を正しいバンドとみなしてバンド訂正する

---

## 2. セットアップ

### Python 3 のインストール

#### macOS Tahoe以降

macOS には OS 自体に Python 3 が付属しているが、OS アップデートで置き換わるリスクや `pip` の利用しづらさがあるため、Homebrew 経由のインストールを推奨する。データ処理スクリプトで追加パッケージが必要になった場合も Homebrew Python であれば `pip` で容易に対応可能

1. Homebrew のインストール（未導入の場合）：
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
2. Python 3 のインストール：
```bash
brew install python3
```
3. インストール確認：
```bash
python3 --version
```
`Python 3.x.x` と表示されれば成功（x は任意の数値）

#### Windows 11 — WSL2 なし

`heatmap.html`（PropMap 本体）の利用からデータ構築まで、Python for Windows と付属の `generate_all.bat` にて対応。`generate_all.sh` は bash スクリプトのため Windows では直接実行できないため、同等の処理を行う `generate_all.bat` を使用する

1. [python.org](https://www.python.org/downloads/) から Windows 用インストーラを取得する
2. インストール時に **「Add Python to PATH」にチェックを入れる**（デフォルトではオフのため必須）
3. インストール確認（コマンドプロンプト）：
```
python --version
```
`Python 3.x.x` と表示されれば成功。`Python 2.x.x` と表示される場合はPATHの設定を見直すこと

> **注意:** Windows では `python3` ではなく `python` コマンドを使用すること

ファイルの配置先は `%USERPROFILE%\heatmap\`（例: `C:\Users\ユーザー名\heatmap\`）とする

#### Windows 11 — WSL2 あり

WSL2 環境ではシェルスクリプトをそのまま利用でき、macOS と同等の操作感で使用可能。WSL2 のセットアップ手順は [Microsoft 公式ドキュメント](https://learn.microsoft.com/ja-jp/windows/wsl/install) を参照。Ubuntu インストール後、以下で Python 3 を導入する：

```bash
sudo apt update && sudo apt install -y python3 python3-pip
python3 --version
```
`Python 3.x.x` と表示されれば成功

以降の操作は macOS と同じ。ファイルの配置先は WSL2 のホームディレクトリ（`~/heatmap/`）とする。ブラウザは Windows 側で `http://localhost:8765` にアクセスする。

---

### ファイル構成

すべてのファイルは `~/heatmap/`（macOS/Linux/WSL2）または `%USERPROFILE%\heatmap\`（Windows）以下に配置する。リポジトリに含まれるファイルのほか、パイプライン初回実行時に fetch スクリプトが自動取得するファイル（★）とデータ構築スクリプトが生成するファイル（☆）がある。

``` { .no-copy }
~/heatmap/
├── heatmap.html              メインアプリ（単一ファイル完結）
├── start_heatmap.command     起動スクリプト（macOS用）
├── start_heatmap.bat         起動スクリプト（Windows用）
├── countries-50m.json        地形データ
├── fetch_cty.py              cty.dat 一式ダウンロードスクリプト
├── fetch_ssn.py              太陽黒点数データダウンロードスクリプト
├── fetch_rbn_nodes.py        RBNノードリスト生成スクリプト
├── cty_data/                 ★ cty.dat 一式（fetch_cty.py が取得）
├── data/
│   ├── {contest}_{year}.json         ☆ QSOデータ（10分解像度）
│   └── {contest}_{year}_rbn.json     ☆ RBNデータ（10分解像度）
└── contest_logs/
    ├── raw/{contest}_{year}/*.txt     ☆ 公開されたCabrilloログ
    ├── csv/                           ☆ 処理済みCSVファイル
    │   ├── annotated/{contest}_{year}/  ☆ 注釈付きCabrilloログ（通常）
    │   └── annotated_approx/{contest}_{year}/  ☆ 注釈付きCabrilloログ（approx）
    ├── rbn/
    │   ├── raw/YYYYMMDD.zip           ★ RBN rawデータ（download_rbn.py が取得）
    │   └── rbn_nodes.csv              ★ RBNノードリスト（fetch_rbn_nodes.py が取得）
    ├── SN_m_tot_V2.0.txt              ★ 太陽黒点数データ（fetch_ssn.py が取得）
    ├── *.py                           データ処理スクリプト群
    ├── generate_all.sh                全データ一括再生成スクリプト（macOS/Linux用）
    └── generate_all.bat               全データ一括再生成スクリプト（Windows用）
```

### 起動方法

**macOS / Windows (WSL2 あり)**

`start_heatmap.command` をダブルクリックするか、ターミナルで以下を実行する。ダブルクリックでの起動ではターミナルが開くと同時にデフォルトブラウザが自動で起動されるため個別にブラウザを開く必要はない。開いたターミナルを終了させるとブラウザのウィンドウも閉じる

```bash
python3 -m http.server 8765 --directory ~/heatmap
```

**Windows (WSL2 なし)**

`start_heatmap.bat` をダブルクリックするか、コマンドプロンプトから以下を実行する

```
python -m http.server 8765 --directory %USERPROFILE%\heatmap
```

起動後、ブラウザで `http://localhost:8765` にアクセスする

> **注意:** ローカルのファイルサーバーが必要であるため、`heatmap.html` をブラウザで直接開いても動作しない

---

## 3. 画面構成

<img src="images/sc1.png" alt="全体画面" style="max-width:100%;width:1400px;">

画面は大きく2つのエリアで構成される

**大圏地図エリア（左側 または 上側）**
中心グリッドを起点とした大圏方位図にヒートマップを表示するエリア

**コントロール＋グラフエリア（右側 または 下側）**
表示条件の設定と、±3 時間の QSO 数・グリッド数の時系列グラフを表示するエリア

### レスポンシブレイアウト

ウィンドウ幅に応じてレイアウトが自動的に切り替わる

ブラウザウィンドウが広い場合（デスクトップ・ノートPC等）は大圏地図エリアとコントロール＋グラフエリアが横並び、狭い場合（タブレット縦向き・スマートフォン等、またはウィンドウを縮小した場合）は縦積みに自動切替。

<img src="images/sc2.png" alt="縦積みレイアウト" style="max-width:100%;width:550px;">

縦積み時は地図幅がウィンドウ幅いっぱいに広がり、グラフ高さは地図高さの 2.2 倍を上限として表示

---

## 4. 基本操作

<img src="images/sc3.png" alt="コントロールパネル" style="max-width:100%;width:700px;">

### 中心グリッドと表示範囲の設定

**Center（中心グリッド）**
4文字のグリッドロケーター（例: PM52）を入力する。入力後、**Apply** ボタンをクリックするか Enter キーで反映される。あるいは大圏地図をドラッグして中心としたい地域を地図の中央に移動させ **Apply** ボタンをクリック

**Dist（表示距離フィルター）**
スライダーで中心グリッドからの距離（km）を設定する。この距離以内に該当する局が存在する QSO・スポットのみが表示対象

**Fixed チェックボックス**

- **チェックあり（デフォルト）**: ドラッグしても地図の見た目だけが動き、ヒートマップは更新されない。Apply を押した時点でヒートマップが新しい中心に合わせて再描画される
- **チェックなし**: ドラッグに合わせてヒートマップがリアルタイムに更新される。広い範囲をドラッグすると描画負荷が高くなる

地図をドラッグすると中心グリッド名が地図上にフル輝度で表示される。ドラッグ終了後 3 秒で自動的に薄くなり、グリッドパネルの表示に干渉しにくくなる。

**Pan チェックボックス**

チェックを入れると地図がパンモードになる。

- **ドラッグ**: 投影の中心（Center グリッド）を変えずに地図表示位置を移動する。PM52 が中心でもヨーロッパ方面など表示範囲外の地域を大圏地図の表示円内に引き込んで確認可能
- **Ctrl + スクロール / ピンチ操作**: 表示スケールを変更（ベクター再描画のため画質劣化しない）
  - ズームイン: 現在のカーソル位置を中心に拡大
  - ズームアウト: 縮小により広い範囲を表示。全球が収まった時点でそれ以上の縮小は不可
- **チェックを外す / オーバーレイクリック**: 移動・スケール変更をリセットして元の表示に戻す

パンモードで地図が移動またはスケール変更されている間は、以下の要素は非表示（地図の表示を単純化）:

| 非表示になるもの | 理由 |
|---|---|
| 中心グリッドマーカー（赤丸・ラベル） | 投影中心が地図の中心から外れるため |
| 距離同心円とラベル | 大圏地図の中心が不明瞭となるため |
| Dist 青丸 | 同上 |
| ベアリング角度ラベル（N/30/60/E…） | 方位線は残ったまま |
| 圏外グリッドの三角マーク | 大圏地図の中心が不明瞭となるため |

### コンテスト・バンド・モード・パワーの選択

| 項目 | 説明 |
|---|---|
| Band | 表示するバンドを選択（160m / 80m / 40m / 20m / 15m / 10m / All (バンド混合)） |
| Mode | 表示するモードを選択（CW / SSB / All (モード混合)） |
| Power | フィルタリングするパワークラス（High / Low / QRP） |
| Contest | 表示するコンテストを選択 |

モード固定のコンテストではそのモード以外の選択は不可

### 年の選択と複数年マージ

**Year** の各チェックボックスで表示する年を選択。複数年を同時にチェックするとデータをマージして重ね合わせ表示する。複数年マージは過去の傾向を総合的に把握する際に有効。公開ログの古いものについてはグリッドロケータの情報がないものが多いためヒートマップに何も表示されないものについてはこのあたりの背景を理解しておくとよい。このような局を補完表示したい場合は **est. QSO** チェックボックスを参照

画面右上に読み込んだレコード数と年が表示される（例: `1,916,313 records (2025)`、`1,052,123 records (2024+2025)`）

### 時刻スライダーの操作

スライダーを左右にドラッグして表示時刻を変更する。UTC時刻が左側のテキストボックスに表示される。テキストボックスに直接時刻（例: `14:30`）を入力してフォーカスを外すあるいは Enter キーで入力するとスライダーがその時刻に移動する

48時間コンテスト（CQ WW、CQ WPX）では **+1d** チェックボックスが表示される。チェックを入れると2日目（コンテスト開始から24時間後以降）の時刻に切り替わる

### Set Default / Reset / Apply

| ボタン | 動作 |
|---|---|
| **Set Default** | 現在の設定（中心グリッド、表示距離など）をデフォルトとして保存 |
| **Reset** | 設定をデフォルトに戻す |
| **Apply** | Center の変更を反映 |
| **Doc** | 操作ガイドをブラウザの言語設定に応じて別タブで開く（日本語または英語） |

---

## 5. 表示モード

### 通常表示（スライダー手動操作）

スライダーを手動で動かして任意の時刻の伝搬状況を確認するモード。大圏地図に表示されるグリッドパネルとグラフは指定した時刻に連動して更新

### Play（自動再生）

**▶ Play** ボタンをクリックするとコンテスト開始時刻からスライダーが自動的に進み、伝搬の変化をアニメーションで確認可能。再生中は **■ Stop** ボタンで停止

任意の時刻から再生が可能で、48時間コンテストでは **+1d** チェックを入れた状態で Play すると2日目から再生

### RT（リアルタイム）

**⏱ RT** ボタンをクリックすると現在のUTC時刻に同期してデータを表示。コンテスト開催中に現時刻に同期させての伝搬状況が確認可能

48時間コンテストでは **+1d** チェックボックスで1日目・2日目を切り替える。コンテスト実施週末の当日は自動的に正しい日に切り替わる

---

## 6. 大圏地図の見方

<img src="images/sc4.png" alt="QSOヒートマップ" style="max-width:100%;width:960px;">

### 大圏方位図とは

大圏方位図（Azimuthal Equidistant Map）は、中心グリッドからの距離と方位が正確に表現される地図投影法。中心から任意の点への直線が大圏（最短経路）を表す。同心円は中心からの距離（km）を示す。

### QSOヒートマップ

4文字グリッドロケータ単位で地図上に配置される色付き矩形を**グリッドパネル**と呼ぶ。局が存在するグリッドごとに選択した時刻付近のQSO数を集計してグリッドパネルの色で表示。

- 色は **低（緑）→ 黄 → オレンジ → 高（赤）** のグラデーション
- 画面左上の **QSO** カラースケールバーで色と数量の対応を確認可能

### RBNヒートマップ

CW のモードがあるコンテストのみ表示可能。SSBコンテストに切り替えるとチェックボックスが自動で外れてグレーアウトされる。**RBN** チェックボックスをONにするとRBNスポットデータをマゼンタ系の色のグリッドパネルにて表示

<img src="images/sc5.png" alt="RBNヒートマップ" style="max-width:100%;width:960px;">

- 色は **低（暗紫）→ マゼンタ → 高（白）** のグラデーション
- 画面左上の **RBN** カラースケールバーで確認可能

### est. QSO / est. RBN（推定グリッドデータ）

2018 年頃までのコンテストログではグリッドロケータ（MY LOCATOR）用のヘッダの多くが空、あるいはヘッダが使用されておらず、パネルとして表示される数がごくわずかあるいは、0 となってしまう。**est. QSO** および **est. RBN** チェックボックスを ON にすることで cty.dat を参照し、コールサインからグリッドロケータを推定表示する。

- **est. QSO**: グリッドロケータ不定局の QSO データを追加表示
- **est. RBN**: グリッドロケータ不定のスポット局の RBN データを追加表示（CW のあるコンテストのみ）

注意事項:

- グリッドロケータの情報は cty.dat で定義されているエンティティ（国・地域）あるいはコールエリアレベルの精度であり、実際の運用場所とは異なる場合がある
- 通常の QSO / RBN データと重複しない
- 右上のレコード数表示に `(+N est.)` として est. データのレコード数を追記

### 圏外グリッドの三角マーク

大圏地図の表示範囲（円）の外側に存在するグリッドは、円の外周上に三角マークとして方位角を示す形で表示。QSOデータは白系、RBNデータはマゼンタ系の三角で表示。est. QSO / est. RBN が有効な場合、est. 分のグリッドも同様に三角マークで表示される。同じ方位に複数のグリッドがある場合は少しずつずらして表示。三角マークは点滅

Pan モードで地図が移動または縮尺が変更されていると非表示

### グレーライン（明暗境界線）

現在時刻の太陽の明暗境界線をオレンジ色の帯で表示。グレーラインは伝搬状況（特に低いバンド）と密接な関係がある

### 右下オーバーレイの見方

<img src="images/sc6.png" alt="右下オーバーレイ" style="max-width:100%;width:162px;">

右下オーバーレイには以下の情報が表示される

``` { .no-copy }
0/21 (  0.0%)        ← QSO: 圏外グリッド数/総グリッド数（割合）
0/17 (  0%)          ← RBN: 圏外グリッド数/総グリッド数（割合）
Center: PM52
Radius: 20,000km
21 grids · 24 QSOs   ← 表示中のグリッド数とQSO数
17 grids · 23 spots  ← 表示中のRBNグリッド数とスポット数
```

**est. QSO / est. RBN が有効な場合**、est. 分のグリッド数・QSO数・スポット数も合算して表示される。

大きいフォントの数値（分子）は**表示範囲外のグリッド数**を示す。数値が0でない場合は点滅することで円外にデータがあることを示す

各行にマウスカーソルを重ねると詳細情報をツールチップにて表示。オーバーレイ全体をクリックすると表示範囲（Radius）をデフォルト値に戻す

### ツールチップ

大圏地図上のグリッドパネルにマウスカーソルを重ねると、そのグリッドの詳細情報がツールチップにて表示

- **グリッド名**（太字）
- 選択年ごとの QSO 数（例: `2024: 12 QSO`）。複数年選択時は年別に列挙
- RBN 有効時はスポット数をマゼンタ色で追加表示（例: `RBN: 5`）
- **est. QSO / est. RBN が有効な場合**、est. 分の QSO 数・スポット数も含めて表示される

---

## 7. グラフパネルの見方

<img src="images/sc7.png" alt="グラフパネル" style="max-width:100%;width:700px;">

グラフパネルには以下の4つのグラフを表示。いずれも**現在表示時刻の±3時間**の範囲が対象

### QSOs (±3h)

コンテストログをベースにした時刻ごとのQSO数をバンド別の折れ線グラフで表示。縦の点線が現在表示時刻となる

### RBN Spots (±3h)

RBNスポットデータをベースにした時刻ごとのスポット数をバンド別の折れ線グラフにて表示

### Grids (±3h)

コンテストログをベースにした時刻ごとのアクティブグリッド数（ユニークなグリッド数）をバンド別に表示

### RBN Grids (±3h)

RBNスポットデータをベースにした時刻ごとのアクティブグリッド数をバンド別に表示

### バンド別カラー

| バンド | 色 |
|---|---|
| 10m | 赤 |
| 15m | オレンジ |
| 20m | 青 |
| 40m | 黄 |
| 80m | 緑 |
| 160m | 紫 |

### ツールチップ

グラフ上にマウスカーソルを重ねるとその時刻のバンド別数値がツールチップにて表示

---

## 8. Crawlモード（バンド自動巡回）

<img src="images/sc8.png" alt="Crawlモード" style="max-width:100%;width:1400px;">

[RT（リアルタイム）](#rtリアルタイム)表示中に設定した時間間隔で表示バンドを自動的に切り替えることで巡回させるモード

### Auto / All / No の違い

| 設定 | 動作 |
|---|---|
| **Auto** | 現在時刻のデータから、中心グリッド周辺に届いているQSOが全体の15%以上を占めるバンドのみ多い順に巡回。アクティブなバンドに絞った効率的な確認が可能 |
| **All** | 全バンド（10m / 15m / 20m / 40m / 80m / 160m）を順番に巡回 |
| **No** | 自動巡回せず、バンドとモードは固定のまま |

モード固定のコンテスト（CW専用・SSB専用）では、Crawlの巡回対象もそのモードのみとなり、他のモードには切り替わらない

### 巡回タイマーの設定

**Crawl Timer** で各バンドの表示時間を選択する（5秒 / 10秒 / 15秒）

---

## 9. データについて

### 対応コンテストと収録期間

| コンテスト | 開催時期 | 時間 | RBNデータ |
|---|---|---|---|
| IARU HF | 7月第2 full weekend（土曜 12Z 開始） | 24時間 | あり |
| CQ WW CW | 11月最終 full weekend（土曜 00Z 開始） | 48時間 | あり |
| CQ WW SSB | 10月最終 full weekend（土曜 00Z 開始） | 48時間 | なし |
| CQ WPX CW | 5月最終 full weekend（土曜 00Z 開始） | 48時間 | あり |
| CQ WPX SSB | 3月最終 full weekend（土曜 00Z 開始） | 48時間 | なし |

### RBNデータについて

RBN（Reverse Beacon Network）は、CWやデジタルモードの信号を自動受信・デコードしてスポットするネットワーク。PropMapではRBNスポットデータを用いて、コンテストログに記録されていない伝搬状況も可視化する。RBNデータはCWコンテスト（IARU、CQ WW CW、CQ WPX CW）でのみ利用可能

### SSN（太陽黒点数）について

`SN_m_tot_V2.0.txt`（SILSOが提供する月別太陽黒点数データ）を使用してコンテスト開催月のSSNを自動解決し、データ処理時に活用する想定（現状 SSN は RBN ペア CSV のメタデータフィールドとして記録されているが、ヒートマップ表示への直接の影響はなく、この値の利用は未実装）。ファイルが存在しない場合は `generate_all.sh`（または `.bat`）実行時に `fetch_ssn.py` が自動的にダウンロードする

---

## 10. 事前データ準備

PropMap を使用するには各種データを事前に構築する必要がある。ツールに含めるにはデータが大きすぎるため、利用者が自分で準備することとしている

### データ処理パイプライン

コンテストログデータの処理順序：

``` { .no-copy }
Cabrilloログ（raw/*.txt）
    ↓
step1_collect_logs_fast.py      ログ収集（公開ログからダウンロード）
    ↓
make_spotted_grids_approx.py    コールサインからグリッドを推定（cty.dat参照）
    ↓
step4_crosscheck.py             QSOペアのクロスチェックとCSV生成（通常）
step4_crosscheck_approx.py      同上（推定グリッドを使用）
    ↓
step5_aggregate.py              CSV → JSON集約（heatmap.html用）
```

RBNデータの処理順序：

``` { .no-copy }
RBN raw data（rbn/raw/YYYYMMDD.zip）
    ↓
download_rbn.py                 RBN rawデータのダウンロード
    ↓
make_spotted_grids.py           スポットされたグリッドの抽出（ログ記載値）
    ↓
step4_rbn.py                    RBNペアCSVの生成（通常）
step4_rbn_approx.py             同上（推定グリッドを使用）
    ↓
step5_rbn.py                    CSV → JSON集約（heatmap.html用）
```

RBNノードリストの更新：

``` { .no-copy }
fetch_rbn_nodes.py
    → RBNサイトから現行ノードを取得
    → raw zipから過去コンテストのスポッターを収集
    → 旧ノードは cty.dat でグリッドを補完
    → rbn/rbn_nodes.csv に保存
```

### 全データの一括再生成

#### macOS / WSL2（generate_all.sh）

まず contest_logs ディレクトリに移動する：

```bash
cd ~/heatmap/contest_logs
```

対象確認のみ（実際には実行しない）：

```bash
bash generate_all.sh --dry-run
```

本実行：

```bash
bash generate_all.sh
```

バックグラウンドで実行する場合：

```bash
nohup bash generate_all.sh &
```

進捗確認（スクリプトが内部で `generate_all.log` に記録する）：

```bash
tail -f generate_all.log
```

#### Windows（generate_all.bat）

コマンドプロンプトで contest_logs ディレクトリに移動する：

```
cd %USERPROFILE%\heatmap\contest_logs
```

対象確認のみ（実際には実行しない）：

```
generate_all.bat --dry-run
```

本実行：

```
generate_all.bat
```

### 各スクリプトの役割

| スクリプト | 役割 |
|---|---|
| `contest_utils.py` | コンテスト定義、パス解決、SSN自動解決の共通ユーティリティ |
| `step1_collect_logs_fast.py` | 公開ログの収集・ダウンロード |
| `step3_grid_survey.py` | ログファイルのグリッドロケーター含有状況調査 |
| `step4_crosscheck.py` | QSOのクロスチェックとペアCSV生成 |
| `step4_crosscheck_approx.py` | QSOのクロスチェックとペアCSV生成（cty.dat推定グリッド使用） |
| `step4_rbn.py` | RBNデータの処理とペアCSV生成 |
| `step4_rbn_approx.py` | RBNデータの処理とペアCSV生成（cty.dat推定グリッド使用） |
| `step5_aggregate.py` | QSOペアCSV → ヒートマップJSON |
| `step5_rbn.py` | RBNペアCSV → ヒートマップJSON |
| `make_spotted_grids.py` | RBNスポットグリッドの抽出 |
| `make_spotted_grids_approx.py` | RBNスポットグリッドの抽出（cty.dat フォールバック付き） |
| `lookup_cty.py` | cty.dat からコールサインのグリッドを引くモジュール |
| `download_rbn.py` | RBN rawデータ（zip）のダウンロード |
| `extract_json.py` | 大容量JSONから条件を絞って切り出し |
| `fetch_cty.py` | cty.dat 一式をダウンロード（`cty_data/` に配置） |
| `fetch_ssn.py` | 太陽黒点数データ（SN_m_tot_V2.0.txt）をダウンロード |
| `fetch_rbn_nodes.py` | RBNノードリスト（`rbn/rbn_nodes.csv`）を生成・更新 |
| `fetch_qrz.py` | QRZ.com からコールサインのグリッドロケータを取得 |
| `generate_all.sh` | 全コンテスト・全年の一括再生成（macOS/Linux用） |
| `generate_all.bat` | 全コンテスト・全年の一括再生成（Windows用） |
| `generate_guides.py` | MD から HTML ユーザーガイド（ja/en）を生成 |
| `check_qso_count.py` | 指定条件で `qso_pairs.csv` を検索し、パネル表示対象を確認（デバッグ用） |
| `check_rbn_count.py` | 指定条件で `rbn_pairs.csv` を検索し、RBNパネル表示対象を確認（デバッグ用） |
| `check_rbn_detail.py` | `*_rbn.json` のレコード構造を確認（デバッグ用） |
| `check_rbn_csv.py` | RBN CSV の utc_day 分布を確認（デバッグ用） |
| `check_rbn_json.py` | RBN JSON の t_step 分布を確認（デバッグ用） |

---

## 11. トラブルシューティング

### `heatmap.html` をブラウザで直接開いてもデータが表示されない

`file://` プロトコルではブラウザのセキュリティ制限により JSON データの読み込みがブロックされる。必ずローカルサーバー経由でアクセスすること（[起動方法](#起動方法) 参照）

### パネルが1件も表示されない

以下の順で確認する。

1. **JSON ファイルの存在確認**  
   `data/` に対象ファイル（例: `cqwpx_cw_2024.json`）があるか確認する。なければ `generate_all.sh`（または `.bat`）で再生成する。既存ファイルがあってもステップを強制再実行したい場合は `--force` を付ける

   ```bash
   cd ~/heatmap/contest_logs
   bash generate_all.sh          # 未生成ファイルのみ処理
   bash generate_all.sh --force  # 全ステップ強制再実行
   ```

2. **コンテスト・年・フィルター設定の確認**  
   Band / Mode / Dist / Year の選択が意図したものになっているか確認する。特に Dist が小さすぎると表示対象が少なくなる

3. **CSV レベルでの確認（QSO）**  
   ```bash
   python3 check_qso_count.py --contest cqwpx_cw --year 2024 \
     --center PM52 --dist-km 500 --hour 12 --min 0
   ```
   該当なしであればそのコンテスト・年・各条件にパネル表示対象の QSO が存在しないことを意味する

4. **CSV レベルでの確認（RBN）**  
   ```bash
   python3 check_rbn_count.py --contest cqwpx_cw --year 2024 \
     --center PM52 --dist-km 500 --hour 12 --min 0
   ```

### est. データが表示されない

`data/` に `*_approx.json` ファイルが存在しない。通常は `generate_all.sh`（または `.bat`）が approx ステップも含めて自動実行する。特定コンテスト・年の approx だけ手動で再生成したい場合は以下を実行する

```bash
cd ~/heatmap/contest_logs
python3 step4_crosscheck_approx.py --contest cqwpx_cw --year 2024 \
  --max-call-dist 2 --band-fix-window 15 --annotate-logs
python3 step5_aggregate.py --contest cqwpx_cw --year 2024 \
  --input csv/cqwpx_cw_2024_qso_pairs_approx.csv \
  --output ../data/cqwpx_cw_2024_approx.json
```

### アニメーション（点滅）がカクつく・止まる

- PropMap のタブをバックグラウンドにするとブラウザのタイマー制限により点滅が一時停止する。これはブラウザの仕様であり不具合ではない
- 他タブ・ウィンドウで重い処理（動画・WebGL 等）を開いている場合、CPU リソース競合によりカクつくことがある。PropMap タブをアクティブにし、他の重いページを閉じると改善する

### 初回読み込みが遅い

JSON ファイルは 1 ファイルあたり数十〜200MB 超になる場合があり、初回読み込みに数秒かかることがある。これはデータ量に起因するものであり、2 回目以降はブラウザキャッシュが効く

### ブラウザ互換性

Chrome / Safari / Edge で動作確認済み。Firefox でも動作するが、大量データ処理時のパフォーマンスに差が出ることがある

### スマートフォン・タブレットでの利用

動作確認・使用を想定していない。PC ブラウザでの利用を前提とする
