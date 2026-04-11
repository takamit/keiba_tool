# 更新定義書: 0.1.1

## 目的
複数日取得時に、非開催日や race_list 系の取得揺れが混ざっても GUI 全体が停止しにくい構成へ修正する。

## 原因
1. `core/collector.py` が 0 件取得を即異常扱いしていた
2. `ui/gui/main_window.py` が日付ごとに `collector.get_race_ids()` を直接呼んでいた
3. 複数日取得をまとめるサービス層が無かった
4. CLI で開催なし日の利用者向けエラー表示が不足していた

## 修正方針
- 非開催日は空配列として扱う
- 明確な異常だけ例外を維持する
- 複数日取得は shared driver を使う
- GUI はサービス経由で開催日判定を行う
- 変更履歴を `VERSION` と `CHANGELOG.md` に記録する

## 変更ファイル
- `core/collector.py`
- `core/services/batch_collect_service.py`
- `core/services/netkeiba_service.py`
- `core/logic/collect_logic.py`
- `ui/gui/main_window.py`
- `ui/cli/cli_menu.py`
- `tests/test_collector_behavior.py`
- `VERSION`
- `CHANGELOG.md`
- `docs/release_0.1.1.md`

## 影響範囲
- 複数日取得の安定性向上
- GUI の開催日判定速度と安定性向上
- CLI の単日収集時エラー明確化
- 既存データ形式や CSV 出力形式には非破壊
