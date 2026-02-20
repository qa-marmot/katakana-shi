from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional
import json
import random
import re
import asyncio
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    "タイムライン", "フィード", "ストリーミング",
    "シェア", "コメント", "フォロー",
    "メッセージ", "チャット", "グループ", "スタンプ",
    "エモジ", "ハッシュタグ", "メンション", "リツイート",
    "スクリーンショット", "スクロール", "タップ", "スワイプ",
    "ズーム", "パン", "ピンチ", "ドラッグ",
    "コピー", "ペースト", "カット",
    "セーブ", "ロード", "エクスポート", "インポート",
    "サムネイル", "プレビュー", "レンダリング", "エンコード",
    "デコード", "アーカイブ",
]

ROUND_DURATION = 180  # 3分
WIN_SCORE = 10
MAX_ATTEMPTS = 2  # 1ラウンドの解答チャンス

rooms: Dict[str, Dict] = {}


def check_katakana(text: str) -> bool:
    katakana_pattern = re.compile(r'[ァ-ヶー]')
    return bool(katakana_pattern.search(text))


def get_room_state_for_broadcast(room_id: str) -> dict:
    """クライアント送信用のルーム状態（timer_end含む）"""
    room = rooms[room_id]
    return {
        "users": room["users"],
        "current_word": room["current_word"],
        "presenter_index": room["presenter_index"],
        "scores": room["scores"],
        "timer_end": room["timer_end"],
        "answer_attempts": room["answer_attempts"],
        "game_over": room.get("game_over", False),
        "winner": room.get("winner", None),
    }


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str, user_name: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)

        if room_id not in rooms:
            rooms[room_id] = {
                "users": [],
                "current_word": random.choice(KATAKANA_WORDS),
                "presenter_index": 0,
                "scores": {},
                "timer_end": time.time() + ROUND_DURATION,
                "answer_attempts": {},  # {user_name: attempt_count}
                "timer_task": None,
                "game_over": False,
                "winner": None,
            }
            # タイマー開始
            rooms[room_id]["timer_task"] = asyncio.create_task(
                self._round_timer(room_id, rooms[room_id]["current_word"])
            )

        if user_name not in rooms[room_id]["users"]:
            rooms[room_id]["users"].append(user_name)
            rooms[room_id]["scores"][user_name] = 0

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            try:
                self.active_connections[room_id].remove(websocket)
            except ValueError:
                pass
            if len(self.active_connections[room_id]) == 0:
                del self.active_connections[room_id]
                if room_id in rooms:
                    if rooms[room_id].get("timer_task"):
                        rooms[room_id]["timer_task"].cancel()
                    del rooms[room_id]

    async def broadcast(self, room_id: str, message: dict):
        if room_id in self.active_connections:
            dead = []
            for conn in self.active_connections[room_id]:
                try:
                    await conn.send_json(message)
                except Exception:
                    dead.append(conn)
            for conn in dead:
                try:
                    self.active_connections[room_id].remove(conn)
                except ValueError:
                    pass

    async def _round_timer(self, room_id: str, word: str):
        """3分後に時間切れ処理"""
        try:
            await asyncio.sleep(ROUND_DURATION)
        except asyncio.CancelledError:
            return

        if room_id not in rooms:
            return
        if rooms[room_id]["current_word"] != word:
            return  # すでに次のラウンドに移行済み
        if rooms[room_id].get("game_over"):
            return

        # 時間切れ: 出題者を交代、お題を捨てる
        await self._next_round(room_id, winner=None, presenter_gets_point=False)
        await self.broadcast(room_id, {
            "type": "time_up",
            "data": get_room_state_for_broadcast(room_id),
        })

    async def _next_round(self, room_id: str, winner: Optional[str], presenter_gets_point: bool):
        """次のラウンドへ移行"""
        room = rooms[room_id]

        # 古いタイマーをキャンセル
        if room.get("timer_task"):
            room["timer_task"].cancel()

        # ポイント付与
        if winner and winner in room["scores"]:
            room["scores"][winner] += 1  # 正解者+1

        presenter = room["users"][room["presenter_index"]]
        if presenter_gets_point and presenter in room["scores"]:
            room["scores"][presenter] += 1  # 出題者+1

        # 勝利チェック
        for user, score in room["scores"].items():
            if score >= WIN_SCORE:
                room["game_over"] = True
                room["winner"] = user
                await self.broadcast(room_id, {
                    "type": "game_over",
                    "data": get_room_state_for_broadcast(room_id),
                })
                return

        # 次のラウンドへ
        room["presenter_index"] = (room["presenter_index"] + 1) % len(room["users"])
        room["current_word"] = random.choice(KATAKANA_WORDS)
        room["answer_attempts"] = {}
        room["timer_end"] = time.time() + ROUND_DURATION

        room["timer_task"] = asyncio.create_task(
            self._round_timer(room_id, room["current_word"])
        )

        await self.broadcast(room_id, {
            "type": "state_update",
            "data": get_room_state_for_broadcast(room_id),
        })


