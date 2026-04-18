"""Mini-games for Twitch chat interaction."""
import random
import threading
import time
import re
from dataclasses import dataclass, field
from typing import Optional


# --- Fortune game ---

FORTUNE_RESULTS = [
    ("大吉", 0.15),  # Great fortune
    ("中吉", 0.20),  # Good fortune
    ("吉", 0.30),    # Fortune
    ("小吉", 0.20),  # Small fortune
    ("末吉", 0.10),  # Uncertain fortune
    ("凶", 0.05),    # Bad fortune
]

FORTUNE_MESSAGES = {
    "大吉": "最高の運勢です！今日は何でもうまくいく日！",
    "中吉": "良い運勢です。積極的に行動しましょう！",
    "吉": "まずまずの運勢。コツコツ頑張れば吉！",
    "小吉": "小さな幸運があります。見逃さないで！",
    "末吉": "これから運が上向きます。焦らずに。",
    "凶": "気をつけて行動しましょう。でもきっと大丈夫！",
}


def fortune() -> str:
    """Draw a fortune result."""
    labels = [r[0] for r in FORTUNE_RESULTS]
    weights = [r[1] for r in FORTUNE_RESULTS]
    result = random.choices(labels, weights=weights, k=1)[0]
    msg = FORTUNE_MESSAGES[result]
    return f"【{result}】{msg}"


# --- Dice game ---

_DICE_PATTERN = re.compile(r'^(\d+)d(\d+)$', re.IGNORECASE)
MAX_DICE_COUNT = 10
MAX_DICE_SIDES = 1000


def roll_dice(notation: str = "1d6") -> str:
    """Roll dice using D&D notation (e.g. 2d6, 1d20)."""
    notation = notation.strip().lower() or "1d6"
    m = _DICE_PATTERN.match(notation)
    if not m:
        return "サイコロの形式が違います（例: 2d6, 1d20）"
    count = int(m.group(1))
    sides = int(m.group(2))
    if count < 1 or count > MAX_DICE_COUNT:
        return f"ダイスの数は1〜{MAX_DICE_COUNT}にしてください"
    if sides < 2 or sides > MAX_DICE_SIDES:
        return f"面の数は2〜{MAX_DICE_SIDES}にしてください"
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls)
    if count == 1:
        return f"🎲 {notation}: {total}"
    detail = " + ".join(str(r) for r in rolls)
    return f"🎲 {notation}: {detail} = {total}"


# --- Coin toss ---

def coin_toss() -> str:
    """Flip a coin."""
    result = random.choice(["表（ヘッズ）🪙", "裏（テイルズ）🌟"])
    return f"コイントス → {result}"


# --- Slot machine ---

SLOT_REELS = ["🍒", "🍋", "🍊", "🍇", "🔔", "⭐", "7️⃣"]
SLOT_JACKPOT_SYMBOL = "7️⃣"


def spin_slot() -> str:
    """Spin a 3-reel slot machine."""
    reels = [random.choice(SLOT_REELS) for _ in range(3)]
    display = " | ".join(reels)
    if reels[0] == reels[1] == reels[2]:
        if reels[0] == SLOT_JACKPOT_SYMBOL:
            suffix = "🎉 JACKPOT!! おめでとう！！"
        else:
            suffix = "✨ 3つ揃い！おめでとう！"
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        suffix = "👍 2つ揃い！惜しい！"
    else:
        suffix = "はずれ〜。またチャレンジ！"
    return f"🎰 [ {display} ] {suffix}"


# --- Roulette ---

DEFAULT_ROULETTE_OPTIONS = ["赤🔴", "青🔵", "緑🟢", "黄🟡", "白⚪"]


def spin_roulette(options: list[str]) -> str:
    """Spin a roulette wheel with given options."""
    if not options:
        options = DEFAULT_ROULETTE_OPTIONS
    winner = random.choice(options)
    return f"🎡 ルーレット → {winner}！"


# --- Janken (rock-paper-scissors) ---

JANKEN_MAP = {
    "rock": "グー", "石": "グー", "gu": "グー", "グー": "グー", "ぐー": "グー",
    "paper": "パー", "紙": "パー", "pa": "パー", "パー": "パー", "ぱー": "パー",
    "scissors": "チョキ", "はさみ": "チョキ", "choki": "チョキ", "チョキ": "チョキ", "ちょき": "チョキ",
    "r": "グー", "p": "パー", "s": "チョキ",
}

