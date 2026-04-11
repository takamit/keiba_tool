import argparse
import os

from config import DATA_DIR, ENTRY_FILE_PATTERN, MODEL_DIR, PREDICT_FILE_PATTERN, RESULT_FILE_PATTERN
from core import dataset, parser
from core.collector import fetch_race_page, get_race_ids
from ml import predictor, trainer


def build_parser() -> argparse.ArgumentParser:
    parser_obj = argparse.ArgumentParser(description="競馬ツール CLI")
    sub = parser_obj.add_subparsers(dest="command")

    collect = sub.add_parser("collect", help="指定日の出走表/結果を収集")
    collect.add_argument("--date", required=True)
    collect.add_argument("--mode", choices=["entry", "result"], default="entry")

    train_cmd = sub.add_parser("train", help="学習を実行")
    train_cmd.add_argument("--data-dir", default=DATA_DIR)
    train_cmd.add_argument("--model-dir", default=MODEL_DIR)

    predict_cmd = sub.add_parser("predict", help="出走表CSVから予測")
    predict_cmd.add_argument("--entry-csv", required=True)
    predict_cmd.add_argument("--model-dir", default=MODEL_DIR)
    predict_cmd.add_argument("--output-path")

    return parser_obj


def run_cli(args=None) -> int:
    parser_obj = build_parser()
    ns = parser_obj.parse_args(args=args)

    if ns.command == "collect":
        os.makedirs(DATA_DIR, exist_ok=True)

        race_ids = get_race_ids(ns.date)
        if not race_ids:
            raise ValueError(
                f"指定日 {ns.date} に開催レースが見つかりませんでした。"
                "開催がない日付か、取得対象条件を見直してください。"
            )

        rows = []
        compact_date = ns.date.replace("-", "").replace("/", "")

        for race_id in race_ids:
            html = fetch_race_page(race_id, mode=ns.mode, use_cache=True)
            if ns.mode == "entry":
                rows.extend(parser.parse_entry(html, race_id))
            else:
                rows.extend(parser.parse_result(html, race_id))

        if ns.mode == "entry":
            df = dataset.build_entry_df(rows)
            path = os.path.join(DATA_DIR, ENTRY_FILE_PATTERN.format(date=compact_date))
        else:
            df = dataset.build_result_df(rows)
            path = os.path.join(DATA_DIR, RESULT_FILE_PATTERN.format(date=compact_date))

        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(path)
        return 0

    if ns.command == "train":
        summary = trainer.train_all_models(data_dir=ns.data_dir, model_dir=ns.model_dir)
        print(summary)
        return 0

    if ns.command == "predict":
        output_path = ns.output_path or os.path.join(
            DATA_DIR,
            PREDICT_FILE_PATTERN.format(date="manual"),
        )
        df = predictor.predict_from_entry(
            ns.entry_csv,
            model_dir=ns.model_dir,
            output_path=output_path,
        )
        print(output_path, len(df))
        return 0

    parser_obj.print_help()
    return 0
