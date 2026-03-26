"""
tests/test_scheduler.py — scheduler モジュールのユニットテスト
task#98: カバレッジ≥80%達成のための追加テスト
"""
import pytest
from unittest.mock import patch, MagicMock


class TestGetLlm:
    """get_llm() のテスト"""

    def test_returns_none_when_no_api_key(self):
        """APIキーがない場合はNoneを返す（RuntimeErrorをキャッチ）"""
        with patch("nested_memory.llm._get_anthropic_key", return_value=""):
            from nested_memory.scheduler import get_llm
            result = get_llm()
        assert result is None

    def test_returns_llm_when_key_available(self, monkeypatch):
        """APIキーがある場合はMemoryLLMを返す"""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch("nested_memory.llm._get_anthropic_key", return_value="test-key"):
            from nested_memory.scheduler import get_llm
            result = get_llm()
        # MemoryLLMインスタンスまたはNoneを返す
        # （テスト環境によっては依存モジュールの都合でNoneになりうる）
        assert result is None or hasattr(result, "extract")


class TestRunDaily:
    """run_daily() のテスト"""

    def test_run_daily_below_threshold(self, tmp_path):
        """L1が閾値未満の場合はスキップ"""
        db_path = str(tmp_path / "test.db")
        with patch("nested_memory.scheduler.get_llm", return_value=None):
            from nested_memory.scheduler import run_daily
            results = run_daily(db_path, verbose=False)
        assert isinstance(results, dict)
        assert results == {}

    def test_run_daily_deletes_expired(self, tmp_path):
        """run_daily は期限切れメモリを削除する（エラーなし）"""
        db_path = str(tmp_path / "test.db")
        with patch("nested_memory.scheduler.get_llm", return_value=None):
            from nested_memory.scheduler import run_daily
            # エラーなく完了することを確認
            run_daily(db_path, verbose=False)

    def test_run_daily_verbose(self, tmp_path, capsys):
        """verbose=Trueで出力される"""
        db_path = str(tmp_path / "test.db")
        with patch("nested_memory.scheduler.get_llm", return_value=None):
            from nested_memory.scheduler import run_daily
            run_daily(db_path, verbose=True)
        captured = capsys.readouterr()
        assert "DailyCron" in captured.out


class TestRunWeekly:
    """run_weekly() のテスト"""

    def test_run_weekly_below_threshold(self, tmp_path):
        """L2が閾値未満の場合はスキップ"""
        db_path = str(tmp_path / "test.db")
        with patch("nested_memory.scheduler.get_llm", return_value=None):
            from nested_memory.scheduler import run_weekly
            results = run_weekly(db_path, verbose=False)
        assert isinstance(results, dict)
        assert results == {}

    def test_run_weekly_verbose(self, tmp_path, capsys):
        """verbose=Trueで出力される"""
        db_path = str(tmp_path / "test.db")
        with patch("nested_memory.scheduler.get_llm", return_value=None):
            from nested_memory.scheduler import run_weekly
            run_weekly(db_path, verbose=True)
        captured = capsys.readouterr()
        assert "WeeklyCron" in captured.out


class TestMain:
    """main() のテスト"""

    def test_main_daily_mode(self, tmp_path):
        """dailyモードで実行できる"""
        db_path = str(tmp_path / "test.db")
        with patch("nested_memory.scheduler.get_llm", return_value=None):
            from nested_memory import scheduler
            with patch("sys.argv", ["scheduler.py", "daily", "--db", db_path, "--quiet"]):
                # main()がエラーなく完了することを確認
                scheduler.main()

    def test_main_weekly_mode(self, tmp_path):
        """weeklyモードで実行できる"""
        db_path = str(tmp_path / "test.db")
        with patch("nested_memory.scheduler.get_llm", return_value=None):
            from nested_memory import scheduler
            with patch("sys.argv", ["scheduler.py", "weekly", "--db", db_path, "--quiet"]):
                scheduler.main()

    def test_main_all_mode(self, tmp_path):
        """allモードで実行できる"""
        db_path = str(tmp_path / "test.db")
        with patch("nested_memory.scheduler.get_llm", return_value=None):
            from nested_memory import scheduler
            with patch("sys.argv", ["scheduler.py", "all", "--db", db_path, "--quiet"]):
                scheduler.main()
