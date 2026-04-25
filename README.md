# 数学I・A・II・B 学習最適化

スマホだけで使える、数学I・A・II・B 専用の Streamlit アプリです。

今回の版は `記述式` ではなく `選択式` に振り切っています。  
目的は、スマホで短時間でも回しやすく、数学の単元別分析と復習ループを強くすることです。

## 現在の対応単元

- 数学I: 二次関数 / 三角比 / 図形と計量
- 数学A: 場合の数 / 確率
- 数学II: 指数・対数 / 微分法
- 数学B: 数列 / ベクトル

## 主な機能

- 単元別の選択式問題生成
- 高品質問題バンク優先の出題
- 正誤判定
- コース別 / 単元別 / 技能別分析
- 復習キュー
- お気に入り / あとで解く
- 解答後の任意振り返り質問
- チェス式の同型3連戦トレーニング
- 選択理由の記録と分析
- GitHub を使った永続保存
- スマホ向け UI

## ファイル構成

```text
.
├── app.py
├── MATH_TEXTBOOK.md
├── MATH_INPUT_GUIDE.md
├── MATH_PRACTICE_SET.md
├── local_ai_simulator.py
├── requirements.txt
├── README.md
└── data
    ├── logs.json
    ├── mistakes.json
    ├── questions.json
    ├── question_bank.json
    └── simulation_jobs.json
```

## デプロイ手順

1. このフォルダを GitHub リポジトリに push します。
2. [Streamlit Community Cloud](https://share.streamlit.io/) にログインします。
3. `New app` を押します。
4. 対象の GitHub リポジトリを選びます。
5. Main file path に `app.py` を指定します。
6. Deploy を押します。
7. 永続保存したい場合は `Settings > Secrets` を設定します。

## 永続保存の設定

```toml
GITHUB_TOKEN = "your-github-token"
GITHUB_REPO = "your-name/your-repo"
GITHUB_BRANCH = "main"
GITHUB_DATA_PATH = "data"
```

## スマホでの使い方

1. `問題生成` でコースと単元を選びます。
2. 4択問題を作成します。
3. `解答` で選択肢を選びます。
4. `分析` で弱点単元と技能を確認します。
5. 必要なら `ホーム画面に追加` してアプリのように使います。

## インプット用ノート

- [MATH_TEXTBOOK.md](./MATH_TEXTBOOK.md)
- [MATH_INPUT_GUIDE.md](./MATH_INPUT_GUIDE.md)
- [MATH_PRACTICE_SET.md](./MATH_PRACTICE_SET.md)
- 問題を解く前に、単元ごとの判断の型を短く確認できます。

## 設計方針

- 数学専用にする
- 数学I・A・II・B を単元別に分析する
- 記述式ではなく選択式で回転率を上げる
- 良問の構造をもつ問題バンクを優先して使う
- 無料で動く
- 外部サーバー不要
- Streamlit Cloud へそのまま載せられる構成にする

## ローカルAIシミュレーター

Ollama を使って高品質な問題候補を自動生成し、問題バンクへ追加するローカルスクリプトを同梱しています。

基本実行:

```powershell
python local_ai_simulator.py --generator-model qwen3:4b --idle-threshold 8
```

放置時に自動再開し続ける:

```powershell
python local_ai_simulator.py --generator-model qwen3:4b --idle-threshold 8 --loop --poll-seconds 120
```

高品質モードを夜や離席中だけ回したいとき:

```powershell
python local_ai_simulator.py --generator-model qwen2-math:7b --idle-threshold 12 --loop --poll-seconds 180 --max-jobs-per-cycle 1
```

ポイント:

- PC を8分以上触っていないときだけ再開
- `data/simulation_jobs.json` にある単元を交代で1件ずつ回す
- 1回の放置で既定では1ジョブだけ、しかも1問だけ作る
- ジョブごとにモデルを停止するので、ほかのアプリと共存しやすい
- 生成された良問候補は `data/question_bank.json` に追記
- 実行順は `data/simulation_state.json` に保存される