JANKEN_CHOICES = ["グー", "チョキ", "パー"]
JANKEN_WINS: dict[str, str] = {"グー": "チョキ", "チョキ": "パー", "パー": "グー"}


def play_janken(player_input: str) -> str:
    """Play rock-paper-scissors against the bot."""
    player = JANKEN_MAP.get(player_input.strip().lower())
    if not player:
        return "グー・チョキ・パーのいずれかを入力してください（例: !janken グー）"
    bot = random.choice(JANKEN_CHOICES)
    if player == bot:
        result = "あいこ！"
    elif JANKEN_WINS[player] == bot:
        result = "あなたの勝ち！🎉"
    else:
        result = "ボットの勝ち！😈"
    return f"じゃんけん: あなた「{player}」vs ボット「{bot}」→ {result}"


# --- Number guessing game ---

@dataclass
class NumberGuessState:
    min_val: int
    max_val: int
    answer: int
    started_by: str
    winner: Optional[str] = None
    ended: bool = False


class NumberGuessGame:
    """Multi-user number guessing game with moderator controls."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Optional[NumberGuessState] = None

    def start(self, started_by: str, min_val: int = 1, max_val: int = 100) -> str:
        """Start a new game. Returns announcement message."""
        if min_val >= max_val:
            return "最小値は最大値より小さくしてください"
        with self._lock:
            if self._state and not self._state.ended:
                return "すでにゲームが進行中です"
            answer = random.randint(min_val, max_val)
            self._state = NumberGuessState(min_val, max_val, answer, started_by)
        return f"🔢 数字当てゲーム開始！{min_val}〜{max_val}の数字を当ててね。!guess <数字> で参加！"

    def guess(self, user: str, number_str: str) -> str:
        """Process a guess. Returns result message."""
        with self._lock:
            if not self._state or self._state.ended:
                return "ゲームが開始されていません。!startguess で始めよう！"
            if self._state.winner:
                return f"すでに {self._state.winner} さんが当てました！"
            try:
                number = int(number_str.strip())
            except (ValueError, AttributeError):
                return "数字を入力してください"
            if number < self._state.min_val or number > self._state.max_val:
                return f"{self._state.min_val}〜{self._state.max_val}の数字を入力してください"
            if number == self._state.answer:
                self._state.winner = user
                self._state.ended = True
                return f"🎉 {user} さんが正解！答えは {self._state.answer} でした！"
            elif number < self._state.answer:
                return f"{user}: {number} → もっと大きい数字！"
            else:
                return f"{user}: {number} → もっと小さい数字！"

    def end(self) -> str:
        """Force-end the game and reveal the answer."""
        with self._lock:
            if not self._state or self._state.ended:
                return "ゲームが進行中ではありません"
            answer = self._state.answer
            self._state.ended = True
        return f"ゲーム終了！答えは {answer} でした。"

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._state is not None and not self._state.ended


# --- Giveaway manager ---

@dataclass
class GiveawayEntry:
    username: str
    display_name: str
    is_subscriber: bool
    entered_at: float = field(default_factory=time.time)


class GiveawayManager:
    """Weighted giveaway system with subscriber priority."""

    SUBSCRIBER_WEIGHT = 3
    VIEWER_WEIGHT = 1

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, GiveawayEntry] = {}
        self._active: bool = False
        self._winners: list[str] = []

    def start(self, started_by: str) -> str:
        """Start a giveaway."""
        with self._lock:
            if self._active:
                return "すでに抽選が進行中です"
            self._entries.clear()
            self._winners.clear()
            self._active = True
        return "🎁 抽選開始！!enter で参加できます！サブスクは当選確率3倍！"

    def enter(self, username: str, display_name: str, is_subscriber: bool) -> str:
        """Enter the giveaway."""
        with self._lock:
            if not self._active:
                return "抽選が開催されていません"
            if username in self._entries:
                return f"{display_name} さんはすでにエントリー済みです"
            self._entries[username] = GiveawayEntry(username, display_name, is_subscriber)
        label = "（サブスク3倍）" if is_subscriber else ""
        return f"✅ {display_name} さんがエントリーしました！{label}"

    def draw(self) -> str:
        """Draw one winner."""
        with self._lock:
            if not self._active:
                return "抽選が開催されていません"
            remaining = {k: v for k, v in self._entries.items() if k not in self._winners}
            if not remaining:
                return "参加者がいません"
            population = list(remaining.values())
            weights = [
                self.SUBSCRIBER_WEIGHT if e.is_subscriber else self.VIEWER_WEIGHT
                for e in population
            ]
            winner = random.choices(population, weights=weights, k=1)[0]
            self._winners.append(winner.username)
        return f"🎉 当選者: {winner.display_name} さん！おめでとうございます！🎊"

    def end(self) -> str:
        """End the giveaway."""
        with self._lock:
            if not self._active:
                return "抽選が開催されていません"
            count = len(self._entries)
            winners = list(self._winners)
            self._active = False
        if winners:
            winner_names = "、".join(winners)
            return f"抽選終了！参加者: {count}人 / 当選者: {winner_names}"
        return f"抽選終了！参加者: {count}人 / 当選者なし"

    def get_state(self) -> dict:
        """Return current state for overlay API."""
        with self._lock:
            return {
                "active": self._active,
                "entry_count": len(self._entries),
                "winners": list(self._winners),
            }

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active


# --- 8-Ball ---

EIGHTBALL_POSITIVE = [
    "そうに違いない！🎱",
    "確実にYES！🎱",
    "見通しは良好！🎱",
    "はい、間違いなく！🎱",
    "きっとそうなる！🎱",
]

EIGHTBALL_NEGATIVE = [
    "それはなさそう...🎱",
    "NO、絶対に違う。🎱",
    "見通しは暗い...🎱",
    "ありえない！🎱",
    "今日は難しそう...🎱",
]

EIGHTBALL_NEUTRAL = [
    "なんとも言えない...🎱",
    "今は答えられない。後でまた聞いて！🎱",
    "集中して、もう一度聞いて！🎱",
    "返答しにくい質問だ...🎱",
    "見えない... 🎱",
]

_EIGHTBALL_POOL = EIGHTBALL_POSITIVE + EIGHTBALL_NEGATIVE + EIGHTBALL_NEUTRAL


def eightball(question: str) -> str:
    """Answer a yes/no question Magic 8-Ball style."""
    if not question.strip():
        return "質問を入力してください（例: !8ball 今日は良いことある？）"
    answer = random.choice(_EIGHTBALL_POOL)
    return f"🎱 「{question.strip()}」→ {answer}"


# --- Quote ---

QUOTES = [
    ("努力は必ず報われる。", "王貞治"),
    ("夢を見るから、そのことが現実になる。", "ナポレオン・ヒル"),
    ("人生とは今日一日のことである。", "デール・カーネギー"),
    ("失敗は成功のもと。", "ことわざ"),
    ("千里の道も一歩から。", "ことわざ"),
    ("笑う門には福来たる。", "ことわざ"),
    ("継続は力なり。", "ことわざ"),
    ("当たって砕けろ。", "ことわざ"),
    ("七転び八起き。", "ことわざ"),
    ("初心忘るべからず。", "世阿弥"),
    ("明日は明日の風が吹く。", "ことわざ"),
    ("案ずるより産むが易し。", "ことわざ"),
    ("急がば回れ。", "ことわざ"),
    ("類は友を呼ぶ。", "ことわざ"),
    ("備えあれば憂いなし。", "ことわざ"),
    ("喜びを分かち合えば二倍になり、悲しみを分かち合えば半分になる。", "ことわざ"),
    ("今日できることを明日に延ばすな。", "ベンジャミン・フランクリン"),
    ("すべては練習だ。", "ミケランジェロ"),
    ("想像力は知識より重要だ。", "アインシュタイン"),
    ("もし今日が人生最後の日だとしたら、今日しようとしていることは本当にしたいことだろうか？", "スティーブ・ジョブズ"),
]


def random_quote() -> str:
    """Return a random inspirational quote."""
    text, author = random.choice(QUOTES)
    return f"💬 「{text}」— {author}"


# --- Module-level singletons ---

_number_guess_game = NumberGuessGame()
_giveaway_manager = GiveawayManager()


def get_number_guess_game() -> NumberGuessGame:
    return _number_guess_game


def get_giveaway_manager() -> GiveawayManager:
    return _giveaway_manager
