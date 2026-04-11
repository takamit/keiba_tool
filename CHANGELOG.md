# CHANGELOG

## [0.1.2] - 2026-04-12

### Fixed
- GUI の取得処理で進捗更新が見えにくく、取得ボタン押下後に反応していないように見える問題を改善
- 一時停止 / 停止が長い取得処理中に効きにくい問題を改善
- 完了直後にプログレスバーを即時リセットしてしまい、進捗が動いていないように見える問題を改善

### Changed
- `core/collector.py` に協調的な停止 / 一時停止フックを追加
- `core/services/batch_collect_service.py` の開催日判定進捗通知を細分化
- `ui/gui/main_window.py` の取得処理を、停止 / 一時停止 / 進捗表示を反映しやすい形へ修正

## [0.1.1] - 2026-04-12

### Added
- `core.collector.get_race_ids_by_date()` を追加
- `core.collector.get_race_ids_for_dates()` を追加
- `core/services/batch_collect_service.py` を追加
- `tests/test_collector_behavior.py` を追加
- `docs/release_0.1.1.md` を追加

### Changed
- `core/collector.py` で非開催日と異常系の判定を分離
- `ui/gui/main_window.py` の開催日判定をバッチ処理へ変更
- `ui/cli/cli_menu.py` で単日収集時の 0 件取得を明示エラー化
- `core/logic/collect_logic.py` に複数日向け関数を追加
- `core/services/netkeiba_service.py` の公開関数を拡張

### Fixed
- 複数日取得時に非開催日や 404 相当ページが混ざると全体停止しやすい問題を修正
- 日付ごとに Selenium ドライバを起動し続けて不安定化しやすい問題を改善
