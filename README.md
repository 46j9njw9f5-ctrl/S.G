# 学習改善エンジン

スマホだけで使える、数学の二次関数の学習改善に特化した Streamlit アプリです。

このアプリは次の流れを 1 つにまとめています。

- 問題生成
- 解答
- ミス分析
- 類題生成
- 次の学習提案

最初の実装は API なしで動きます。問題生成と解説は Python テンプレートで完結しており、Streamlit Community Cloud にそのままデプロイできます。

保存は 2 モードです。

- デフォルト: ローカル JSON
- 推奨: GitHub リポジトリ JSON への永続保存

## 主な機能

- 学習ログ記録
- ミス記録
- 二次関数の最大最小問題の自動生成
- 解答判定
- 弱点分析
- 類題の自動追加
- スマホ向け 4 タブ UI
- GitHub を使った永続保存
- 復習キュー
- お気に入り / あとで解く
- 段階表示の解説
- 自動難易度調整
- YouTube 解説おすすめ
- 解答後の任意振り返り質問

## ファイル構成

```text
.
├── app.py
├── requirements.txt
├── README.md
└── data
    ├── logs.json
    ├── mistakes.json
    └── questions.json
```

## デプロイ手順

1. このフォルダを GitHub リポジトリに push します。
2. [Streamlit Community Cloud](https://share.streamlit.io/) にログインします。
3. `New app` を押します。
4. 対象の GitHub リポジトリを選びます。
5. Main file path に `app.py` を指定します。
6. Deploy を押します。
7. 永続保存したい場合は、Deploy 後に `Settings > Secrets` を設定します。

## GitHub 連携方法

1. GitHub で新しいリポジトリを作成します。
2. このプロジェクトの内容をリポジトリに配置します。
3. Streamlit Community Cloud 側でそのリポジトリを選択してデプロイします。

GitHub Actions や外部サーバーは不要です。

## 永続保存の設定

Streamlit Community Cloud では、アプリ内の JSON ファイルは再起動や再デプロイで消える可能性があります。
そのため、長く使う場合は GitHub リポジトリに JSON を直接保存する設定を推奨します。

### 必要なもの

- 保存先に使う GitHub リポジトリ
- そのリポジトリに書き込める Personal Access Token

### 推奨トークン権限

- Fine-grained token
- Repository contents: Read and write

### Streamlit secrets の設定例

```toml
GITHUB_TOKEN = "your-github-token"
GITHUB_REPO = "your-name/your-repo"
GITHUB_BRANCH = "main"
GITHUB_DATA_PATH = "data"
```

ローカルで内容を確認したい場合は、[.streamlit/secrets.toml.example](C:/Users/uzer/Documents/Codex/2026-04-25-github-github-plugin-github-openai-curated/.streamlit/secrets.toml.example) を元に `secrets.toml` を作ります。
ただし、実運用では Streamlit Community Cloud の `Secrets` 画面に直接設定するのが安全です。

### 動作

- `logs.json`
- `mistakes.json`
- `questions.json`

これらの JSON を GitHub 上の `data/` フォルダに保存します。
この方式なら、スマホから使っても学習履歴が残ります。

## スマホでの使い方

1. `ホーム` で学習ログや手動ミス記録を追加します。
2. `問題生成` で難易度、定義域、苦手パターン、問題数を選んで生成します。
3. `解答` で答えを入力して正誤判定します。
4. `分析` でミスの傾向と次の学習提案を確認します。
5. `類題生成` を押すと、弱点に応じた問題を追加できます。
6. iPhone / Android のブラウザで `ホーム画面に追加` を使うと、アプリのように 1 タップで開けます。

## データ保存について

保存先は JSON ファイルです。

- `data/logs.json`
- `data/mistakes.json`
- `data/questions.json`

この構成は無料で動かしやすく、SQLite より Streamlit Cloud で扱いやすいです。

注意:
Secrets 未設定のままでは Streamlit Cloud 上のローカル JSON を使うため、再起動や再デプロイで保存内容が消えることがあります。長期運用する場合は GitHub 永続保存を使ってください。

## API キー設定方法（任意）

このアプリは API なしで動きます。あとから OpenAI / Gemini / Groq を足したい場合は、`.env` ではなく Streamlit secrets を使います。

Streamlit Community Cloud のアプリ設定で `Secrets` を開き、たとえば次のように設定します。

```toml
OPENAI_API_KEY = "your-key"
GEMINI_API_KEY = "your-key"
GROQ_API_KEY = "your-key"
```

その後、`st.secrets["OPENAI_API_KEY"]` のように参照します。

## 今回の設計方針

- 無料で動く
- 外部サーバー不要
- スマホだけで利用可能
- API なしでも問題生成と解説が成立する
- GitHub secrets を使えば永続保存できる
- 二次関数の最大最小に特化して精度を上げる
- 現在の対応科目は数学のみ
