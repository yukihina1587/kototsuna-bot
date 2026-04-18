"""Tests for src/games.py"""
import pytest
from src.games import (
    fortune, roll_dice, coin_toss, spin_slot, spin_roulette,
    play_janken, eightball, random_quote, NumberGuessGame, GiveawayManager,
)


class TestFortune:
    def test_returns_string(self):
        result = fortune()
        assert isinstance(result, str)
        assert "【" in result

    def test_multiple_calls_vary(self):
        results = {fortune() for _ in range(50)}
        assert len(results) > 1


class TestDice:
    def test_default_1d6(self):
        result = roll_dice()
        assert "1d6" in result

    def test_2d6_shows_sum(self):
        result = roll_dice("2d6")
        assert "2d6" in result
        assert "=" in result

    def test_invalid_notation(self):
        result = roll_dice("invalid")
        assert "形式" in result

    def test_too_many_dice(self):
        result = roll_dice("11d6")
        assert "1〜" in result

    def test_result_in_range(self):
        for _ in range(20):
            result = roll_dice("1d6")
            num = int(result.split(": ")[1])
            assert 1 <= num <= 6


class TestCoin:
    def test_returns_head_or_tail(self):
        result = coin_toss()
        assert "表" in result or "裏" in result


class TestSlot:
    def test_returns_slot_string(self):
        result = spin_slot()
        assert "🎰" in result
        assert "|" in result


class TestRoulette:
    def test_default_options(self):
        result = spin_roulette([])
        assert "ルーレット" in result

    def test_custom_options(self):
        result = spin_roulette(["A", "B", "C"])
        assert "A" in result or "B" in result or "C" in result


class TestJanken:
    def test_guu(self):
        result = play_janken("グー")
        assert "グー" in result

    def test_english_rock(self):
        result = play_janken("rock")
        assert "グー" in result

    def test_invalid_input(self):
        result = play_janken("???")
        assert "グー・チョキ・パー" in result

    def test_result_contains_outcome(self):
        result = play_janken("グー")
        assert any(word in result for word in ["勝ち", "あいこ", "ボット"])


class TestNumberGuessGame:
    def test_start_and_guess_correct(self):
        game = NumberGuessGame()
        game.start("mod", 1, 10)
        game._state.answer = 5
        result = game.guess("user1", "5")
        assert "正解" in result

    def test_guess_too_low(self):
        game = NumberGuessGame()
        game.start("mod", 1, 100)
        game._state.answer = 50
        result = game.guess("user1", "25")
        assert "大きい" in result

    def test_guess_too_high(self):
        game = NumberGuessGame()
        game.start("mod", 1, 100)
        game._state.answer = 50
        result = game.guess("user1", "75")
        assert "小さい" in result

    def test_end_game(self):
        game = NumberGuessGame()
        game.start("mod", 1, 100)
        result = game.end()
        assert "終了" in result

    def test_guess_when_not_active(self):
        game = NumberGuessGame()
        result = game.guess("user1", "5")
        assert "開始" in result

    def test_invalid_range(self):
        game = NumberGuessGame()
        result = game.start("mod", 100, 1)
        assert "最小値" in result


class TestGiveawayManager:
    def test_start_and_enter(self):
        g = GiveawayManager()
        g.start("mod")
        result = g.enter("user1", "User1", False)
        assert "エントリー" in result

    def test_duplicate_entry(self):
        g = GiveawayManager()
        g.start("mod")
        g.enter("user1", "User1", False)
        result = g.enter("user1", "User1", False)
        assert "済み" in result

    def test_draw_winner(self):
        g = GiveawayManager()
        g.start("mod")
        g.enter("user1", "User1", False)
        result = g.draw()
        assert "当選" in result

    def test_end_giveaway(self):
        g = GiveawayManager()
        g.start("mod")
        g.enter("user1", "User1", False)
        g.draw()
        result = g.end()
        assert "終了" in result

    def test_enter_when_not_active(self):
        g = GiveawayManager()
        result = g.enter("user1", "User1", False)
        assert "開催されていません" in result

    def test_subscriber_weight(self):
        g = GiveawayManager()
        assert g.SUBSCRIBER_WEIGHT == 3


class TestEightball:
    def test_returns_answer(self):
        result = eightball("今日は良いことある？")
        assert "🎱" in result
        assert "今日は良いことある？" in result

    def test_empty_question(self):
        result = eightball("")
        assert "質問を入力" in result

    def test_whitespace_only_question(self):
        result = eightball("   ")
        assert "質問を入力" in result

    def test_multiple_calls_vary(self):
        results = {eightball("テスト") for _ in range(30)}
        assert len(results) > 1


class TestRandomQuote:
    def test_returns_string(self):
        result = random_quote()
        assert isinstance(result, str)
        assert "💬" in result
        assert "「" in result
        assert "—" in result

    def test_multiple_calls_vary(self):
        results = {random_quote() for _ in range(30)}
        assert len(results) > 1
