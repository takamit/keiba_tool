\# 競馬予想ツール



netkeiba からレース情報を取得し、学習済みモデルを作成して予測まで行う GUI ツールです。



このリポジトリは、既存の GUI / データ取得 / 学習 / 予測 の流れを維持したまま、

安定運用しやすい形で GitHub 管理と venv 運用を行うことを目的としています。



\---



\## 特徴



\- GUI でデータ取得・学習・予測を操作

\- Selenium で race\_id を取得

\- requests でレース詳細を取得

\- 複数モデルを保存して比較可能

\- HTML キャッシュの ON / OFF 切替対応

\- ログ出力あり

\- CSV 出力あり



\---



\## ディレクトリ構成



```text

keiba\_tool/

├─ main.py

├─ config.py

├─ requirements.txt

├─ core/

│  ├─ collector.py

│  ├─ parser.py

│  └─ dataset.py

├─ ml/

│  ├─ trainer.py

│  └─ predictor.py

├─ ui/

│  └─ gui.py

├─ data/

├─ models/

├─ cache/

└─ logs/

