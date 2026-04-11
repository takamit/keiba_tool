# 更新定義書: 0.1.2

## 目的
GUI の取得処理が反応していないように見える問題を解消し、
一時停止・停止・進捗表示が実処理と連動するように修正する。

## 原因
1. `collector.get_race_ids_by_date()` 実行中に GUI 側の停止 / 一時停止確認が細かく入っていなかった
2. `fetch_race_page()` 実行中も停止 / 一時停止の協調制御が不足していた
3. 完了時にプログレスバーを即リセットしていたため、進捗が見えにくかった

## 修正方針
- collector 層へ協調的な停止 / 一時停止フックを追加
- GUI の開催日判定進捗を細分化
- 完了時はプログレスバー状態を保持し、次回開始時のみリセットする

## 変更ファイル
- `core/collector.py`
- `core/services/batch_collect_service.py`
- `ui/gui/main_window.py`
- `VERSION`
- `CHANGELOG.md`
- `docs/release_0.1.2.md`
