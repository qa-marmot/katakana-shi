from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Set
import json
import random
import re

app = FastAPI()

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# カタカナ語リスト
KATAKANA_WORDS = [
    "スマートフォン", "コンビニエンスストア", "リモートワーク", "インターネット",
    "コンピューター", "アプリケーション", "セキュリティ", "パスワード",
    "プログラミング", "アルゴリズム", "データベース", "サーバー",
    "クラウド", "ストレージ", "ダウンロード", "アップロード",
    "ブラウザ", "タブレット", "キーボード", "マウス",
    "モニター", "プリンター", "スキャナー", "ルーター",
    "カメラ", "ビデオ", "オーディオ", "スピーカー",
    "イヤホン", "マイク", "リモコン", "エアコン",
    "テレビ", "ラジオ", "ステレオ", "アンプ",
    "バッテリー", "チャージャー", "ケーブル", "アダプター",
    "メモリーカード", "ハードディスク", "フラッシュメモリ", "バックアップ",
    "ソフトウェア", "ハードウェア", "ファームウェア", "ドライバー",
    "インストール", "アンインストール", "アップデート", "バージョン",
    "ライセンス", "サブスクリプション", "フリーソフト", "シェアウェア",
    "ウイルス", "マルウェア", "ファイアウォール", "暗号化",
    "ログイン", "ログアウト", "アカウント", "プロフィール",
    "タイムライン", "フィード", "ストリーミング", "ダウンロード",
    "シェア", "コメント", "いいね", "フォロー",
    "メッセージ", "チャット", "グループ", "スタンプ",
    "エモジ", "ハッシュタグ", "メンション", "リツイート",
    "スクリーンショット", "スクロール", "タップ", "スワイプ",
    "ズーム", "パン", "ピンチ", "ドラッグ",
    "コピー", "ペースト", "カット", "デリート",
    "セーブ", "ロード", "エクスポート", "インポート",
    "サムネイル", "プレビュー", "レンダリング", "エンコード",
    "デコード", "コンプレス", "解凍", "アーカイブ",
]

# ルーム管理
rooms: Dict[str, Dict] = {}
# WebSocket接続管理
connections: Dict[str, List[WebSocket]] = {}


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str, user_name: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)
        
        # ルームが存在しない場合は作成
        if room_id not in rooms:
            rooms[room_id] = {
                "users": [],
                "current_word": random.choice(KATAKANA_WORDS),
                "presenter_index": 0,
                "scores": {}
            }
        
        # ユーザーを追加
        if user_name not in rooms[room_id]["users"]:
            rooms[room_id]["users"].append(user_name)
            rooms[room_id]["scores"][user_name] = 0

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].remove(websocket)
            if len(self.active_connections[room_id]) == 0:
                del self.active_connections[room_id]
                # ルームが空になったら削除
                if room_id in rooms:
                    del rooms[room_id]

    async def broadcast(self, room_id: str, message: dict):
        if room_id in self.active_connections:
            for connection in self.active_connections[room_id]:
                try:
                    await connection.send_json(message)
                except:
                    pass


manager = ConnectionManager()


def check_katakana(text: str) -> bool:
    """カタカナが含まれているかチェック"""
    katakana_pattern = re.compile(r'[ァ-ヶー]')
    return bool(katakana_pattern.search(text))


@app.get("/")
async def root():
    return {"message": "カタカナーシ API Server"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/{room_id}/{user_name}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, user_name: str):
    await manager.connect(websocket, room_id, user_name)
    
    try:
        # 初期状態を送信
        await manager.broadcast(room_id, {
            "type": "state_update",
            "data": rooms[room_id]
        })
        
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "next_word":
                # 次のお題へ
                rooms[room_id]["current_word"] = random.choice(KATAKANA_WORDS)
                rooms[room_id]["presenter_index"] = (rooms[room_id]["presenter_index"] + 1) % len(rooms[room_id]["users"])
                
                # 正解者にポイント追加
                if "winner" in message:
                    winner = message["winner"]
                    if winner in rooms[room_id]["scores"]:
                        rooms[room_id]["scores"][winner] += 1
                
                await manager.broadcast(room_id, {
                    "type": "state_update",
                    "data": rooms[room_id]
                })
            
            elif message["type"] == "check_katakana":
                # カタカナチェック
                text = message.get("text", "")
                has_katakana = check_katakana(text)
                
                await websocket.send_json({
                    "type": "katakana_check_result",
                    "data": {
                        "text": text,
                        "has_katakana": has_katakana
                    }
                })
            
            elif message["type"] == "chat":
                # チャットメッセージをブロードキャスト
                await manager.broadcast(room_id, {
                    "type": "chat",
                    "data": {
                        "user": user_name,
                        "message": message.get("message", "")
                    }
                })
            
            elif message["type"] == "get_state":
                # 現在の状態を送信
                await websocket.send_json({
                    "type": "state_update",
                    "data": rooms[room_id]
                })
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        # ユーザーが退出したことを通知
        if room_id in rooms and user_name in rooms[room_id]["users"]:
            rooms[room_id]["users"].remove(user_name)
            if user_name in rooms[room_id]["scores"]:
                del rooms[room_id]["scores"][user_name]
            
            # 出題者のインデックスを調整
            if len(rooms[room_id]["users"]) > 0:
                rooms[room_id]["presenter_index"] = rooms[room_id]["presenter_index"] % len(rooms[room_id]["users"])
            
            await manager.broadcast(room_id, {
                "type": "state_update",
                "data": rooms[room_id]
            })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
