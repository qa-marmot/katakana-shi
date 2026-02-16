# カタカナーシ - オンライン版

カタカナを使わずにお題を説明するパーティーゲーム「カタカナーシ」のWeb版です。

## 遊び方

1. ルームIDとユーザー名を入力して参加
2. 出題者は表示されたカタカナ語を、カタカナを使わずに説明
3. 他のプレイヤーが正解したら「正解！次のお題へ」ボタンを押す
4. 出題者が交代し、新しいお題が表示される

## 起動方法

### 方法1: Pythonから直接起動

## バックエンド

bash

cd backend
pip install -r requirements.txt
python main.py

バックエンドは `http://localhost:8000` で起動します。

## フロントエンド

bash

cd frontend

## 任意のHTTPサーバーで起動（例：Python）

python -m http.server 3000

フロントエンドは `http://localhost:3000` で起動します。

### 方法2: Dockerで起動

bash

## プロジェクトルートで実行

docker-compose up -d

- バックエンド: `http://localhost:8000`
- フロントエンド: `http://localhost:3000`

停止する場合:
bash
docker-compose down

### フロントエンド（GitHub Pages）

GitHub Pagesは静的サイトのみなので、フロントエンドのみホスト可能です。
バックエンドは別途Renderなどにデプロイする必要があります。

## 技術スタック

- **バックエンド**: FastAPI + WebSocket
- **フロントエンド**: React (CDN版)
- **リアルタイム通信**: WebSocket
- **コンテナ化**: Docker

## 機能一覧

- ✅ ルーム作成・参加機能
- ✅ リアルタイム同期（WebSocket）
- ✅ お題のランダム表示
- ✅ 出題者の自動交代
- ✅ スコア管理
- ✅ カタカナ判定機能
- ✅ チャット機能
- ✅ レスポンシブデザイン

## 環境変数

フロントエンドでWebSocket接続先を変更する場合、`index.html`の以下の部分を編集してください:

javascript
const WS_URL = 'ws://localhost:8000'; // ローカル環境
// const WS_URL = 'wss://your-backend.onrender.com'; // 本番環境