manager = ConnectionManager()


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
        # 初期状態を全員に送信
        await manager.broadcast(room_id, {
            "type": "state_update",
            "data": get_room_state_for_broadcast(room_id),
        })

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if rooms[room_id].get("game_over"):
                continue  # ゲーム終了後は操作を受け付けない

            if message["type"] == "submit_answer":
                # 解答提出（出題者以外）
                room = rooms[room_id]
                presenter = room["users"][room["presenter_index"]]
                if user_name == presenter:
                    continue  # 出題者は解答できない

                attempts = room["answer_attempts"].get(user_name, 0)
                if attempts >= MAX_ATTEMPTS:
                    await websocket.send_json({
                        "type": "answer_result",
                        "data": {"correct": False, "message": "解答チャンスを使い切りました", "attempts_left": 0}
                    })
                    continue

                answer = message.get("answer", "").strip()
                correct = (answer == room["current_word"])

                room["answer_attempts"][user_name] = attempts + 1
                attempts_left = MAX_ATTEMPTS - room["answer_attempts"][user_name]

                if correct:
                    # 正解: 解答者+1, 出題者+1
                    await manager.broadcast(room_id, {
                        "type": "correct_answer",
                        "data": {
                            "answerer": user_name,
                            "word": room["current_word"],
                        }
                    })
                    await manager._next_round(room_id, winner=user_name, presenter_gets_point=True)
                else:
                    await websocket.send_json({
                        "type": "answer_result",
                        "data": {
                            "correct": False,
                            "message": f"不正解です（残り{attempts_left}回）" if attempts_left > 0 else "解答チャンスを使い切りました",
                            "attempts_left": attempts_left,
                        }
                    })
                    # 全員の解答チャンスが尽きたか確認
                    non_presenters = [u for u in room["users"] if u != presenter]
                    all_exhausted = all(
                        room["answer_attempts"].get(u, 0) >= MAX_ATTEMPTS
                        for u in non_presenters
                    )
                    if all_exhausted and non_presenters:
                        await manager.broadcast(room_id, {
                            "type": "all_attempts_used",
                            "data": {"word": room["current_word"]}
                        })
                        await manager._next_round(room_id, winner=None, presenter_gets_point=False)

            elif message["type"] == "chat":
                # チャット: 出題者がカタカナを使ったら-1pt
                room = rooms[room_id]
                presenter = room["users"][room["presenter_index"]]
                chat_text = message.get("message", "")
                penalty = False

                if user_name == presenter and check_katakana(chat_text):
                    room["scores"][user_name] = max(0, room["scores"].get(user_name, 0) - 1)
                    penalty = True

                await manager.broadcast(room_id, {
                    "type": "chat",
                    "data": {
                        "user": user_name,
                        "message": chat_text,
                        "penalty": penalty,
                    }
                })

                if penalty:
                    # スコア更新を通知
                    await manager.broadcast(room_id, {
                        "type": "state_update",
                        "data": get_room_state_for_broadcast(room_id),
                    })

            elif message["type"] == "get_state":
                await websocket.send_json({
                    "type": "state_update",
                    "data": get_room_state_for_broadcast(room_id),
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        if room_id in rooms and user_name in rooms[room_id]["users"]:
            rooms[room_id]["users"].remove(user_name)
            if user_name in rooms[room_id]["scores"]:
                del rooms[room_id]["scores"][user_name]

            if len(rooms[room_id]["users"]) > 0:
                rooms[room_id]["presenter_index"] = (
                    rooms[room_id]["presenter_index"] % len(rooms[room_id]["users"])
                )
                await manager.broadcast(room_id, {
                    "type": "state_update",
                    "data": get_room_state_for_broadcast(room_id),
                })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)